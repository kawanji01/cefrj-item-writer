# M4 コードレビュー R2 対応記録

- R2-01: candidate検証のvalid=false/E-CONTRACT-01を共通停止より先にT2/T3へ分岐し、invalid監査保存・再指示・世代消費とその他CLI停止の境界を明記した。 (`agent/author-core.md`)

## 回帰確認

- コマンド: `PYTHONPATH=scripts .venv/bin/python - <<'PY' ... validate.pyのcandidate不通過2回とlookup.pyの定義済み停止を分類し、invalid監査形式を一時ディレクトリで検証 ... PY`
- 結果: candidate不通過1回目はT2・FMT-80b事象2・`candidate.invalid1.txt`、2回目はT3・事象3・`candidate.invalid2.txt`、lookupのE-INPUT-01は事象16へ分類され、全条件pass。candidateの各検証結果はstdoutに50件のエラーを含み、監査テキストは生出力・区切り行・stdout JSONの順で復元できた。

## DoD再確認

- コマンド: `PYTHONPATH=scripts .venv/bin/python - <<'PY' ... 状態機械、lookup実データ、正本内9形式例、validate.py、machine_check.py、設定、文法9レベルを一括検証 ... PY`
- DoD 1: S00〜S99の16状態、1ターン1質問、固定再質問、`be` / A1.2の10件をlookup順で扱うM4D-01分岐がpass。
- DoD 2: `abandon`は実値verb/B1のためA1で拒否、`Tokyo`はWordlist一致0件として拒否しpass。
- DoD 3: 9形式すべてでcandidateスキーマ、`machine_check.py`のverdict=pass、machine reportスキーマが9/9 pass。
- DoD 4: PRM-01〜PRM-14、現行limits、50語の固有名詞allowlist全件実行時展開指示がpass。
- DoD 5: 9レベルすべてで教員版直接割当だけを返し、親レベル継承枝番と未付与16項目を拒否してpass。適格件数はA1.1=28、A1.2=50、A1.3=61、A2.1=65、A2.2=63、B1.1=76、B1.2=67、B2.1=53、B2.2=34。
- 結果: M4 DoD 5/5 pass。
