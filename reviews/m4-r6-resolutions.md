# M4 コードレビュー R6 対応記録

- R6-01: 承認済みM4D-07/M4D-08に基づき、対象出現フィールドの同長候補では宣言ターゲットを優先し、`vocab_mcq_ja2en`の選択肢では実在・実値・表記が一致する宣言アンカーの全トークン区間を同じentryとして消費するよう、正本文書・作問指示・機械検査を同期した。より長い一般候補、非対象フィールドのID順、不正アンカーの通常照合は維持した。 (`DECISIONS.md`, `docs/cefrj-validation-spec.md`, `docs/question-generation-spec.md`, `agent/author-core.md`, `scripts/machine_check.py`)

## 回帰確認

- コマンド: `PYTHONPATH=scripts .venv/bin/python - <<'PY' ... 同一複数語キー8組の後順位ターゲット、非対象ID順、最長一致、wedの対象文・選択肢、不正アンカー、'mの分割を実データで検証 ... PY`
- 結果: `e-mail` / `full-time:adverb` / `grown-up:noun` / `half-price:adverb` / `part-time:adverb` / `second-hand:adverb` / `all right:adverb` / `upside down:adverb` は全件で対象回数1・宣言対象IDを採用した。非対象`all right`のadjective優先と、短い`right`より長い一般候補を優先する規則は維持した。`wed`は完成文と正解選択肢の各2トークンを`lex:wed:verb`として採用して`verdict=pass`、記録pos不一致では宣言アンカー照合を使わず`V-DIS-01` / `V-LEX-01`となった。`'m`の2トークンも同じ宣言アンカーID・`wordlist_match`で採用した。

## DoD再確認

- 最終コマンド: `PYTHONPATH=scripts .venv/bin/python - <<'PY' ... 16状態と固定再質問、lookup実データ、正本内9形式例の正準化、validate.py、machine_check.py、machine reportスキーマ、PRM-01〜14、現行設定、固有名詞allowlist、文法9レベル適格件数、未付与16項目と継承枝番を検証 ... PY`
- DoD 1: S00〜S99の16状態、1ターン1質問、固定再質問、動的件数境界、`be` / A1.2の10件をlookup順で扱うM4D-01分岐がpass。
- DoD 2: `abandon`は実値verb/B1のためA1で拒否し、`Tokyo`はWordlist一致0件として辞書外拒否がpass。
- DoD 3: 正準化した9形式すべてでcandidateスキーマ、`validate.py`、`machine_check.py`の`verdict=pass`、machine reportスキーマ、machine reportの`validate.py`再検証が9/9 pass。
- DoD 4: PRM-01〜PRM-14、現行limits（語数A1=10/A2=14/B1=20/B2=26、解説brief=200/detailed=400、set_question_max=20）、50語の固有名詞allowlist全件展開指示がpass。
- DoD 5: 9レベルで教員版直接割当だけを返し、未付与16項目と親レベル継承枝番`gp:1-1`を拒否してpass。適格件数はA1.1=28、A1.2=50、A1.3=61、A2.1=65、A2.2=63、B1.1=76、B1.2=67、B2.1=53、B2.2=34。
- 結果: M4 DoD 5/5 pass。`.venv/bin/python -m py_compile scripts/machine_check.py scripts/lookup.py scripts/validate.py scripts/doctor.py`と`git diff --check`はpassし、`.venv/bin/python scripts/doctor.py`は12 pass / 0 fail。
