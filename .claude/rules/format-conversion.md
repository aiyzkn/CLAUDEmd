---
paths:
  - "**/*.docx"
  - "**/*.xlsx"
  - "**/*.xlsm"
  - "**/*.pptx"
  - "**/*.pdf"
  - "**/*.csv"
---

# 形式変換の検証

Office・PDF と Markdown を相互に変換して保存するときは、**変換と別のパーサ**で再変換し、スクリプトで照合する（同じツールを再実行しても同じ欠落が再現するだけで、検証にならない）。

- 検証に使うツール: docx・csv=pandoc / xlsx=openpyxl / pptx=python-pptx / pdf=pdftotext か Docling（pandoc は xlsx・pptx・pdf を読めない）。markitdown で変換した xlsx・pptx は、パーサが共通なので anytomd で検証する（`--gemini` は画像を外部 API へ送るので使わない）
- コンテキストに載せるのは、正規化した後の指標と差分の有無だけにする（両方の全文は読み込まない）。差分が出たら差分箇所と推定原因を報告し、どちらを採用するか確認する
