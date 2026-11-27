---
name: long-run
description: 長時間かかるコマンド（ビルド・大量データ処理・E2E テスト・ベンチマークなど）を、Claude Code のセッションから切り離したジョブとして起動し、セッションが切れても完了まで走らせる。「セッションが切れても続くように実行して」「時間のかかる処理を流しておいて」で使う。
---

# long-run

コマンドを OS 側のプロセスとして切り離して実行する。セッションの終了・中断・利用上限に達しても処理は止まらず、結果は `.jobs/` に残る。

## 使う場面

- 数十分以上かかる、または途中で止まると困る処理
- 出力が大量で、会話に流すとトークンを浪費する処理（結果はログに書き、必要な部分だけ読む）

数分で終わる処理には使わない。通常の実行かバックグラウンド実行で足りる。

## 起動

起動前に、実行するコマンドをユーザーに示す。破壊的な操作・本番環境への接続・外部送信を含む場合は、承認を得てから起動する。

```bash
# Windows
powershell -NoProfile -ExecutionPolicy Bypass -File ~/.claude/scripts/long-run.ps1 start -Name <名前> -Command "<コマンド>" -Intent "<完了後にやること>"
# Linux / macOS
bash ~/.claude/scripts/long-run.sh start --name <名前> --command "<コマンド>" --intent "<完了後にやること>"
```

- Windows 版の `-Command` は PowerShell として実行する。Linux / macOS 版の `--command` は bash として実行する
- **`-Intent` / `--intent` は必ず書く。** 会話履歴を持たない新しいセッションで再開したとき、何のためのジョブかを伝える手がかりは `intent.md` だけになる
- ジョブはカレントディレクトリの `.jobs/<日時>_<名前>/` に作られる。`.jobs/` を git で管理しているリポジトリなら、`.gitignore` に加えることをユーザーに提案する

## 確認

```bash
powershell -NoProfile -ExecutionPolicy Bypass -File ~/.claude/scripts/long-run.ps1 status [-Id <ジョブID>]
powershell -NoProfile -ExecutionPolicy Bypass -File ~/.claude/scripts/long-run.ps1 log -Id <ジョブID> [-Lines 80]
# Linux / macOS は long-run.sh status [--id ...] / log --id ... [--lines 80]
```

| 状態 | 意味 |
|---|---|
| 実行中 | プロセスが動いている |
| 完了（未報告） | `exit.code` がある。結果をまだユーザーへ報告していない |
| 完了（報告済み） | `claim` 済み |
| 停止 | `exit.code` を書く前にプロセスが消えた（強制終了・再起動など）。ログを見て原因をユーザーに報告する |

セッション中に完了を待つときは、状態確認を短い間隔で繰り返さない。処理時間の見込みに合わせて間隔をあける。

## 完了後

1. `log` で出力を確認する。ログ全体は読まず、末尾と、エラーを grep した結果だけを読む
2. 終了コードと要点をユーザーに報告する
3. 報告が済んだら `claim` で報告済みにする

```bash
powershell -NoProfile -ExecutionPolicy Bypass -File ~/.claude/scripts/long-run.ps1 claim -Id <ジョブID>
bash ~/.claude/scripts/long-run.sh claim --id <ジョブID>
```

## セッションを閉じて開き直した場合

SessionStart フック（`~/.claude/hooks/job-resume-check.ps1`、Linux / macOS は `.sh`）が `settings.json` に登録されていれば、未報告のジョブがあるときだけ、セッション開始時に知らせる。通知を受けたら、`intent.md` を読んでから上の「完了後」の手順を進める。

フックが登録されていない場合は、作業を始める前に `status` を実行して未報告のジョブを探す。

## 後片付け

報告済みのジョブディレクトリは削除してよい。削除する前にユーザーに確認する。
