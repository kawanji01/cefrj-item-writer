# M4 コードレビュー R5 対応記録

- R5-01: 生成生出力をホスト側のパース前にUTF-8生バイトで検証し、生成起因の構文・スキーマ・厳格パース・正準化失敗を監査付きT2/T3へ統一した。 (`DECISIONS.md`, `docs/json-output-spec.md`, `docs/subagent-review-spec.md`, `agent/author-core.md`)
- R5-02: 明示対象集合の1〜`set_question_max`件不変条件と、追加超過・重複の原子的処理、全件削除の不受理、S80前の再検証を同期した。 (`DECISIONS.md`, `docs/interaction-flow.md`, `agent/author-core.md`)
- R5-03: S00後に`set_question_max`をセッション固定し、S31/S40の質問・再質問・受理境界・残容量・`--requested-count`を同じ動的値に統一した。 (`DECISIONS.md`, `docs/interaction-flow.md`, `agent/author-core.md`)

## 回帰確認

- R5-01コマンド: `PYTHONPATH=scripts .venv/bin/python - <<'PY' ... 1e400、NaN、Infinity、孤立サロゲートの生出力受理・T2/T3分類・invalid監査をvalidate.pyと一時ディレクトリで検証 ... PY`
- R5-01結果: `1e400` は生バイト検証で`E-CONTRACT-01`、`NaN` / `Infinity` は`E-INPUT-03`、エスケープされた孤立サロゲートはスキーマ通過後のJS-01正準化失敗、UTF-8化不能なホスト文字列はstrict UTF-8失敗として全てT2/T3へ分類された。1回目の`invalid1`、2回目の`invalid2`、生出力を置換文字で改変しない監査形式もpass。
- R5-02/R5-03コマンド: `.venv/bin/python - <<'PY' ... 対象集合の追加・削除境界、max=10/20の質問表示・受理・拒否、設計とauthor-coreの静的同期を検証 ... PY`
- R5-02/R5-03結果: 20+1追加は元集合保持、19+1は20件で受理、重複のみは不変、19+2は操作全体拒否、全件削除は不変、1件残す削除は受理。`set_question_max=10` / `20` の表示と境界受理、上限+1の拒否理由が一致した。

## DoD再確認

- 最終コマンド: `PYTHONPATH=scripts .venv/bin/python - <<'PY' ... 16状態と固定再質問、lookup実データ、正本内9形式例の正準化、validate.py、machine_check.py、machine reportスキーマ、PRM-01〜14、現行設定、固有名詞allowlist、文法9レベル適格件数、未付与16項目と継承枝番を検証 ... PY`
- DoD 1: S00〜S99の16状態、1ターン1質問、固定再質問、動的件数境界、`be` / A1.2の10件をlookup順で扱うM4D-01分岐がpass。
- DoD 2: `abandon`は実値verb/B1のためA1で拒否、`Tokyo`はWordlist一致0件として辞書外拒否がpass。
- DoD 3: 正準化した9形式すべてでcandidateスキーマ、`machine_check.py`の`verdict=pass`、machine reportスキーマが9/9 pass。
- DoD 4: PRM-01〜PRM-14、現行limits（語数A1=10/A2=14/B1=20/B2=26、解説brief=200/detailed=400）、50語の固有名詞allowlist全件展開指示がpass。
- DoD 5: 9レベルで教員版直接割当だけを返し、未付与16項目と親レベル継承枝番`gp:1-1`を拒否してpass。適格件数はA1.1=28、A1.2=50、A1.3=61、A2.1=65、A2.2=63、B1.1=76、B1.2=67、B2.1=53、B2.2=34。
- 結果: M4 DoD 5/5 pass。`.venv/bin/python -m py_compile scripts/machine_check.py scripts/lookup.py scripts/validate.py scripts/doctor.py`と`git diff --check`はpass、`.venv/bin/python scripts/doctor.py`は12 pass / 0 fail。
