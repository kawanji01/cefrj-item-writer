# M6 コードレビュー R2 対応記録

- R2-01: レンダリング全文のCRLFと単独CRをLFへ決定的に正規化してから末尾をLF1個に揃えた (`scripts/build_html.py`)
- R2-02: 英語選択肢内へ動的追加する正解・選択ラベルに`lang="ja"`を設定した (`templates/index.html.j2`)
- R2-03: 形式③の「まだ」一覧へ動的追加する英例文の`li`だけに`lang="en"`を設定した (`templates/index.html.j2`)
