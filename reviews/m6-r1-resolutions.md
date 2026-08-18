# M6 コードレビュー R1 対応記録

- R1-01: 語彙IDの品詞接尾辞15種を固定対応表でWordlist品詞へ復元し、全15種のHTML生成と品詞ラベル表示を確認した (`scripts/build_html.py`)
- R1-02: 承認済みM6D-06として強調対象形式の`target_surface`原文完全一致を一意化し、生成指示と機械検査で先行部分文字列を`V-TGT-02`へ拒否した (`DECISIONS.md`, `docs/question-generation-spec.md`, `docs/cefrj-validation-spec.md`, `agent/author-core.md`, `scripts/machine_check.py`)
- R1-03: 判定済み正解・不正解のdisabled選択肢だけを不透明表示にし、初期・disabled・正解・不正解の全状態でコントラスト4.5:1以上を確認した (`templates/index.html.j2`)
- R1-04: 全buttonへ最小幅44pxを追加し、375pxレイアウトの初期・動的整序状態と1文字トークン`i`/`a`で44×44px以上かつ横溢れなしを確認した (`templates/index.html.j2`)
- R1-05: 穴埋め印刷解答の段落を日本語既定へ戻し、正答と各別解だけを個別の`span[lang="en"]`で囲んだ (`templates/index.html.j2`)
