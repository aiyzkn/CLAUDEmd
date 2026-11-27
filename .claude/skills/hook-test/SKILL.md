---
name: hook-test
description: "Claude Code のフック（.ps1 / .py / .sh）に架空のイベント JSON を流し、終了コード・stdout の JSON・stderr・所要時間・文字コードを確かめる。.ps1 は PowerShell 5.1 と 7.x の両方で走らせる。「フックをテストして」「フックが動くか確かめて」で自動適用。/hook-test <スクリプト> --event <イベント名>。"
---

# /hook-test スキル — フックを架空のイベントで試す

フックを `settings.json` に登録する前と、フックを書き換えた後に使う。Claude Code を再起動して実際にイベントを起こさなくても、入力 JSON に対する振る舞いを確かめられる。

## 実行

```sh
python ~/.claude/skills/hook-test/scripts/hook_test.py <スクリプト> --event <イベント名> [オプション]
```

| オプション | 内容 |
|---|---|
| `--event` | `SessionStart` / `UserPromptSubmit` / `PreToolUse` / `PostToolUse` / `Notification` / `Stop` / `SubagentStop` / `PreCompact` / `SessionEnd`。イベントごとの標準的なペイロードを作る |
| `--set キー=値` | ペイロードの一部を上書きする。入れ子はドットでつなぐ。値は JSON として解釈し、だめなら文字列。複数回指定できる |
| `--input JSON` / `--input @ファイル` | ペイロードを丸ごと与える（`--set` はその後に適用） |
| `--expect-exit N` | 期待する終了コード。外れたらスクリプトの終了コードが 1 になる |
| `--shell powershell,pwsh` | `.ps1` を走らせるシェル（既定は両方） |
| `--cwd` | フックを実行するディレクトリ（ペイロードの `cwd` にも入る） |

## 典型例

```sh
H=~/.claude/skills/hook-test/scripts/hook_test.py
# 本番らしい語で ask が返るか
python $H ~/.claude/hooks/bash-guard.py --event PreToolUse --set tool_input.command="kubectl --context prod get pods"
# 0 バイト検出でブロックされるか
python $H ~/.claude/hooks/post-edit-check.py --event PostToolUse --set tool_name=Edit --set tool_input.file_path=C:/tmp/empty.txt --expect-exit 2
# SessionStart の resume で 5.1 と 7.x の両方が通るか
python $H ~/.claude/hooks/job-resume-check.ps1 --event SessionStart --set source=resume
```

## 結果の読み方

- `exit=0`: 成功。PreToolUse なら stdout の `hookSpecificOutput.permissionDecision`（allow / ask / deny）を確認する
- `exit=2`: ブロック。stderr が Claude に差し戻される。差し戻す文面が Claude にとって次の行動が分かるものか確認する
- それ以外: 非ブロックのエラー。stderr はユーザーにだけ見え、処理は続行される。fail-open の設計なら想定どおり
- `ENCODING ERROR`: `.ps1` に BOM が無い、`.sh` が CRLF など。`check-encoding.py --fix` で直す
- `.ps1` で `powershell` だけ失敗する: 7.x 専用の構文（`??`・三項演算子・`-Parallel` など）を使っていないか確認する

## 注意

- フックが副作用を持つ場合（ファイル作成・通知・外部コマンド）は、それも実際に起きる。gitleaks のような外部コマンドを呼ぶフックは、一時リポジトリを `--cwd` に指定して試す
- 所要時間は、ツール呼び出しのたびに上乗せされる遅延の目安になる。PreToolUse / PostToolUse で数百 ms を超える場合は、matcher を絞るか、軽い処理系に書き換えることを検討する
