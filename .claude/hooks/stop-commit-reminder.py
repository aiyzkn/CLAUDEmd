"""Stop フック: 応答の終わりに未コミットの変更があれば、ユーザーに知らせる（止めない）。

CLAUDE.md「Git」の「適切な粒度でコミットする」を思い出すきっかけを作る。
- 知らせるだけ: systemMessage（ユーザーに表示）を返す。decision: block や additionalContext は
  会話を続けさせてしまうので使わない
- うるさくしない: 変更されたファイルの組（パスの集合）が、このセッションで前回知らせたときと
  同じなら黙る。新しいファイルが変更されたときと、いったんきれいになった後に再び変更が出たときだけ知らせる
- git 管理外・変更なし・stop_hook_active のときは何もしない

状態は ~/.claude/state/stop-commit-reminder/<session_id>.json に置き、7 日より古いものは消す。
fail-open 設計: フック自体の障害では何も出さずに exit 0 で抜ける。
"""
import hashlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path

for _s in (sys.stdout, sys.stderr):
    if hasattr(_s, "reconfigure"):
        _s.reconfigure(encoding="utf-8")

STATE_DIR = Path(
    os.environ.get("CLAUDE_STOP_REMINDER_STATE")  # テスト用の差し替え
    or Path(__file__).resolve().parent.parent / "state" / "stop-commit-reminder"
)
KEEP_SECONDS = 7 * 24 * 3600
SHOW_FILES = 5


def changed_files(cwd: str) -> list[str] | None:
    try:
        r = subprocess.run(
            # core.quotePath=false: 日本語のファイル名を \346... の形にしない
            ["git", "-C", cwd, "-c", "core.quotePath=false", "status", "--porcelain", "-uall"],
            capture_output=True, timeout=15,
        )
    except Exception:
        return None
    if r.returncode != 0:  # git 管理外など
        return None
    lines = r.stdout.decode("utf-8", "replace").splitlines()
    return sorted({ln[3:].strip().strip('"') for ln in lines if len(ln) > 3})


def prune(now: float) -> None:
    try:
        for p in STATE_DIR.glob("*.json"):
            if now - p.stat().st_mtime > KEEP_SECONDS:
                p.unlink()
    except OSError:
        pass


def main() -> int:
    try:
        event = json.loads(sys.stdin.buffer.read().decode("utf-8") or "{}")
    except Exception:
        return 0
    if event.get("stop_hook_active"):
        return 0
    cwd = event.get("cwd") or "."
    session = "".join(c for c in str(event.get("session_id", "unknown")) if c.isalnum() or c in "-_")
    files = changed_files(cwd)
    if files is None:
        return 0

    state_file = STATE_DIR / f"{session or 'unknown'}.json"
    key = cwd + "\0" + "\n".join(files)
    digest = hashlib.sha256(key.encode("utf-8")).hexdigest() if files else ""
    try:
        last = json.loads(state_file.read_text(encoding="utf-8")).get("digest", "")
    except Exception:
        last = ""
    if digest == last:
        return 0
    try:
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        state_file.write_text(json.dumps({"digest": digest}), encoding="utf-8")
        prune(time.time())
    except OSError:
        pass
    if not files:  # きれいになった: 状態だけ更新して黙る
        return 0

    shown = ", ".join(files[:SHOW_FILES])
    more = f" ほか {len(files) - SHOW_FILES} 件" if len(files) > SHOW_FILES else ""
    msg = f"未コミットの変更が {len(files)} 件あります: {shown}{more}。区切りがよければコミットを検討してください。"
    sys.stdout.write(json.dumps({"systemMessage": msg}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
