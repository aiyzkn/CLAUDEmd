"""フックのスクリプトに架空のイベント JSON を流し、終了コード・出力・所要時間を確かめる。

使い方:
    python hook_test.py <スクリプト> --event <イベント名> [--set キー=値 ...] [--input JSON|@ファイル]
                        [--expect-exit N] [--shell powershell,pwsh]

- .ps1 は既定で powershell（5.1）と pwsh（7.x）の両方で実行する（5.1 で通ることがユーザー設定の要件）
- .py は python、.sh は bash で実行する
- --set は入れ子のキーをドットでつなぐ（例: tool_input.command="git commit -m x"）。値は JSON として解釈し、失敗したら文字列にする
- 実行前に check-encoding.py で BOM と改行コードを検査する

終了コード: 0 = すべての実行が期待どおり / 1 = 期待と違う実行がある / 2 = 引数エラー
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
import time
import uuid
from pathlib import Path

for _s in (sys.stdout, sys.stderr):
    if hasattr(_s, "reconfigure"):
        _s.reconfigure(encoding="utf-8")

CHECKER = Path.home() / ".claude" / "scripts" / "check-encoding.py"


def base_payload(event: str, cwd: str) -> dict:
    common = {
        "session_id": "hooktest-" + uuid.uuid4().hex[:8],
        "transcript_path": str(Path(cwd) / "hooktest-transcript.jsonl"),
        "cwd": cwd,
        "hook_event_name": event,
        "permission_mode": "default",
    }
    samples = {
        "SessionStart": {"source": "startup"},
        "UserPromptSubmit": {"prompt": "テスト用のプロンプト"},
        "PreToolUse": {"tool_name": "Bash", "tool_input": {"command": "echo hello", "description": "test"}},
        "PostToolUse": {"tool_name": "Write",
                        "tool_input": {"file_path": str(Path(cwd) / "hooktest.txt"), "content": "x\n"},
                        "tool_response": {"success": True}},
        "Notification": {"message": "Claude needs your permission to use Bash", "title": "Claude Code",
                         "notification_type": "permission_prompt"},
        "Stop": {"stop_hook_active": False},
        "SubagentStop": {"stop_hook_active": False},
        "PreCompact": {"trigger": "manual", "custom_instructions": ""},
        "SessionEnd": {"reason": "exit"},
    }
    if event not in samples:
        raise SystemExit(f"未対応のイベントです: {event}（{', '.join(samples)}）")
    return {**common, **samples[event]}


def apply_set(payload: dict, expr: str) -> None:
    key, sep, raw = expr.partition("=")
    if not sep:
        raise SystemExit(f"--set は キー=値 の形で指定してください: {expr}")
    try:
        value = json.loads(raw)
    except json.JSONDecodeError:
        value = raw
    node = payload
    parts = key.split(".")
    for part in parts[:-1]:
        node = node.setdefault(part, {})
    node[parts[-1]] = value


def runners(script: Path, shells):
    ext = script.suffix.lower()
    if ext == ".ps1":
        out = []
        for sh in shells:
            exe = shutil.which(sh)
            if exe:
                out.append((sh, [exe, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script)]))
            else:
                print(f"SKIP   {sh} が見つかりません")
        return out
    if ext == ".py":
        return [("python", [sys.executable, str(script)])]
    if ext in (".sh", ".bash"):
        return [("bash", [shutil.which("bash") or "bash", str(script)])]
    raise SystemExit(f"未対応の拡張子です: {ext}")


def describe_stdout(text: str) -> str:
    t = text.strip()
    if not t:
        return "（空）"
    if t.startswith("{"):
        try:
            obj = json.loads(t)
            hso = obj.get("hookSpecificOutput", {})
            keys = ", ".join(f"{k}={v!r}" for k, v in hso.items() if k != "additionalContext")
            return f"JSON として妥当: {keys or ', '.join(obj)}"
        except json.JSONDecodeError as e:
            return f"JSON として不正（{e}）: Claude Code はプレーンテキストとして扱う"
    return f"テキスト {len(t)} 文字（SessionStart / UserPromptSubmit ではコンテキストに注入される）"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("script")
    ap.add_argument("--event", required=True)
    ap.add_argument("--set", action="append", default=[])
    ap.add_argument("--input", help="ペイロード全体を JSON 文字列か @ファイル で与える（--set より先に適用）")
    ap.add_argument("--cwd", default=os.getcwd())
    ap.add_argument("--expect-exit", type=int)
    ap.add_argument("--shell", default="powershell,pwsh")
    ap.add_argument("--max-output", type=int, default=1500, help="表示する stdout / stderr の最大文字数")
    a = ap.parse_args()

    script = Path(a.script).expanduser().resolve()
    if not script.is_file():
        print(f"スクリプトが見つかりません: {script}", file=sys.stderr)
        return 2

    ok = True
    if CHECKER.is_file():
        r = subprocess.run([sys.executable, str(CHECKER), str(script), "--quiet"], capture_output=True)
        if r.returncode == 1:
            ok = False
            print("ENCODING ERROR\n" + r.stdout.decode("utf-8", "replace").strip())

    payload = base_payload(a.event, a.cwd)
    if a.input:
        src = Path(a.input[1:]).read_text(encoding="utf-8") if a.input.startswith("@") else a.input
        payload.update(json.loads(src))
    for expr in a.set:
        apply_set(payload, expr)
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    print("INPUT  " + json.dumps(payload, ensure_ascii=False)[: a.max_output])

    for name, cmd in runners(script, a.shell.split(",")):
        t0 = time.perf_counter()
        try:
            r = subprocess.run(cmd, input=data, capture_output=True, cwd=a.cwd, timeout=120)
        except subprocess.TimeoutExpired:
            print(f"\n[{name}] TIMEOUT（120 秒）")
            ok = False
            continue
        ms = (time.perf_counter() - t0) * 1000
        out = r.stdout.decode("utf-8", "replace")
        err = r.stderr.decode("utf-8", "replace")
        verdict = ""
        if a.expect_exit is not None:
            good = r.returncode == a.expect_exit
            ok &= good
            verdict = "  OK" if good else f"  NG（期待 {a.expect_exit}）"
        meaning = {0: "成功", 2: "ブロック（stderr を Claude へ差し戻す）"}.get(r.returncode, "非ブロックのエラー（stderr はユーザーにだけ見える）")
        print(f"\n[{name}] exit={r.returncode}（{meaning}）{verdict}  {ms:.0f} ms")
        print("  stdout: " + describe_stdout(out))
        if out.strip():
            print("    " + out.strip()[: a.max_output].replace("\n", "\n    "))
        if err.strip():
            print("  stderr:\n    " + err.strip()[: a.max_output].replace("\n", "\n    "))
        if "�" in out + err:
            print("  WARN: 出力に置換文字（�）があります。文字コードの扱いを確認してください")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
