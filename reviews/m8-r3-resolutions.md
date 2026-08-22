# M8 コードレビュー R3 対応記録

- R3-01: 承認済みM8D-10に基づき両レビュアーラッパーから固定argv・バイトstdinでC12へ直接渡すshell-free bridgeへ変更し、REV02/ERR02許可を撤去してdelimiter・NUL・制御文字の完全保存を検査した (`DECISIONS.md`, `docs/architecture.md`, `docs/cross-agent-compatibility.md`, `agent/author-core.md`, `.claude/run_reviewer.py`, `.codex/run_reviewer.py`, `.claude/settings.json`, `.claude/hooks/guard_flow_control.py`, `tests/unit/test_flow_control.py`)
- R3-02: review受理3回失敗と最終set_check failのaborted actionへ教師選択と区別したCLI-05完全形errorを含め、validation/process failureと最終検査の回帰検査を追加した (`docs/architecture.md`, `agent/author-core.md`, `scripts/flow_control.py`, `tests/unit/test_flow_control.py`)
- R3-03: S80後の定義済み停止・内部エラーを共通終端化して監査と衝突対象を保持したままflow-stateを削除し、作成済みrequest rawとcandidate provider入力を所有境界内で後始末するよう変更した (`docs/architecture.md`, `scripts/flow_control.py`, `tests/unit/test_flow_control.py`)
- R3-04: finalize終了0のstderrをCLI-22a正準警告として厳格検証し、W-CLEANUP-01の全フィールドをcompleted actionへ非改変で伝播するよう変更した (`docs/architecture.md`, `agent/author-core.md`, `scripts/flow_control.py`, `tests/unit/test_flow_control.py`)
- R3-05: machine_check_disputesのcode/location組を現在のmachine_report違反と完全照合し、不在・別箇所・machine passをINF再実行へ送って正準監査と件数加算を防ぐ検査を追加した (`scripts/flow_control.py`, `tests/unit/test_flow_control.py`)
- R3-06: validate.pyのE-CONTRACT-01/E-INPUT-03だけをprovider不当へ分類し、他のCLI-05終了1を完全伝播、終了2と不正な終了1をflow内部エラーとしてstate削除付きで停止するよう変更した (`scripts/flow_control.py`, `tests/unit/test_flow_control.py`)
- R3-07: 承認済みM8D-12で教師判断イベントを製品decide CLIへの外部入力として追加し、q01・q04〜q06・q02・q03の各3世代計18試行、2件のreduce終端監査、q07未要求を固定検査した (`DECISIONS.md`, `docs/testing-and-acceptance.md`, `tests/generate_assets.py`, `tests/fixtures/scenarios/`, `tests/replay/harness.py`, `tests/replay/test_replay.py`)
- R3-08: リモート公開済み`v1.0.0`（dereference先`c7d35ac66edbc6789e9629fc6526d0aadb6e62d1`）は移動せず、承認済みM8D-11に従ってコードレビュー収束後の最終コミット候補でA-01〜A-15を再実施し、合格後に修正版`v1.0.1`の受け入れ記録・CHANGELOG・annotated tagを作成するリリースゲートへ変更した (`DECISIONS.md`, `docs/architecture.md`, `docs/testing-and-acceptance.md`)
