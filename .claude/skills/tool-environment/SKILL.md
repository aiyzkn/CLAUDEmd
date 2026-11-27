---
name: tool-environment
description: 外部コマンド（python・node・pandoc・gh など）を実行する前に、呼び出し名・格納パス・版・文字コード環境を記録から引く。記録が無い・古いときは検出スクリプトで調べて記録する。「pip が見つからない」「pandoc が無い」「文字化けする」「このツールは入っている？」でも使う。
---

# tool-environment

同じ端末で同じ調査を繰り返さないため、外部コマンドの所在と環境を記録しておき、それを引く。

## 参照の順番

見つかった時点で止める。

1. `~/.claude/CLAUDE.md` の「端末環境」の節（常に読み込まれているので追加の手間がかからない）
2. `~/.claude/tool-environment.json`（このスキルの検出スクリプトが書く記録）
3. 上のどちらにも無い、または古いと分かったときだけ、検出スクリプトを実行する

記録にあるコマンドは導入済みとして扱い、存在確認のための試し打ちはしない。版が作業の結果を左右するときだけ確かめ直す。

## 検出

```bash
# Windows
powershell -NoProfile -ExecutionPolicy Bypass -File ~/.claude/skills/tool-environment/scripts/detect-tools.ps1 [追加のコマンド名...]
# Linux / macOS
bash ~/.claude/skills/tool-environment/scripts/detect-tools.sh [追加のコマンド名...]
```

- よく使うコマンド約 35 種の所在と版、文字コード環境を調べて `~/.claude/tool-environment.json` に書く。標準の一覧に無いコマンドは引数で足す
- 出力は件数の要約だけなので、詳細は json から必要な項目だけを読む
- json に `"notes"` を書いておくと、次に検出したときも残る。手で調べた補足はそこに書く

## Windows で気をつけること

- **`python` が `WindowsApps` の下にある場合は、Microsoft Store の案内用スタブ。** 実体の Python ではないので、`py` や、mise・uv などの管理ツールが入れた実体を探す
- **PowerShell は 5.1（`powershell`）と 7.x（`pwsh`）が別物として同居しうる。** どちらで動かすかを決めてからスクリプトを書く。`powershell -File` で起動すると 5.1 が使われる
- **ANSI コードページが 932 のとき、BOM の無い UTF-8 の `.ps1` は 5.1 で文字化けして構文エラーになる。** 日本語を含む `.ps1` は BOM 付きで保存する
- **Claude Code の Bash ツールは Git Bash で動く。** PowerShell からは見えるのに Git Bash からは見えないコマンドがある（逆もある）。見つからないときは、もう一方のシェルからも確かめる

## 記録の更新

- 検出結果のうち毎回の作業に効くもの（主要な言語の呼び出し名・PATH に無いツールの場所・未導入のツール）は、`~/.claude/CLAUDE.md` の「端末環境」の節に 1 行ずつ書くことをユーザーに提案する
- CLAUDE.md と json の内容が食い違ったら、どちらが正しいかをユーザーに確認する

## 導入

- 見つからないツールを入れるときは、公式の手順 → パッケージマネージャ（winget・brew・apt など）の順に検討する
- **導入は必ずユーザーの承認を得てから行う。** 何を・どの手段で・どこから入れるかを示す
- 導入後、PATH が今のシェルに反映されていないことがある。フルパスで呼ぶか、新しいシェルで確かめる
