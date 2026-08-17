# M4 コードレビュー R3 対応記録

- R3-01: candidateの一時・監査JSONをBOMなしUTF-8、非ASCII非エスケープ、キー順、indent 2、LF、末尾改行1つで再直列化し、標準外数値も拒否する手順へ補完した。 (`agent/author-core.md`)

## 回帰確認

- コマンド: `PYTHONPATH=scripts .venv/bin/python - <<'PY' ... 日本語を含むgrammar_cloze候補を新手順とbuild_normalized.pyの正準JSON参照実装で直列化し、バイト列・スキーマ・標準外数値拒否を検証 ... PY`
- 結果: 836バイトで参照実装とバイト一致し、BOMなし、ASCII Unicodeエスケープなし、CRなし、末尾LF 1個、日本語UTF-8直接保持、candidateスキーマ適合、NaN拒否が全てpass。

## DoD再確認

- コマンド: `PYTHONPATH=scripts .venv/bin/python - <<'PY' ... 状態機械、lookup実データ、正本内9形式例の正準化、validate.py、machine_check.py、設定、文法9レベルを一括検証 ... PY`
- DoD 1: S00〜S99の16状態、1ターン1質問、固定再質問、`be` / A1.2の10件をlookup順で扱うM4D-01分岐がpass。
- DoD 2: `abandon`は実値verb/B1のためA1で拒否、`Tokyo`はWordlist一致0件として拒否しpass。
- DoD 3: 正準化した9形式すべてでcandidateスキーマ、`machine_check.py`のverdict=pass、machine reportスキーマが9/9 pass。
- DoD 4: PRM-01〜PRM-14、現行limits、50語の固有名詞allowlist全件実行時展開指示がpass。
- DoD 5: 9レベルすべてで教員版直接割当だけを返し、親レベル継承枝番と未付与16項目を拒否してpass。適格件数はA1.1=28、A1.2=50、A1.3=61、A2.1=65、A2.2=63、B1.1=76、B1.2=67、B2.1=53、B2.2=34。
- 結果: M4 DoD 5/5 pass。
