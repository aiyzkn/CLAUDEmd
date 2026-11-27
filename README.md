# Claude Code ユーザー設定（`~/.claude`）移行パッケージ

## 入っているもの

| パス | 内容 |
|---|---|
| `.claude/CLAUDE.md` | 全プロジェクトに共通の指示。「端末環境」の節は雛形なので、移行先で書き直す |
| `.claude/RTK.md` | コマンド出力を圧縮する rtk の説明（CLAUDE.md から読み込まれる） |
| `.claude/rules/` | 常時適用のルール（環境安全・外部リソース・ファイル操作）と、Office / PDF の変換時だけ読むルール |
| `.claude/skills/long-run/` | 長時間かかるコマンドを、セッションから切り離したジョブとして実行する |
| `.claude/skills/file-lock/` | 編集・削除されては困るファイルを OS の機能でロックする |
| `.claude/skills/tool-environment/` | 外部コマンドの所在・版・文字コード環境を検出して記録し、調査の繰り返しを防ぐ |
| `.claude/skills/office-reader/` | Office / PDF を読むときの手順 |
| `.claude/scripts/check-encoding.py` | 文字コード・BOM・改行コードの検査と修正（`.ps1` は BOM 必須、`.sh` は LF のみ など。形式ごとの要件と根拠は `RULES`）。`--gitattributes` で `.gitattributes` のひな形を出す |
| `.claude/scripts/long-run.ps1` / `.sh` | long-run スキルの本体（Windows / Linux・macOS） |
| `.claude/scripts/file-lock.ps1` / `.sh` | file-lock スキルの本体（Windows / Linux・macOS） |
| `.claude/skills/hook-test/` | フックに架空のイベント JSON を流し、終了コード・出力・所要時間・文字コードを確かめる |
| `.claude/skills/handover/` | セッションの区切りに引継ぎノートを `~/.claude/handover/<プロジェクト>/` へ書き出し、次のセッションで読み込んで再開する |
| `.claude/skills/verify-done/` | 完了を報告する前に、差分・検証の再実行・TODO の残りを点検し、証拠付きの完了報告を作る |
| `.claude/skills/claude-md-audit/` | CLAUDE.md・rules・memory を棚卸しし、矛盾・重複・古い記述と、Hook やスキルへ移すべき記述を洗い出す（読み取りだけ） |
| `.claude/hooks/job-resume-check.ps1` / `.sh` | SessionStart フック。完了したが未報告の long-run ジョブを、セッション開始時に知らせる |
| `.claude/hooks/bash-guard.py` | PreToolUse フック（Bash）。本番らしい語（`prod` / `prd` / `production`）や `--no-verify` を含むコマンドで確認を求め、`git commit` の前に gitleaks で秘密情報を検査して、見つかればコミットを止める |
| `.claude/hooks/post-edit-check.py` | PostToolUse フック（Write / Edit）。編集後に 0 バイトになったファイルと、`check-encoding.py` の規則にある全形式（`.ps1`・`.sh`・`.json`・`.toml`・`.bat` など）の文字コード・BOM・改行・shebang の違反を Claude に差し戻す（WARN は差し戻さず注意として伝える） |
| `.claude/hooks/notify.ps1` / `.sh` | Notification フック。許可待ち・入力待ちを OS の通知で知らせる（Windows はトースト、macOS は `osascript`、Linux は `notify-send`） |
| `.claude/hooks/handover-compact.py` | PreCompact / PostCompact フック。compact の要約に引継ぎ用の節（目的・決めたこと・検証の状態・次の一手など）を含めさせ、git の状態と要約を `~/.claude/handover/<プロジェクト>/` に保存する（handover スキルの `load` で読める） |
| `.claude/hooks/stop-commit-reminder.py` | Stop フック。応答の終わりに未コミットの変更があればユーザーに知らせる（止めない）。変更されたファイルの組が前回知らせたときと同じなら黙る |
| `.claude/settings.json` | 権限・フック・プラグイン・ステータスラインの設定。秘密情報（`~/.ssh`・`~/.aws`・`.env`・`*.pem`・各種認証情報ファイル）の読み取りは deny にしてある（`.env.example` も読めなくなる。Windows ネイティブには sandbox が無いため、Python などのスクリプトが直接開く読み取りまでは防げない） |

## 入れていないもの

- 認証情報・アカウント状態・会話履歴・メモリ・キャッシュ: 個人データのため。移行先で `claude` にログインすれば必要なものは作られる

## 前提ツール

| ツール | 使う場所 | 無いときの影響 |
|---|---|---|
| rtk | `settings.json` の PreToolUse フック（`rtk hook claude`） | Bash 実行のたびにフックがエラーになる。入れないなら、このフックの記述を消す |
| Node.js（`npx`） | ステータスライン（`ccstatusline`） | ステータスラインが表示されない |
| Python 3（`python` の名前で呼べること） | `check-encoding.py`、フック（`bash-guard.py`・`post-edit-check.py`）、`hook-test` スキル | 文字コード検査が使えない。2 本のフックは、ツール呼び出しのたびにエラーを出す（ブロックはしない）。`python3` しか無い環境では、`settings.json` のフックのコマンドを `python3` に書き換える |
| gitleaks（8.19 以降） | `bash-guard.py` のコミット前検査 | 検査を省略してコミットを通す（stderr に警告だけ出す） |
| PowerShell 5.1 | Windows 版のスクリプトとフック（`notify.ps1` は WinRT を使うため 5.1 で動かす） | ― |
| Podman | CLAUDE.md の方針 | `settings.json` で `docker` コマンドを deny している。Docker を使う人は deny の 7 件と CLAUDE.md のコンテナの節を外す |

## 導入手順

> **注意**: このリポジトリをそのまま Claude Code で開くと、直下の `.claude/` が「プロジェクト設定」として読み込まれ、`settings.json` のフックが `~/.claude/hooks/` のスクリプトを呼ぶ。未導入の端末では Bash などのツール呼び出しがフックのエラー（`can't open file ...bash-guard.py`）で止まるので、先に手順 2・3 を済ませるか、`.claude/hooks/bash-guard.py` だけを先に `~/.claude/hooks/` へコピーする。

1. 移行先の `~/.claude/` を丸ごとバックアップする
2. 移行先にまだ `settings.json` が無い場合は、このリポジトリの `.claude/` の中身を `~/.claude/` にそのまま複製する
3. 移行先にすでに `settings.json` がある場合は上書きしない。`permissions`・`hooks`・`enabledPlugins` などを項目ごとに統合する
4. **Linux / macOS の場合**: `settings.json` の SessionStart フックと Notification フックを次のように書き換える
   ```json
   "command": "bash \"$HOME/.claude/hooks/job-resume-check.sh\""
   "command": "bash \"$HOME/.claude/hooks/notify.sh\""
   ```
5. Claude Code を起動し、`tool-environment` スキルで端末の環境を検出する。結果をもとに `CLAUDE.md` の「端末環境」の節を書き直す
6. `settings.json` の `enabledPlugins` に書かれたプラグインは、初回起動時に導入を求められる
7. 文字コードを確かめる: `python ~/.claude/scripts/check-encoding.py ~/.claude/scripts ~/.claude/hooks ~/.claude/skills --quiet`（展開ツールによっては改行コードが変わる。問題があれば `--fix` で直る）
8. フックを試す: `python ~/.claude/skills/hook-test/scripts/hook_test.py ~/.claude/hooks/bash-guard.py --event PreToolUse --set tool_input.command="kubectl --context prod get pods"` で `permissionDecision='ask'` が返れば正常

## 推奨する外部スキル（同梱していない）

必要に応じて、それぞれの原典から導入する。ライセンスは 2026-11-18 時点で GitHub に登録されていたもの。

| 用途 | 原典 | ライセンス |
|---|---|---|
| Containerfile / Dockerfile・compose の作成とレビュー | [docker/skills](https://github.com/docker/skills) | Apache-2.0 |
| 多数ファイルの一括処理をスクリプトで完結させる | [mhattingpete/claude-skills-marketplace](https://github.com/mhattingpete/claude-skills-marketplace) | Apache-2.0 |
| 日本語の文章を、執筆意図と文機能を記録しながら一文ずつ書く（tsuzuri） | [MaryCache/tsuzuri](https://github.com/MaryCache/tsuzuri) | MIT（2026-11-25 に確認） |
| AI が書いた日本語を推敲する（yomiyasu） | [nanaism/yomiyasu](https://github.com/nanaism/yomiyasu) | MIT |

tsuzuri と yomiyasu は [Skills CLI](https://github.com/vercel-labs/skills) で導入できる（Node.js が必要。`-g` はユーザーレベル、`-a claude-code` は Claude Code だけに入れる指定）。

```sh
npx skills add MaryCache/tsuzuri@tsuzuri -g -a claude-code
npx skills add nanaism/yomiyasu@yomiyasu -g -a claude-code
```

導入の前に、原典の `SKILL.md` と `scripts/` を読み、自動実行や外部送信をするコードが無いか確かめる。更新は `npx skills update`。

Skills CLI は導入のたびに匿名の利用統計を送り、公開リポジトリのスキルにはセキュリティ監査の問い合わせもする。止めるときは、ユーザー環境変数に `DISABLE_TELEMETRY=1`（または `DO_NOT_TRACK=1`）を設定する。セキュリティ監査の問い合わせも止まるので、その分、導入前に自分でコードを読む。Windows では `[Environment]::SetEnvironmentVariable('DISABLE_TELEMETRY', '1', 'User')` で設定し、ターミナルを開き直すと有効になる。
