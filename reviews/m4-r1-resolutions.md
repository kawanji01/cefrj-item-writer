# M4 コードレビュー R1 対応記録

- R1-01: 文法ID照合でレベル包含より先にtarget_eligibleを判定し、親レベル継承枝番を教員版256項目の対象外としてDLG-42へ送る分岐を明記した。 (`agent/author-core.md`)
- R1-02: 同品詞プール不足時の決定的な互換品詞統合を明記し、承認済みM4D-02の表層形優先照合により希少3ターゲットの緩和candidateが機械判定までpassすることを確認した。 (`agent/author-core.md`, `scripts/machine_check.py`)
- R1-03: 全CLIを構造化argvで起動し、自由入力・ID・カテゴリ・ファイルパスを単一引数として安全に渡す共通規則を追加した。 (`agent/author-core.md`)
- R1-04: 終了コード1ではstderr全体をCLI-05 JSONとして解析し、error_codeとremedyをFMT-80bへ渡す停止処理に修正した。 (`agent/author-core.md`)
- R1-05: M4 DoD 4の50語リストを機能語ではなく固有名詞allowlistとする正しい記録へ訂正した。 (`CHANGELOG.md`)

## DoD再確認

- コマンド: `PYTHONPATH=scripts .venv/bin/python - <<'PY' ... 状態機械、lookup実データ、正本内9形式例、validate.py、machine_check.py、設定、文法9レベルを一括検証 ... PY`
- DoD 1: S00〜S99の16状態、1ターン1質問、固定再質問、`be` / A1.2の10件をlookup順で扱うM4D-01分岐がpass。
- DoD 2: `abandon`は実値verb/B1のためA1で拒否、`Tokyo`はWordlist一致0件として拒否しpass。
- DoD 3: 9形式すべてでcandidateスキーマ、`machine_check.py`のverdict=pass、machine reportスキーマが9/9 pass。
- DoD 4: PRM-01〜PRM-14、現行limits、50語の固有名詞allowlist全件実行時展開指示がpass。
- DoD 5: 9レベルすべてで教員版直接割当だけを返し、親レベル継承枝番と未付与16項目を拒否してpass。適格件数はA1.1=28、A1.2=50、A1.3=61、A2.1=65、A2.2=63、B1.1=76、B1.2=67、B2.1=53、B2.2=34。
- 結果: M4 DoD 5/5 pass。
