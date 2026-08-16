# CHANGELOG

## 2026-08-16 — M1 正規化＋doctor

### 実装

- `scripts/setup.py` と `requirements.txt` を追加し、`.venv`、spaCy 3.8.15、openpyxl 3.1.5、jsonschema 4.26.0、Jinja2 3.1.6、en_core_web_sm 3.8.0を構築可能にした。
- `scripts/build_normalized.py` を追加し、固定名の原本xlsx 2件から正準形の `lexicon.json`、`grammar.json`、`meta.json` を決定的・オフラインで生成できるようにした。`--diff`、`--dry-run`、`--accept-source-change`、原子的書込み、チェックサム拒否を含む。
- `scripts/doctor.py` を追加し、環境・データ・設定・スキーマ・レビュアー配線の12項目を一括診断できるようにした。
- `data/source/sources.json`、`data/config/limits.json`、`data/config/proper_nouns.json` と、ビルド済み `data/normalized/` 3ファイルを追加した。
- PLN-05で承認されたM1D-01〜M1D-10を `DECISIONS.md` へ記録し、影響する設計文書を承認内容どおりに改訂した。スキーマ9本は変更していない。

### 原本と正規化成果物

- 原本 `CEFR-J Wordlist Ver1.6.xlsx`: SHA-256 `e41033a12f92983012a0a6b201d4f1f860b7ba3de700c2c3b89660ea21a390e1`
- 原本 `CEFR-J Grammar Profile full 20200220.xlsx`: SHA-256 `f292ef17a60396797c0da2efea95f2ca3de940571164c93e5488c70029eab1c2`
- `lexicon.json`: SHA-256 `e751f9f32cd7f021e9697ba564e8327f4c9ef83c0fc76d9a77808a79abee1fea`
- `grammar.json`: SHA-256 `ced546d49ee948b40b8e35fac897a493bd8e9075aeb02ef2a62b599e7473a328`
- `meta.json`: SHA-256 `4bddb99255405d54bbe554acc6d23ded0f0922ce24298f33cd9b3cec4faacb7d`

### M1 DoD実行記録（6/6 pass）

1. 決定性
   - コマンド: `.venv/bin/python scripts/build_normalized.py` を2回連続実行し、`shasum -a 256 data/normalized/lexicon.json data/normalized/grammar.json data/normalized/meta.json` 相当のinline Python検証で比較。
   - 結果: 2回の3ファイルがそれぞれバイト一致。SHA-256は上記の値で固定。両ビルドのstderrは空、終了コード0。
2. スキーマ・meta適合
   - コマンド: `.venv/bin/python - <<'PY' ... Draft202012Validator ... validate_meta_document ... PY`（jsonschema直接呼出し）。
   - 結果: `lexicon.json` は `normalized_lexicon.schema.json`、`grammar.json` は `normalized_grammar.schema.json` に適合。`meta.json` はNRM-29に適合。終了コード0。
3. 件数不変条件（CI-NRM-03）
   - コマンド: `.venv/bin/python - <<'PY' ... json/openpyxlによる件数・ID集合検証 ... PY`。
   - 結果: entries=7,988、A1=1,200 / A2=1,443 / B1=2,486 / B2=2,859、`(headword,pos)`ユニーク=7,988、ALL行=7,801、groups=179（全member 2件以上）、教員版ターゲット=256、ITEM LIST=501、全枝番の親が存在、未付与親16件のID集合が仕様値と一致。終了コード0。
4. レベル継承・範囲分解（CI-NRM-05 / CI-NRM-07）
   - コマンド: `.venv/bin/python - <<'PY' ... grammar.jsonのlevelブロック検証 ... PY`。
   - 結果: `gp:1-1` / `gp:1-2` / `gp:1-3` が `gp:1` の下限・上限を継承し、`source=kyoinban_inherited`、`inherited_from=gp:1`。教員版は単一値152件、範囲値104件で、単一値は下限=上限。終了コード0。
5. doctor完全環境・異常模擬（CI-NRM-06 / CI-CLI-03）
   - コマンド: `.venv/bin/python scripts/doctor.py` および `.venv/bin/python - <<'PY' ... tempfile上の4環境をsubprocess実行 ... PY`。
   - 結果: 完全環境は12 pass / 0 fail・終了コード0。正規化欠落は終了コード1で `E-DATA-02` / `E-DATA-03` / `E-DATA-04`、原本1バイト改変はdoctorとbuildの双方が終了コード1・`E-DATA-02`、`limits.json` 欠落は終了コード1・`E-DATA-05`。全fail項目に具体的remedyがあり、doctorのstderrは空。
6. 差分ゼロ
   - コマンド: `.venv/bin/python scripts/build_normalized.py --diff`（実行前後の3ファイルSHA-256もinline Pythonで比較）。
   - 結果: lexicon / grammarのadded / removed / level_changedが全て `count=0, ids=[]`。`written=[]`、実行前後の3ファイルはバイト一致、終了コード0。

### 追加確認

- `python3 scripts/setup.py`: 固定版依存とen_core_web_sm 3.8.0の導入に成功、終了コード0。
- `python3 -m py_compile scripts/setup.py scripts/build_normalized.py scripts/doctor.py`: pass。
- `git diff --check`: pass。
- `build_normalized.py --help` / `doctor.py --help`: 日本語ヘルプを表示、終了コード0。
- 両CLIの未知引数: `E-INPUT-01`、日本語message/remedy、終了コード1。
