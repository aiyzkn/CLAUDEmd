---
name: office-reader
description: Word(.docx)、Excel(.xlsx/.xlsm/.csv)、PowerPoint(.pptx)、PDFの内容を読み込む際に使用する。ユーザーがOfficeファイルやPDFの中身を読みたい・要約したい・抽出したいと言ったときに発動。
---

# Office / PDF 読み込み

OfficeファイルやPDFの内容を読む場合、パーサを新規実装しない。
以下のコマンドでMarkdownに変換し、その出力を読むこと。

## 手順
1. 対象ファイルのパスを確認する
2. 次を実行する:
   `anydoc "<ファイルパス>"`
   - **リポジトリに `.claude/scripts/office/read_document.py` がある場合はそちらを使う**（`python .claude/scripts/office/read_document.py "<パス>"`）。anydoc を一次変換とし、anydoc が使えない・表の欠落・抽出過少・多段組崩れを検知したときは markitdown へ、それでも品質が低ければ Docling へ自動フォールバックする。プロジェクト側に `/office` スキルがある場合は、書き込み手段の選択も含めてそのスキルの規約が優先される
   - **anydoc が未導入ならグローバルインストールする**: `npm install -g @firecrawl/anydoc`（Node 20 以上）。`npx` での都度実行はしない。**スコープなしの `anydoc` は無関係な同名パッケージ**なので、スコープ付きの完全な名前で指定する
   - anydoc が使えない場合のフォールバックは `markitdown "<ファイルパス>"`。Windows では `markitdown` CLI が PATH に載らないことがあるため `python -m markitdown "<パス>"` を使う
3. 標準出力されたMarkdownを内容として扱う
4. **Markdownファイルとして保存する場合は、変換に使ったツールとは別のツールで検証する**（下記「クロスツール検証」）

## クロスツール検証（Markdownファイルとして保存する場合は必須）

変換結果をファイルに残す・成果物へ転記する場合は、**変換に使ったツールとは別のツール**で同じ原本を再変換し、両者を突き合わせて欠落・崩れを検出する。同一ツールの再実行・オプション変更は検証にならない（同じ欠落を同じように再現する）。

pandoc は xlsx / pptx / pdf を入力として読めないため、原本の形式ごとに検証ツールを選ぶ。

| 原本 | 変換 | 検証（必ず別ツール） |
|---|---|---|
| .docx | anydoc（未導入時は markitdown） | `pandoc -f docx -t gfm --wrap=none "<原本>" -o "<検証.md>"` |
| .csv | anydoc（未導入時は markitdown） | `pandoc -f csv -t gfm "<原本>" -o "<検証.md>"` |
| .xlsx / .xlsm | anydoc（未導入時は markitdown） | openpyxl（`read_only=True, data_only=True`）でシート数・行列数・セル値を照合 |
| .pptx | anydoc（未導入時は markitdown） | python-pptx でスライド数・テキスト・ノートを照合 |
| .pdf | anydoc（未導入時は markitdown） | `pdftotext -layout "<原本>" "<検証.txt>"` または Docling |

一次変換が anydoc の場合、xlsx / pptx の検証（openpyxl / python-pptx）は markitdown 一次のときと違って低レベルパーサを共有しないため、検証の独立性が高い。

**リポジトリに `.claude/scripts/office/verify_conversion.py` がある場合はそれを使う**（照合が自動化され、両者の全文をコンテキストに載せずに済む）。

```bash
python .claude/scripts/office/verify_conversion.py <原本> <一次変換.md>
# 終了コード 0=差分なし / 1=差分あり（独断で採用せず報告）/ 2=実行不能
```

ない場合は上表のツールを直接実行し、次の指標を手作業で照合する: 見出し数・表の個数と行列数・本文文字数の比（0.9〜1.1）・数値/日付/固有名詞の一致・シート数/スライド数/ページ数。

**文字数比は正規化してから比べる。** ツールごとに Markdown 記法の書き方が違うため、生の文字数では内容が一致していても 1 割以上ずれる（実測: 同一内容の docx で markitdown 151 / pandoc 132 = 1.14。差分は表区切り行 `| --- |` vs `|------|` 等の記法のみ。正規化後は 81 / 81 = 1.000）。比較前に ①HTML コメント ②表の区切り行 ③記法文字（`|`・`#`・`*`・`_`・`>`・`-`・バッククォート）④空白 を除去する。

Windows で変換結果をファイルへリダイレクト保存する場合は `PYTHONUTF8=1 PYTHONIOENCODING=utf-8` を付けて起動する（付けないと cp932 で保存され、後続の UTF-8 読み込みが `UnicodeDecodeError` で失敗する）。

- 検証出力は一時ディレクトリへ書き出し、両者の全文はコンテキストに載せない。**要点（照合指標と差分の有無）だけを報告する**
- 差分があった場合は独断でどちらかを採用せず、差分箇所と推定原因を提示して採用方針を確認する
- 保存したMarkdownの冒頭に使用ツールを注記する: `<!-- 変換: anydoc / 検証: pandoc（YYYY-MM-DD・差分なし） -->`

## 注意
- **anydoc も markitdown も OCR を行わない。** スキャン PDF・画像のみの PDF は anydoc が終了コード 3（`needsOcr`）で拒否するため、OCR が必要な資料は Docling（`pip install docling`）で処理する。
- **anydoc の `--ocr hosted` は使わない。** このオプションは文書そのものを Firecrawl のホスト API（`api.firecrawl.dev`）へ送信する。受領資料・業務文書を外部へ送る操作にあたるため、使う必要が生じたら実行せずユーザーに送信先と目的を提示して判断を仰ぐ。
- 巨大なxlsxは出力が長くなるため、必要なシートのみを
  openpyxl で読む方が安い場合がある。その際は read_only=True を使う。
- 文字化けや表崩れが起きた場合のみ、個別ライブラリ
  (python-docx / openpyxl / pdfplumber) にフォールバックする。