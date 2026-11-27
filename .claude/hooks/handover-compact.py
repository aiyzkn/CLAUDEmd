"""PreCompact / PostCompact フック: compact のたびに引継ぎノートを自動で残す。

- PreCompact: stdout が compact の要約への指示になる（exit 0 のとき）。handover スキルの
  テンプレートの節（目的・状況・決めたこと・検証の状態・はまったこと・次の一手・最初に読むファイル）を
  要約に含めるよう指示する。compact は止めない
- PostCompact: 入力の compact_summary と git の状態を、
  ~/.claude/handover/<プロジェクト>/YYYYMMDD-HHMM.md に保存する（/handover load で読める）

git の状態の取り方とノートの置き場所は skills/handover/scripts/git_snapshot.py と共通。
fail-open 設計: フック自体の障害では何も出さずに exit 0 で抜ける（compact を妨げない）。
"""
import json
import os
import sys
from pathlib import Path

for _s in (sys.stdout, sys.stderr):
    if hasattr(_s, "reconfigure"):
        _s.reconfigure(encoding="utf-8")

CLAUDE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(CLAUDE_DIR / "skills" / "handover" / "scripts"))

PRECOMPACT_INSTRUCTIONS = """\
この要約は、次の文脈で作業を引き継ぐための引継ぎノートを兼ねる。通常の要約に加えて、次の節を必ず含めること（該当が無い節は「なし」と書く）。
- 目的: このセッションで何をしようとしていたか
- 状況: 済み / 進行中（どこまで進んだか、途中の成果物のパス）/ 未着手
- 決めたこと: 決定・理由・却下した案と却下理由（次の文脈が決め直さずに済むように）
- 検証の状態: 実行した検証コマンドと終了コード、それが最後の編集の後か前か。未検証のもの
- はまったこと: 試して駄目だったことと原因（同じ失敗を繰り返さないように）
- ユーザー作業: ユーザーが自分でやると言った操作（git push など。次の文脈が実行しないように）
- 次の一手: 最初にやること（具体的なコマンドかファイル）
- 最初に読むファイル: パスと理由
事実と推測を分け、確かめていないことは「未確認」と書く。機密（トークン・パスワード・本番の接続文字列）は含めない。
"""


def main() -> int:
    try:
        event = json.loads(sys.stdin.buffer.read().decode("utf-8") or "{}")
    except Exception:
        return 0
    name = event.get("hook_event_name", "")

    if name == "PreCompact":
        sys.stdout.write(PRECOMPACT_INSTRUCTIONS)
        return 0

    if name == "PostCompact":
        summary = (event.get("compact_summary") or "").strip()
        if not summary:
            return 0
        try:
            cwd = event.get("cwd")
            if cwd and Path(cwd).is_dir():
                os.chdir(cwd)
            from git_snapshot import DEFAULT_DIR, save_note

            trigger = event.get("trigger") or "?"
            save_note(
                Path(os.environ.get("CLAUDE_HANDOVER_DIR") or DEFAULT_DIR),
                title_suffix=f"（compact 時に自動保存: {trigger}）",
                extra="## compact の要約\n\n" + summary,
            )
        except Exception:
            pass
        return 0

    return 0


if __name__ == "__main__":
    sys.exit(main())
