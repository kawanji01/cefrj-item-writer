# テストと受け入れ仕様（docs/testing-and-acceptance.md）

## 冒頭ブロック

- **目的**: 本プロジェクトの3層テスト（第1層=決定的CI、第2層=フィクスチャ・リプレイ、第3層=手動受け入れ）の対象・様式・合否条件・資産管理を、実装担当（Codex GPT-5.6 sol）が追加判断なしで実装・実施できる粒度で定義する。
- **対象読者**: 実装担当（Codex GPT-5.6 sol）、リリース実施者（教師・開発者）、レビュー担当。
- **参照文書**:
  - `docs/requirements.md`（機能・非機能要件、スコープ外/v2リストの正）
  - `docs/architecture.md`（CLI契約一覧・エラーコード目録の正・運用手順）
  - `docs/cefrj-validation-spec.md`（レベル体系・正規化仕様・機械検査仕様・検証マトリクスの正）
  - `docs/subagent-review-spec.md`（レビュアー契約・再生成ループ・監査ファイル配置の正）
  - `docs/question-generation-spec.md`（9形式の生成仕様・JSON例の正）
  - `docs/json-output-spec.md`（set.json・監査ファイル・ID規則の正）
  - `docs/html-output-spec.md`（HTML生成器契約・画面UI・印刷CSSの正）
  - `docs/cross-agent-compatibility.md`（コア/アダプタ構造・互換性保証範囲の正）
  - `docs/interaction-flow.md`（対話状態機械の正）
  - `schemas/`（JSON Schema 9本）
  - `IMPLEMENTATION_PLAN.md`（実装マイルストーン）
- **規範語彙凡例**: 「しなければならない(MUST)」=絶対要件。「してはならない(MUST NOT)」=絶対禁止。「すべきである(SHOULD)」=正当な理由がない限り従う。「してもよい(MAY)」=任意。
- **この文書が「正」とする範囲**: 3層テストの構成と実施規則、決定的CIのテスト対象一覧（テストID）、リプレイシナリオ一覧、ゴールデン・フィクスチャの保存場所・様式・更新手順、手動受け入れチェックリストの全項目と合否判定規則。検証規則そのもの（何が違反か）の正は `docs/cefrj-validation-spec.md` と `docs/subagent-review-spec.md` であり、本文書はそれらを「テストとしてどう確かめるか」に限って定義する。エラーコードの目録は `docs/architecture.md` が正である。

> 注: 本文書は他文書を「文書名＋その文書が正とする節の主題」で参照する。参照先の文書内規則IDが確定した後、参照を `docs/xxx.md の VAL-03` 形式へ置換してもよい（MAY）。置換は参照先の変更を伴わないため軽微修正として扱う。

---

## 1. 総則

- **TST-01**: テストは次の3層で構成しなければならない(MUST)。
  1. **第1層 決定的CI**（pytest）: LLMを一切呼ばず、同一入力から同一結果が得られる検査のみを対象とする。
  2. **第2層 フィクスチャ・リプレイ**（pytest）: LLM呼び出し境界を記録済みJSONで置換し、再生成ループ・合否集計・監査配置の制御ロジックをLLM抜きで検証する。
  3. **第3層 手動受け入れ**: 実LLMを使い、リリース時にチェックリスト（第5節）を人手で実施する。
- **TST-02**: 第1層・第2層のテストコードは `tests/unit/`・`tests/replay/` に置き、`pytest tests/unit tests/replay` で全件実行できなければならない(MUST)。
- **TST-03**: 第1層・第2層のテストは実行中に外部ネットワークへアクセスしてはならない(MUST NOT)。spaCyモデルはセットアップ済み環境を前提とする（前提未充足は `doctor.py` が検出する。`docs/architecture.md` のCLI契約参照）。
- **TST-04**: 第1層・第2層のテストは乱数シード非固定の乱数を使用してはならない(MUST NOT)。乱数が必要なテストはシードを固定値でコードに明記しなければならない(MUST)。
- **TST-05**: 第1層・第2層の全テスト通過をリポジトリのマージ条件としなければならない(MUST)。リリースタグ作成前には第1層・第2層の全通過に加えて第3層の全項目passが必要である（第5節・第6節）。
- **TST-06**: LLMの出力内容そのもの（生成された英文の質・レビュー判定の言語表現）は第1層・第2層の検証対象にしてはならない(MUST NOT)。LLM出力の同一性は互換性保証の範囲外である（`docs/cross-agent-compatibility.md` の互換性保証範囲参照）。
- **TST-07**: 本文書に現れる所要時間は参考目標であり、合否条件にしてはならない(MUST NOT)。合否は正しさのみで判定する。
- **TST-08**: テストIDは本文書の目録が正であり、実装のテスト関数名・docstringに対応するテストIDを記載しなければならない(MUST)。1テストIDを複数テスト関数に分割してもよい(MAY)が、その場合すべての関数に同一IDを記載する。

---

## 2. 第1層: 決定的CIテスト

### 2.1 実行契約

- **CI-R-01**: 第1層テストは `machine_check.py` / `build_normalized.py` / `validate.py` / `set_check.py` / `finalize_set.py` / `build_html.py` / `doctor.py` / `lookup.py` を、実装内部関数の直接呼び出しではなくCLI契約（`docs/architecture.md` のCLI契約一覧）どおりのプロセス起動で検証するテストを、各CLIにつき少なくとも1件含まなければならない(MUST)。それ以外のテストは内部関数を直接呼び出してもよい(MAY)。
- **CI-R-02**: 「バイト一致」と記載した合否条件は、出力ファイルまたはstdoutのバイト列の完全一致を意味する。ただし `machine_check.py` の出力比較に限り、`machine_report.schema.json` が実行日時として定義するフィールドを除去した後のバイト一致とする（除去対象フィールド名の正は `schemas/machine_report.schema.json` の日本語description）。
- **CI-R-03**: テストが使う入力は第4節のフィクスチャ・ゴールデンに限らなければならない(MUST)。テストコード内へのJSON直書きは、スキーマ不当例（CI-SCH-03）の必須欠落・型不正の生成に限り許可する(MAY)。

### 2.2 テスト対象一覧: 正規化（CI-NRM群）

規則の正: `docs/cefrj-validation-spec.md` の正規化仕様。

| テストID | 検査対象 | 入力 | 合否条件 |
|---|---|---|---|
| CI-NRM-01 | `build_normalized.py` の決定性 | `data/source/` の原本xlsx | 2回連続実行し、`lexicon.json`・`grammar.json`・`meta.json` がそれぞれバイト一致すること |
| CI-NRM-02 | 正規化ゴールデン（チェックサム固定） | コミット済み `data/normalized/` 3ファイル | 各ファイルのSHA-256が `tests/golden/normalized/checksums.json` の値と一致すること |
| CI-NRM-03 | 件数不変条件（`docs/cefrj-validation-spec.md` NRM-31 と同一の定義を共有する） | `data/normalized/` 3ファイル | `entries`（ALL_sep由来）=7,988、`entries` のレベル別度数 A1=1,200 / A2=1,443 / B1=2,486 / B2=2,859、`(headword, pos)` ユニーク数=7,988、原本ALL行数=7,801、`groups` の全要素の `member_ids` が2件以上（`groups` 総数は初回ビルド時に実測し CI-NRM-02 のチェックサムゴールデンで固定する）、文法項目数=教員版256・ITEM LIST 501、全枝番IDの親IDが存在、教員版レベル未付与16件のIDが `36,47,48,52,80,83,94,96,98,115,130,191,225,226,227,238` と一致すること |
| CI-NRM-04 | 正規化データのスキーマ適合 | `data/normalized/lexicon.json`・`grammar.json` | `validate.py` で `normalized_lexicon.schema.json`・`normalized_grammar.schema.json` に合格すること |
| CI-NRM-05 | 枝番のレベル継承 | `data/normalized/grammar.json` | `gp:1-1`・`gp:1-2`・`gp:1-3` のレベルが `gp:1` のレベルと一致すること（継承規則の正は `docs/cefrj-validation-spec.md`） |
| CI-NRM-06 | 原本チェックサム不一致の検出 | 1バイト改変した原本xlsxのコピー（テスト一時ディレクトリ） | `build_normalized.py` および `doctor.py` が処理を拒否し、`docs/architecture.md` のエラーコード目録に定義された E-DATA 系コードで停止すること |
| CI-NRM-07 | 教員版レベル値の解釈 | `data/normalized/grammar.json` | 単一値152項目・範囲値104項目が下限・上限フィールドに分解されて保持され、単一値は下限=上限であること |

### 2.3 テスト対象一覧: 機械検査（CI-MCH群）

規則の正: `docs/cefrj-validation-spec.md` の機械検査仕様。入力は `tests/fixtures/candidates/` の候補フィクスチャ（第4節）。違反コードの期待値は各フィクスチャの `index.json` に記録する。

| テストID | 検査対象 | 入力（フィクスチャ要件） | 合否条件 |
|---|---|---|---|
| CI-MCH-01 | 語数上限違反の検出 | A1語彙候補、例文が句読点除き11トークン | verdict `fail`、`violations[]` に語数上限違反（`limits.json` のA1上限10超過）が含まれること |
| CI-MCH-02 | 語数上限の境界 | A1語彙候補、例文が句読点除きちょうど10トークン | 語数上限違反が `violations[]` に含まれないこと |
| CI-MCH-03 | 辞書外語違反の検出 | 例文にWordlist非収録かつallowlist外の語（`Helsinki`）を含む候補 | verdict `fail`、当該語を `location` に持つ辞書外語違反が含まれること |
| CI-MCH-04 | allowlist免除 | 例文に `data/config/proper_nouns.json` 収録語のみを辞書外語として含む候補 | 辞書外語違反が含まれないこと |
| CI-MCH-05 | 機械的免除（数字・記号・句読点・縮約） | 例文に数字・記号・句読点・縮約形（`can't` 系）を含む候補 | これらを理由とする違反が含まれず、縮約はレンマ展開されて照合されること |
| CI-MCH-06 | 語彙レベル超過の検出 | A1語彙候補、例文にB1語 `abandon`（verb）を含む | verdict `fail`、`abandon` を `location` に持ち `expected_level`=A1・`actual_level`=B1 の違反が含まれること |
| CI-MCH-07 | 対象語ちょうど1回出現 | (a)対象語0回 (b)対象語2回 (c)活用形で1回（レンマ一致） の3候補 | (a)(b)は verdict `fail`、(c)は当該違反なし |
| CI-MCH-08 | 複数語見出しのトークン列マッチ | 対象が複数語見出し `CD player`（noun）である候補（例文に `CD player` を含む。語彙エントリIDの表記は `docs/json-output-spec.md` のID規則が正） | トークン列マッチが単語照合より先に適用され、`CD`・`player` 単体の辞書外・レベル違反が発生しないこと |
| CI-MCH-09 | spaCy POS→pos15種対応表 | 対応表（`docs/cefrj-validation-spec.md` の対応表）の全行 | 各spaCyタグの入力トークンが対応表どおりのWordlist posに写像されること（対応表の全行を網羅） |
| CI-MCH-10 | 誤答由来の機械照合 | 誤答の `headword`+`pos`+`level` が正規化データと矛盾する語彙4択候補 | verdict `fail`、由来照合違反が含まれること |
| CI-MCH-11 | 誤答プール規則と緩和記録 | (a)同レベル・同品詞誤答で緩和記録なし (b)品詞緩和済みで緩和事実の記録あり (c)品詞不一致なのに緩和記録なし の3候補 | (a)(b)は当該違反なし、(c)は verdict `fail` |
| CI-MCH-12 | machine_reportのスキーマ適合 | 任意の候補フィクスチャ1件 | M2では`machine_check.py`のstdout出力がjsonschemaライブラリの直接検証で`machine_report.schema.json`に合格すること。M3完成後は`validate.py --schema machine_report`でも再確認すること |
| CI-MCH-13 | 2文例文の条件 | (a)先行文脈要求の文タイプ記録付き2文候補 (b)記録なし2文候補 | (a)は当該違反なし、(b)は verdict `fail` |
| CI-MCH-14 | 整序シャッフルの非同一性 | シャッフル提示順が正解順と同一の `grammar_reorder` 候補 | verdict `fail`、シャッフル同一違反が含まれること |
| CI-MCH-15 | 出力の決定性 | 任意の候補フィクスチャ1件 | 2回実行の出力がCI-R-02の意味でバイト一致すること |
| CI-MCH-16 | セット確定条件と候補の一致 | 同一の適合candidateに対し、(a)format・level・question_id番号が期待条件内 (b)format不一致 (c)level不一致 (d)N=3で補充ID`q04` (e)N=3で試行上限超過ID`q07`。加えてNが大きい場合も上限は`q20` | (a)(d)は`V-COND-01`なし、(b)(c)(e)はverdict `fail`かつ該当フィールドをlocationに持つ`V-COND-01`が含まれること。依頼数に対する欠問、初期スロットと補充IDの割当、全試行2N以下の立証はfinalizeの責務であり本テストに含めない |
| CI-MCH-17 | 期待レベル基準の全件列挙 | (a)candidateはB1語彙フラッシュカード・対象`abandon`・11語以上、期待A1 (b)candidateでは適格だが期待文法レベルでは不適格な文法対象 (c)candidateレベルにだけ一致する語彙4択誤答アンカー | scaleが同じ場合は全て期待レベル基準で判定し、(a)は`V-COND-01`と`V-LEN-01`・`V-LEX-02`・`V-TGT-03`、(b)は`V-COND-01`と`V-TGT-01`、(c)は`V-COND-01`と`V-DIS-02`を同一レポートに列挙すること。format不一致でscaleが異なる場合は候補scaleの検査を継続すること |
| CI-MCH-18 | candidate JSON整数の決定的上限 | トップレベルの余分フィールド値に(a)4,300桁 (b)4,301桁 (c)5,000桁の整数を含むcandidate JSON。(c)は`PYTHONINTMAXSTRDIGITS=4300|0`で同一入力を実行 | (a)は整数桁数を理由とする`E-INPUT-03`にならずスキーマ検証へ進む。(b)(c)は対象・行・列・上限4,300・実測桁数付き`E-INPUT-03`。(c)の2環境はエラーJSONがバイト一致すること |

### 2.4 テスト対象一覧: lookup（CI-LKP群）

規則の正: `docs/interaction-flow.md` の明示指定照合フロー、`docs/architecture.md` のCLI契約。

| テストID | 検査対象 | 入力 | 合否条件 |
|---|---|---|---|
| CI-LKP-01 | レベル照合 | (a) `--headword abandon`（レベル指定なし）で照会 (b) `--headword abandon --level A1` で照会 | (a)は収録全品詞のエントリ（verb/B1 を含む各 `headword`+`pos`+`level`）が `matches` に返ること。(b)は `total`=0・`matches` 空配列・終了コード0が返ること（レベル不一致の指摘文言の組み立てはエージェント側の責務であり、`docs/interaction-flow.md` IF-17〜IF-20 に従う） |
| CI-LKP-02 | 辞書外判定 | `Tokyo` を照会 | Wordlist非収録の判定が返ること |
| CI-LKP-03 | 多品詞の曖昧性 | `watch` を品詞指定なしで照会 | 収録されている全品詞の候補（各 `headword`+`pos`+`level`）が返ること |
| CI-LKP-04 | 文法項目照会 | `gp:13` と枝番 `gp:1-1` を照会 | 教員版レベル・文法項目(平易版)・パターン略記が返り、枝番は親のレベルを継承していること |

### 2.5 テスト対象一覧: スキーマ（CI-SCH群）

規則の正: `schemas/`（9本）、`docs/json-output-spec.md`。

| テストID | 検査対象 | 入力 | 合否条件 |
|---|---|---|---|
| CI-SCH-01 | スキーマ自体の妥当性 | `schemas/` の9ファイル | 各ファイルがJSON Schema draft 2020-12のメタスキーマに適合し、`$id` が `https://cefr-j-agents.local/schemas/<name>/<semver>` 形式であること |
| CI-SCH-02 | 妥当例の合格 | 9スキーマそれぞれの妥当例フィクスチャ各1件以上（`set.schema.json` の妥当例は `tests/golden/sets/` の9ファイルを兼用する） | `validate.py` が終了コード0で合格を返すこと |
| CI-SCH-03 | 不当例の不合格 | 9スキーマそれぞれの不当例各3件以上（必須欠落・型不正・additionalProperties違反を各1件以上） | `validate.py` が E-CONTRACT 系コードで不合格を返し、違反パスを報告すること |
| CI-SCH-04 | format判別共用体 | 9形式コード（`vocab_mcq_en2ja` / `vocab_mcq_ja2en` / `vocab_flashcard_en2ja` / `vocab_flashcard_ja2en` / `grammar_mcq` / `grammar_cloze` / `grammar_reorder` / `grammar_rewrite` / `grammar_example_selfcheck`）それぞれの妥当ペイロード、および `format` と不整合なペイロード1件 | 9件は合格、不整合は E-CONTRACT 系で不合格になること |
| CI-SCH-05 | ID書式 | `set_id`・`question_id`・世代・語彙/文法エントリIDの妥当値と不当値（`set_id` が `^\d{8}-\d{6}-[a-z0-9]{4}$` に不一致、`question_id` が `q21`、世代が `gen4`、を含む） | 妥当値は合格、不当値は不合格になること |

### 2.6 テスト対象一覧: セット横断・原子的確定（CI-SET群）

規則の正: `docs/cefrj-validation-spec.md` の検証マトリクス（セット横断検査項目）、`docs/subagent-review-spec.md` の監査ファイル配置、`docs/json-output-spec.md` の監査ファイル仕様。

| テストID | 検査対象 | 入力 | 合否条件 |
|---|---|---|---|
| CI-SET-01 | 対象重複の検出 | 同一対象（同一 `lex:` ID）が2問に現れるセット状態フィクスチャ | `set_check.py` が重複違反を報告すること |
| CI-SET-02 | 例文使い回しの検出 | 2問が同一例文を持つセット状態フィクスチャ | `set_check.py` が使い回し違反を報告すること |
| CI-SET-03 | 誤答の過度な再利用の検出 | 同一誤答語の再利用が閾値（`docs/cefrj-validation-spec.md` の検証マトリクスが定める値）を超えるセット状態フィクスチャ | `set_check.py` が再利用違反を報告すること |
| CI-SET-04 | 原子的確定 | (a)全問合格のセット状態 (b)不合格問題が残るセット状態 (c)固定一時名のシンボリックリンクと同一set_idへの並行finalize | (a)は `finalize_set.py` が `output/<set_id>/set.json` を作成しスキーマ合格、(b)は `set.json` を作成せず終了コード非0で停止し、監査ファイルのみが残ること。(c)はリンク先を変更せず、並行処理のちょうど1件だけが成功し、他方はE-CONTRACT-05となり、成功した`set.json`を変更しないこと |
| CI-SET-05 | 監査ファイル命名・配置 | (a)の確定済み出力 | `review/<question_id>.<gen>.candidate.json` / `.machine.json` / `.request.json` / `.review.json` および補助監査ファイル（`docs/json-output-spec.md` ID-07 の目録）の命名規則に合致するファイルのみが存在し、`set.json` からの相対参照が全て解決すること |
| CI-SET-06 | 正本の内容制約 | (a)の確定済み `set.json` | 合格問題のみが収録され、`question_id` が昇順・一意であり（本フィクスチャ(a)は欠番なしのため `q01` からの連番となる。減数時の欠番は `docs/json-output-spec.md` ID-02/SET-03 により許容される）、`schema_version`・セットメタデータ・原本参照・設定スナップショット・`data_version`＋原本チェックサム・`attribution` の全必須ブロックが存在すること |

### 2.7 テスト対象一覧: HTML生成（CI-HTM群）

規則の正: `docs/html-output-spec.md`。

| テストID | 検査対象 | 入力 | 合否条件 |
|---|---|---|---|
| CI-HTM-01 | 生成の決定性 | `tests/golden/sets/` の任意の1ファイル | `build_html.py` を2回実行し、出力HTMLがバイト一致すること |
| CI-HTM-02 | ゴールデン一致（9形式） | `tests/golden/sets/<format>.set.json`（9ファイル） | 生成HTMLが `tests/golden/html/<format>.html` とそれぞれバイト一致すること |
| CI-HTM-03 | 自己完結性 | CI-HTM-02の生成HTML9件 | リソース取得を伴う参照（`src` 属性・`link` 要素の `href`・CSS内 `url()`・`@import`）に `http://`・`https://` のURLが1件も存在しないこと（フッター出典のURL文字列表示・ハイパーリンクは検査対象外。正は `docs/html-output-spec.md` のフッター出典仕様） |
| CI-HTM-04 | 選択肢順序の固定 | 4択形式のゴールデンset.json（`vocab_mcq_en2ja`・`vocab_mcq_ja2en`・`grammar_mcq`） | HTML内の選択肢DOM順が `set.json` の選択肢配列順と一致し、HTML内スクリプトに選択肢並び替え処理が存在しないこと（検査方法の正は `docs/html-output-spec.md` の決定性要件） |
| CI-HTM-05 | schema_versionメジャー不一致の拒否 | `schema_version` のメジャーを1繰り上げた `set.json` フィクスチャ | `build_html.py` が E-CONTRACT 系コードで拒否し、HTMLを出力しないこと |
| CI-HTM-06 | 穴埋め同値リストの埋め込み | `grammar_cloze` のゴールデンset.json | `set.json` の正答同値表記リストの全要素がHTML内の判定用データに含まれること（判定ロジック自体の動作確認は第5節 A-04） |

### 2.8 テスト対象一覧: CLI契約・互換・doctor（CI-CLI群）

規則の正: `docs/architecture.md` のCLI契約一覧・エラーコード目録、`docs/cross-agent-compatibility.md` の互換テスト。

| テストID | 検査対象 | 入力 | 合否条件 |
|---|---|---|---|
| CI-CLI-01 | 入力不正時の停止 | 全8 CLI に対し (a)必須引数欠落 (b)存在しないファイルパス (c)JSONとして不正なstdin（stdinを取るCLIのみ） | 各CLIが `docs/architecture.md` の目録に定義された E-INPUT / E-CONTRACT 系コードと日本語対処手順を出力し、定義済み終了コードで停止すること |
| CI-CLI-02 | 互換一致（機械検査） | `tests/fixtures/candidates/compat/` の互換用候補フィクスチャ一式 | `machine_check.py` の出力が `tests/golden/machine/` のゴールデンとCI-R-02の意味でバイト一致すること（ホストツール・OSに依存しない） |
| CI-CLI-03 | doctor診断 | (a)完全な環境 (b)`data/normalized/` 欠落 (c)チェックサム不一致 (d)`data/config/limits.json` 欠落 を模擬した一時環境 | (a)は終了コード0、(b)(c)(d)はそれぞれ目録に定義された E-ENV / E-DATA 系コードで停止すること |
| CI-CLI-04 | 中断セットの残置状態 | `finalize_set.py` 未実行のセット作業ディレクトリフィクスチャ | `output/<set_id>/` に `set.json` が存在せず監査のみが残ること、および `validate.py --set-dir output/<set_id>` が終了コード0・stderrなしで `status=incomplete`、`set_json_path=null`、`validation=null` を返すこと |

---

## 3. 第2層: フィクスチャ・リプレイテスト

### 3.1 リプレイの仕組み

- **RPL-R-01**: リプレイハーネス（実装物、`tests/replay/` 配下）は、LLM呼び出し境界の2点、すなわち (1)候補生成 (2)独立レビュー実行 のみをシナリオ定義のフィクスチャ返却で置換しなければならない(MUST)。
- **RPL-R-02**: それ以外の処理（機械検査・スキーマ検証・`set_check.py`・`finalize_set.py`・監査ファイル出力・世代管理）は実装コードをそのまま実行しなければならない(MUST)。制御ロジックのモック化をしてはならない(MUST NOT)。
- **RPL-R-03**: ハーネスは、再生成時に生成側へ渡された再指示ペイロード（前世代レビューの `violations[]` を含む構造化指摘）を記録し、テストから検証可能にしなければならない(MUST)。受け渡し内容の正は `docs/subagent-review-spec.md` の再生成ループ仕様。
- **RPL-R-04**: リプレイの出力先はテスト一時ディレクトリとし、`output/` を汚してはならない(MUST NOT)。

### 3.2 シナリオ定義ファイルの様式

保存場所: `tests/fixtures/scenarios/<scenario_id>.json`。`scenario_id` は `^rpl_[0-9]{2}_[a-z0-9_]+$`。このファイルはテスト専用であり `schemas/` の9本の管理対象外とする。フィールドは次のとおり（全フィールド必須。値なしは空配列・nullではなくフィールド自体を検証対象から外すことはしない）。

| フィールド | 型 | 内容 |
|---|---|---|
| `scenario_id` | string | 上記書式のID |
| `description` | string | シナリオの目的（日本語） |
| `request` | object | セット条件: `format`（形式コード）・`level_scale`・`level`・`mode`（`explicit` / `proposal`）・`question_count`（1〜20）・`targets`（明示モード時の対象IDリスト。提案モード時は候補プールのIDリスト） |
| `steps` | array | 時系列の応答定義。各要素: `question_id`・`gen`（`gen1|gen2|gen3`）・`candidate`（`tests/fixtures/candidates/` からの相対パス。生成候補スキーマ不通過を模擬する場合は不正JSONフィクスチャを指す）・`review`（`tests/fixtures/reviews/` からの相対パス。レビュー出力スキーマ不通過を模擬する場合は不正JSONフィクスチャを指す）・`review_retries`（同一世代でのレビュー再実行用フィクスチャの配列。不要なら空配列） |
| `expected` | object | 期待結果: `outcome`（`completed` / `aborted` / `teacher_consult`）・`set_questions`（`set.json` に収録されるべき `question_id` の配列。`outcome` が `completed` 以外なら空配列）・`audit_files`（存在すべき監査ファイル名の完全列挙）・`attempts_total`（試行された問題×世代の総数）・`regeneration_payload_checks`（再指示ペイロードに含まれるべき `violations[].code` の列挙。再生成がないシナリオは空配列） |

### 3.3 シナリオ一覧

規則の正: `docs/subagent-review-spec.md`（再生成ループ・インフラ障害・監査配置）、`docs/cefrj-validation-spec.md`（機械検査優越）。

| テストID | シナリオ | 合否条件 |
|---|---|---|
| RPL-01 | 全問gen1合格（`question_count`=3） | `outcome`=`completed`。`set.json` に3問収録・スキーマ合格。監査に各問 `q0N.gen1.candidate.json` / `.machine.json` / `.request.json` / `.review.json` と増分 `set_check.q0N.gen1.json`、各論理スロットの `slot.q0N.outcome.json`、最終 `set_check.final.json` のみ存在 |
| RPL-02 | 1問がgen1不合格→gen2合格 | gen2の再指示ペイロードにgen1レビューの `violations[]`（`code`・`location`・`evidence`・`expected_level`・`actual_level`・`suggestion`）が含まれること。監査にgen1とgen2の両世代が残ること |
| RPL-03 | 提案モードで1問が3世代不合格 | 候補プールから`q{N+1}`以降のIDで自動補充され、そのIDが`min(2N,20)`以下ならmachine_checkの`V-COND-01`を受けず、補充問題も最大3世代で試行されること。試行対象総数が要求数の2倍へ達した時点で補充が停止すること |
| RPL-04 | 明示モードで1問が3世代不合格 | 自動代替が行われず、`outcome`=`teacher_consult` となり、不成立理由（3世代分の指摘要約）が教師照会用に構造化されて残ること。教師指定の代替へ`q{N+1}`を割り当てた場合はmachine_checkの条件照合を通過できること |
| RPL-05 | レビュー出力の受理失敗（インフラ障害） | JSONパース不能、スキーマ不通過、スキーマ有効だが孤立サロゲート等でstrict UTF-8/JS-01正準化不能の各ケースで、同一request・同一世代内で最大2回再実行されること。初回を含む3回すべてが失敗した場合セット中止（`outcome`=`aborted`）となり、当該事象が問題の不合格世代に数えられず、AUD-09の適切なkindで3件のinvalid監査が残り、`set.json`が作成されないこと |
| RPL-06 | 生成候補スキーマ不通過 | 同一世代内で1回だけ再指示されること。再指示も失敗した場合に当該世代が消費される（`gen` が進む）こと |
| RPL-07 | 機械検査fail＋レビューpass | 最終判定が `fail` のままであること（機械検査違反はレビューで覆せない） |
| RPL-08 | セット横断違反（例文使い回し） | `set_check.py` が違反を報告し、違反が残る限り `finalize_set.py` が `set.json` を作成しないこと。違反検出後の後続処理が `docs/subagent-review-spec.md` の再生成ループ仕様の定義どおり進むこと |
| RPL-09 | 監査と正本の参照整合 | RPL-01の完成セットで、`set.json` から `review/` への相対参照が全て実在ファイルに解決し、監査ファイルが欠けても `set.json` 単体で全問題を解釈できる（監査への参照以外に監査依存フィールドがない）こと |
| RPL-10 | 最悪コスト境界 | `question_count`=n の提案モードで全問全世代不合格のとき、試行対象IDは`q01`〜`q{min(2n,20)}`、生成試行総数は`min(2n,20)×3世代`を上限として停止し、それを超える生成・レビューが発生しないこと（`docs/requirements.md` の非機能要件参照） |

---

## 4. テスト資産（ゴールデン・フィクスチャ）の管理

### 4.1 保存場所

- **FIX-01**: テスト資産は次の配置に置かなければならない(MUST)。この配置は実装時に作成する（`IMPLEMENTATION_PLAN.md` M8）。

```
tests/
├── unit/                         # 第1層テストコード（pytest）
├── replay/                       # 第2層テストコード＋リプレイハーネス
├── golden/
│   ├── normalized/checksums.json # 正規化ゴールデン（SHA-256）
│   ├── sets/<format>.set.json    # 9形式のゴールデンset.json（CI-SCH-02の妥当例を兼ねる）
│   ├── html/<format>.html        # 9形式のゴールデンHTML
│   ├── machine/                  # 互換用machine_reportゴールデン（CI-CLI-02）
│   └── cases/                    # 受け入れ用ゴールデンケース候補JSON（4.4節）
├── fixtures/
│   ├── candidates/               # 候補JSONフィクスチャ（compat/ サブディレクトリを含む）
│   ├── reviews/                  # review_result JSONフィクスチャ
│   ├── machine/                  # machine_report JSONフィクスチャ
│   ├── schemas/valid/<スキーマ名>/   # スキーマ妥当例
│   ├── schemas/invalid/<スキーマ名>/ # スキーマ不当例
│   └── scenarios/                # リプレイシナリオ定義（3.2節）
└── acceptance/
    └── records/                  # 第3層の実施記録（5.2節）
```

### 4.2 様式

- **FIX-02**: フィクスチャJSON（`tests/fixtures/` 配下）は UTF-8（BOMなし）・改行LF・`json.dumps(obj, ensure_ascii=False, indent=2, sort_keys=True)` の出力＋末尾改行1つ、で正規書式化しなければならない(MUST)。
- **FIX-03**: ゴールデン（`tests/golden/sets/`・`html/`・`machine/`・`cases/`）は生成器・検査器の出力バイト列そのままを保存しなければならない(MUST)。FIX-02の再整形をしてはならない(MUST NOT)。
- **FIX-04**: `tests/golden/normalized/checksums.json` の様式は `{"data_version": "<正規化データのdata_version>", "files": {"lexicon.json": "<sha256>", "grammar.json": "<sha256>", "meta.json": "<sha256>"}}` としなければならない(MUST)。
- **FIX-05**: `tests/fixtures/candidates/`・`reviews/`・`machine/`・`schemas/invalid/` の各ディレクトリ直下に `index.json` を置き、`{"cases": [{"file": "<ファイル名>", "purpose": "<日本語の目的>", "expected": "<期待結果の要約（違反コード・判定値）>", "test_ids": ["CI-MCH-01"]}]}` の形式で全ファイルを登録しなければならない(MUST)。`index.json` 未登録のフィクスチャファイルが存在しないことをCIで検査する（このメタ検査のテストIDは CI-FIX-01 とする）。
- **FIX-06**: 候補・レビューのフィクスチャは対応するスキーマ（`candidate.schema.json` / `review_result.schema.json`）に合格しなければならない(MUST)。例外はスキーマ不通過を意図するフィクスチャ（RPL-05・RPL-06・CI-SCH-03用）のみであり、これらは `index.json` の `purpose` に不通過意図を明記する。
- **FIX-07**: フィクスチャ・ゴールデンには実在の個人名・メールアドレス・所属を含めてはならない(MUST NOT)。人名が必要な場合は `data/config/proper_nouns.json` 収録語から選ぶ。
- **FIX-08**: 実LLMの出力を記録してフィクスチャ化する場合の手順: ①受け入れ実施または開発中の実行で得た候補/レビューJSONを採取する ②FIX-02の正規書式に変換する ③FIX-07を確認する ④`index.json` に登録する ⑤対応するスキーマ合格をCIで確認する。この5手順を全て行わなければならない(MUST)。

### 4.3 更新手順

- **GLD-01**: ゴールデンおよびチェックサムの更新が正当なのは次の6ケースのみである。これ以外の理由で更新してはならない(MUST NOT)。
  1. 原本xlsxの更新（`data_version` 変更を伴う。手順の正は `docs/architecture.md` の運用手順「原本更新」）
  2. 正規化パイプラインの仕様変更（`docs/cefrj-validation-spec.md` の改訂を伴う）
  3. スキーマの変更（`schemas/` のsemver更新を伴う）
  4. HTMLテンプレート・生成器の仕様変更（`docs/html-output-spec.md` の改訂を伴う）
  5. `data/config/limits.json`・`data/config/proper_nouns.json` の設定変更
  6. フィクスチャ・ゴールデン自体の誤りの修正
- **GLD-02**: 更新手順は次の順で行わなければならない(MUST)。
  1. 更新理由（GLD-01のどのケースか）を `CHANGELOG.md` に記載する
  2. 該当する生成を再実行する（正規化: `build_normalized.py`、HTML: `build_html.py`、machine: `machine_check.py`）
  3. 新旧差分を確認する（正規化は `build_normalized.py` の差分レポート、HTML・machineはテキストdiff）。差分が更新理由から説明できない場合は更新を中止し原因を調査する
  4. ゴールデン・チェックサムを置換する
  5. `pytest tests/unit tests/replay` の全通過を確認する
  6. ゴールデン更新と原因となった変更を同一コミットでコミットする
- **GLD-03**: ゴールデンset.json（`tests/golden/sets/`）の初回作成は、受け入れ済みの実セットから採取し、FIX-07・スキーマ合格を確認して保存する。以後の更新はGLD-01・GLD-02に従う。
- **GLD-04**: 本節の更新手順が本文書の正であり、`docs/architecture.md` の運用手順「フィクスチャ更新」は本節を参照する。

### 4.4 ゴールデンケース候補（受け入れ用）

- **GLD-05**: `tests/golden/cases/` に次の2ファイルを置かなければならない(MUST)。いずれも `candidate.schema.json` に合格し、作成時に `machine_check.py` で verdict `fail` にならないこと（機械検査を通過し、LLMレビューだけが検出できるケースであること）を確認して保存する。
  1. **`these_relative_clause.candidate.json`**（A-07用）: `format`=`vocab_mcq_en2ja`、`level_scale`=`cefr`、レベルA1、対象 `lex:these:pronoun`。例文は `These are the books that I bought yesterday.`（句読点除き8トークン、関係節を含む、全語がWordlist A1収録）。誤答3語はA1・pronounの実在語で由来記録付き。作成時に例文の全語のA1収録を `lookup.py` で確認し、収録外の語があった場合は関係節を維持したままA1語に差し替える。
  2. **`estimate_label.candidate.json`**（A-08用）: `format`=`grammar_example_selfcheck`、`level_scale`=`cefrj`、レベルB2.2、対象は教員版の単一値B2.2項目（例: `gp:84` 受動態(助動詞+完了)）。例文に教員版レベル未付与項目の構造（ID 98 `so as not to DO` または ID 96 `in order not to DO`）を含む。参考例文: `The window must have been closed so as not to let the cold air in.`。作成時に語彙レベル・語数の機械検査通過を確認する。

---

## 5. 第3層: 手動受け入れテスト

### 5.1 実施規則

- **ACC-01**: 手動受け入れは、タグ付きリリースの作成前に毎回、実LLMを用いて実施しなければならない(MUST)。実施タイミングの位置づけは `docs/architecture.md` の運用手順「リリース」に従う。
- **ACC-02**: 実施前に `pytest tests/unit tests/replay` の全通過と `doctor.py` の成功を確認しなければならない(MUST)。
- **ACC-03**: A-01〜A-14はプライマリツール（Claude CodeまたはCodexのうちリリース実施者が選んだ一方）で実施し、A-15で他方のツールを検証する。リリースごとにプライマリツールを交代すべきである(SHOULD)。
- **ACC-04**: 各項目の合否は当該項目の「合否条件」の全文の充足のみで判定しなければならない(MUST)。所要時間は参考であり合否に影響しない（TST-07）。全体の参考目標は30分。
- **ACC-05**: 手順中の「セットを完走する」は、`docs/interaction-flow.md` の対話フロー（①形式→②レベル→③対象指定方法→④問題数→⑤トピック任意→⑥固有名詞任意→⑦条件サマリー確認→生成開始）を経て、`output/<set_id>/set.json` と `index.html` が生成され、`validate.py` で `set.json` が合格する、までを指す。
- **ACC-06**: 完走系項目（A-02〜A-06）では、⑤トピックと⑥固有名詞はいずれか1セットでのみ指定し（どのセットで指定したかを記録に残す）、残りは指定なしで進める。

### 5.2 実施記録

- **ACC-07**: 実施結果は `tests/acceptance/records/<リリースタグ>.md` に記録しなければならない(MUST)。記録必須項目: リリースタグ / 実施日 / 実施者 / プライマリツール名とモデル名 / A-15で用いた他方ツール名とモデル名 / 各項目（A-01〜A-15）の pass・fail と特記事項 / 生成された `set_id` の一覧 / 総合判定。
- **ACC-08**: 1項目でもfailの場合、リリースを中止しなければならない(MUST)。再実施の範囲は第6節に従う。

### 5.3 チェックリスト（全15項目）

#### A-01 環境診断

- **前提**: リリース対象コミットのクリーンなクローン。
- **手順**: セットアップ手順書（`docs/cross-agent-compatibility.md` のセットアップ手順書要件に基づく実装物）に従い環境を構築し、`python scripts/doctor.py` を実行する。
- **合否条件**: 終了コード0。診断項目（Python版・spaCyモデル・`data/source/` チェックサム・`data/normalized/` 整合・`data/config/` 2ファイルの存在とスキーマ合格）が全てOKと表示される。

#### A-02 語彙4択2形式の完走

- **前提**: A-01合格。
- **手順**: プライマリツールで次の2セットを完走する（ACC-05）。(1) `vocab_mcq_en2ja`・レベルA2・提案モード・2問。(2) `vocab_mcq_ja2en`・レベルA1・明示モード・2問（対象は事前に `python scripts/lookup.py` でA1収録を確認した名詞2語を指定する）。
- **合否条件**: 両セットが完走し `validate.py` 合格。対話が1ターン1質問で進む。各問の誤答3語すべてに由来（`headword`+`pos`+`level`）が `set.json` に記録されている。`index.html` の選択肢表示順が `set.json` の選択肢配列順と一致する。

#### A-03 語彙フラッシュカード2形式の完走

- **前提**: A-01合格。
- **手順**: (1) `vocab_flashcard_en2ja`・レベルA2・提案モード・2問。(2) `vocab_flashcard_ja2en`・レベルA1・提案モード・2問。各セット完走後、`index.html` をブラウザで開きカードをめくる。
- **合否条件**: 両セット完走・`validate.py` 合格。表面に例文（(1)は英文、(2)は日本語訳）、裏面に対訳が表示され、対象語がハイライトされる。「覚えた/まだ」の自己採点とサマリー表示が動作する。(2) の各問について、`set.json` のレビュー参照先 `review/*.review.json` に訳文からの英文復元可能性（時制・数・人称）の検証記録がある。

#### A-04 文法選択・穴埋めの完走

- **前提**: A-01合格。
- **手順**: (1) `grammar_mcq`・レベルA1.2・提案モード・2問。(2) `grammar_cloze`・レベルA2.1・提案モード・2問。完走後、(2) の `index.html` で空欄に「正答の大文字化した表記」「前後に空白を付けた表記」「`set.json` の同値リストにある別表記（存在する場合）」を入力する。
- **合否条件**: 両セット完走・`validate.py` 合格。全問の対象が教員版256項目のIDを持ち、指定レベルが当該項目のレベル（範囲値は[下限,上限]包含、単一値は一致）に適格である。(1) の各問解説が200字以内で正解の理由と各誤答の排除理由を含む。(2) の3通りの入力がいずれも正解と判定される（大文字小文字無視・前後空白除去・同値リスト照合）。

#### A-05 整序・書き換えの完走

- **前提**: A-01合格。
- **手順**: (1) `grammar_reorder`・レベルB1.1・提案モード・2問。(2) `grammar_rewrite`・レベルB1.2・提案モード・2問。完走後、(1) の `index.html` でトークンをタップして解答し、解答表示を開く。
- **合否条件**: 両セット完走・`validate.py` 合格。(1) 提示トークンは句読点を除く全トークンの小文字化で、提示順が正解順と異なり、文頭ヒントがなく、タップ順選択で解答でき、解答表示は正書法（大文字・句読点あり）である。解説は200字以内で語順の根拠を含む。(2) 問題文に何を使って書き換えるかの指示が明示され、目標文が部分入力（空欄）方式で、元文・目標文の全語彙・全文法が指定レベル制約内である。解説は200字以内で元文と目標文の文法的関係を含む。

#### A-06 例文問題の完走

- **前提**: A-01合格。
- **手順**: `grammar_example_selfcheck`・レベルB2.1・提案モード・2問を完走し、`index.html` で解説の開閉と自己採点を操作する。
- **合否条件**: 完走・`validate.py` 合格。各問の詳細解説が400字以内で「①項目の機能→②この例文での使われ方→③注意点・よくある誤り」の順に構成され、教員版の文法項目名を明記し、です・ます調・中高標準文法用語のみで書かれている。訳想起→正解表示→自己採点のUIが動作する。

#### A-07 ゴールデンケース: A1 these＋関係節の不合格

- **前提**: A-01合格。`tests/golden/cases/these_relative_clause.candidate.json`（4.4節）。
- **手順**: ①`python scripts/machine_check.py` に当該候補を入力し結果を確認する。②`docs/subagent-review-spec.md` のレビュアー起動手順（プライマリツール側の配線）に従い、当該候補＋①の機械検査レポートを入力として独立レビューを2回実行する（毎回新規の独立実行）。
- **合否条件**: ①の機械検査は verdict `fail` にならない（このケースの検出はLLMレビューの担当であることの確認）。②の2回とも `review_result` の verdict が `fail` であり、`violations[]` に次を満たす違反が含まれる: `location` が例文中の関係節を指す / `evidence` の `level_source` が `kyoinban` で教員版の関係節項目のIDとレベルを引用する / `expected_level` がA1帯（許容上限A1.3）以下 / `actual_level` がA2帯以上 / `suggestion` が空でない。

#### A-08 estimateラベルの付与

- **前提**: A-01合格。`tests/golden/cases/estimate_label.candidate.json`（4.4節）。
- **手順**: A-07②と同じ手順で当該候補の独立レビューを1回実行する。
- **合否条件**: `review_result` の文法構造列挙に、教員版レベル未付与構造（ID 96または98）へ `level_source`=`reviewer_estimate` が付与された項目が存在し、推定レベルと根拠記述が空でない。同じ列挙の中の教員版レベルあり構造には `level_source`=`kyoinban` が付与されており、両者が区別できる。

#### A-09 明示指定のレベル不一致指摘

- **前提**: A-01合格。
- **手順**: `vocab_mcq_en2ja`・レベルA1・明示モードのセッションを開始し、対象として `abandon` を指定する。
- **合否条件**: エージェントがその場で不一致を指摘し、指摘文言に指定レベル（A1）とWordlist上の実レベル（verb: B1）の両方が明示され、代替の指定または提案への切り替えを促す（文言テンプレートの正は `docs/interaction-flow.md` の明示指定照合フロー）。`abandon` が対象として採用されない。

#### A-10 明示指定の辞書外語指摘

- **前提**: A-09のセッションを継続、または新規セッション。
- **手順**: 対象として `Tokyo` を指定する。
- **合否条件**: エージェントがその場でWordlist非収録である旨を指摘し、代替を促す。`Tokyo` が対象として採用されない。セッションはエラー停止せず継続する。

#### A-11 監査ファイルと正本の整合

- **前提**: A-04(1) の完走済みセット。
- **手順**: `output/<set_id>/` を検査する。
- **合否条件**: `review/` 配下の全ファイル名が `docs/json-output-spec.md` ID-07 の目録（`<question_id>.<gen>.candidate.json` / `.machine.json` / `.request.json` / `.review.json`・set_check レポート・invalid テキスト・スロット終端監査）に合致し、実行された全世代分と要求数分の終端監査が揃っている。`set.json` からの相対参照が全て解決する。`set.json` に不合格問題が含まれない。`attribution` にWordlistとGrammar Profileの両引用があり、URL・ダウンロード日が `data/normalized/meta.json` の値と一致する。

#### A-12 HTMLのオフライン動作とスマホ表示

- **前提**: A-02(1) と A-04(2) の `index.html`。
- **手順**: OSのネットワークを遮断（機内モードまたはブラウザ開発者ツールのオフラインモード）した状態でブラウザで開き、全操作（選択・入力・正誤表示）を行う。次にブラウザの開発者ツールで表示幅375pxにして再操作する。開発者ツールのネットワークタブで外部リクエストを確認する。
- **合否条件**: オフラインで全機能が動作する。外部リクエストが0件。幅375pxで横スクロールが発生せず全操作が可能（基準の正は `docs/html-output-spec.md` のスマホ対応基準）。

#### A-13 印刷CSS

- **前提**: A-04(1) と A-03(1) の `index.html`。
- **手順**: ブラウザの印刷プレビューを開く。
- **合否条件**: A-04(1) は問題ワークシートの後に改ページされ解答・解説が続く。A-03(1)（フラッシュカード）はカードUIではなくリスト形式で印刷される（仕様の正は `docs/html-output-spec.md` の印刷CSS仕様）。

#### A-14 出典表示

- **前提**: A-02〜A-06で生成した任意の `index.html` 1件と対応する `set.json`。
- **手順**: HTMLのフッターを目視確認し、`set.json` の `attribution` と突き合わせる。
- **合否条件**: フッターに『CEFR-J Wordlist Version 1.6』とCEFR-J Grammar Profileの両出典が引用書式（`docs/json-output-spec.md` の出典ブロック仕様）どおりに常時表示され、`set.json` の `attribution` と同内容である。

#### A-15 互換確認（他方ツール）

- **前提**: A-01〜A-14がプライマリツールで合格。他方ツールの環境構築済み。
- **手順**: ①他方ツールで `grammar_mcq`・レベルA1.2・提案モード・2問を完走する。②他方ツールの環境で `python scripts/machine_check.py` を `tests/fixtures/candidates/compat/` の互換用フィクスチャに対して実行する。
- **合否条件**: ①が完走し `validate.py` 合格。②の出力が `tests/golden/machine/` のゴールデンとCI-R-02の意味でバイト一致する。アダプタ（CLAUDE.md / AGENTS.md / `.claude/`）に挙動規則が書かれていないことを目視確認する（配線のみ。正は `docs/cross-agent-compatibility.md`）。

### 5.4 参考時間配分（合否条件ではない）

A-01: 2分 / A-02〜A-06: 各3分 / A-07: 3分 / A-08: 2分 / A-09・A-10: 計2分 / A-11: 2分 / A-12: 2分 / A-13: 1分 / A-14: 1分 / A-15: 4分。合計約30分。

---

## 6. 不合格時の扱いと再実施

- **ACC-09**: 第3層でfailが出た場合、リリースを中止し、原因を修正した後、次の範囲で再実施しなければならない(MUST)。
  1. 修正が `agent/` 配下（コア指示書）または `docs/` 配下の文書に及んだ場合: 第1層・第2層の全実行に加え、A-01〜A-15の全項目を再実施する。
  2. 修正が `scripts/`・HTMLテンプレート・`schemas/`・`data/config/` のみの場合: 第1層・第2層の全実行に加え、failした項目と、その項目の「前提」欄が参照する項目のみを再実施する。
- **ACC-10**: failの内容が機械検査の誤検出（レンマ化誤りを含む）に起因すると疑われる場合でも、当該リリースは中止しなければならない(MUST)。誤検出疑いは `docs/subagent-review-spec.md` の機械検査誤検出疑い報告様式で記録し、機械検査側の修正後にGLD-02とACC-09を適用する。
- **ACC-11**: 再実施の結果は同一リリースタグ予定の記録ファイルに追記し、実施回数が分かる形で残さなければならない(MUST)。

---

## 7. v2課題

本文書に関係するスコープ外項目（localStorageによる採点状態永続化、二重レビュー、セット再開機能、TreeTagger正規表現の機械照合、語彙問題への解説拡張）は `docs/requirements.md` のスコープ外/v2リストが正である。これらに対するテストを本文書は定義しない。
