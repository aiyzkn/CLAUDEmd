"""handover スキル用: git の状態を Markdown で出し、引継ぎノートの置き場所を管理する。

使い方:
  git_snapshot.py --out-dir DIR   ノートを DIR/<プロジェクト>/YYYYMMDD-HHMM.md に作り、
                                  1 行目にパス、続けて書き込んだ内容を出力する
  git_snapshot.py --print-only    git の状態だけを出力する（ファイルは作らない）
  git_snapshot.py --latest        最新ノートのパスを出力する（無ければ終了コード 1）
  git_snapshot.py --list          ノート一覧（新しい順に 10 件）
--latest / --list の既定の DIR は ~/.claude/handover。
"""
from __future__ import annotations

import argparse
import datetime as dt
import subprocess
import sys
from pathlib import Path

DEFAULT_DIR = Path.home() / ".claude" / "handover"
MAX_LINES = 40  # 変更ファイルが多いときに出力を抑える


def git(*args: str) -> tuple[int, str]:
    try:
        p = subprocess.run(
            # core.quotePath=false: 日本語のファイル名を \346... の形にしない
            ["git", "-c", "core.quotePath=false", *args], capture_output=True, text=True, encoding="utf-8", errors="replace"
        )
    except FileNotFoundError:
        return 127, ""
    return p.returncode, p.stdout.rstrip("\n")


def project_name() -> str:
    code, top = git("rev-parse", "--show-toplevel")
    return Path(top).name if code == 0 and top else Path.cwd().name


def clip(text: str) -> str:
    lines = text.splitlines()
    if len(lines) <= MAX_LINES:
        return text
    return "\n".join(lines[:MAX_LINES] + [f"... ほか {len(lines) - MAX_LINES} 行"])


def snapshot() -> str:
    out = ["## リポジトリの状態", ""]
    code, top = git("rev-parse", "--show-toplevel")
    if code != 0:
        out += [f"- 作業ディレクトリ: `{Path.cwd()}`（git 管理外）", ""]
        return "\n".join(out)
    _, branch = git("branch", "--show-current")
    _, head = git("log", "-1", "--format=%h %s")
    up_code, upstream = git("rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}")
    out += [
        f"- リポジトリ: `{top}`",
        f"- ブランチ: `{branch or '(detached HEAD)'}`",
        f"- HEAD: {head}",
        f"- upstream: `{upstream}`" if up_code == 0 else "- upstream: なし",
        "",
    ]
    _, status = git("status", "--short")
    out += ["### 未コミットの変更", "", f"```\n{clip(status)}\n```" if status else "なし", ""]
    if up_code == 0:
        _, unpushed = git("log", "--oneline", "@{u}..HEAD")
        out += ["### 未 push のコミット", "", f"```\n{clip(unpushed)}\n```" if unpushed else "なし", ""]
    _, stash = git("stash", "list")
    out += ["### stash", "", f"```\n{clip(stash)}\n```" if stash else "なし", ""]
    return "\n".join(out)


def notes(base: Path) -> list[Path]:
    d = base / project_name()
    if not d.is_dir():
        return []

    def key(p: Path) -> tuple[str, int]:
        # YYYYMMDD-HHMM[-n]。文字列のまま並べると "-2" が無印より前に来るので、連番を数で比べる
        parts = p.stem.split("-")
        n = int(parts[2]) if len(parts) > 2 and parts[2].isdigit() else 1
        return ("-".join(parts[:2]), n)

    return sorted(d.glob("*.md"), key=key, reverse=True)


def main() -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--out-dir", type=Path)
    g.add_argument("--print-only", action="store_true")
    g.add_argument("--latest", action="store_true")
    g.add_argument("--list", action="store_true")
    ap.add_argument("--dir", type=Path, default=DEFAULT_DIR, help="--latest / --list で見るフォルダ")
    a = ap.parse_args()

    if a.print_only:
        print(snapshot())
        return 0
    if a.latest:
        found = notes(a.dir)
        if not found:
            print(f"ノートがありません: {a.dir / project_name()}", file=sys.stderr)
            return 1
        print(found[0])
        return 0
    if a.list:
        found = notes(a.dir)
        print("\n".join(str(p) for p in found[:10]) or "ノートがありません")
        return 0

    path, body = save_note(a.out_dir.expanduser())
    print(path)
    print(body)
    return 0


def save_note(base: Path, title_suffix: str = "", extra: str = "") -> tuple[Path, str]:
    """base/<プロジェクト>/YYYYMMDD-HHMM[-n].md に、見出し・git の状態・extra を書く。
    フック（hooks/handover-compact.py）からも呼ぶ。"""
    now = dt.datetime.now()
    d = base / project_name()
    d.mkdir(parents=True, exist_ok=True)
    path = d / f"{now:%Y%m%d-%H%M}.md"
    n = 1
    while path.exists():  # 同じ分に 2 回保存しても上書きしない
        n += 1
        path = d / f"{now:%Y%m%d-%H%M}-{n}.md"
    body = f"# 引継ぎノート {now:%Y-%m-%d %H:%M}{title_suffix}\n\n" + snapshot()
    if extra:
        body += "\n" + extra.rstrip("\n") + "\n"
    path.write_text(body + "\n", encoding="utf-8", newline="\n")
    return path, body


if __name__ == "__main__":
    sys.exit(main())
