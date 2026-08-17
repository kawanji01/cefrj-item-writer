# M4 コードレビュー R4 対応記録

- R4-01: 承認済みM4D-03に従い、GEN-13の意味的除外後の有効候補数で緩和要否を判断し、機械検査を同レベル・互換品詞・異品詞実使用の検査へ限定してCHK-06へ意味的必要性判定を追加した。 (`DECISIONS.md`, `docs/question-generation-spec.md`, `docs/subagent-review-spec.md`, `docs/cefrj-validation-spec.md`, `agent/author-core.md`, `scripts/machine_check.py`)

## 回帰確認

- コマンド: `PYTHONPATH=scripts .venv/bin/python - <<'PY' ... do/haveの生プール、互換品詞緩和candidate、不正フラグ、CHK-06境界を検証 ... PY`
- 結果: `lex:do:do-verb` と `lex:have:have-verb` の生プールは各3件のまま、A1 verbの誤答3件を実使用した `pos_pool_relaxed=true` candidateがともに `verdict=pass`・`V-DIS-02`なし。フラグfalseでの異品詞使用、および異品詞を実使用しないフラグtrueは `V-DIS-02`。CHK-06には `does` / `has` を区別不能語として有効候補から除外し、有効候補3件以上の不要な緩和をfailにする手順がある。
- 追加コマンド: `.venv/bin/python -m py_compile scripts/machine_check.py scripts/lookup.py scripts/validate.py scripts/doctor.py` / `.venv/bin/python scripts/doctor.py` / `git diff --check`
- 結果: Python構文検査と差分検査はpass、doctorは12 pass / 0 fail。

## DoD再確認

- コマンド: `PYTHONPATH=scripts .venv/bin/python - <<'PY' ... 状態機械、lookup実データ、正本文書内9形式例の正準化、validate.py、machine_check.py、設定、文法9レベルを一括検証 ... PY`
- DoD 1: S00〜S99の16状態、1ターン1質問、固定再質問、`be` / A1.2の10件をlookup順で扱うM4D-01分岐がpass。
- DoD 2: `abandon`は実値verb/B1のためA1で拒否、`Tokyo`はWordlist一致0件として拒否しpass。
- DoD 3: 正準化した9形式すべてでcandidateスキーマ、`machine_check.py`のverdict=pass、machine reportスキーマが9/9 pass。
- DoD 4: PRM-01〜PRM-14、現行limits、50語の固有名詞allowlist全件実行時展開指示がpass。
- DoD 5: 9レベルすべてで教員版直接割当だけを返し、親レベル継承枝番と未付与16項目を拒否してpass。適格件数はA1.1=28、A1.2=50、A1.3=61、A2.1=65、A2.2=63、B1.1=76、B1.2=67、B2.1=53、B2.2=34。
- 結果: M4 DoD 5/5 pass。
