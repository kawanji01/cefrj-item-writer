# CEFR-J適合性検証仕様書（cefrj-validation-spec）

## 0. 文書情報

### 0.1 目的

本文書は、CEFR-J準拠作問エージェントにおける (a) レベル体系の解釈規則、(b) 原本xlsxから正規化JSONへの変換規則、(c) 決定的機械検査パイプライン、(d) 検証項目の担当区分（機械/LLM）と違反コード・警告コード目録、(e) `level_source` 規則を定義する。実装者（Codex GPT-5.6 sol）が追加判断なしで `build_normalized.py` / `machine_check.py` / `set_check.py` を実装できる粒度で規定する。

### 0.2 対象読者

- 実装者（Codex GPT-5.6 sol）
- レビュアー指示書（`agent/reviewer-core.md`）・作問指示書（`agent/author-core.md`）の執筆者
- スキーマ（`schemas/`）の執筆者

### 0.3 参照文書

- `docs/requirements.md` — 機能要件・スコープ外/v2リスト（正）
- `docs/architecture.md` — CLI契約一覧・エラーコード目録（正）・`data_version` 書式（VER-04、正）・運用手順（正）
- `docs/question-generation-spec.md` — 9形式の生成仕様・candidateフィールド定義の言語仕様（正）
- `docs/subagent-review-spec.md` — レビュアー契約・チェックリスト（CHK-01〜CHK-19）・判定手順・記録様式（正）
- `docs/json-output-spec.md` — set.json全フィールド・ID規則・監査ファイル仕様（正）
- `docs/testing-and-acceptance.md` — ゴールデン管理・受け入れチェックリスト（正）
- `schemas/machine_report.schema.json` / `schemas/normalized_lexicon.schema.json` / `schemas/normalized_grammar.schema.json` — 本文書の定義を形式化したスキーマ（構造・型・必須性の正）

### 0.4 規範語彙凡例

- **しなければならない（MUST）**: 絶対要件。違反する実装は不適合である。
- **してはならない（MUST NOT）**: 絶対禁止。
- **すべきである（SHOULD）**: 正当な理由がない限り従う要件。逸脱時は理由を記録しなければならない。
- **してもよい（MAY）**: 任意。

### 0.5 この文書が「正」とする範囲

本文書は次の規則の唯一の正である。他文書はこれらを再定義してはならず、`docs/cefrj-validation-spec.md の LVL-03` の形式で参照しなければならない。

1. レベル体系（Q3/Q6/Q8の全規則・対応表）— 第1章（LVL-01〜LVL-14）
2. 正規化仕様（xlsx→`data/normalized/` の全変換規則）— 第2章（NRM-01〜NRM-31）
3. 機械検査仕様（`machine_check.py` / `set_check.py` の検査内容）— 第3章（MC-01〜MC-31、VAL-CFG-01）
4. 検証マトリクスと機械検査の違反コード・警告コード目録 — 第4章（MAT-01〜MAT-03、MC-28/MC-29/MC-31）
5. `level_source` 規則 — 第5章（LS-01〜LS-06）

本文書が正としないもの: エラーコード（`E-*`）の目録は `docs/architecture.md`、レビュアーの判定手順・記録様式・入出力封筒・**レビュー違反コード（`CHK-01`〜`CHK-19`）**は `docs/subagent-review-spec.md` と `schemas/review_result.schema.json`、candidate/set.jsonのフィールド名は `docs/json-output-spec.md` と `schemas/` が正である。正規化データ・machine_report の**構造・型・必須性**は各スキーマが正であり、本文書とスキーマが構造の点で食い違う場合はスキーマが正である（本文書は変換・検査の**規則**の正である）。

---

## 1. レベル体系の正（Q3・Q6・Q8）

### 1.1 スケール定義と順序（LVL-01〜LVL-04）

**LVL-01** レベルスケールは2種類のみ存在する。

| `level_scale` | 用途 | 値域 | 段数 |
|---|---|---|---|
| `cefr` | 語彙問題の指定レベル・Wordlistエントリのレベル | `A1` / `A2` / `B1` / `B2` | 4 |
| `cefrj` | 文法問題の指定レベル・教員版レベル | `A1.1` / `A1.2` / `A1.3` / `A2.1` / `A2.2` / `B1.1` / `B1.2` / `B2.1` / `B2.2` | 9 |

対応範囲はA1〜B2のみである。Pre-A1およびC1以上は扱ってはならない（`docs/requirements.md` の V2-07 参照）。

**LVL-02** `cefr` の全順序（rank値）を次表で固定する。実装はこのrank整数で比較しなければならない。

| cefr | rank |
|---|---|
| A1 | 1 |
| A2 | 2 |
| B1 | 3 |
| B2 | 4 |

**LVL-03** `cefrj` の全順序（rank値）を次表で固定する。

| cefrj | rank |
|---|---|
| A1.1 | 1 |
| A1.2 | 2 |
| A1.3 | 3 |
| A2.1 | 4 |
| A2.2 | 5 |
| B1.1 | 6 |
| B1.2 | 7 |
| B2.1 | 8 |
| B2.2 | 9 |

**LVL-04** 2つのスケール間の対応は次の2つの写像のみで行わなければならない。これ以外の換算を実装してはならない。

(a) 帯写像 `band(cefrj) → cefr`（cefrj値のドット前部分）:

| cefrj | band |
|---|---|
| A1.1 / A1.2 / A1.3 | A1 |
| A2.1 / A2.2 | A2 |
| B1.1 / B1.2 | B1 |
| B2.1 / B2.2 | B2 |

(b) 上限写像 `ceiling(cefr) → cefrj`（帯内の最上位枝番）:

| cefr | ceiling |
|---|---|
| A1 | A1.3 |
| A2 | A2.2 |
| B1 | B1.2 |
| B2 | B2.2 |

### 1.2 教員版レベル値の解釈（Q6、LVL-05〜LVL-08）

**LVL-05** 教員版の `CEFR-J level` 列の値は、単一値（例 `A1.3`）または範囲値（例 `A2.2-B1.2`、区切りはASCIIハイフン `-`）である。正規化時に `level.min` / `level.max` に分解しなければならない（NRM-23）。

- 単一値 `X` → `min = X`, `max = X`
- 範囲値 `X-Y` → `min = X`, `max = Y`。`rank(X) < rank(Y)` でない場合はビルドエラーとして停止しなければならない（エラーコードは `docs/architecture.md` の `E-DATA-*` 目録による。以下同様）。

**LVL-06（意味論）** `level.min` は**導入レベル**（その項目が導入され始めるレベル）、`level.max` は**定着レベル**（定着が期待されるレベル）と解釈しなければならない。

**LVL-07（ターゲット適格判定・文法）** 指定レベル `L`（cefrj）に対し、文法項目がターゲット適格であるのは次を全て満たす場合であり、かつその場合に限る。

1. その項目の `level.source` が `kyoinban_direct` である（`target_eligible = true` と等価。NRM-21/NRM-22）。継承レベル（`level.source = "kyoinban_inherited"`）およびレベル未付与（`level.source = null`）の項目はターゲットにしてはならない。
2. `rank(level.min) ≤ rank(L) ≤ rank(level.max)`（単一値は `L` 一致と等価）。

**LVL-08（文脈検証・文法構造）** 問題の例文中に現れる、ターゲット以外の文法構造の合否判定は次による。

- 文法問題（指定レベル `L`、cefrj）: その構造の導入レベル `level.min` について `rank(level.min) ≤ rank(L)` なら合格、超えるなら不合格。
- 語彙問題（指定レベル `L`、cefr）: `rank(level.min) ≤ rank(ceiling(L))` なら合格、超えるなら不合格。
- 構造のレベルが教員版由来（`kyoinban_direct` / `kyoinban_inherited`）で得られない場合は、レビュアーの推定（第5章 `reviewer_estimate`）に従う。

`level.max`（定着レベル）を文脈検証の合否に使ってはならない。文脈検証で使うのは `level.min` のみである。

### 1.3 スケール交差規則（Q8、LVL-09〜LVL-12）

**LVL-09（文法問題の例文語彙）** 指定レベル `Lx.y`（cefrj）の文法問題では、例文・完成文・元文・目標文・誤答選択肢に含まれる全ての語（第3.5節の照合手順で辞書照合対象となるトークン）のWordlistレベルが `rank_cefr(entry.level) ≤ rank_cefr(band(Lx.y))` を満たさなければならない。超過は機械検査違反 `V-LEX-02` である。

**LVL-10（語彙問題の例文語彙）** 指定レベル `L`（cefr）の語彙問題では、例文中の全ての語が `rank_cefr(entry.level) ≤ rank_cefr(L)` を満たさなければならない。超過は `V-LEX-02` である。

**LVL-11（語彙問題の例文文法）** 指定レベル `L`（cefr）の語彙問題では、例文中の全ての文法構造の導入レベルが `rank(level.min) ≤ rank(ceiling(L))` を満たさなければならない（LVL-08の語彙問題の場合と同一）。この判定はLLMレビューの担当である（第4章）。

**LVL-12（語彙問題のターゲット語）** ターゲット語は、指定レベル `L` のWordlistエントリに `headword` + `pos` で完全一致しなければならない（`entry.level = L` の完全一致。`≤` ではない）。機械検査は candidate が宣言する語彙エントリID（`lex:<headword>:<pos'>`）が正規化lexiconに存在し、かつ `level = L` であることを照合しなければならない。不一致は `V-TGT-03` である（MC-19）。

**LVL-13（誤答語のレベル）** 語彙4択の誤答語は `entry.level = L`（指定レベルと同一。`≤` ではない）でなければならない。品詞は原則ターゲットと同一とし、緩和時の規則は `docs/question-generation-spec.md`（GEN-15）が正である。機械照合は MC-23 による。

### 1.4 教員版レベル未付与の親項目（LVL-14）

**LVL-14** 次の16件の親IDとその枝番は教員版レベルを持たない。これらは `level.source = null` で正規化し（NRM-21-3）、ターゲットにしてはならない（LVL-07）。教師がこれらを明示指定した場合の対話手順は `docs/interaction-flow.md` が正である。

| ID | 文法項目 |
|---|---|
| 36 | 副詞(準否定) |
| 47 | so+形容詞+a/an+名詞 |
| 48 | too+形容詞+a/an+名詞 |
| 52 | 最上級の強調 by far |
| 80 | 受動態(未来進行) |
| 83 | 受動態(助動詞+進行) |
| 94 | -thing+to不定詞 |
| 96 | in order not to DO |
| 98 | so as not to DO |
| 115 | 動詞+目的語+not+動詞-ing形 |
| 130 | may as well |
| 191 | 感嘆文How単体 |
| 225 | 倒置による仮定法過去 |
| 226 | 倒置による仮定法過去完了 |
| 227 | shouldを用いた倒置による仮定 |
| 238 | 疑問詞疑問文 Whom |

---

## 2. 正規化仕様の正

出力ファイルの構造・型・必須性の形式的な正は `schemas/normalized_lexicon.schema.json` / `schemas/normalized_grammar.schema.json` である。本章は変換規則（何をどう写すか）の正であり、フィールド名・構造はスキーマと一致させて記述する。

### 2.1 入出力と決定性（NRM-01〜NRM-05）

**NRM-01** 正規化は `build_normalized.py`（CLI契約は `docs/architecture.md` が正）が実行し、次の入力から次の出力を生成しなければならない。

| 入力 | 出力 |
|---|---|
| `data/source/CEFR-J Wordlist Ver1.6.xlsx` | `data/normalized/lexicon.json` |
| `data/source/CEFR-J Grammar Profile full 20200220.xlsx` | `data/normalized/grammar.json` |
| `data/source/sources.json`（原本URL・ダウンロード日の手動維持ファイル。NRM-29。更新手順は `docs/architecture.md` OPS-01、欠落・不正の検出は同 E-DATA-01 が正） | `data/normalized/meta.json` |

`sources.json` は `{"sources": [<wordlist>, <grammar_profile>]}` とし、配列順を `wordlist` → `grammar_profile` に固定する。各要素は `role` / `file` / `version_label` / `url` / `download_date` の5キーのみを持ち、`role` と `file` は NRM-29 の `sources[]` と同じ固定値、`version_label` は `^[0-9A-Za-z.\-]+$`、`url` は `http://` または `https://` で始まる文字列、`download_date` は `YYYY-MM-DD` とする。`build_normalized.py` は `version_label` を `meta.json` の同名フィールドへ、`download_date` を `retrieved_date` へ転記し、`data_version` を両原本の`version_label`と正規化パイプライン版から構築する。

**NRM-02（決定性）** 同一入力（xlsxのSHA-256・`sources.json`・パイプライン版・spaCyモデル版が同一）からの出力はバイト一致しなければならない。出力にビルド時刻・乱数・環境依存値を含めてはならない。

**NRM-03（出力整形）** 全出力JSONは `docs/json-output-spec.md` JS-01 の正準形（UTF-8・BOMなし・非ASCII非エスケープ・キー辞書順ソート・インデント2・改行LF・末尾改行1つ）で直列化しなければならない（`docs/json-output-spec.md` NDS-05）。

**NRM-04（スキーマ適合）** 出力は `normalized_lexicon.schema.json` / `normalized_grammar.schema.json` に適合しなければならない。

**NRM-05（meta.jsonの扱い）** `meta.json` の構造は NRM-29 が正であり、スキーマ化は `schemas/` の9本には含まれない（検証は `doctor.py` の構造検査と各CLIの起動時検査 E-DATA-04 による。`docs/json-output-spec.md` SV-02）。

### 2.2 Wordlist → lexicon.json（NRM-06〜NRM-14）

**NRM-06（基礎シート）** エントリの基礎はシート `ALL_sep`（7,988行、1行1見出し）である。シート `ALL` は併記グループの抽出（NRM-10）のみに使用する。シート `A1`〜`B2`・`A1_sep`〜`B2_sep` はエントリ生成に使用してはならず、整合検査（NRM-31）のみに使用する。シート `README` は使用しない（出典情報は `sources.json` → `meta.json` 経由で管理する）。

**NRM-07（列マッピング）** ALL_sep各行から次のとおり変換しなければならない。ヘッダー行（1行目）はスキップする。

| xlsx列（ALL_sep） | JSONフィールド | 型 | 変換規則 |
|---|---|---|---|
| `headword` | `headword` | string | 前後空白をtrim、Unicode NFC正規化。空ならビルドエラー |
| `pos` | `pos` | string | trim。15値（`noun` / `adjective` / `verb` / `adverb` / `pronoun` / `preposition` / `determiner` / `conjunction` / `number` / `modal auxiliary` / `be-verb` / `do-verb` / `have-verb` / `interjection` / `infinitive-to`）のいずれかでなければビルドエラー |
| `CEFR` | `level` | string | `A1` / `A2` / `B1` / `B2` 以外はビルドエラー |
| `CoreInventory 1` | `core_inventory_1` | string \| null | 空セルは `null`。非空はtrim |
| `CoreInventory 2` | `core_inventory_2` | string \| null | 同上 |
| `Threshold` | `threshold` | string \| null | 同上 |

**NRM-08（id）** 各エントリの `id` は `lex:<headword>:<pos'>` とする。`<headword>` は原表記のまま（内部空白を保持）、`<pos'>` は `pos` の空白を `-` に置換した値（例 `lex:watch:verb`, `lex:a.m.:adverb`, `lex:can:modal-auxiliary`, `lex:CD player:noun`）。ID書式の正は `docs/json-output-spec.md` ID-04 である。

**NRM-09（派生フィールド）** 各エントリに次を付与しなければならない。`headword` に `:` を含む行を検出した場合はビルドエラーとして停止しなければならない（ID書式の破壊を防ぐ。`docs/json-output-spec.md` ID-04）。

| フィールド | 型 | 規則 |
|---|---|---|
| `is_multiword` | boolean | `headword` にASCII空白またはハイフン（`-`）が1つ以上含まれるとき `true` |
| `group_ids` | string[] | NRM-10で所属する併記グループIDの配列。所属なしは空配列。複数グループ所属時を含め、`group_id` の辞書順に整列する |

照合キー（headword の小文字化NFC文字列）および複数語見出しのトークン列は、正規化データには**保存しない**。これらは `machine_check.py` が実行時に `headword` から決定的に導出する（MC-14/MC-15）。

**NRM-09a（一意性）** `(headword, pos)` の組はlexicon内で一意でなければならない（`id` の一意性と等価）。ALL_sep内の重複（同一 `headword`+`pos` の複数行）を検出した場合、`level` と全カテゴリ列が完全一致するなら1エントリに統合し、いずれかが不一致ならビルドエラーとして停止しなければならない。

**NRM-10（併記グループ）** シート `ALL` の `headword` に `/` を含む行（併記見出し）は1つのグループを定義し、トップレベル配列 `groups[]` に1件として出力する。

1. ALL行の `headword` を `/` で分割した各断片（trim後）を **variant** と呼ぶ。`group_id = "grp:" + <先頭variant> + ":" + <pos'>`（例 `a.m./A.M./am/AM` 行 → `grp:a.m.:adverb`）。
2. 各variantが、同一 `pos` のALL_sep行に1対1対応しなければならない。対応が取れない断片・余る断片があればビルドエラー。
3. グループの内容: `{"group_id", "headword_joined"（ALL行原表記そのまま）, "pos", "level", "member_ids"（対応エントリIDのALL行出現順配列、2件以上）}`。
4. 対応したALL_sepエントリの `group_ids` にこの `group_id` を追加する。同一グループの全エントリは `level` が一致しなければならない（不一致はビルドエラー）。

**NRM-11（グループの用途）** 同一グループのエントリは同一語の表記ゆれである。生成・レビュー・HTMLでの表記選択規則は `docs/question-generation-spec.md` が正である。機械検査ではグループを展開済みのALL_sepエントリ単位で照合するため、追加処理は不要である。

**NRM-12（lexicon.jsonトップレベル）** トップレベルは次の4キーのみとする（構造の正は `normalized_lexicon.schema.json`）。

```json
{
  "schema_version": "1.0.0",
  "data_version": "wl1.6+gp20200220+norm1.0.0",
  "entries": [ { "id": "...", "headword": "...", "pos": "...", "level": "...", "core_inventory_1": null, "core_inventory_2": null, "threshold": null, "is_multiword": false, "group_ids": [] } ],
  "groups": [ { "group_id": "grp:a.m.:adverb", "headword_joined": "a.m./A.M./am/AM", "pos": "adverb", "level": "A1", "member_ids": ["lex:a.m.:adverb", "lex:A.M.:adverb", "lex:am:adverb", "lex:AM:adverb"] } ]
}
```

**NRM-13（並び順）** `entries` は `(headwordのcasefold, headword, pos)` の辞書順、`groups` は `group_id` の辞書順に整列しなければならない。この整列は決定的であり、原本の行順への依存を持ち込んではならない（原本行との対応は `id` により常に追跡できる）。

**NRM-14（非収録語・縮約形の扱い）** 人名・地名・言語名・`Christmas` はWordlist非収録であり、正規化で補ってはならない（照合時の扱いはallowlist、MC-18）。縮約・融合形（原本で非収録が確認済みの具体例: `cannot` / `n't` / `gonna`）のエントリを追加してはならない。活用形（`watches`, `watched`）のエントリを事前展開して追加してはならない。これらの照合は実行時のspaCyトークン分割・レンマ化で行う（MC-13〜MC-16）。

### 2.3 Grammar Profile → grammar.json（NRM-15〜NRM-28）

**NRM-15（対象シート）** 使用するシートは `ITEM LIST`（501項目）、`教員版`（256項目）、`EFL SUMMARY (FULL)`（傍証）の3枚のみである。他の9シートは使用してはならない。

**NRM-16（読み取り規則）** ITEM LISTは1行目にタイトル、2行目に列ヘッダー、3〜503行目に501データ行を持つ。教員版は1行目にタイトル、2行目に列ヘッダー、3〜258行目に256データ行を持つ。EFL SUMMARY (FULL) は1行目にコーパス母数、2行目にタイトル、3行目に列ヘッダー、4〜504行目に501データ行を持つ。各エントリの `id` は `gp:<ID列原表記>`（例 `gp:13`, `gp:1-1`）、`item_list_id` はID列原表記（trimのみ）とする。

**NRM-17（ITEM LIST列マッピング）** ITEM LIST由来の属性は各エントリのネストオブジェクト `item_list` に格納しなければならない。

| xlsx列（ITEM LIST） | JSONフィールド（`item_list.*`） | 型 | 変換規則 |
|---|---|---|---|
| `文法項目` | `name_ja` | string | trim・NFC |
| `文タイプ(不問のものは空欄)` | `sentence_type_ja` | string \| null | 空セルは `null` |
| `Shorthand Code` | `shorthand_code` | string \| null | trim。空セルは `null` |
| `Grammatical Item` | `grammatical_item_en` | string \| null | trim。空セルは `null` |
| `Sentence Type (...)` | `sentence_type_en` | string \| null | 空セルは `null` |
| `備考` | `note` | string \| null | 空セルは `null` |
| `パターン略記` | `pattern_shorthand` | string \| null | trim。LLMレビューでの対象構造照合の根拠（MC-25）。空セルは `null` |
| `正規表現(TreeTaggerベース...)` | `regex_treetagger` | string \| null | trim。参考保持のみ。機械照合への使用は `docs/requirements.md` の V2-04 |

上表の省略表記2列は、原本ヘッダーのうち `Sentence Type (` および `正規表現(TreeTaggerベース` でそれぞれ始まる列を指す。この2列は当該固定接頭辞で識別し、その他の列は上表の文字列との完全一致で識別する。

**NRM-18（教員版結合）** 教員版の256行は `ID` でITEM LIST項目に結合しなければならない（教員版のIDがITEM LISTに存在しない場合はビルドエラー）。

**NRM-19（kyoinbanフィールド）** 各エントリの `kyoinban` は次の2分岐のいずれかとする（スキーマのoneOfで強制）。

- 教員版行がある256項目: `{"present": true, "name_ja"（文法項目）, "name_simple_ja"（文法項目(平易版)。教師向け表示名の正）, "name_en"（Grammatical item (English)。空セルはnull）, "level_raw"（CEFR-J level列原文をtrim。`had it not been for ` の末尾空白に対応。LVL-05の構文でなければビルドエラー）}`
- 教員版行がない項目: `{"present": false, "name_ja": null, "name_simple_ja": null, "name_en": null, "level_raw": null}`

教員版シートの `A1.1`〜`B2.2` の9マーカー列は `level_raw` の冗長表現とみなし、読み取らない。

**NRM-20（親子関係）** `item_list_id` が `<数字>` のみの項目は親（263件）、`<数字>-<数字>` の項目は枝番（238件）である。枝番には `parent_id = "gp:<親数字>"` を付与しなければならない。親には `parent_id = null`。枝番の親がITEM LISTに存在しない場合はビルドエラー。

**NRM-21（levelブロック）** 各エントリの `level` は `{"min", "max", "source", "inherited_from"}` とし、次の3分岐のいずれかとする（スキーマのoneOfで強制）。

1. **NRM-21-1（直接付与）**: 自身に教員版行がある場合（`kyoinban.present = true`）、`level_raw` をNRM-23で分解し、`source = "kyoinban_direct"`, `inherited_from = null` とする。枝番が教員版行を直接持つ場合（256件のうち親IDでない9件）も本分岐であり、継承より直付与を優先しなければならない。
2. **NRM-21-2（継承）**: 教員版行を持たない枝番のうち、親項目が `source = "kyoinban_direct"` を持つものは、親の `min` / `max` をコピーし `source = "kyoinban_inherited"`, `inherited_from = <親のgp ID>` とする。
3. **NRM-21-3（未付与）**: LVL-14の16親項目、およびその枝番のうち教員版直付与を持たないものは `min = max = source = inherited_from = null` とする。

**NRM-22（target_eligible）** `target_eligible` は `kyoinban.present = true` の256項目のみ `true` とする（LVL-07と等価。継承項目・レベルnull項目は `false`）。

**NRM-23（レベル分解）** `kyoinban.level_raw` は LVL-05 の規則で `level.min` / `level.max` に分解する。

**NRM-24（display_name）** 各エントリの `display_name`（教師向け表示名）は、教員版行がある場合は `kyoinban.name_simple_ja` の値、ない場合は `item_list.name_ja` の値とする。

**NRM-25（並び順）** `entries` は `(親番号N昇順, 親自身→枝番M昇順)` に整列しなければならない（例: `gp:1`, `gp:1-1`, `gp:1-2`, `gp:2`, …。NとMは数値として比較する）。

**NRM-26（EFL傍証）** `EFL SUMMARY (FULL)` を `ID` で結合し、各エントリの `efl` に `{"rel_freq": {A1..C1の百万語あたり相対頻度（空セルはnull）}, "range": {A1..C1の教科書RANGE整数（空セルはnull）}}` を格納する。数値は原本セル値をそのまま保持し、丸めてはならない。

**NRM-27（efl_corpus）** EFLコーパスの母数は項目ごとではなく定数であり、`grammar.json` トップレベルの `efl_corpus` に1回だけ記録しなければならない: `{"words": {"A1": <レベル別総語数>, ...}, "books": {"A1": 17, "A2": 21, "B1": 26, "B2": 23, "C1": 8}}`。

**NRM-28（EFL行なし）** EFL SUMMARY に該当行がないエントリの `efl` は `null` とする。

`grammar.json` のトップレベルは `{"schema_version", "data_version", "efl_corpus", "entries"}` の4キーのみである（構造の正は `normalized_grammar.schema.json`。構造例は `docs/json-output-spec.md` 実例9）。

### 2.4 meta.json・チェックサム・data_version（NRM-29）

**NRM-29（meta.json）** `build_normalized.py` は次の `meta.json` を生成しなければならない。`data_version` の書式の正は `docs/architecture.md` VER-04（`wl<Wordlist版>+gp<GrammarProfile版>+norm<パイプラインsemver>`、初版 `wl1.6+gp20200220+norm1.0.0`）である。

```json
{
  "data_version": "wl1.6+gp20200220+norm1.0.0",
  "pipeline_version": "1.0.0",
  "spacy_model": { "name": "en_core_web_sm", "version": "<インストール版をそのまま記録>" },
  "sources": [
    {
      "role": "wordlist",
      "file": "CEFR-J Wordlist Ver1.6.xlsx",
      "sha256": "<64桁hex小文字>",
      "version_label": "1.6",
      "url": "<data/source/sources.json から転記>",
      "retrieved_date": "<data/source/sources.json から転記。YYYY-MM-DD>"
    },
    {
      "role": "grammar_profile",
      "file": "CEFR-J Grammar Profile full 20200220.xlsx",
      "sha256": "<64桁hex小文字>",
      "version_label": "20200220",
      "url": "<sources.jsonから転記>",
      "retrieved_date": "<sources.jsonから転記>"
    }
  ],
  "counts": { "lexicon_entries": 7988, "lexicon_groups": "<groups実件数>", "grammar_items": 501, "target_eligible": 256 }
}
```

SHA-256は原本xlsxファイル全体に対して計算した小文字16進64桁でなければならない。meta.json は引用文（citation）を保持しない。引用文の組み立ては `docs/json-output-spec.md` ATT-02（`finalize_set.py` が `version_label` / `url` / `retrieved_date` からテンプレートで決定的に組み立てる）が正である。`set.json` への転記規則は `docs/json-output-spec.md` ATT-01・FIN-02 が正である。

`data_version` は `wl<wordlist.version_label>+gp<grammar_profile.version_label>+norm<pipeline_version>` として構築し、meta内の3値と常に整合しなければならない。

`data/normalized/` の「出典ヘッダー付き」とは、`lexicon.json` / `grammar.json` の `data_version` と、同一ディレクトリの `meta.json.sources` を一体として出典追跡できる状態をいう。lexicon / grammar のスキーマに出典フィールドを追加してはならない。

### 2.5 起動時整合検証（NRM-30）

**NRM-30** 正規化データを読み込む全CLI（`machine_check.py` / `set_check.py` / `lookup.py` / `build_html.py` / `finalize_set.py`）は、処理前に次を検証し、不一致なら `E-DATA-*` で停止しなければならない（コード値は `docs/architecture.md`）。

1. `lexicon.json` / `grammar.json` / `meta.json` が存在し読み取り可能である。
2. 3ファイルの `data_version` が一致する。
3. `lexicon.json` / `grammar.json` が各スキーマに適合する。
4. `meta.json` の `counts` が `entries` / `groups` の実要素数と一致する。

M2の`machine_check.py`と`lookup.py`は、上記の自己整合に加えて`docs/architecture.md` CLI-08の【データ】を全て実施し、原本xlsx存在・原本SHA-256・設定ファイルも検証する。その他のCLIの前提検査範囲は同文書第5.1節の契約一覧を正とする。

### 2.6 ビルド時整合検査（NRM-31）

**NRM-31** `build_normalized.py` は出力生成後に次を検査し、失敗時はビルドエラーで停止しなければならない（この定数は `docs/testing-and-acceptance.md` CI-NRM-03 と同一の定義を共有する）。

1. `entries` 数 = 7,988（ALL_sep行数）。レベル別度数 A1:1200 / A2:1443 / B1:2486 / B2:2859（ALL_sep単位。原本更新でこの定数が変わる場合の手順は `docs/architecture.md` OPS-01 による）。
2. `A1_sep`〜`B2_sep` 各シートの行数が上記レベル別度数と一致する。
3. `(headword, pos)` のユニーク数 = 7,988。ALLシートのデータ行数 = 7,801。併記見出しを展開したALL_sepとの差分を保持しつつ、NRM-09aの一意性を満たす。
4. `groups` の全要素の `member_ids` が2件以上である。`groups` の総数は初回ビルド時の実測値をゴールデン（`docs/testing-and-acceptance.md` CI-NRM-02 のチェックサム）で固定する。
5. grammar `entries` 数 = 501、親263・枝番238、`target_eligible = true` が256件、`level.source = null` の項目がLVL-14の16親とその継承不能枝番に限られる。
6. 全枝番の `parent_id` が解決できる。

---

## 3. 機械検査仕様の正

### 3.1 契約と前提（MC-01〜MC-05）

**MC-01** `machine_check.py` は候補問題1問1世代を検査単位とする。入力は candidate JSON（`candidate.schema.json` 適合）、セットの確定済み期待条件（format・level・依頼問題数）、正規化データ（`data/normalized/`）、設定（`data/config/limits.json` / `data/config/proper_nouns.json`）であり、出力は `machine_report.schema.json`（`scope = "question"`）に適合するレポート1件である。candidateの`level.scale`と期待レベルのscaleが同じ場合、S4〜S6のレベル依存検査は期待レベルを指定レベルとして実行する。format不一致でscaleも異なる場合は`V-COND-01`を発行した上で、実行可能なレベル依存検査をcandidateのscaleと値で継続する。引数・stdin/stdout・終了コードは `docs/architecture.md` のCLI契約が正である。

**MC-02（verdict）** `verdict` は `violations` が1件以上あれば `fail`、0件なら `pass` である。他の判定基準を導入してはならない。

**MC-03（覆せない判定・誤検出疑い）** 機械検査の `fail` は、LLMレビューを含む後続工程が覆してはならない（Q7）。機械検査の誤検出が疑われる場合の報告様式は `docs/subagent-review-spec.md` 第7節が正であり、報告があっても当該セットでは不合格のままである。警告（`warnings[]`、MC-29）は verdict に影響せず、レビュアーの誤検出調査の手がかりとして渡す。

**MC-04（全件列挙）** 検査は途中で打ち切らず、実行可能な全検査を実行してから検出可能な全違反を単一レポートに集約しなければならない（レビュアーと再生成に全violationsを渡すため）。

**MC-05（スキーマ不適合入力）** 入力candidateが `candidate.schema.json` に適合しない場合、機械検査は問題の不合格ではなく契約違反（`E-CONTRACT-01`）として停止しなければならない。ただし、candidate JSONの整数トークンが符号を除く10進4,300桁を超える場合はスキーマ検証前の入力不正`E-INPUT-03`とする（M2D-11）。スキーマ不通過の扱い（世代消費の規則）は `docs/subagent-review-spec.md` の再生成ループ仕様（T2/T3）が正である。

**VAL-CFG-01（運用パラメータ）** 実行時に変更可能な運用パラメータは `data/config/limits.json` の値のみである（キー目録と既定値の正は `config_limits.schema.json`、構造の要点は `docs/json-output-spec.md` NDS-03）。本文書・他文書に現れる数値既定値（語数上限・字数上限・誤答再利用上限・世代上限・問題数上限・レビュータイムアウト）は同ファイルの初期値であり、実装は必ず同ファイルの現在値を読まなければならない。

### 3.2 パイプライン段一覧（MC-06）

**MC-06** `machine_check.py` は次の7段を順に実行しなければならない。S1・S2で停止（エラー）した場合はレポートを出力しない。S3以降の違反は検査を中断せず、MC-04に従い集約する。

| 段 | 名称 | 入力 | 出力 | 停止/違反 |
|---|---|---|---|---|
| S1 | 前提検査 | CLI引数・正規化データ・設定 | 検証済みリソース | 不備は `E-ENV-*` / `E-DATA-*` で停止 |
| S2 | 検査対象テキスト抽出 | candidate | 形式別の検査対象フィールド集合（MC-07） | candidateスキーマ不適合は `E-CONTRACT-01` で停止 |
| S3 | spaCy解析 | 検査対象英文 | Doc（トークン列・レンマ・タグ・文分割） | — |
| S4 | 構造・セット条件制約検査 | candidate・期待条件・Doc・limits.json | format・level・question_id上限・文数・語数・字数・日本語フィールドの判定 | `V-COND-01`, `V-SENT-01`, `V-LEN-01`, `V-EXP-01`, `V-JPN-01` |
| S5 | 語彙照合 | Doc・lexicon・allowlist | トークン別照合結果・レベル判定・対象語出現数 | `V-LEX-01`, `V-LEX-02`, `V-TGT-02` |
| S6 | 形式固有検査 | candidate・lexicon・grammar | ターゲット照合・選択肢・誤答由来・整序・穴埋め・書き換えの判定 | `V-TGT-01`, `V-TGT-03`, `V-CHO-01`, `V-DIS-01/02/03`, `V-ORD-01/02`, `V-CLZ-01/02`, `V-RWT-01` |
| S7 | レポート生成 | S3〜S6の全結果 | machine_report JSON（MC-30） | — |

### 3.3 形式別の検査対象（MC-07）

**MC-07** 検査対象は形式ごとに次表で確定する。「文として検査」= S3〜S5を文単位で適用（文数・語数・語彙照合）。「語として検査」= S5の語彙照合のみをトークン単位で適用（文数・語数は適用しない）。フィールドの物理名・必須性は `docs/json-output-spec.md` §5 と `candidate.schema.json` が正である。空欄を含む文は `#filled:` 記法の合成文（`docs/json-output-spec.md` AUD-06）で検査する。

| 形式コード | 文として検査 | 語として検査 | 対象語出現照合（MC-19-2） | 形式固有検査（S6） |
|---|---|---|---|---|
| `vocab_mcq_en2ja` | `body.stem` | — | `body.stem` に対して実施 | 選択肢構成・誤答由来 |
| `vocab_mcq_ja2en` | `body.sentence_with_blank#filled:answer`（= `sentence_complete`） | 英語選択肢4語 | `sentence_complete` に対して実施 | 選択肢構成・誤答由来・完成文整合 |
| `vocab_flashcard_en2ja` | `body.example.en` | — | `body.example.en` に対して実施 | — |
| `vocab_flashcard_ja2en` | `body.example.en` | — | `body.example.en` に対して実施 | — |
| `grammar_mcq` | `body.sentence_with_blank#filled:answer` および `#filled:choices[k]`（k=誤答3肢） / `body.context_sentence`（非null時） | — | — | ターゲット適格・選択肢構成 |
| `grammar_cloze` | `body.sentence_with_blank#filled:answer` / `body.context_sentence`（非null時） | `answer_equivalents` の各要素のトークン | — | ターゲット適格・空欄・同値リスト |
| `grammar_reorder` | `body.answer_sentence` | — | — | ターゲット適格・シャッフル列 |
| `grammar_rewrite` | `body.source_sentence` および `body.target_sentence_with_blank#filled:answer` | — | — | ターゲット適格・書き換え整合 |
| `grammar_example_selfcheck` | `body.example.en` / `body.context_sentence`（非null時） | — | — | ターゲット適格 |

日本語フィールド（語義・訳・解説）は英語の語彙照合対象ではない（検査は MC-09 の字数と MC-22 の日本語判定のみ）。

### 3.4 spaCy解析と構造制約（MC-08〜MC-12）

**MC-08（文数・2文例外整合）** 次を検査し、不成立は `V-SENT-01` とする。

1. 「文として検査」する各フィールド（`#filled:` 合成文・`context_sentence` を含む）は、`doc.sents` の文数がちょうど1でなければならない。先行文脈は `context_sentence` という独立フィールドで保持されるため、いずれのフィールドも常に1文である。
2. `context_required_by` が非nullのとき `context_sentence` も非null、`context_sentence` が非nullのとき `context_required_by` も非nullでなければならない（対の整合。`docs/json-output-spec.md` PAY-12）。
3. `context_required_by` の値は `前文が肯定平叙` または `前文が否定平叙` の2値のいずれかでなければならない（`docs/question-generation-spec.md` GEN-06 の2値制限の機械照合）。
4. `grammar_reorder` / `grammar_rewrite` に `context_sentence` フィールドは存在しない（スキーマが持たない）。他形式で宣言された文タイプが実際に先行文脈を要求するものかの判断はLLMレビュー（CHK-17）の担当である。

**MC-09（語数・字数）** 計測定義を次で固定する。

- **語数** = 対象の1文に含まれるspaCyトークンのうち、UPOSが `PUNCT` または `SYM` のトークンを除いた数。縮約の分割トークン（`do` + `n't`）は各1語と数える。所有格標識 `'s`（タグ `POS`）も1語と数える。
- **語数上限** = `limits.json` のキー `sentence_word_limits`（cefr帯別マップ。既定 A1:10 / A2:14 / B1:20 / B2:26）。文法問題はLVL-04の帯写像でcefr帯に落として上限を引く。`context_sentence` を含む2文構成の場合は合算ではなく各文に適用し、いずれかの文の超過で `V-LEN-01`。
- **字数** = 解説文字列（`explanation.text`）をNFC正規化した後の全Unicodeコードポイント数（空白・句読点を含む。前後空白の除去は行わない）。上限は `limits.json` のキー `explanation_char_limits` の `brief`（⑤⑥⑦⑧、既定200）/ `detailed`（⑨、既定400）。形式→brief/detailedの対応は `docs/question-generation-spec.md` GEN-21 が正。超過は `V-EXP-01`。語彙4形式は解説を持たない（拡張は `docs/requirements.md` V2-05）。

**MC-10（limits.jsonの参照キー）** 機械検査が参照する `limits.json` のキーは `sentence_word_limits` / `explanation_char_limits` / `distractor_reuse_max`（MC-27） / `set_question_max` の4つのみである。`machine_check.py` による`set_question_max`の参照はS1の`--requested-count`値域検査に限る。`generation_max` / `review_timeout_seconds` はオーケストレータ・対話が参照する。キーの完全な目録と既定値は `config_limits.schema.json` が正である。

**MC-11（解析器の固定）** 解析はspaCy `en_core_web_sm`（`meta.json` に記録された版と同一のインストール版）で行わなければならない。文分割は `doc.sents`（依存構造パーサに基づく既定の文分割）を使用する。パイプラインのコンポーネント無効化・差し替えをしてはならない。

**MC-12（整序検査）** `grammar_reorder` について次を検査する。

1. シャッフル提示列 `tokens_shuffled` と、正解文 `answer_sentence` から `docs/json-output-spec.md` FIN-04 と同一の決定的手順で導出したトークン列が、多重集合として一致する（並べ替え関係が成立する）。不成立は `V-ORD-01`。
2. シャッフル提示列が正解順トークン列と完全一致しない。一致は `V-ORD-02`。
3. トークンの正規化（全小文字・句読点なし）は `candidate.schema.json` のパターン制約が拒否するため機械検査の違反コードを持たない。

別解となる正しい並びが存在しないことの検証はLLM担当である（`docs/subagent-review-spec.md` CHK-14）。

### 3.5 語彙照合手順（MC-13〜MC-18）

**MC-13（照合順序）** 「文として検査」対象の各文について、トークン列を先頭から走査し、各トークンを次の順で判定しなければならない。先に一致した段階で判定は確定し、後続の段は評価しない。

1. **複数語トークン列マッチ**（MC-14）
2. **単語照合**（MC-15）
3. **allowlist照合**（MC-18）
4. **免除クラス**（MC-17）
5. いずれにも該当しない → 違反 `V-LEX-01`（辞書外語）

「語として検査」対象（選択肢トークン列・同値表記リスト）にも同一の順序を適用する。

**MC-14（複数語トークン列マッチ）** lexiconの `is_multiword = true` エントリを対象に、文のトークン列に対して左から右へ、最長一致優先・非重複で照合する。

1. 照合キー: エントリの `headword` を実行時にspaCy（en_core_web_sm、meta.json記録版）でトークン化し各トークンを小文字化した列（NRM-09。正規化データには保存せず、`machine_check.py` 起動時に全複数語エントリについて決定的に導出する）。文側は (a) 表層形の小文字列、(b) 一致しなければ各トークンのレンマの小文字列、の順で試す。
2. 同一開始位置で複数エントリが一致する場合はトークン数が最大のものを採用する。トークン数も同じ場合は `id` の辞書順で先のエントリを採用する。
3. 一致した区間の全トークンは「消費済み」となり、単語照合の対象にしない。
4. 採用エントリの `level` にLVL-09/LVL-10のレベル判定を適用し、超過は `V-LEX-02`。

**MC-15（単語照合）** 消費されていない各トークンについて:

1. 照合キー = トークンのレンマ（`token.lemma_`、MC-16の補正表適用後）を小文字化しNFC正規化した文字列。
2. MC-16の対応表からトークンのタグに対する**pos候補列**を得る。候補列の先頭から順に「headwordの小文字化NFC文字列 = 照合キー」かつ `pos = 候補` のエントリを探し、最初に見つかったエントリを採用する。
3. 候補列で見つからない場合、照合キーに一致する全エントリ（品詞不問）のうち `level` のrankが最小のものを採用し、警告 `W-POS-01`（MC-29）を発行する（品詞タグ付け誤りへの耐性。採用しても後段のレベル判定は通常どおり行う）。
4. それでもエントリが存在しない場合はMC-13の次段（allowlist）へ進む。
5. 採用エントリの `level` にLVL-09/LVL-10のレベル判定を適用し、超過は `V-LEX-02`。

**MC-16（spaCyタグ → Wordlist pos 対応表・レンマ補正表）** 単語照合のpos候補列は次表で確定する。判定は (1) レンマ補正表 → (2) レンマ優先規則 → (3) タグ表 の順で行う。表にないタグは候補列なし（MC-15の3.以降へ直行）とする。タグは `token.tag_`（Penn Treebank体系）、UPOSは `token.pos_` である。本表の変更は正規化パイプライン版（`docs/architecture.md` VER-04 の norm）のメジャー更新を伴わなければならない。

**(1) レンマ補正表**（spaCyのレンマをWordlist収録レンマへ写す決定的な置換。適用時は警告 `W-LEMMA-01` を発行する）:

| 表層形（小文字化） | 補正レンマ |
|---|---|
| `gon`（`gonna` の分割断片） | `go` |
| `na`（`gonna` の分割断片） | `to` |
| `ca`（`can't` の分割断片） | `can` |
| `wo`（`won't` の分割断片） | `will` |
| `sha`（`shan't` の分割断片） | `shall` |

**(2) レンマ優先規則**（UPOSが `VERB` または `AUX` のトークンに先立って適用）:

| 条件 | pos候補列 |
|---|---|
| レンマ = `be` | `be-verb` |
| レンマ = `do` | `do-verb` |
| レンマ = `have` | `have-verb` |

**(3) タグ表**:

| `tag_` | 追加条件 | pos候補列（優先順） |
|---|---|---|
| `NN`, `NNS` | — | `noun` |
| `NNP`, `NNPS` | — | `noun`（不一致時はallowlist照合が主経路となる。一致した場合は警告 `W-PROPN-01` を発行する） |
| `JJ`, `JJR`, `JJS` | — | `adjective` |
| `VB`, `VBP`, `VBZ`, `VBD`, `VBN`, `VBG` | レンマ優先規則非該当 | `verb` |
| `MD` | — | `modal auxiliary` |
| `RB`, `RBR`, `RBS`, `WRB` | — | `adverb` |
| `PRP`, `PRP$`, `WP`, `WP$` | — | `pronoun` |
| `DT`, `PDT`, `WDT` | — | `determiner` → `pronoun` |
| `IN` | — | `preposition` → `conjunction` |
| `CC` | — | `conjunction` |
| `CD` | 免除クラス「数値」非該当（綴り数詞） | `number` |
| `TO` | UPOS = `PART` | `infinitive-to` |
| `TO` | UPOS = `ADP` | `preposition` |
| `UH` | — | `interjection` |
| `EX` | — | `adverb` → `pronoun` |
| `RP` | — | `adverb` → `preposition` |
| `POS`, `HYPH` | — | （免除クラス。MC-17） |
| `.` `,` `:` `''` ` `` ` `-LRB-` `-RRB-` `NFP` `SYM` `$` `#` | — | （免除クラス。MC-17） |
| `FW`, `LS`, `ADD`, `XX`, `GW` | — | （候補列なし） |

この表はWordlistの品詞15種（NRM-07）を完全に被覆する（15種すべてがいずれかの行の候補列に現れる）。

**MC-17（免除クラス）** 次のトークンは照合不要の免除とする。免除区分は machine_report の `exemption_class` 4値で記録する（MC-30）。免除クラスはこの4つで全てであり、実装が独自の免除を追加してはならない。

| `exemption_class` | 判定条件 |
|---|---|
| `numeric` | 表層形が正規表現 `^[0-9]+([.,:][0-9]+)*$` または `^[0-9]+(st\|nd\|rd\|th)$`（大文字小文字不問）に一致 |
| `punct_sym_space` | UPOSが `PUNCT` または `SYM`、またはタグが `HYPH`、または空白のみのトークン |
| `possessive` | タグが `POS`（`'s` / `'`） |
| `contraction_fragment` | 縮約分割断片のうち、レンマ補正（MC-16）とレンマ化のいずれでもWordlist照合に到達し得ない痕跡トークン（該当例は原本・spaCy版に依存するため、実装はこの区分を「補正表適用後もレンマが空または記号のみになる縮約断片」に限定して適用する） |

縮約形（`n't` → レンマ `not`、`'m`/`'re` → `be`、`'ve` → `have`、`'ll` → `will`）は免除ではなく、レンマ化（および補正表）により通常の単語照合（MC-15）で解決しなければならない。

**MC-18（allowlist照合）** `data/config/proper_nouns.json` の `words` 配列（文字列配列。構造の正は `config_proper_nouns.schema.json` と `docs/json-output-spec.md` NDS-04）の各語とトークンの**表層形**を、大文字小文字を区別して完全一致で照合する。一致すれば合格（`decision = "allowlist"`）。

- allowlistの全語は空白を含まない1トークンである（スキーマのパターン `^\S+$` で強制）。複数語固有名詞はv1では登録できない（必要が生じた場合はv2課題として扱い、`docs/requirements.md` のスコープ外リスト改訂を要する）。
- allowlistの内容要件: キュレーション済み固有名詞50〜100語。選定基準は (a) 日本の中高生学習者に馴染みがある固有名詞（人名・地名・言語名・国名・祝祭名）であること、(b) 特定の宗教・政治的立場の擁護と受け取られない文化的に中立な語であること、の両方を満たすことと定める。追加・削除の運用手順は `docs/architecture.md` OPS-02 が正。生成側への同リストの提示は `docs/question-generation-spec.md` PRM-04 が正。

### 3.6 ターゲット照合と形式固有検査（MC-19〜MC-26）

**MC-19（語彙ターゲット照合）** 語彙4形式では、candidateが宣言するターゲット語彙エントリID（`target.ref`）について次を検査する。

1. lexiconに存在し、`level` = 指定レベル `L` である（LVL-12）。不一致・不存在は `V-TGT-03`。
2. 対象語出現照合（MC-07の対象フィールド）: 出現回数がちょうど1回である（Q12）。回数の定義: 単一語エントリはレンマ照合（MC-15の照合キー）でheadwordに一致したトークン数、複数語エントリはMC-14で当該エントリに消費された区間数。0回または2回以上は `V-TGT-02`。活用形（`watch` → `watched`）はレンマ一致により1回と数える。対象語として一致したトークンの `decision` は `target` と記録する（MC-30）。複数語ターゲットでは一致区間の全トークンを`target`とし、全トークンに同じ対象entry IDとlevelを記録する。`multiword_match`は非ターゲット複数語の一致区間だけに用いる。
3. `body.target_surface` が対象フィールドの部分文字列として存在する。不成立は `V-TGT-02`。
4. `vocab_mcq_ja2en`では、`body.target_surface`が対象エントリの`headword`と一致し、`body.sentence_with_blank`の`____`を`target_surface`で置換した文字列が`body.sentence_complete`と完全一致しなければならない。不成立は`V-TGT-02`。

**MC-20（文法ターゲット照合）** 文法5形式では、candidateが宣言するターゲット文法項目ID（`target.ref`）について次を検査する。

1. grammarに存在し、`target_eligible = true` である。
2. LVL-07の範囲包含 `rank(level.min) ≤ rank(L) ≤ rank(level.max)` を満たす。

いずれかの不成立は `V-TGT-01`。例文中での対象構造の実現の照合は行わない（MC-25。LLM担当）。

**MC-21（選択肢構成）** `vocab_mcq_en2ja` / `vocab_mcq_ja2en` / `grammar_mcq` について:

1. 選択肢はちょうど4個、正解指定はちょうど1個（`candidate.schema.json` でも強制されるが、検査として再確認する）。
2. 選択肢の表記（trim後の文字列比較。英語選択肢は小文字化して比較、日本語選択肢はNFC正規化して比較）に重複がない。

いずれかの不成立は `V-CHO-01`。

**MC-22（日本語フィールド検査）** 日本語であるべき必須フィールド（①の `stem_ja`・選択肢 `text`/`gloss`、②の `stem`・`sentence_ja`・`gloss`、③④の `gloss`・`example.ja`、⑤〜⑨の `example_ja`/`example.ja`/`source_ja`/`target_ja`/`instruction`/`explanation.text`）について、NFC正規化後の文字列に日本語文字（ひらがな U+3040–U+309F、カタカナ U+30A0–U+30FF、CJK統合漢字 U+4E00–U+9FFF のいずれか）が1文字も含まれない場合は `V-JPN-01` とする。訳・語義・解説の品質判定はLLM担当（CHK-08〜CHK-10）である。

**MC-23（誤答由来照合）** `vocab_mcq_en2ja` / `vocab_mcq_ja2en` の各選択肢には由来記録 `anchor`（`entry_id` / `headword` / `pos` / `level`。Q11）が必須である。各選択肢について:

1. `anchor.entry_id` がlexiconに存在し、記録された `headword` / `pos` / `level` がエントリの実値と一致する。`vocab_mcq_ja2en` では選択肢の英語表記 `text` が由来エントリの `headword` と一致する（小文字化比較）。不成立は `V-DIS-01`。
2. 誤答3肢の `anchor.level` = 指定レベル `L` である（LVL-13）。誤答の `anchor.pos` がターゲットと同一である。ただし `body.pos_pool_relaxed = true` の場合、品詞同一性検査に代えて `docs/question-generation-spec.md` GEN-15 の互換品詞群（同一群内）であることを検査する（緩和後の品詞群の妥当性の意味的判断はLLMレビューが検証する）。`pos_pool_relaxed = false` なのに品詞が不一致の場合も本項の違反である。不成立は `V-DIS-02`。
3. 誤答の由来エントリがターゲットのエントリと同一（同一 `id`）でない。4選択肢の `anchor.entry_id` が互いに異なる。正解肢の `anchor.entry_id` = `target.ref` である。不成立は `V-DIS-03`。

**MC-24（穴埋め検査）** `grammar_cloze` について:

1. `sentence_with_blank` の空欄に `answer` を代入した文字列がMC-07の完成文としてspaCy解析可能な1文である（空欄記法の正しさは `candidate.schema.json` のパターンで強制）。空欄が対象構造の実現部分を覆うことの判定はLLM担当（CHK-01）。形式不正は `V-CLZ-01`。
2. `answer_equivalents` は空配列でもよい。`answer` 自身を含んではならず、リスト内に重複（大文字小文字無視・前後空白除去後の比較）があってはならない。違反は `V-CLZ-02`。

同値リストの網羅性・過剰（誤りを含む同値）の検証はLLM担当である（CHK-15）。`grammar_rewrite` の `answer` / `answer_equivalents` にも本条2を準用する（違反コードは同じく `V-CLZ-02`）。

**MC-25（対象構造の機械照合はしない）** 機械検査は英文の文法構造の同定・レベル判定を行ってはならない。TreeTagger正規表現による機械照合は `docs/requirements.md` V2-04 である。対象構造の実現の照合は、ITEM LISTの `pattern_shorthand`（NRM-17）を根拠とするLLMレビュー（`docs/subagent-review-spec.md` CHK-01）の担当である。

**MC-26（書き換え検査）** `grammar_rewrite` について、`source_sentence` と目標文完成形（`target_sentence_with_blank#filled:answer`）を正規化（NFC・trim・小文字化・連続空白1個化）して比較し、同一である場合は `V-RWT-01`（書き換えが成立していない）。書き換え指示の明示・元文と目標文の文法的関係の検証はLLM担当である（CHK-16）。

### 3.7 セット横断検査 `set_check.py`（MC-27）

**MC-27** `set_check.py` は増分検査（確定済み問題×当該候補）または全体最終検査（CLIモードの正は `docs/architecture.md` CLI-19）として、対象の全候補について次を検査しなければならない（Q15）。違反はセット確定（`finalize_set.py`）を阻止する。再生成・差し替えの手順は `docs/subagent-review-spec.md` が正である。出力は `machine_report.schema.json`（`scope = "set"`）に適合する（MC-31）。

| コード | 検査 | 規則 |
|---|---|---|
| `V-SET-01` | 対象の重複 | 同一ターゲットID（`lex:*` または `gp:*`）が2問以上に出現してはならない |
| `V-SET-02` | 例文の使い回し | 「文として検査」対象文の正規化文字列（小文字化・連続空白1つ化・NFC）が2問以上で一致してはならない |
| `V-SET-03` | 誤答の過度な再利用 | 同一の誤答由来エントリID（`anchor.entry_id`。MC-23）がセット内で `limits.json` の `distractor_reuse_max`（既定2）を超える問数に出現してはならない |

### 3.8 machine_report の内容（MC-28〜MC-31）

**MC-28（質問スコープ違反コード目録）** `machine_check.py` が発行する違反コード（`violations[].code`）は次の19種のみである。`machine_report.schema.json` の enum と一致する。エラーコード `E-*`（CLI停止）とは別体系であり混同してはならない。

| コード | 意味 | 発行規則 |
|---|---|---|
| `V-COND-01` | セットの確定済み条件とcandidateの不一致（format・level・question_id番号上限） | GEN-02 |
| `V-SENT-01` | 文数・2文例外の不正（文数≠1・対の不整合・要求元文タイプ値不正） | MC-08 |
| `V-LEN-01` | 文の語数上限超過 | MC-09 |
| `V-EXP-01` | 解説の字数上限超過 | MC-09 |
| `V-JPN-01` | 日本語フィールド不正（日本語文字を含まない） | MC-22 |
| `V-LEX-01` | 辞書外語（Wordlist・allowlist・免除クラスのいずれにも該当しない語） | MC-13〜MC-18 |
| `V-LEX-02` | 語彙レベル超過（採用エントリのレベルが許容上限超） | LVL-09/LVL-10, MC-14/MC-15 |
| `V-TGT-01` | 対象文法項目の不適格（教員版非収録・レベル範囲外・レベルnull） | MC-20 |
| `V-TGT-02` | 対象語の出現回数不正（0回・2回以上・target_surface不整合） | MC-19 |
| `V-TGT-03` | 対象語彙の照合不一致（headword+posが指定レベルに不存在） | MC-19 |
| `V-CHO-01` | 選択肢構成不正（個数・正解数・表記重複） | MC-21 |
| `V-DIS-01` | 誤答由来の照合不一致（不存在・記録値不一致・表記不一致） | MC-23-1 |
| `V-DIS-02` | 誤答のレベル・品詞規則違反（レベル不一致・緩和記録と品詞の不整合） | MC-23-2 |
| `V-DIS-03` | 誤答由来の同一性違反（ターゲットと同一・アンカー重複・正解肢の不一致） | MC-23-3 |
| `V-ORD-01` | 整序シャッフル列の並べ替え関係不成立 | MC-12 |
| `V-ORD-02` | シャッフル列が正解順と同一 | MC-12 |
| `V-CLZ-01` | 穴埋めの空欄・完成文不正 | MC-24 |
| `V-CLZ-02` | 同値表記リスト不正（answer の重複混入・リスト内重複） | MC-24 |
| `V-RWT-01` | 書き換え不成立（元文と目標文完成形が同一） | MC-26 |

**MC-29（警告目録）** 機械検査は次の場合に verdict に影響しない警告（`warnings[]`、各要素 `{code, location, message}`）を発行しなければならない。コードは次の3種のみである。警告はレビュアー（`docs/subagent-review-spec.md` CHK-18）が誤検出調査の手がかりとして精査する。

| コード | 発行条件 |
|---|---|
| `W-POS-01` | MC-15-3 の品詞フォールバック（pos候補列で不一致となり品詞不問で採用）が発生したトークン |
| `W-PROPN-01` | タグ `NNP` / `NNPS` のトークンがallowlist照合を経ずにWordlist照合（MC-14/MC-15）で解決された場合（固有名詞らしき語が一般語として通過した疑い） |
| `W-LEMMA-01` | MC-16 のレンマ補正表を適用したトークン、およびレンマが表層形の小文字化とも一致せず照合が全段不一致（`V-LEX-01`）となったトークン（レンマ化誤りの疑い） |

**MC-30（machine_report・scope=question）** `machine_check.py` の出力は `machine_report.schema.json` の `question_report` に適合しなければならない。フィールドの意味の正は `docs/json-output-spec.md` AUD-03〜AUD-06 である。要点:

| フィールド | 内容 |
|---|---|
| `schema_version` / `data_version` / `generated_at` | 版と生成日時。`generated_at` は唯一の実行毎可変フィールド（`docs/json-output-spec.md` JS-03） |
| `scope` | `"question"` 固定 |
| `set_id` / `question_id` / `generation` / `format` / `level` | 検査対象の識別（candidateとオーケストレータ入力から転記） |
| `spacy_model` / `spacy_model_version` | `"en_core_web_sm"` 固定文字列とインストール版 |
| `verdict` | MC-02 |
| `violations[]` | `{code（MC-28の19種）, location（文字列。AUD-06のフィールドパス記法＋該当語列の引用）, evidence（採用エントリID・レベル値・計測値の引用。日本語）, expected_level（許容上限。無関係な違反はnull）, actual_level（検出レベル。同null）, suggestion（修正案。定型文でもよいが非空）}` |
| `warnings[]` | MC-29 |
| `stats` | `{"texts": [...], "explanation_char_count": <int\|null>}`。`texts[]` の各要素は `{field（AUD-06記法）, text（検査した完成文）, sentence_count, word_count（MC-09）, tokens[]}`。`tokens[]` の各要素は `{surface, lemma（MC-16補正後）, upos, tag, decision, matched_entry_id, level, exemption_class}` |

`decision` は次の6値のみ: `multiword_match`（複数語トークン列マッチで判定・消費）/ `wordlist_match`（単語照合で判定）/ `allowlist`（固有名詞allowlist合格）/ `exempt`（免除クラス。`exemption_class` を非nullで記録）/ `target`（語彙問題の対象語トークン）/ `violation`（`V-LEX-01` または `V-LEX-02` の対象トークン）。`tokens[]` はレビュアーがレンマ化誤り・タグ付け誤りを検出するための一次資料であり、省略してはならない。

**MC-31（セット横断コード目録と set_report）** `set_check.py` が発行する違反コードは `V-SET-01` / `V-SET-02` / `V-SET-03` の3種のみである（意味はMC-27）。出力は `machine_report.schema.json` の `set_report`（`scope = "set"`・`target_question_id`（増分検査の対象問題ID。全体最終検査はnull）・`checked_question_ids[]`・`verdict`・`violations[]`・`warnings[]`（常に空配列））に適合しなければならない。フィールドの意味の正は `docs/json-output-spec.md` AUD-05 である。

---

## 4. 検証マトリクスと担当区分

### 4.1 検証マトリクス（MAT-01）

**MAT-01** 全検証項目・担当・適用形式・コードを次表で確定する。担当「機械」の違反は覆せない自動不合格（MC-03）、担当「LLM」はレビュアーによる追加不合格のみ可（機械判定の上書き不可。上書きは `docs/requirements.md` V2-08 により恒久的スコープ外）。機械のコード値の正は本文書 MC-28/MC-31、LLMのコード値（`CHK-*`）の正は `docs/subagent-review-spec.md` 第3節と `schemas/review_result.schema.json` である。

形式の略記: V1=`vocab_mcq_en2ja` V2=`vocab_mcq_ja2en` V3=`vocab_flashcard_en2ja` V4=`vocab_flashcard_ja2en` G5=`grammar_mcq` G6=`grammar_cloze` G7=`grammar_reorder` G8=`grammar_rewrite` G9=`grammar_example_selfcheck`

| # | 検証項目 | 担当 | コード | V1 | V2 | V3 | V4 | G5 | G6 | G7 | G8 | G9 | 規則 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | ターゲット語彙のレベル・品詞一致 | 機械 | V-TGT-03 | ✓ | ✓ | ✓ | ✓ | — | — | — | — | — | MC-19 |
| 2 | 対象語の例文中ちょうど1回出現 | 機械 | V-TGT-02 | ✓ | ✓ | ✓ | ✓ | — | — | — | — | — | MC-19 |
| 3 | ターゲット文法項目の適格性 | 機械 | V-TGT-01 | — | — | — | — | ✓ | ✓ | ✓ | ✓ | ✓ | MC-20 |
| 4 | 例文中の全文法構造のレベル（level_source付き列挙） | LLM | CHK-03 | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | LVL-08/LVL-11, 第5章 |
| 5 | 例文語彙のレベル・辞書外語（allowlist・免除除く） | 機械 | V-LEX-01/02 | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | MC-13〜MC-18 |
| 6 | 対象文法構造の実現（パターン略記照合） | LLM | CHK-01 | — | — | — | — | ✓ | ✓ | ✓ | ✓ | ✓ | MC-25, `docs/subagent-review-spec.md` |
| 7 | 文数・2文例外の整合 | 機械 | V-SENT-01 | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | MC-08 |
| 8 | 文の語数上限 | 機械 | V-LEN-01 | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | MC-09 |
| 9 | 解説字数・日本語フィールドの形式 | 機械 | V-EXP-01/V-JPN-01 | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | MC-09, MC-22 |
| 10 | 選択肢の構成・重複 | 機械 | V-CHO-01 | ✓ | ✓ | — | — | ✓ | — | — | — | — | MC-21 |
| 11 | 語彙誤答の質（同義語・区別不能・排除知識） | LLM | CHK-06 | ✓ | ✓ | — | — | — | — | — | — | — | Q11, `docs/subagent-review-spec.md` |
| 12 | 文法誤答の成立性（パラダイム内・不成立・排除知識） | LLM | CHK-07 | — | — | — | — | ✓ | — | — | — | — | Q11, 同上 |
| 13 | 正解の一意性 | LLM | CHK-05 | ✓ | ✓ | — | — | ✓ | ✓ | — | ✓ | — | 同上 |
| 14 | 整序のシャッフル束縛 | 機械 | V-ORD-01/02 | — | — | — | — | — | — | ✓ | — | — | MC-12 |
| 15 | 整序: 別解となる正しい並びの不存在 | LLM | CHK-14 | — | — | — | — | — | — | ✓ | — | — | 同上 |
| 16 | 穴埋めの空欄・同値リスト形式 | 機械 | V-CLZ-01/02 | — | — | — | — | — | ✓ | — | ✓ | — | MC-24 |
| 17 | 穴埋め同値表記リストの網羅性・過剰 | LLM | CHK-15 | — | — | — | — | — | ✓ | — | — | — | MC-24, 同上 |
| 18 | 書き換えの機械整合（元文≠目標文） | 機械 | V-RWT-01 | — | — | — | — | — | — | — | ✓ | — | MC-26 |
| 19 | 書き換え指示の明確さ・元文と目標文の文法的関係 | LLM | CHK-16 | — | — | — | — | — | — | — | ✓ | — | 同上 |
| 20 | 日本語訳・語義の質 | LLM | CHK-08 | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | Q13, 同上 |
| 21 | 誤答語義が正解語の別義と重ならないこと | LLM | CHK-06（手順2） | ✓ | ✓ | — | — | — | — | — | — | — | Q13, 同上 |
| 22 | ④訳文からの英文復元可能性 | LLM | CHK-09 | — | — | — | ✓ | — | — | — | — | — | Q13, 同上 |
| 23 | セット横断（重複・使い回し・誤答再利用） | 機械 | V-SET-01/02/03 | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | MC-27 |
| 24 | 解説の内容要件・文体・用語 | LLM | CHK-10 | — | — | — | — | ✓ | ✓ | ✓ | ✓ | ✓ | Q24, 同上 |
| 25 | 英文の自然さ | LLM | CHK-11 | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | 同上 |
| 26 | 学習上の適切さ（内容の中立性・教育的妥当性） | LLM | CHK-12 | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | 同上 |
| 27 | 指定レベル超の前提知識の不要性 | LLM | CHK-13 | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | 同上 |
| 28 | セット確定条件と候補の一致 | 機械 | V-COND-01 | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | GEN-02 |

**MAT-02（網羅と追加不合格）** LLM担当の全項目は `docs/subagent-review-spec.md` 第3節のチェックリスト（CHK-01〜CHK-19）で網羅されなければならない（対応表は同文書3.0節）。レビュアーは本表のLLM担当項目と同文書の追加チェック（CHK-02・CHK-17・CHK-19）についてのみ不合格を追加でき、機械担当項目の再判定・上書きをしてはならない。

**MAT-03（レベル系違反の根拠）** レビュアーは CHK-03 の違反（例文文法構造のレベル超過）に必ず `level_source`（第5章）を伴う根拠を記録しなければならない。記録様式は `docs/subagent-review-spec.md` RR-02〜RR-04 が正である。

### 4.2 違反コード目録の所在（MAT-04）

**MAT-04** コード値の正の所在を次のとおり固定する。いずれの文書もこれを再定義・追加・変更してはならない（変更は当該正文書とスキーマの同時改版による）。

| 体系 | 値 | 正 |
|---|---|---|
| 機械検査（1問） | MC-28 の19種 | 本文書 MC-28 と `schemas/machine_report.schema.json` |
| 機械検査（警告） | MC-29 の3種 | 本文書 MC-29 と同スキーマ |
| 機械検査（セット横断） | `V-SET-01`〜`V-SET-03` | 本文書 MC-27/MC-31 と同スキーマ |
| LLMレビュー | `CHK-01`〜`CHK-19`（violationは CHK-18 を除く） | `docs/subagent-review-spec.md` 第3節と `schemas/review_result.schema.json` |
| CLI停止エラー | `E-ENV-*` / `E-DATA-*` / `E-CONTRACT-*` / `E-INPUT-*` | `docs/architecture.md` 第6節 |

---

## 5. level_source規則（Q19）

**LS-01** レビュアーは、例文（および完成文・元文・目標文）中に認定した各文法構造について、`level_source` を必ず付与しなければならない。値は次の2値のみである（語彙照合の根拠表記は `wordlist` であり、`level_source` の値域には含まれない）。

| 値 | 意味 | 必須の根拠 |
|---|---|---|
| `kyoinban` | 教員版由来のレベル（正規化データの `level.source` が `kyoinban_direct` または `kyoinban_inherited` の項目） | 文法項目ID（`gp:<ID>`）と `kyoinban.level_raw` の引用。継承の場合は継承元親ID（`inherited_from`）を併記 |
| `reviewer_estimate` | 教員版・継承で得られないレベルのレビュアー推定 | CEFR-J準拠の推定レベル（cefrj値）と推定根拠の記述（自由文。`efl` 傍証を引用してもよい） |

**LS-02** `kyoinban` の判定はLVL-08の規則（`level.min` と許容上限のrank比較）に従わなければならない。

**LS-03** `reviewer_estimate` の判定は、推定した**導入レベル**を `level.min` とみなしてLVL-08と同一の比較を行い、許容上限を超えるなら当該問題を不合格（`CHK-03` の violation）としなければならない。推定に `level.max` 相当の値を導入してはならない。

**LS-04** 正規化データの `efl`（NRM-26）はレビュアーへの提示用傍証である。傍証のみを根拠にレベルを機械決定してはならず、最終判定は常にレビュアーの構造化された記述根拠を伴わなければならない。

**LS-05** 原本根拠の判定（`kyoinban`）と推定の判定（`reviewer_estimate`）は、レビュー結果内で常に区別可能でなければならない。集計・表示の様式は `docs/subagent-review-spec.md` と `docs/json-output-spec.md` が正である。

**LS-06** ターゲット項目としての使用は教員版256項目に限る（LVL-07）。`reviewer_estimate` はターゲット選定に使用してはならず、文脈検証にのみ使用しなければならない。

---

## 6. 合格例と不合格例

本章の例は規範の説明用である。candidateの物理フィールド名は `docs/json-output-spec.md` の確定値に従うこと。例中の `gp:` ID・教員版レベル値のうち「仮値」と明記したものは説明用であり、実装・テストフィクスチャでは正規化データの実値を使用しなければならない（フィクスチャの正は `docs/testing-and-acceptance.md`）。

### 6.1 合格例（機械検査・語彙A1）

条件: `format = vocab_flashcard_en2ja`、`level_scale = cefr`、`level = A1`、ターゲット `lex:book:noun`（A1・noun）。例文: `These are my books.`

トークン照合結果（`stats.texts[].tokens` の抜粋列）:

| surface | lemma | tag | decision | matched_entry_id | level | 判定 |
|---|---|---|---|---|---|---|
| These | these | DT | wordlist_match | lex:these:determiner | A1 | 合格（A1 ≤ A1） |
| are | be | VBP | wordlist_match | lex:be:be-verb | A1 | 合格 |
| my | my | PRP$ | wordlist_match | lex:my:pronoun | A1 | 合格 |
| books | book | NNS | target | lex:book:noun | A1 | 合格・対象語1回目 |
| . | . | . | exempt（punct_sym_space） | null | null | 免除 |

構造制約: 文数1で合格。語数4 ≤ 10 で合格。対象語出現1回で合格。`verdict = "pass"`。この候補は続いて独立LLMレビュー（文法構造 be動詞+指示代名詞の `level_source = kyoinban` 判定、訳・自然さ・学習適切性）に進む。

### 6.2 不合格例A（機械検査・語彙レベル超過）

条件: `format = grammar_mcq`、`level_scale = cefrj`、`level = A1.2`（帯 = A1）、ターゲット `gp:1`（人称代名詞主格(I)+be、教員版 `A1.1-A1.2`、LVL-07により適格）。完成文: `I am ready to abandon the plan.`

`abandon` はレンマ照合で `lex:abandon:verb`（B1）に一致する。帯A1に対し `rank(B1)=3 > rank(A1)=1` で `V-LEX-02`。machine_reportの違反記録（`machine_report.schema.json` 適合形）:

```json
{
  "code": "V-LEX-02",
  "location": "body.sentence_with_blank#filled:answer token 4: \"abandon\"",
  "evidence": "採用エントリ lex:abandon:verb（Wordlist B1）。許容上限は指定レベルA1.2の帯 A1（LVL-09）",
  "expected_level": "A1",
  "actual_level": "B1",
  "suggestion": "A1帯の動詞（例: lex:stop:verb A1）への置換、または文の再生成"
}
```

`verdict = "fail"`。MC-03によりレビューはこの判定を覆せず、この違反はそのまま再生成入力に渡される（受け渡しは `docs/subagent-review-spec.md`）。

### 6.3 不合格例B（ゴールデンケース: A1のthese + 関係節、LLMレビュー）

条件: `format = vocab_mcq_en2ja`、`level_scale = cefr`、`level = A1`、ターゲット `lex:these:pronoun`（品詞は説明用の仮値）。例文: `These are the pictures that my sister took in Kyoto.`

**機械検査は合格する**: `pictures`→`lex:picture:noun`(A1)、`took`→レンマ`take`(A1)、`that`→タグ`WDT`で候補列 `determiner → pronoun` により照合、`Kyoto`→allowlist（`proper_nouns.json` の `words` に収録）。全語A1以下、辞書外語なし、語数9 ≤ 10、対象語1回。`verdict = "pass"`。

**LLMレビューは不合格にしなければならない**: 例文は関係代名詞（目的格）による関係節を含む。この構造は教員版に収録されており、その導入レベル（例中では `A2.2` の仮値で示す。実値は正規化データによる）は語彙問題A1の許容上限 `ceiling(A1) = A1.3`（LVL-04/LVL-11）を超える。よって `CHK-03` の violation である。レビュアーの違反記録（記録様式の正は `docs/subagent-review-spec.md`・`schemas/review_result.schema.json`）:

```json
{
  "code": "CHK-03",
  "location": "body.stem: \"the pictures that my sister took\"",
  "evidence": "level_source=kyoinban: gp:<関係代名詞(目的格)の実ID>（教員版 level_raw=\"A2.2-B1.2\"〔仮値〕）。導入レベルA2.2 > 許容上限A1.3（LVL-11）",
  "expected_level": "A1.3",
  "actual_level": "A2.2",
  "suggestion": "関係節を除去し単文化する（例: These are my sister's pictures.）"
}
```

この例は手動受け入れチェックリストのゴールデンケースであり、必ず不合格にならなければならない（`docs/testing-and-acceptance.md` A-07）。

### 6.4 不合格例C（reviewer_estimateによる不合格）

条件: `format = vocab_flashcard_en2ja`、`level = A1`。例文中に、教員版・継承のいずれからもレベルが得られない構造（例: LVL-14の `gp:47` so+形容詞+a/an+名詞に相当する `so big a dog`）が現れた場合、レビュアーは `level_source = reviewer_estimate` で導入レベルを推定し（`efl` の相対頻度分布を傍証にできる）、推定導入レベルが `A1.3` を超えるならLS-03により `CHK-03` の violation で不合格としなければならない。推定根拠の記述を省略した判定は無効であり、レビュー結果のスキーマ検証（`review_result.schema.json`）で拒否される。

---

## 7. v2課題の参照

本文書に関係するv2課題（`docs/requirements.md` のスコープ外リストが正）: TreeTagger正規表現による対象構造の機械照合（MC-25、V2-04）、語彙問題への解説拡張（MC-09、V2-05）、レビューによる機械検査判定の上書き（MC-03、V2-08）。本文書はこれらを実装対象から除外する。
