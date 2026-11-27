"""PostToolUse フック（Write / Edit / MultiEdit）: 編集直後のファイルを検査する。

rules/safe-file-ops.md の 2 項目を、Claude の記憶に頼らず機械的に守らせる。

1. 編集後に 0 バイトになったファイルを検出する（Write で空の内容を意図して書いた場合を除く）
2. scripts/check-encoding.py の規則で、文字コード・BOM・改行コード・shebang を検査する。
   対象の形式はチェッカーの RULES（と、ファイル名による規則・shebang）で決まり、このフックは一覧を持たない

結果の返し方:
- 0 バイト・ERROR: stderr に理由を書いて exit 2。PostToolUse の exit 2 は、ツールの実行を取り消さずに
  stderr を Claude に差し戻す
- WARN だけ: hookSpecificOutput.additionalContext で Claude に伝える（エラーにはしない）
fail-open 設計: フック自体の障害（JSON の破損・チェッカーが見つからないなど）では exit 0 で抜ける。
"""
import importlib.util
import json
import sys
from pathlib import Path

for _s in (sys.stdout, sys.stderr):
    if hasattr(_s, "reconfigure"):
        _s.reconfigure(encoding="utf-8")

CHECKER = Path(__file__).resolve().parent.parent / "scripts" / "check-encoding.py"
FIXABLE = {"bom", "eol", "shebang"}


def load_checker():
    spec = importlib.util.spec_from_file_location("check_encoding", CHECKER)
    mod = importlib.util.module_from_spec(spec)
    # 登録しないと、チェッカーの dataclass が sys.modules から自分のモジュールを引けずに例外になる
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def main() -> int:
    try:
        event = json.loads(sys.stdin.buffer.read().decode("utf-8") or "{}")
    except Exception:
        return 0
    tool = event.get("tool_name", "")
    tin = event.get("tool_input") or {}
    raw = tin.get("file_path")
    if not raw:
        return 0
    path = Path(raw)
    if not path.is_file():
        return 0

    errors: list[str] = []
    warns: list[str] = []

    # 1. 0 バイト検査
    try:
        size = path.stat().st_size
    except OSError:
        size = -1
    intended_empty = tool == "Write" and tin.get("content", None) == ""
    if size == 0 and not intended_empty:
        errors.append(
            f"{path} が編集後に 0 バイトになっています。"
            "rules/safe-file-ops.md に従い、ここで作業を止めてユーザーに報告してください（自分で復元を試みないこと）。"
        )

    # 2. 文字コード・BOM・改行コード・shebang の検査
    if size > 0 and CHECKER.is_file():
        try:
            findings, _ = load_checker().check(path)
        except Exception as e:  # 止めはしないが、検査が無言で無効になったままにしない
            findings = []
            warns.append(f"post-edit-check: {CHECKER.name} で {path} を検査できませんでした（{type(e).__name__}: {e}）。"
                         "フックかチェッカーの不具合の可能性があるので、ユーザーに伝えてください。")
        kinds = {k for _, _, k in findings}
        enc_errors = [m for lv, m, _ in findings if lv == "ERROR"]
        enc_warns = [m for lv, m, _ in findings if lv != "ERROR"]
        if enc_errors:
            how = (f"原因を確認してから `python \"{CHECKER}\" \"{path}\" --fix` で修正してください。"
                   if kinds & FIXABLE and "encoding" not in kinds else
                   "文字コードの違反は自動修正できません。変換先の文字コードを確かめてから保存し直してください。")
            errors.append(f"{path} の文字コード・改行コードが要件を満たしていません。\n"
                          + "\n".join(f"- {m}" for m in enc_errors + enc_warns) + f"\n{how}")
        elif enc_warns:
            warns.append(f"{path} の文字コード・改行コードについての注意（修正は必須ではない。意図したものでなければ直す）:\n"
                         + "\n".join(f"- {m}" for m in enc_warns))

    if errors:
        sys.stderr.write("\n\n".join(errors + warns) + "\n")
        return 2
    if warns:
        sys.stdout.write(json.dumps({"hookSpecificOutput": {
            "hookEventName": "PostToolUse", "additionalContext": "\n\n".join(warns)}}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
