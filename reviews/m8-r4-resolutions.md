# M8 コードレビュー R4 対応記録

- R4-01: 非init処理はset-dir検証直後から共通終端範囲へ入り、共通環境検査を含むS80中の終了1・2で監査を保持してflow-stateを削除するよう修正した (`scripts/flow_control.py`, `tests/unit/test_flow_control.py`)
- R4-02: 子CLIは終了1かつCLI-05完全形だけを非改変伝播し、不正終了1・終了2・その他異常終了をC12自身の終了2へ分類して全5呼出し境界でstate削除と監査保持を検査した (`scripts/flow_control.py`, `tests/unit/test_flow_control.py`)
- R4-03: Codex最終メッセージ作業ファイルの欠落・空・directory・symlink時も実returncodeと生stderrを保持してC12のprocess_failureへ渡し、後始末失敗が送信を先取りしないよう修正した (`.codex/run_reviewer.py`, `tests/unit/test_flow_control.py`)
- R4-04: candidate provider rawの削除を正規candidate監査またはinvalid監査の排他保存成功後へ移し、監査衝突・validate異常・raw削除失敗では未監査rawを保持するよう修正した (`scripts/flow_control.py`, `tests/unit/test_flow_control.py`)
- R4-05: candidateからL_ctxを決定的に導出し、CHK-03のexpected完全一致・actual真超過・CEFR-J 9段階・同一span/導入レベル/根拠のinventory対応を意味検証し、RPL fail fixtureを整合するB1.1超過へ更新した (`scripts/flow_control.py`, `tests/generate_assets.py`, `tests/fixtures/reviews/`, `tests/unit/test_flow_control.py`)
