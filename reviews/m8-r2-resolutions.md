# M8 コードレビュー R2 対応記録

- R2-01: 固定FLOW01・REV02・ERR02の一致時にガードを成功終了させ、空・不正JSONを含むreview生stdoutを解釈せず製品CLIへ渡し、区切り注入と追加コマンドを拒否する単体検査を追加した (`.claude/hooks/guard_flow_control.py`, `tests/unit/test_flow_control.py`)
- R2-02: statusを含む全非init処理とfinalize前に開始時設定との完全一致を検査してE-DATA-08で監査保持・state削除し、子CLIの定義済みJSONエラーを元のcode/detail/remedyのまま伝播するよう変更した (`scripts/flow_control.py`, `tests/unit/test_flow_control.py`)
- R2-03: 不成立スロットの自動補充・教師照会を未処理初期assignmentより優先し、N=3でq01失敗後にq04をq02より先に処理するprovider順・slot所属・確定集合を固定検査した (`scripts/flow_control.py`, `tests/generate_assets.py`, `tests/fixtures/scenarios/rpl_03_proposal_replacement.json`, `tests/replay/test_replay.py`)
- R2-04: T8/T11再生成actionへ直前candidate・machine/review/set_check違反・disputesを別フィールドで保持し、dispute時の固定注意文を付け、T3診断専用形と分離した (`scripts/flow_control.py`, `tests/replay/test_replay.py`, `tests/unit/test_flow_control.py`)
- R2-05: 正準review監査の保存成功後だけdisputes件数をstateへ加算し、completed・aborted・teacher_consultのactionに累計を含める回帰検査を追加した (`scripts/flow_control.py`, `tests/unit/test_flow_control.py`)
- R2-06: failチェックとviolation・verdict・レベル値null規則・not_applicable条件を決定的に意味検証し、不一致を正準監査へ保存せず3回のINF再実行後に世代未消費で中止するよう変更した (`scripts/flow_control.py`, `tests/generate_assets.py`, `tests/fixtures/reviews/`, `tests/unit/test_flow_control.py`)
- R2-07: 資産生成器のreview_request・AUD-11・FIN-01手組みを削除して初回ゴールデンも製品flow_control.pyへ通し、生成器内の契約辞書再実装を検出するCI-R-03走査を追加した (`tests/generate_assets.py`, `tests/unit/test_fixtures.py`)
