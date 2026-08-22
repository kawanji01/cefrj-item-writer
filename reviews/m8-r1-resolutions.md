# M8 コードレビュー R1 対応記録

- R1-01: 世代管理・補充・教師照会・監査保存を製品側の決定的フローCLIへ集約し、通常フローとリプレイが同じ状態遷移を使用して候補生成・独立レビューの2境界だけをfixture化する構成へ変更した (`scripts/flow_control.py`, `agent/author-core.md`, `tests/replay/harness.py`, `tests/replay/test_replay.py`, `tests/fixtures/scenarios/rpl_03_proposal_replacement.json`, `tests/fixtures/scenarios/rpl_04_explicit_consult.json`, `tests/fixtures/scenarios/rpl_10_worst_case_bound.json`)
- R1-02: リプレイごとにpytestの一時リポジトリとその配下の`output/`を使用し、実リポジトリの`output/`へ予約set_idを作成しないことを回帰検査した (`tests/replay/harness.py`, `tests/replay/test_replay.py`)
- R1-03: review_request・slot outcome・finalize metadataの生成を製品実装へ移し、テストは製品出力を利用するとともにCI-R-03の禁止事項をASTで検査するメタテストを追加した (`scripts/flow_control.py`, `tests/support.py`, `tests/replay/harness.py`, `tests/unit/test_fixtures.py`)
- R1-04: 9形式と必須ゴールデンケース2件を固定目録で定義し、set・HTML・公式candidate・golden caseの実ファイル集合との完全一致を検査するよう変更した (`tests/support.py`, `tests/unit/test_fixtures.py`, `tests/unit/test_html.py`, `tests/unit/test_schemas.py`)
