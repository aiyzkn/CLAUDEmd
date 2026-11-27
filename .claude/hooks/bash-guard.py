"""PreToolUse フック（Bash）: CLAUDE.md の禁止・確認事項を機械的に守らせる。

1. 本番らしい語（prod / prd / production）を含むコマンド → ユーザーに確認を求める（ask）
2. --no-verify を含むコマンド → ユーザーに確認を求める（ask）
3. git commit → gitleaks で秘密情報を検査し、検出したらブロックする（exit 2）
   - ステージ済みの差分（--staged）と、未ステージの追跡済み差分（--pre-commit。commit -a に備える）を検査する
   - 同じコマンドに git add が含まれるときは、未追跡ファイル（.gitignore 除外後）も検査する
     （フックはコマンド実行前に走るため、add の結果はまだステージに無い）

ask は拒否ではなく確認なので、`grep production` のような読み取りでも止まるが実害は小さい。
fail-open 設計: JSON の破損や gitleaks 未導入ではブロックしない（gitleaks 未導入は stderr に警告のみ）。
"""
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

for _s in (sys.stdout, sys.stderr):
    if hasattr(_s, "reconfigure"):
        _s.reconfigure(encoding="utf-8")

PROD_RE = re.compile(r"(?i)(?<![A-Za-z0-9])(prod|prd|production)(?![A-Za-z0-9])")
NO_VERIFY_RE = re.compile(r"(?<![\w-])--no-verify(?![\w-])")
GIT_COMMIT_RE = re.compile(r"(?<![\w./-])git(?P<opts>(?:\s+-[cC]\s+\S+)*)\s+commit(?![\w-])")
GIT_ADD_RE = re.compile(r"(?<![\w./-])git(?:\s+-[cC]\s+\S+)*\s+add(?![\w-])")
MAX_UNTRACKED_BYTES = 1_000_000  # これより大きい未追跡ファイルは検査しない（生成物の可能性が高い）
MAX_UNTRACKED_FILES = 500


def ask(reasons):
    out = {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "ask",
            "permissionDecisionReason": " / ".join(reasons),
        }
    }
    sys.stdout.write(json.dumps(out, ensure_ascii=False))


def repo_dir(opts: str, cwd: str) -> str:
    """git -C <path> があればそのパスを、無ければ cwd を返す。"""
    try:
        tokens = shlex.split(opts)
    except ValueError:
        return cwd
    d = cwd
    for i, t in enumerate(tokens[:-1]):
        if t == "-C":
            d = os.path.join(d, tokens[i + 1])
    return d


LEAK_EXIT = 99  # 検出ありの終了コード。gitleaks 自体のエラー（1）と区別する

# gitleaks が呼ぶ git の stderr に CRLF 変換の警告が出ると、gitleaks は "stderr is not empty" で
# 失敗する。Windows（core.autocrlf=true）では常態的に起きるので、検査中だけ警告を止める。
GIT_ENV = dict(os.environ, GIT_CONFIG_COUNT="1", GIT_CONFIG_KEY_0="core.safecrlf", GIT_CONFIG_VALUE_0="false")


def gitleaks(args, cwd):
    """(状態, 要約) を返す。状態は "leak" / "clean" / "error"。値は伏せ、ルール・ファイル・行だけを出す。"""
    r = subprocess.run(
        ["gitleaks", *args, "--no-banner", "--no-color", "--redact", "--log-level", "error",
         "--exit-code", str(LEAK_EXIT), "--report-format", "json", "--report-path", "-"],
        cwd=cwd, capture_output=True, timeout=120, env=GIT_ENV,
    )
    if r.returncode == 0:
        return "clean", ""
    if r.returncode != LEAK_EXIT:
        return "error", r.stderr.decode("utf-8", "replace").strip()[-500:]
    try:
        items = json.loads(r.stdout.decode("utf-8", "replace") or "[]")
        lines = [f"  - {i.get('RuleID')}: {i.get('File')}:{i.get('StartLine')}" for i in items[:30]]
        if len(items) > 30:
            lines.append(f"  - ほか {len(items) - 30} 件")
        return "leak", "\n".join(lines)
    except Exception:
        return "leak", "  （レポートを解析できませんでした）"


def scan_untracked(repo):
    r = subprocess.run(
        ["git", "ls-files", "--others", "--exclude-standard", "-z"],
        cwd=repo, capture_output=True, timeout=30,
    )
    if r.returncode != 0:
        return "clean", ""
    files = [f for f in r.stdout.decode("utf-8", "replace").split("\0") if f][:MAX_UNTRACKED_FILES]
    if not files:
        return "clean", ""
    with tempfile.TemporaryDirectory(prefix="bash-guard-") as tmp:
        copied = 0
        for rel in files:
            src = Path(repo) / rel
            try:
                if src.is_file() and src.stat().st_size <= MAX_UNTRACKED_BYTES:
                    dst = Path(tmp) / rel
                    dst.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copyfile(src, dst)
                    copied += 1
            except OSError:
                continue
        if copied == 0:
            return "clean", ""
        state, out = gitleaks(["dir", tmp], repo)
        # gitleaks は一時ディレクトリを区切り文字や短縮名を変えて報告するので、名前の接頭辞で取り除く
        return state, re.sub(r"(?m)(: )\S*?bash-guard-[^/\\\s]+[/\\]", r"\1", out)


def check_commit(cmd, cwd):
    m = GIT_COMMIT_RE.search(cmd)
    if not m:
        return None
    if shutil.which("gitleaks") is None:
        sys.stderr.write("bash-guard: gitleaks が見つからないため、コミット前の秘密情報検査を省略しました。\n")
        return None
    repo = repo_dir(m.group("opts"), cwd)
    findings = []
    scans = [("ステージ済みの差分", lambda: gitleaks(["git", "--staged"], repo)),
             ("未ステージの差分", lambda: gitleaks(["git", "--pre-commit"], repo))]
    if GIT_ADD_RE.search(cmd):
        scans.append(("未追跡ファイル", lambda: scan_untracked(repo)))
    for label, scan in scans:
        try:
            state, out = scan()
        except Exception as e:  # fail-open
            state, out = "error", str(e)
        if state == "leak":
            findings.append(f"[{label}]\n{out}")
        elif state == "error":
            sys.stderr.write(f"bash-guard: {label}の gitleaks 検査に失敗したため省略しました: {out}\n")
    return findings


def main() -> int:
    try:
        event = json.loads(sys.stdin.buffer.read().decode("utf-8") or "{}")
    except Exception:
        return 0
    cmd = (event.get("tool_input") or {}).get("command") or ""
    cwd = event.get("cwd") or ""
    if not os.path.isdir(cwd):
        cwd = os.getcwd()
    if not cmd:
        return 0

    findings = check_commit(cmd, cwd)
    if findings:
        sys.stderr.write(
            "gitleaks がコミット対象に秘密情報らしき文字列を検出したため、コミットを止めました（値は伏せています）。\n"
            "秘密情報を消すか、誤検出なら理由を添えてユーザーに報告し、判断を仰いでください。"
            "--no-verify や .gitleaksignore で回避しないこと。\n\n" + "\n\n".join(findings) + "\n"
        )
        return 2

    reasons = []
    hit = PROD_RE.search(cmd)
    if hit:
        reasons.append(f"本番らしい語「{hit.group(0)}」を含むコマンドです（CLAUDE.md「セキュリティ」）。接続先・操作対象が本番でないことを確認してください")
    if NO_VERIFY_RE.search(cmd):
        reasons.append("--no-verify はユーザーの明示的な指示があるときだけ使います（CLAUDE.md「Git」）")
    if reasons:
        ask(reasons)
    return 0


if __name__ == "__main__":
    sys.exit(main())
