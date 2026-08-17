# M5 コードレビュー R6 解決記録

- R6-01: FIN-01全文字列をファイル操作前にstrict UTF-8検証し、完成setの正準バイト列も一時ファイル作成前に構築して孤立サロゲートを残留物なしのE-CONTRACT-01へ変換した (`scripts/finalize_set.py`)
- R6-02: 承認済みM5D-12に基づきAUD-09を種別固定キーとBase64ペイロードを持つ正準JSON封筒へ変更し、任意の生出力・診断との予約行衝突を排除した (`DECISIONS.md`, `docs/json-output-spec.md`, `docs/subagent-review-spec.md`, `agent/author-core.md`, `scripts/set_support.py`)
- R6-03: 承認済みM5D-13に基づきDLG-82も対象別・世代別の実終端経路T3/T8/T11、診断または違反要約、実在監査パスを表示する契約へ統一した (`DECISIONS.md`, `docs/interaction-flow.md`, `agent/author-core.md`)
- R6-04: 承認済みM5D-14に基づきset.json公開を確定境界とし、公開後cleanup失敗を終了コード0・成功stdout・W-CLEANUP-01 stderr警告として正本完成状態と整合させた (`DECISIONS.md`, `docs/architecture.md`, `docs/interaction-flow.md`, `agent/author-core.md`, `scripts/finalize_set.py`)
- R6-05: set_id採番とcreated_atを同一ローカル日時から同時取得・保持するよう指示し、finalizeで実在日時・UTCオフセット・set_id日時部分との一致を検証した (`agent/author-core.md`, `scripts/finalize_set.py`)
- R6-06: E-CONTRACT-03では不整合目録をmessageとdetail.problemsへ決定的順序のまま全件保持し、50件超でも対象名を欠落させないようにした (`scripts/set_support.py`)
