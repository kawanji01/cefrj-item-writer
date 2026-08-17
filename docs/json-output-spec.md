# JSON出力仕様（json-output-spec）

## 0. 文書情報

- **目的**: 問題データの正本 `set.json` の全フィールド、9形式ペイロード、監査ファイル（candidate / machine_report / review_result / review_request / set_check レポート）の内容、ID規則、出典ブロック、`schema_version` の運用を、実装者（Codex GPT-5.6 sol）が追加判断なしで実装できる粒度で定める。本書は `schemas/` 配下の9スキーマと完全に整合しており、構造・型・必須性の機械検証はスキーマが行い、本書は各フィールドの意味・組み立て手順・記入規則を定める。
- **対象読者**: 実装担当（Codex GPT-5.6 sol）、コア指示書（`agent/author-core.md` / `agent/reviewer-core.md`）の執筆者、テスト設計者。
- **参照文書**:
  - `docs/requirements.md`（機能要件・スコープ外/v2リストの正）
  - `docs/architecture.md`（CLI契約・エラーコード目録・`data_version` 書式・スキーマ版上げ規則 VER-01〜VER-08 の正）
  - `docs/question-generation-spec.md`（9形式の生成内容規則の正）
  - `docs/cefrj-validation-spec.md`（レベル体系・正規化変換規則・機械検査の判定規則の正）
  - `docs/subagent-review-spec.md`（レビュアー契約・監査ファイルの配置・命名・書き込みタイミングの正）
  - `docs/html-output-spec.md`（HTML生成器契約・表示規則の正）
  - `docs/interaction-flow.md`（`set_id` 採番タイミング・完了報告様式の正）
  - `schemas/` 配下の9スキーマ（構造・型・必須性の機械検証の正）
- **規範語彙凡例**: 「しなければならない(MUST)」=絶対要件。「してはならない(MUST NOT)」=絶対禁止。「すべきである(SHOULD)」=正当な理由がない限り従う。「してもよい(MAY)」=任意。
- **この文書が「正」とする範囲**: ①JSON直列化規則（第1節）、②ID規則（第2節）、③`schema_version` 運用と9スキーマの対応表（第3節）、④`set.json` の全フィールドと組み立て手順・出典ブロック仕様・`finalize_set.py` へのセットメタデータ入力様式（第4節）、⑤9形式ペイロードのフィールド定義（第5節）、⑥監査ファイルの内容仕様（第6節）、⑦正規化データ・設定ファイルの構造の要点（第7節。構造の詳細はスキーマ、変換規則は `docs/cefrj-validation-spec.md`）。本書は次の正ではない: 生成内容の規則（`docs/question-generation-spec.md`）、機械検査・レビューの判定手順（`docs/cefrj-validation-spec.md` / `docs/subagent-review-spec.md`）、監査ファイルの配置・命名・書き込みタイミング（`docs/subagent-review-spec.md` 第8節）、エラーコードの目録（`docs/architecture.md`）。

---

## 1. JSON直列化規則

- **JS-01（正準形）**: 本システムの決定的CLIが書き出す全JSONファイル（`set.json`・監査JSON・`data/normalized/` の3ファイル）およびCLIのstdout結果JSONは、次の正準形で直列化しなければならない(MUST)。この規則は `docs/architecture.md` CLI-04 と同一であり、両文書のいずれかを改訂する場合は他方も同時に改訂しなければならない(MUST)。
  1. エンコーディングは UTF-8（BOMなし）。
  2. 非ASCII文字はエスケープしない（Python `json.dump` の `ensure_ascii=False`）。
  3. オブジェクトのキーは辞書順ソート（`sort_keys=True`）。
  4. インデントは半角スペース2個。
  5. 改行は LF。ファイル末尾に改行1個。
- **JS-02（LLM出力の受理形）**: LLM（生成エージェント・レビュアー）が出力するJSON（candidate・review_result）は、正準形であることを要求しない(MAY)。candidateはホスト側のパース・再直列化より先に生成生出力をUTF-8バイト列として`validate.py`へ渡し、標準JSON・candidateスキーマの検証後に厳格パースして本節の正準形へ再直列化しなければならない(MUST)。これらの受理検証を通過したLLM出力を監査ファイルとして保存する際、オーケストレータは正準形に再直列化して保存しなければならない(MUST)（監査ファイルのバイト再現性のため）。受理失敗時のT2/T3分類は`docs/subagent-review-spec.md`、invalid監査の形式はAUD-09が正である。
- **JS-03（実行毎に変わるフィールド）**: 決定的CLIが書き出すJSONのうち、実行毎に値が変わるフィールドは machine_report（scope=question / scope=set とも）の `generated_at` のみとしなければならない(MUST)。`generated_at`はUTC・秒精度・末尾`Z`のISO 8601文字列とする。テストのバイト比較（`docs/testing-and-acceptance.md`）は本フィールドのみを比較から除外する。これ以外のフィールドに実行時刻・乱数・環境依存値を書き込んではならない(MUST NOT)（`set_id` と `created_at` は入力として与えられる値であり、この禁止の対象外である）。
- **JS-04（数値の表現）**: 整数はJSONの整数リテラル、実数は入力（原本xlsx）の値をPython `json` モジュールの既定の表現で保持する。丸め・指数表記への変換を行ってはならない(MUST NOT)。

## 2. ID規則（正）

本節が全成果物のID書式の正である。他文書（`docs/architecture.md` E-INPUT-04/05、`docs/interaction-flow.md` IF-05）は本節を参照する。

- **ID-01（set_id）**: 書式は正規表現 `^\d{8}-\d{6}-[a-z0-9]{4}$` に一致しなければならない(MUST)。構成は `<YYYYMMDD>-<hhmmss>-<英小文字数字4字>`（例 `20260816-142530-k7x2`）。先頭14桁は採番時のローカル日時、末尾4字は乱数とする。採番はセット実行開始時に1回だけ行う（タイミングの正は `docs/interaction-flow.md` IF-05）。`output/<set_id>/` が既に存在する場合は末尾4字を再生成しなければならない(MUST)。
- **ID-02（question_id）**: 書式は `^q(0[1-9]|1[0-9]|20)$`（`q01`〜`q20`、ゼロ埋め2桁）。セット内で一意であり、対象の確定順に `q01` から連番で割り当てる。減数（教師選択によるスロット放棄）が発生した場合、`set.json` の `questions[]` に欠番が生じてもよい(MAY)。割り当て済みの `question_id` を再割り当てしてはならない(MUST NOT)。
- **ID-03（世代表記）**: 世代は全成果物（`set.json` の `provenance.generation` を含む）で文字列 `gen1` / `gen2` / `gen3` の3値のみとする(MUST)。整数表記を用いてはならない(MUST NOT)。
- **ID-04（語彙エントリID）**: 書式は `lex:<headword>:<pos'>`。`<headword>` は正規化済み見出し語の原文（大文字小文字・ピリオド・ハイフン・アポストロフィ・内部空白を保持）、`<pos'>` は Wordlist pos 15種の空白を `-` に置換した値（例 `lex:watch:verb`、`lex:a.m.:adverb`、`lex:may:modal-auxiliary`、`lex:CD player:noun`）。headword に `:` を含むIDを生成してはならない(MUST NOT)（生成時の検査は `docs/cefrj-validation-spec.md` NRM-09）。
- **ID-05（文法項目ID）**: 書式は `gp:<ID>`（`<ID>` は ITEM LIST のID列原文。例 `gp:13`、枝番 `gp:1-1`）。正規表現 `^gp:[0-9]+(-[0-9]+)?$`。
- **ID-06（併記グループID）**: 書式は `grp:<先頭variant>:<pos'>`（導出規則の正は `docs/cefrj-validation-spec.md` NRM-10）。
- **ID-07（監査ファイル名）**: 正規監査ファイルは `review/<question_id>.<gen>.request.json`（レビュアー入力封筒。AUD-08） / `review/<question_id>.<gen>.candidate.json` / `review/<question_id>.<gen>.machine.json` / `review/<question_id>.<gen>.review.json`、補助監査ファイルは `review/<question_id>.<gen>.candidate.invalid<k>.txt`（k=1,2）・`review/<question_id>.<gen>.review.invalid<k>.txt`（k=1,2,3）・`review/set_check.<question_id>.<gen>.json`・`review/set_check.final.json` とする。配置・書き込みタイミングの正は `docs/subagent-review-spec.md` 第8節（AU-01〜AU-07）。
- **ID-08（スキーマ$id）**: 各スキーマの `$id` は `https://cefr-j-agents.local/schemas/<name>/<semver>` とする（`docs/architecture.md` VER-01）。`<semver>` はそのスキーマの現行版と一致しなければならない(MUST)。このURLは識別子であり、ネットワーク解決してはならない(MUST NOT)。

## 3. スキーマ体系と schema_version 運用

### 3.1 9スキーマの対応表

- **SV-01**: スキーマは次の9本のみとする(MUST)。`validate.py --schema` の識別子（`docs/architecture.md` CLI-26）との対応は次表のとおり。

| スキーマファイル | validate.py 識別子 | 検証対象文書 | 初版 |
|---|---|---|---|
| `schemas/set.schema.json` | `set` | `output/<set_id>/set.json`（正本） | 1.0.0 |
| `schemas/candidate.schema.json` | `candidate` | 生成候補1問分・監査 `*.candidate.json` | 1.0.0 |
| `schemas/machine_report.schema.json` | `machine_report` | `machine_check.py` / `set_check.py` の出力・監査 `*.machine.json` / `set_check.*.json` | 1.0.0 |
| `schemas/review_request.schema.json` | `review_request` | レビュアー入力封筒 | 1.0.0 |
| `schemas/review_result.schema.json` | `review_result` | レビュアー出力・監査 `*.review.json` | 1.0.0 |
| `schemas/normalized_lexicon.schema.json` | `normalized_lexicon` | `data/normalized/lexicon.json` | 1.0.0 |
| `schemas/normalized_grammar.schema.json` | `normalized_grammar` | `data/normalized/grammar.json` | 1.0.0 |
| `schemas/config_limits.schema.json` | `config_limits` | `data/config/limits.json` | 1.0.0 |
| `schemas/config_proper_nouns.schema.json` | `config_proper_nouns` | `data/config/proper_nouns.json` | 1.0.0 |

- **SV-02（meta.json の扱い）**: `data/normalized/meta.json` は9スキーマの検証対象ではない。その構造の正は `docs/cefrj-validation-spec.md` NRM-29 であり、整合検査は各CLIの起動時検査（E-DATA-04、`docs/architecture.md`）が行う。

### 3.2 schema_version の運用

- **SV-03（文書側フィールド）**: 次の文書はトップレベルに `schema_version` フィールド（文字列semver）を持たなければならない(MUST): `set.json`・machine_report・review_request・review_result・`lexicon.json`・`grammar.json`・`limits.json`・`proper_nouns.json`。candidate は `schema_version` を持たない（生成エージェントの出力を最小化するため。candidate の版は検証に用いた `candidate.schema.json` の版で定まり、監査上は同世代の machine_report の `schema_version` 群から追跡できる）。
- **SV-04（メジャー一致）**: 各スキーマは文書側 `schema_version` のメジャー番号が自身のメジャーと一致することをパターン制約（現行は `^1\.\d+\.\d+$`）で強制する。文書のマイナー・パッチがスキーマの版と異なることは許容する(MAY)（後方互換な範囲での混在を認めるため）。
- **SV-05（版上げ）**: 版上げの判定基準・`$id` の更新・HTML生成器のメジャー拒否（E-CONTRACT-02）は `docs/architecture.md` VER-01〜VER-03 の正に従う。スキーマのメジャーを上げた場合、当該スキーマのパターン制約 `^<メジャー>\.\d+\.\d+$` を同時に更新しなければならない(MUST)。
- **SV-06（記入値）**: 各CLI・オーケストレータが文書を新規作成する際の `schema_version` には、その時点でリポジトリにある対応スキーマの現行版（`$id` 末尾のsemver）を記入しなければならない(MUST)。
- **SV-07（スキーマ間参照の禁止）**: 各スキーマは自己完結でなければならず(MUST)、他スキーマファイルへの `$ref` を含んではならない(MUST NOT)（オフライン検証と実装の単純化のため。共通定義は各スキーマの `$defs` に複製されており、9スキーマ間の定義差分はCIの検査対象とする。`docs/testing-and-acceptance.md`）。review_request に埋め込まれる candidate / machine_report は封筒スキーマ上は `type: object` として受け、封筒作成前にそれぞれのスキーマで検証済みでなければならない(MUST)（`docs/subagent-review-spec.md` RC-06 / RC-08）。

## 4. set.json 仕様

### 4.1 トップレベルフィールド表

- **SET-01**: `set.json` のトップレベルは次表の16フィールドのみとし(MUST)、これ以外のフィールドを含んではならない(MUST NOT)。全フィールド必須。型の機械検証は `schemas/set.schema.json` が行う。

| フィールド | 型 | 説明 | 例 |
|---|---|---|---|
| `schema_version` | string | set スキーマのsemver（SV-06） | `"1.0.0"` |
| `set_id` | string | セットID（ID-01） | `"20260816-142530-k7x2"` |
| `format` | string | 形式コード9値のいずれか。`questions[]` 全要素の `format` と一致 | `"vocab_mcq_en2ja"` |
| `level` | object | `{"scale": "cefr"\|"cefrj", "value": ...}`。語彙4形式は `cefr`、文法5形式は `cefrj`。`questions[]` 全要素の `level` と一致 | `{"scale":"cefr","value":"A2"}` |
| `mode` | string | 対象選定モード。`explicit`（明示指定）/ `proposal`（提案） | `"explicit"` |
| `requested_count` | integer | 教師の要求問題数（1〜`limits.json` の `set_question_max`） | `10` |
| `topic` | string \| null | 教師指定トピック。未指定は `null`。HTMLは非null時のみ表示（`docs/html-output-spec.md` LAY-14） | `"学校生活"` |
| `preferred_proper_nouns` | array of string | 教師が優先使用を指定した固有名詞（allowlist収録済み語のみ。`docs/interaction-flow.md` IF-16）。指定なしは空配列 | `["Ken"]` |
| `created_at` | string | セット作成日時。ISO 8601・秒精度・タイムゾーン付き（`YYYY-MM-DDThh:mm:ss±hh:mm` または末尾 `Z`）。`set_id` 採番と同時に取得した値 | `"2026-08-16T14:25:30+09:00"` |
| `tool` | string | 実行ホストツール。`claude_code` / `codex` の2値 | `"claude_code"` |
| `model` | string | 使用LLMモデル名（ホストツールが報告する文字列をそのまま記録） | `"claude-fable-5"` |
| `data_version` | string | データ版文字列（書式の正は `docs/architecture.md` VER-04）。`meta.json` から転記 | `"wl1.6+gp20200220+norm1.0.0"` |
| `source_checksums` | object | 原本xlsx 2ファイルのSHA-256。キー=ファイル名（E-DATA-01の固定名）、値=16進小文字64桁。`meta.json` の `sources[]` から転記 | 第4.5節の例参照 |
| `config_snapshot` | object | 生成時に適用された設定の写し（SET-02） | 同上 |
| `attribution` | object | CEFR-J出典ブロック（第4.3節） | 同上 |
| `questions` | array | 合格問題の配列（1〜20件）。`question_id` 昇順 | 同上 |

- **SET-02（config_snapshot）**: `config_snapshot` は `{"limits": <limits.jsonの全内容>, "proper_nouns": <proper_nouns.jsonのwords配列>}` としなければならない(MUST)。`limits` は `data/config/limits.json` のトップレベルオブジェクトをそのまま複製し、`proper_nouns` は `data/config/proper_nouns.json` の `words` 配列をそのまま複製する。S00のdoctor成功直後に読み取ったセッション設定スナップショットを、セット実行開始時（`set_id` 採番時）に現在値との完全一致を確認したうえで固定する。実行中の設定ファイル変更を反映してはならず(MUST NOT)、不一致は `E-DATA-08` でセット中止とする。
- **SET-03（questions の順序と欠番）**: `questions[]` は `question_id` の昇順に整列しなければならない(MUST)。減数が発生した場合は欠番を許す（ID-02）。要素数は `requested_count` 以下でなければならない(MUST)。
- **SET-04（正本の自立性）**: `set.json` は監査ファイル（`review/` 配下）が欠けても単体で解釈・HTML生成可能でなければならない(MUST)。`provenance` の参照は相対パスの記録のみであり、`build_html.py` は参照先を読み取ってはならない(MUST NOT)（`docs/html-output-spec.md` CON-01）。

### 4.2 問題オブジェクト共通骨格

- **SET-05**: `questions[]` の各要素は次の共通骨格に従わなければならない(MUST)。内容規則の正は `docs/question-generation-spec.md` 第2節。

| フィールド | 型 | 必須 | 説明 |
|---|---|---|---|
| `question_id` | string | 必須 | ID-02。 |
| `format` | string | 必須 | 形式コード。セットの `format` と一致。 |
| `level` | object | 必須 | セットの `level` と一致。 |
| `target` | object | 必須 | `{"type": "lexical"\|"grammar", "ref": <lex ID \| gp ID>, "display_name": string}`。問題ごとの原本参照。 |
| `body` | object | 必須 | 形式別ペイロード（第5節）。 |
| `explanation` | object | 文法5形式のみ必須。語彙4形式では存在してはならない(MUST NOT) | `{"type": "brief"\|"detailed", "text": string}`。`type` は ⑤⑥⑦⑧=`brief`、⑨=`detailed` 固定。 |
| `provenance` | object | `set.json` では必須。candidate に含めてはならない(MUST NOT) | SET-06。 |

- **SET-06（provenance）**: `provenance` は `finalize_set.py` が合格世代から構築する(MUST)。フィールド:
  - `generation`: 合格した世代の文字列 `gen1` / `gen2` / `gen3`（ID-03）。
  - `candidate_ref` / `machine_report_ref` / `review_ref`: 合格世代の監査3ファイルへの相対パス（`set.json` と同ディレクトリ起点、ID-07 の命名）。パス中の `<question_id>` と `<gen>` は、当該問題の `question_id` および `generation` と一致しなければならない(MUST)（スキーマはパス書式のみ検証する。一致検証は `finalize_set.py` の責務）。
- **SET-07（セット・問題間の一致検証）**: スキーマで表現できない次の一致は `finalize_set.py` が検証し、不成立は E-CONTRACT-01（内部バグ扱い、`docs/architecture.md` CLI-21）で停止しなければならない(MUST): ①セットの `format`/`level` と全問題の `format`/`level` の一致、②`question_id` の一意性と昇順、③SET-06 のパス一致、④`questions` 要素数 ≤ `requested_count`、⑤grammar_reorder の `answer_tokens` 導出整合（FIN-05）。

### 4.3 出典ブロック仕様（attribution）

- **ATT-01**: `attribution` は `{"wordlist": <出典>, "grammar_profile": <出典>}` の2キー構成とし(MUST)、各出典は `citation_ja` / `citation_en` / `url` / `retrieved_date` / `version_label` の5フィールドを持つ(MUST)。`url` と `retrieved_date`（`YYYY-MM-DD`）と `version_label` は `data/normalized/meta.json` の `sources[]` の対応エントリから転記する(MUST)。
- **ATT-02（引用文の組み立て）**: `citation_ja` / `citation_en` は `finalize_set.py` が次のテンプレートから決定的に組み立てなければならない(MUST)。`{年}` は `retrieved_date` の先頭4文字、`{月}` は `retrieved_date` の6〜7文字目から先頭の `0` を除いた10進表記とする。
  - Wordlist `citation_ja`: `『CEFR-J Wordlist Version {version_label}』 東京外国語大学投野由紀夫研究室.（URL: {url} より{年}年{月}月ダウンロード）`
  - Wordlist `citation_en`: `The CEFR-J Wordlist Version {version_label}. Compiled by Yukio Tono, Tokyo University of Foreign Studies. Retrieved from {url} on {retrieved_date}.`
  - Grammar Profile `citation_ja`: `『CEFR-J Grammar Profile』（{version_label}版） 東京外国語大学投野由紀夫研究室.（URL: {url} より{年}年{月}月ダウンロード）`
  - Grammar Profile `citation_en`: `The CEFR-J Grammar Profile ({version_label}). Compiled by Yukio Tono, Tokyo University of Foreign Studies. Retrieved from {url} on {retrieved_date}.`
- **ATT-03（両出典の常時記録）**: 語彙形式・文法形式を問わず、`attribution` には両原本の出典を記録しなければならない(MUST)（語彙問題でも例文の文法検証に Grammar Profile を使用しているため）。HTMLフッターは `citation_ja` の2文字列を改変せず表示する（`docs/html-output-spec.md` LAY-12）。
- **ATT-04（NOTICE との関係）**: ライセンス条件・再配布注意の全文は NOTICE（実装物）が担う。`attribution` は引用表示に必要な情報のみを保持する。

### 4.4 finalize_set.py へのセットメタデータ入力

- **FIN-01**: `finalize_set.py` の stdin に与えるセットメタデータJSONは次のフィールドのみで構成しなければならない(MUST)。これは `set.json` トップレベルのうちオーケストレータだけが知る値の受け渡しであり、9スキーマの検証対象ではない（内容検査は `finalize_set.py` が行い、不正は E-CONTRACT-01、パース不能は E-INPUT-03）。

| フィールド | 型 | 説明 |
|---|---|---|
| `set_id` | string | ID-01。`--set-dir` のディレクトリ名と一致しなければならない(MUST)。 |
| `format` | string | 形式コード9値。 |
| `level` | object | `{"scale", "value"}`。 |
| `mode` | string | `explicit` / `proposal`。 |
| `requested_count` | integer | 要求問題数。 |
| `topic` | string \| null | トピック。 |
| `preferred_proper_nouns` | array of string | 優先使用固有名詞。指定なしは空配列。 |
| `created_at` | string | セット作成日時（SET-01 の書式）。 |
| `tool` | string | `claude_code` / `codex`。 |
| `model` | string | モデル名。 |
| `config_snapshot` | object | SET-02で固定した開始時設定。`{"limits": <limits.json全内容>, "proper_nouns": <proper_nouns.jsonのwords配列>}`。 |
| `final_question_ids` | array of string | 確定してセットに収録する `question_id` の列挙（昇順・一意）。減数・不成立で除外したスロットを含めない。1件以上 `requested_count` 件以下でなければならない(MUST)。 |

- **FIN-02（組み立て手順）**: `finalize_set.py` は `set.json` を次の手順で組み立てなければならない(MUST)（前提検査・原子的書き込みの正は `docs/architecture.md` CLI-21）。
  1. stdinメタデータ（FIN-01）のうち `final_question_ids` を除く全フィールドをトップレベルへ転記する（`final_question_ids` は手順4の収集対象の決定と検査にのみ使い、`set.json` には含めない。SET-01 のフィールド目録が正）。
  2. `data/normalized/meta.json` から `data_version`・`source_checksums`（`sources[]` の `file` のファイル名部分をキー、`sha256` を値とする）・出典情報（ATT-01〜ATT-02）を構築する。
  3. stdinの `config_snapshot` が現在の検証済み `data/config/` 2ファイルから構築した値とJSON値として完全一致することを検査し、不一致は E-DATA-08 で停止する。一致したstdin値をset.jsonへ保持し、現在値から再構築して置き換えてはならない。
  4. `final_question_ids`（FIN-01）に列挙された各問題について、合格世代（machine_report と review_result がともに `pass` かつ対応する `review/set_check.<question_id>.<gen>.json` の verdict が `pass` である最大世代）の `review/<question_id>.<gen>.candidate.json` を読み、問題オブジェクトへ複製し、`provenance` を付加する（SET-06）。`final_question_ids` 外のスロットの監査ファイルは収集対象にしてはならない(MUST NOT)。宣言された集合と監査上の合格世代集合が一致しない場合は E-CONTRACT-04 で停止する（`docs/architecture.md` CLI-21 手順5）。
  5. `format` が `grammar_reorder` の場合、各問題の `body` に `answer_tokens` を導出して付加する（FIN-04〜FIN-05）。
  6. `schema_version` に set スキーマ現行版を記入し、SET-07 の一致検証と `set.schema.json` 検証を実施して原子的に書き込む。
- **FIN-03（candidate の不改変）**: 手順4の複製で candidate の内容を書き換えてはならない(MUST NOT)。許される追加は `provenance`（全形式）と `answer_tokens`（grammar_reorder のみ）の2つに限る(MUST)。
- **FIN-04（answer_tokens の導出）**: `answer_tokens` は `body.answer_sentence` から次の決定的手順で導出しなければならない(MUST)。
  1. Unicode NFC 正規化を適用し、U+2019（'）を U+0027（'）に置換する。
  2. 空白文字（U+0020・U+0009）で分割する。
  3. 各要素から句読点6種 `.` `,` `?` `!` `;` `:` を全出現位置で除去する（アポストロフィ・ハイフンは保持する）。
  4. 空文字列になった要素を除去する。
  5. 各要素に Python `str.lower()` を適用する。
- **FIN-05（導出整合）**: FIN-04 の結果は `body.tokens_shuffled` と多重集合として一致し、かつ配列順が `tokens_shuffled` と完全一致しないことを検証しなければならない(MUST)。不成立は E-CONTRACT-01（内部バグ扱い）で停止する（機械検査 `docs/cefrj-validation-spec.md` MC-12 通過済みであれば理論上発生しない）。`answer_tokens` が `set.json` に保存されることにより、HTMLの整序判定（`docs/html-output-spec.md` JDG-03）は保存済み正解トークン列との位置ごとの完全一致で行える。

### 4.5 実例

次の実例は `schemas/set.schema.json`（1.0.0）に適合する。URL・チェックサム・モデル名は例示値であり、実運用では `meta.json` とホストツールの実値を用いる。

**実例1: 語彙4択セット（`vocab_mcq_en2ja`、A2、1問）**

<!-- example:set -->
```json
{
  "schema_version": "1.0.0",
  "set_id": "20260816-142530-k7x2",
  "format": "vocab_mcq_en2ja",
  "level": { "scale": "cefr", "value": "A2" },
  "mode": "explicit",
  "requested_count": 1,
  "topic": null,
  "preferred_proper_nouns": [],
  "created_at": "2026-08-16T14:25:30+09:00",
  "tool": "claude_code",
  "model": "claude-fable-5",
  "data_version": "wl1.6+gp20200220+norm1.0.0",
  "source_checksums": {
    "CEFR-J Wordlist Ver1.6.xlsx": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
    "CEFR-J Grammar Profile full 20200220.xlsx": "a5f2d94d51b1cc7e4c3d0e9b8a716253449fa2c8d7b6e5f4a3b2c1d0e9f8a7b6"
  },
  "config_snapshot": {
    "limits": {
      "schema_version": "1.0.0",
      "sentence_word_limits": { "A1": 10, "A2": 14, "B1": 20, "B2": 26 },
      "explanation_char_limits": { "brief": 200, "detailed": 400 },
      "distractor_reuse_max": 2,
      "generation_max": 3,
      "set_question_max": 20,
      "review_timeout_seconds": 300
    },
    "proper_nouns": ["Ken", "Emi", "Tom", "Tokyo", "Kyoto", "London"]
  },
  "attribution": {
    "wordlist": {
      "citation_ja": "『CEFR-J Wordlist Version 1.6』 東京外国語大学投野由紀夫研究室.（URL: https://www.cefr-j.org/download.html より2026年8月ダウンロード）",
      "citation_en": "The CEFR-J Wordlist Version 1.6. Compiled by Yukio Tono, Tokyo University of Foreign Studies. Retrieved from https://www.cefr-j.org/download.html on 2026-08-16.",
      "url": "https://www.cefr-j.org/download.html",
      "retrieved_date": "2026-08-16",
      "version_label": "1.6"
    },
    "grammar_profile": {
      "citation_ja": "『CEFR-J Grammar Profile』（20200220版） 東京外国語大学投野由紀夫研究室.（URL: https://www.cefr-j.org/download.html より2026年8月ダウンロード）",
      "citation_en": "The CEFR-J Grammar Profile (20200220). Compiled by Yukio Tono, Tokyo University of Foreign Studies. Retrieved from https://www.cefr-j.org/download.html on 2026-08-16.",
      "url": "https://www.cefr-j.org/download.html",
      "retrieved_date": "2026-08-16",
      "version_label": "20200220"
    }
  },
  "questions": [
    {
      "question_id": "q01",
      "format": "vocab_mcq_en2ja",
      "level": { "scale": "cefr", "value": "A2" },
      "target": { "type": "lexical", "ref": "lex:abroad:adverb", "display_name": "abroad" },
      "body": {
        "stem": "My sister studied abroad last year.",
        "target_surface": "abroad",
        "stem_ja": "私の姉は昨年、海外で勉強しました。",
        "choices": [
          {
            "text": "最近",
            "is_correct": false,
            "anchor": { "entry_id": "lex:recently:adverb", "headword": "recently", "pos": "adverb", "level": "A2" },
            "gloss": "最近"
          },
          {
            "text": "海外で、海外へ",
            "is_correct": true,
            "anchor": { "entry_id": "lex:abroad:adverb", "headword": "abroad", "pos": "adverb", "level": "A2" },
            "gloss": "海外で、海外へ"
          },
          {
            "text": "ゆっくりと",
            "is_correct": false,
            "anchor": { "entry_id": "lex:slowly:adverb", "headword": "slowly", "pos": "adverb", "level": "A2" },
            "gloss": "ゆっくりと"
          },
          {
            "text": "簡単に",
            "is_correct": false,
            "anchor": { "entry_id": "lex:easily:adverb", "headword": "easily", "pos": "adverb", "level": "A2" },
            "gloss": "簡単に"
          }
        ],
        "pos_pool_relaxed": false
      },
      "provenance": {
        "generation": "gen1",
        "candidate_ref": "review/q01.gen1.candidate.json",
        "machine_report_ref": "review/q01.gen1.machine.json",
        "review_ref": "review/q01.gen1.review.json"
      }
    }
  ]
}
```

**実例2: 語句整序セット（`grammar_reorder`、A1.1、1問。`answer_tokens` を含む）**

<!-- example:set -->
```json
{
  "schema_version": "1.0.0",
  "set_id": "20260816-153012-b8m4",
  "format": "grammar_reorder",
  "level": { "scale": "cefrj", "value": "A1.1" },
  "mode": "proposal",
  "requested_count": 1,
  "topic": "学校生活",
  "preferred_proper_nouns": [],
  "created_at": "2026-08-16T15:30:12+09:00",
  "tool": "codex",
  "model": "gpt-5.6-sol",
  "data_version": "wl1.6+gp20200220+norm1.0.0",
  "source_checksums": {
    "CEFR-J Wordlist Ver1.6.xlsx": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
    "CEFR-J Grammar Profile full 20200220.xlsx": "a5f2d94d51b1cc7e4c3d0e9b8a716253449fa2c8d7b6e5f4a3b2c1d0e9f8a7b6"
  },
  "config_snapshot": {
    "limits": {
      "schema_version": "1.0.0",
      "sentence_word_limits": { "A1": 10, "A2": 14, "B1": 20, "B2": 26 },
      "explanation_char_limits": { "brief": 200, "detailed": 400 },
      "distractor_reuse_max": 2,
      "generation_max": 3,
      "set_question_max": 20,
      "review_timeout_seconds": 300
    },
    "proper_nouns": ["Ken", "Emi", "Tom", "Tokyo", "Kyoto", "London"]
  },
  "attribution": {
    "wordlist": {
      "citation_ja": "『CEFR-J Wordlist Version 1.6』 東京外国語大学投野由紀夫研究室.（URL: https://www.cefr-j.org/download.html より2026年8月ダウンロード）",
      "citation_en": "The CEFR-J Wordlist Version 1.6. Compiled by Yukio Tono, Tokyo University of Foreign Studies. Retrieved from https://www.cefr-j.org/download.html on 2026-08-16.",
      "url": "https://www.cefr-j.org/download.html",
      "retrieved_date": "2026-08-16",
      "version_label": "1.6"
    },
    "grammar_profile": {
      "citation_ja": "『CEFR-J Grammar Profile』（20200220版） 東京外国語大学投野由紀夫研究室.（URL: https://www.cefr-j.org/download.html より2026年8月ダウンロード）",
      "citation_en": "The CEFR-J Grammar Profile (20200220). Compiled by Yukio Tono, Tokyo University of Foreign Studies. Retrieved from https://www.cefr-j.org/download.html on 2026-08-16.",
      "url": "https://www.cefr-j.org/download.html",
      "retrieved_date": "2026-08-16",
      "version_label": "20200220"
    }
  },
  "questions": [
    {
      "question_id": "q01",
      "format": "grammar_reorder",
      "level": { "scale": "cefrj", "value": "A1.1" },
      "target": { "type": "grammar", "ref": "gp:239", "display_name": "WH-疑問文: What ...?" },
      "body": {
        "tokens_shuffled": ["lunch", "do", "what", "you", "for", "want"],
        "answer_tokens": ["what", "do", "you", "want", "for", "lunch"],
        "answer_sentence": "What do you want for lunch?",
        "example_ja": "あなたは昼食に何が欲しいですか。"
      },
      "explanation": {
        "type": "brief",
        "text": "WH-疑問文: What ...? では、たずねたい内容を表す疑問詞 what を文の先頭に置き、その後に do+主語+動詞の原形の語順を続けます。What do you want で「あなたは何が欲しいですか」となり、最後に for lunch（昼食に）を置きます。平叙文と同じ you want の語順のままでは疑問文になりません。"
      },
      "provenance": {
        "generation": "gen1",
        "candidate_ref": "review/q01.gen1.candidate.json",
        "machine_report_ref": "review/q01.gen1.machine.json",
        "review_ref": "review/q01.gen1.review.json"
      }
    }
  ]
}
```

## 5. 9形式ペイロード定義

- **PAY-01**: `body` のフィールド構成は形式コードにより次のとおり判別され（`schemas/set.schema.json` / `schemas/candidate.schema.json` の oneOf + `format` const）、次表以外のフィールドを含んではならない(MUST NOT)。内容規則（何をどう書くか）の正は `docs/question-generation-spec.md` の各形式節であり、本表は構造の正である。

### 5.1 `vocab_mcq_en2ja`（①）

| フィールド | 型 | 説明 |
|---|---|---|
| `stem` | string | 対象語をちょうど1回含む英例文 |
| `target_surface` | string | `stem` 中の対象語の表層形 |
| `stem_ja` | string | `stem` の日本語訳（解答後表示用） |
| `choices` | array(4) | PAY-10 の語彙選択肢。`text` は日本語語義 |
| `pos_pool_relaxed` | boolean | 誤答プール緩和の記録（GEN-15） |

### 5.2 `vocab_mcq_ja2en`（②）

| フィールド | 型 | 説明 |
|---|---|---|
| `stem` | string | 対象語の日本語語義（設問） |
| `sentence_with_blank` | string | 空欄 `____` を1箇所含む英例文（PAY-11） |
| `sentence_complete` | string | 空欄を `target_surface` で置換した完成文 |
| `target_surface` | string | 空欄に入る表層形（headword と同一） |
| `sentence_ja` | string | 完成文の日本語訳（解答後表示用） |
| `choices` | array(4) | PAY-10 の語彙選択肢。`text` は headword |
| `pos_pool_relaxed` | boolean | 誤答プール緩和の記録 |

### 5.3 / 5.4 `vocab_flashcard_en2ja`（③）・`vocab_flashcard_ja2en`（④）

両形式は同一構造である（提示面の違いはHTML仕様が定める）。

| フィールド | 型 | 説明 |
|---|---|---|
| `headword` | string | 対象語の見出し語（`target.ref` と一致） |
| `pos` | string | Wordlist pos 15種の値そのまま |
| `gloss` | string | 日本語語義 |
| `example` | object | `{"en": string, "ja": string}` |
| `target_surface` | string | `example.en` 中の対象語の表層形 |

### 5.5 `grammar_mcq`（⑤）

| フィールド | 型 | 説明 |
|---|---|---|
| `sentence_with_blank` | string | 空欄 `____` を1箇所含む英文 |
| `choices` | array(4) | `{"text", "is_correct"}` の4肢（正解1肢） |
| `example_ja` | string | 完成文（先行文脈含む）の日本語訳 |
| `context_sentence` | string \| null | 2文例外の先行文脈（PAY-12） |
| `context_required_by` | string \| null | 2文例外の要求元文タイプ（PAY-12） |

### 5.6 `grammar_cloze`（⑥）

| フィールド | 型 | 説明 |
|---|---|---|
| `sentence_with_blank` | string | 空欄 `____` を1箇所含む英文 |
| `cue` | string \| null | 内容語の原形ヒント（GEN-30a）。機能語のみの正答では `null` |
| `answer` | string | 正解の代表形 |
| `answer_equivalents` | array of string | 同値表記の全列挙（空配列可、重複禁止） |
| `example_ja` | string | 完成文の日本語訳 |
| `context_sentence` | string \| null | PAY-12 |
| `context_required_by` | string \| null | PAY-12 |

### 5.7 `grammar_reorder`（⑦）

| フィールド | 型 | candidate | set.json | 説明 |
|---|---|---|---|---|
| `tokens_shuffled` | array of string | 必須 | 必須 | シャッフル済みトークン列（全小文字・句読点なし・4トークン以上） |
| `answer_tokens` | array of string | 存在してはならない(MUST NOT) | 必須 | 正解順トークン列。`finalize_set.py` が FIN-04 で導出（生成エージェントに書かせない） |
| `answer_sentence` | string | 必須 | 必須 | 正書法どおりの正解文 |
| `example_ja` | string | 必須 | 必須 | 正解文の日本語訳 |

### 5.8 `grammar_rewrite`（⑧）

| フィールド | 型 | 説明 |
|---|---|---|
| `source_sentence` | string | 元文（対象構造を含まない） |
| `instruction` | string | 書き換え指示（日本語） |
| `target_sentence_with_blank` | string | 空欄 `____` を1箇所含む目標文 |
| `answer` | string | 空欄に入る語列の代表形 |
| `answer_equivalents` | array of string | 同値表記の全列挙（空配列可） |
| `source_ja` | string | 元文の日本語訳 |
| `target_ja` | string | 目標文完成形の日本語訳 |

### 5.9 `grammar_example_selfcheck`（⑨）

| フィールド | 型 | 説明 |
|---|---|---|
| `example` | object | `{"en": string, "ja": string}` |
| `context_sentence` | string \| null | PAY-12 |
| `context_required_by` | string \| null | PAY-12 |

### 5.10 共通部品

- **PAY-10（語彙選択肢）**: 語彙4択の `choices[]` 要素は `{"text": string, "is_correct": boolean, "anchor": {"entry_id", "headword", "pos", "level"}, "gloss": string}` とする。`anchor` は誤答由来の機械照合（`docs/cefrj-validation-spec.md` MC-23）の入力である。正解肢の `anchor.entry_id` は `target.ref` と一致しなければならない(MUST)。
- **PAY-11（空欄記法）**: 空欄を含む文フィールド（`sentence_with_blank` / `target_sentence_with_blank`）は、半角アンダースコア4連 `____` をちょうど1箇所含み、それ以外にアンダースコアを含んではならない(MUST NOT)（スキーマのパターン `^[^_]*____[^_]*$` で強制）。
- **PAY-12（2文例外の記録）**: `context_sentence` と `context_required_by` は対で記録する(MUST)。2文例外（`docs/question-generation-spec.md` GEN-06）を使わない場合は両方 `null`、使う場合は両方非nullでなければならない(MUST)（対の整合はスキーマでは片側nullを排除できないため、機械検査 `docs/cefrj-validation-spec.md` MC-08 と candidate 自己点検が検証する）。`context_required_by` にはITEM LIST文タイプ列の文字列をそのまま記録する。
- **PAY-13（選択肢順序の固定）**: `choices[]` と `tokens_shuffled[]` の配列順は生成時に確定した提示順であり、以降のどの工程でも並べ替えてはならない(MUST NOT)（`docs/html-output-spec.md` DET-04）。

## 6. 監査ファイル仕様

配置・命名・書き込みタイミングの正は `docs/subagent-review-spec.md` 第8節。本節は各ファイルの内容を定める。

- **AUD-01（candidate: `<question_id>.<gen>.candidate.json`）**: `schemas/candidate.schema.json` に適合する1問分の候補。第4.2節の問題オブジェクトから `provenance` を除いた形であり、grammar_reorder では `answer_tokens` を含まない（第5.7節）。`schema_version` フィールドを持たない（SV-03）。保存時は正準形に再直列化する（JS-02）。
- **AUD-02（machine_report: `<question_id>.<gen>.machine.json` / `set_check.*.json`）**: `schemas/machine_report.schema.json` に適合するレポート。`machine_check.py` の出力は `scope: "question"`、`set_check.py` の出力は `scope: "set"` とする（AUD-03〜AUD-05）。
- **AUD-03（machine_report 共通フィールド）**:

| フィールド | 型 | 説明 |
|---|---|---|
| `schema_version` | string | machine_report スキーマのsemver |
| `data_version` | string | 検査に使用した正規化データの版 |
| `generated_at` | string | 生成日時（ISO 8601）。唯一の実行毎可変フィールド（JS-03） |
| `scope` | string | `question` / `set` |
| `set_id` | string | セットID |
| `verdict` | string | `pass` / `fail`。`violations` が1件以上なら `fail`（MC-02） |
| `violations` | array | `{code, location, evidence, expected_level, actual_level, suggestion}`。レベルと無関係な違反では `expected_level` / `actual_level` は `null` |
| `warnings` | array | `{code, location, message}`。verdict に影響しない |

- **AUD-04（scope=question の追加フィールド）**: `question_id`・`generation`（`gen1|gen2|gen3`）・`format`・`level`・`spacy_model`（`en_core_web_sm` 固定）・`spacy_model_version`・`stats`。`violations[].code` は machine_check の19コード（`docs/cefrj-validation-spec.md` MC-28）のみ、`warnings[].code` は3コード（MC-29）のみ。`stats` は次の構造とする(MUST):
  - `texts[]`: 英文検査対象ごとに `{field, text, sentence_count, word_count, tokens[]}`。`tokens[]` の各要素は `{surface, lemma, upos, tag, decision, matched_entry_id, level, exemption_class}`（`decision` は `multiword_match` / `wordlist_match` / `allowlist` / `exempt` / `target` / `violation` の6値、`exemption_class` は `punct_sym_space` / `numeric` / `possessive` / `contraction_fragment` / `null`）。
  - `explanation_char_count`: 解説の字数（S7の計測値）。解説を持たない語彙4形式では `null`。
- **AUD-05（scope=set の追加フィールド）**: `target_question_id`（増分検査で加えた候補の `question_id`。全体最終検査 `set_check.final.json` では `null`）・`checked_question_ids[]`（検査範囲の問題ID昇順）。`violations[].code` は `V-SET-01`〜`V-SET-03` のみ。`warnings` は常に空配列とする(MUST)。
- **AUD-06（field 記法）**: `stats.texts[].field` は検査対象テキストの所在を次の記法で記録しなければならない(MUST)。
  - candidate 内の実フィールド: ドット区切りパス（例 `body.stem`、`body.source_sentence`、`body.example.en`、`body.context_sentence`）。
  - 空欄置換による合成文: `<空欄フィールドパス>#filled:answer`（正答で置換）または `<空欄フィールドパス>#filled:choices[k]`（k=0〜3。選択肢kの `text` で置換。grammar_mcq の誤答検査文）。
- **AUD-07（review_result: `<question_id>.<gen>.review.json`）**: `schemas/review_result.schema.json` に適合するレビュー結果。フィールド:

| フィールド | 型 | 説明 |
|---|---|---|
| `schema_version` / `set_id` / `question_id` / `generation` | string | 識別情報（`generation` は `gen1|gen2|gen3`） |
| `verdict` | string | レビュアー担当項目のみの判定 `pass` / `fail` |
| `checks` | array(19) | `{check_id, result, note}`。CHK-01〜CHK-19 をちょうど1件ずつ（欠番・重複はスキーマで拒否）。`result` は `pass`/`fail`/`not_applicable`。CHK-18 に `fail` はない |
| `sentence_grammar_inventory` | array | 例文文法構造インベントリ。各要素は `{structure, span, level_source, grammar_item_id, level, evidence}`。`level_source: "kyoinban"` では `grammar_item_id`=gp ID・`level`=教員版値（範囲値可）、`level_source: "reviewer_estimate"` では `grammar_item_id`=null・`level`=推定導入レベル（cefrj単一値）。両者はスキーマ上も常に機械判別可能（LS-05） |
| `violations` | array | `{code, location, evidence, expected_level, actual_level, suggestion}`。`code` は CHK-01〜CHK-17・CHK-19（CHK-18を除く）。`verdict: "fail"` なら1件以上、`pass` なら0件（スキーマで強制） |
| `machine_check_disputes` | array | `{machine_violation_code, location, dispute_type, claim, evidence, suggested_correction}`。`dispute_type` は `lemmatization`/`pos_tagging`/`multiword_match`/`exemption`/`measurement` の5値。該当なしは空配列 |

  記入規則（何をどう書くか）の正は `docs/subagent-review-spec.md` RR-01〜RR-05・FP-01〜FP-05。
- **AUD-08（review_request）**: レビュアー入力封筒は `schemas/review_request.schema.json` の検証を通過してからレビュアーに渡さなければならない(MUST)（RC-08）。検証通過済みの封筒は、レビュアー起動直前に監査ファイル `review/<question_id>.<gen>.request.json` として正準形（JS-02）で保存しなければならない(MUST)（レビュアーには封筒のファイルパスを渡す。配置・書き込みタイミングの正は `docs/subagent-review-spec.md` AU-02）。フィールド:

| フィールド | 型 | 説明 |
|---|---|---|
| `schema_version` / `set_id` / `question_id` / `generation` / `format` / `level` | — | 識別情報 |
| `target_ref` | string | 語彙= lex ID、文法= gp ID |
| `level_limits` | object | `{"vocabulary_level_max": cefr値, "grammar_intro_level_max": cefrj値}`。オーケストレータが `docs/cefrj-validation-spec.md` LVL-09〜LVL-11 で算出 |
| `candidate` | object | 候補JSON全体（candidate スキーマ検証通過済み。封筒スキーマでは再検証しない） |
| `machine_report` | object | 機械検査レポート全体（machine_report スキーマ検証通過済み） |
| `constraints_snapshot` | object | `{"limits": {"sentence_word_limit": int, "explanation_char_limit": int\|null}, "proper_nouns": [...], "topic": string\|null}` |
| `readable_resources` | array of string | 読み取り許可パス一覧（許可範囲の正は RC-10） |

- **AUD-09（invalid テキストファイル）**: `*.invalid<k>.txt` は、UTF-8で保持できる生成生出力テキスト全文と、その後に区切り行 `---- validation error ----` を挟んで受理検証診断を連結したUTF-8テキストとしなければならない(MUST)。診断は、`validate.py`がstdoutを返した場合はそのJSON全文、stdoutがない場合はstderrのCLI-05 JSON全文、厳格パース・JS-01正準化で失敗した場合は失敗段階・例外型・理由・取得可能な位置を含むUTF-8テキストとする。ホストが受け取った生成テキスト自体を孤立サロゲート等によりUTF-8化できない場合は、置換文字やエスケープで生出力を改変保存せず、UTF-8化不能の理由と取得可能な位置だけを記録する。プロセス失敗で出力が得られない場合は、エラー情報（終了コード・stderr）のみを記録する。
- **AUD-10（不変性）**: 監査ファイルは書き込み後に変更・削除してはならない(MUST NOT)（`docs/subagent-review-spec.md` AU-05）。

### 6.1 実例

**実例3: candidate（`grammar_cloze`、A1.2）**

<!-- example:candidate -->
```json
{
  "question_id": "q01",
  "format": "grammar_cloze",
  "level": { "scale": "cefrj", "value": "A1.2" },
  "target": { "type": "grammar", "ref": "gp:61", "display_name": "現在進行形" },
  "body": {
    "sentence_with_blank": "My father ____ his car now.",
    "cue": "wash",
    "answer": "is washing",
    "answer_equivalents": ["'s washing"],
    "example_ja": "父は今、車を洗っています。",
    "context_sentence": null,
    "context_required_by": null
  },
  "explanation": {
    "type": "brief",
    "text": "now があるので、今まさに進行中の動作を表す現在進行形（be動詞+動詞の-ing形）を使います。主語の My father は3人称単数なので be動詞は is になり、wash に -ing を付けて is washing とします。's washing と短縮して書くこともできます。washes のような現在形は習慣を表すため、ここでは使えません。"
  }
}
```

**実例4: machine_report（scope=question、`grammar_mcq` A2.2、語彙レベル超過で fail）**

<!-- example:machine_report -->
```json
{
  "schema_version": "1.1.0",
  "data_version": "wl1.6+gp20200220+norm1.0.0",
  "generated_at": "2026-08-16T14:26:02+09:00",
  "scope": "question",
  "set_id": "20260816-142530-k7x2",
  "question_id": "q01",
  "generation": "gen1",
  "format": "grammar_mcq",
  "level": { "scale": "cefrj", "value": "A2.2" },
  "spacy_model": "en_core_web_sm",
  "spacy_model_version": "3.7.1",
  "verdict": "fail",
  "violations": [
    {
      "code": "V-LEX-02",
      "location": "body.sentence_with_blank#filled:choices[1] token 2: \"abandoned\"",
      "evidence": "wordlist lex:abandon:verb（headword \"abandon\", pos \"verb\", level \"B1\"）",
      "expected_level": "A2",
      "actual_level": "B1",
      "suggestion": "A2以下の動詞に置き換えてください。"
    }
  ],
  "warnings": [],
  "stats": {
    "texts": [
      {
        "field": "body.sentence_with_blank#filled:choices[1]",
        "text": "The team abandoned the plan last night.",
        "sentence_count": 1,
        "word_count": 7,
        "tokens": [
          { "surface": "The", "lemma": "the", "upos": "DET", "tag": "DT", "decision": "wordlist_match", "matched_entry_id": "lex:the:determiner", "level": "A1", "exemption_class": null },
          { "surface": "team", "lemma": "team", "upos": "NOUN", "tag": "NN", "decision": "wordlist_match", "matched_entry_id": "lex:team:noun", "level": "A1", "exemption_class": null },
          { "surface": "abandoned", "lemma": "abandon", "upos": "VERB", "tag": "VBD", "decision": "violation", "matched_entry_id": "lex:abandon:verb", "level": "B1", "exemption_class": null },
          { "surface": "the", "lemma": "the", "upos": "DET", "tag": "DT", "decision": "wordlist_match", "matched_entry_id": "lex:the:determiner", "level": "A1", "exemption_class": null },
          { "surface": "plan", "lemma": "plan", "upos": "NOUN", "tag": "NN", "decision": "wordlist_match", "matched_entry_id": "lex:plan:noun", "level": "A2", "exemption_class": null },
          { "surface": "last", "lemma": "last", "upos": "ADJ", "tag": "JJ", "decision": "wordlist_match", "matched_entry_id": "lex:last:adjective", "level": "A1", "exemption_class": null },
          { "surface": "night", "lemma": "night", "upos": "NOUN", "tag": "NN", "decision": "wordlist_match", "matched_entry_id": "lex:night:noun", "level": "A1", "exemption_class": null },
          { "surface": ".", "lemma": ".", "upos": "PUNCT", "tag": ".", "decision": "exempt", "matched_entry_id": null, "level": null, "exemption_class": "punct_sym_space" }
        ]
      }
    ],
    "explanation_char_count": 132
  }
}
```

**実例5: machine_report（scope=set、増分セット横断検査、pass）**

<!-- example:machine_report -->
```json
{
  "schema_version": "1.1.0",
  "data_version": "wl1.6+gp20200220+norm1.0.0",
  "generated_at": "2026-08-16T14:40:11+09:00",
  "scope": "set",
  "set_id": "20260816-142530-k7x2",
  "target_question_id": "q02",
  "checked_question_ids": ["q01", "q02"],
  "verdict": "pass",
  "violations": [],
  "warnings": []
}
```

**実例6: review_request（`grammar_cloze` A1.2。candidate は実例3、machine_report は pass）**

<!-- example:review_request -->
```json
{
  "schema_version": "1.0.0",
  "set_id": "20260816-160500-c2w9",
  "question_id": "q01",
  "generation": "gen1",
  "format": "grammar_cloze",
  "level": { "scale": "cefrj", "value": "A1.2" },
  "target_ref": "gp:61",
  "level_limits": {
    "vocabulary_level_max": "A1",
    "grammar_intro_level_max": "A1.2"
  },
  "candidate": {
    "question_id": "q01",
    "format": "grammar_cloze",
    "level": { "scale": "cefrj", "value": "A1.2" },
    "target": { "type": "grammar", "ref": "gp:61", "display_name": "現在進行形" },
    "body": {
      "sentence_with_blank": "My father ____ his car now.",
      "cue": "wash",
      "answer": "is washing",
      "answer_equivalents": ["'s washing"],
      "example_ja": "父は今、車を洗っています。",
      "context_sentence": null,
      "context_required_by": null
    },
    "explanation": {
      "type": "brief",
      "text": "now があるので、今まさに進行中の動作を表す現在進行形（be動詞+動詞の-ing形）を使います。主語の My father は3人称単数なので be動詞は is になり、wash に -ing を付けて is washing とします。's washing と短縮して書くこともできます。washes のような現在形は習慣を表すため、ここでは使えません。"
    }
  },
  "machine_report": {
    "schema_version": "1.1.0",
    "data_version": "wl1.6+gp20200220+norm1.0.0",
    "generated_at": "2026-08-16T16:05:31+09:00",
    "scope": "question",
    "set_id": "20260816-160500-c2w9",
    "question_id": "q01",
    "generation": "gen1",
    "format": "grammar_cloze",
    "level": { "scale": "cefrj", "value": "A1.2" },
    "spacy_model": "en_core_web_sm",
    "spacy_model_version": "3.7.1",
    "verdict": "pass",
    "violations": [],
    "warnings": [],
    "stats": {
      "texts": [
        {
          "field": "body.sentence_with_blank#filled:answer",
          "text": "My father is washing his car now.",
          "sentence_count": 1,
          "word_count": 7,
          "tokens": [
            { "surface": "My", "lemma": "my", "upos": "PRON", "tag": "PRP$", "decision": "wordlist_match", "matched_entry_id": "lex:my:pronoun", "level": "A1", "exemption_class": null },
            { "surface": "father", "lemma": "father", "upos": "NOUN", "tag": "NN", "decision": "wordlist_match", "matched_entry_id": "lex:father:noun", "level": "A1", "exemption_class": null },
            { "surface": "is", "lemma": "be", "upos": "AUX", "tag": "VBZ", "decision": "wordlist_match", "matched_entry_id": "lex:be:be-verb", "level": "A1", "exemption_class": null },
            { "surface": "washing", "lemma": "wash", "upos": "VERB", "tag": "VBG", "decision": "wordlist_match", "matched_entry_id": "lex:wash:verb", "level": "A1", "exemption_class": null },
            { "surface": "his", "lemma": "his", "upos": "PRON", "tag": "PRP$", "decision": "wordlist_match", "matched_entry_id": "lex:his:pronoun", "level": "A1", "exemption_class": null },
            { "surface": "car", "lemma": "car", "upos": "NOUN", "tag": "NN", "decision": "wordlist_match", "matched_entry_id": "lex:car:noun", "level": "A1", "exemption_class": null },
            { "surface": "now", "lemma": "now", "upos": "ADV", "tag": "RB", "decision": "wordlist_match", "matched_entry_id": "lex:now:adverb", "level": "A1", "exemption_class": null },
            { "surface": ".", "lemma": ".", "upos": "PUNCT", "tag": ".", "decision": "exempt", "matched_entry_id": null, "level": null, "exemption_class": "punct_sym_space" }
          ]
        }
      ],
      "explanation_char_count": 156
    }
  },
  "constraints_snapshot": {
    "limits": { "sentence_word_limit": 10, "explanation_char_limit": 200 },
    "proper_nouns": ["Ken", "Emi", "Tom", "Tokyo", "Kyoto", "London"],
    "topic": null
  },
  "readable_resources": [
    "data/normalized/lexicon.json",
    "data/normalized/grammar.json",
    "data/normalized/meta.json",
    "data/config/limits.json",
    "data/config/proper_nouns.json",
    "docs/cefrj-validation-spec.md",
    "docs/subagent-review-spec.md",
    "agent/reviewer-core.md"
  ]
}
```

**実例7: review_result（ゴールデンケース: `vocab_mcq_en2ja` A1 の these の例文に関係節が混入 → fail）**

<!-- example:review_result -->
```json
{
  "schema_version": "1.0.0",
  "set_id": "20260816-142530-k7x2",
  "question_id": "q03",
  "generation": "gen1",
  "verdict": "fail",
  "checks": [
    { "check_id": "CHK-01", "result": "not_applicable", "note": "形式①のため。" },
    { "check_id": "CHK-02", "result": "pass", "note": "these は代名詞として代表語義で使われています。" },
    { "check_id": "CHK-03", "result": "fail", "note": "例文に関係代名詞節が含まれ、許容上限 A1.3 を超えます。" },
    { "check_id": "CHK-04", "result": "pass", "note": "対象語以外の語彙用法に上限超はありません。" },
    { "check_id": "CHK-05", "result": "pass", "note": "誤答語義はいずれも例文中の these の語義として成立しません。" },
    { "check_id": "CHK-06", "result": "pass", "note": "誤答は正解の同義語・別義と重なりません。" },
    { "check_id": "CHK-07", "result": "not_applicable", "note": "形式①のため。" },
    { "check_id": "CHK-08", "result": "pass", "note": "語義は辞書形式・品詞反映、訳は忠実で自然です。" },
    { "check_id": "CHK-09", "result": "not_applicable", "note": "形式①のため。" },
    { "check_id": "CHK-10", "result": "not_applicable", "note": "形式①のため。" },
    { "check_id": "CHK-11", "result": "pass", "note": "英文は文法的で自然です。" },
    { "check_id": "CHK-12", "result": "pass", "note": "内容は中立で教室での使用に問題ありません。" },
    { "check_id": "CHK-13", "result": "pass", "note": "CHK-03 で検出した構造以外にレベル超の前提知識はありません。" },
    { "check_id": "CHK-14", "result": "not_applicable", "note": "形式①のため。" },
    { "check_id": "CHK-15", "result": "not_applicable", "note": "形式①のため。" },
    { "check_id": "CHK-16", "result": "not_applicable", "note": "形式①のため。" },
    { "check_id": "CHK-17", "result": "not_applicable", "note": "例文が1文のため。" },
    { "check_id": "CHK-18", "result": "pass", "note": "機械検査レポートを精査しました。誤検出の疑いはありません。" },
    { "check_id": "CHK-19", "result": "not_applicable", "note": "トピック指定なしのため。" }
  ],
  "sentence_grammar_inventory": [
    {
      "structure": "指示代名詞(these/those)+be",
      "span": "These are the books",
      "level_source": "kyoinban",
      "grammar_item_id": "gp:9",
      "level": "A1.2-A1.3",
      "evidence": "教員版 ID 9 CEFR-J level A1.2-A1.3（導入 A1.2）"
    },
    {
      "structure": "定冠詞",
      "span": "the books",
      "level_source": "kyoinban",
      "grammar_item_id": "gp:14",
      "level": "A1.1",
      "evidence": "教員版 ID 14 CEFR-J level A1.1"
    },
    {
      "structure": "関係代名詞(目的格)(that)",
      "span": "the books that I bought yesterday",
      "level_source": "kyoinban",
      "grammar_item_id": "gp:178",
      "level": "A2.2-B2.2",
      "evidence": "教員版 ID 178 CEFR-J level A2.2-B2.2（導入 A2.2）"
    }
  ],
  "violations": [
    {
      "code": "CHK-03",
      "location": "body.stem: \"the books that I bought yesterday\"",
      "evidence": "level_source=kyoinban / gp:178 関係代名詞(目的格)(that) / CEFR-J level \"A2.2-B2.2\"（導入レベル A2.2）",
      "expected_level": "A1.3",
      "actual_level": "A2.2",
      "suggestion": "関係節を削除し、例文を These are my books. に差し替えてください。"
    }
  ],
  "machine_check_disputes": []
}
```

## 7. 正規化データ・設定ファイルの構造

変換規則（xlsx→JSON）の正は `docs/cefrj-validation-spec.md` 第2節。本節は構造の要点とスキーマの対応を定める。

- **NDS-01（lexicon.json）**: トップレベルは `{"schema_version", "data_version", "entries": [...], "groups": [...]}`。エントリは `{id, headword, pos, level, core_inventory_1, core_inventory_2, threshold, is_multiword, group_ids}`、グループは `{group_id, headword_joined, pos, level, member_ids}`。構造の機械検証は `schemas/normalized_lexicon.schema.json`。
- **NDS-02（grammar.json）**: トップレベルは `{"schema_version", "data_version", "efl_corpus": {...}, "entries": [...]}`。エントリは `{id, item_list_id, parent_id, display_name, target_eligible, item_list: {...}, kyoinban: {...}, level: {min, max, source, inherited_from}, efl: {...}\|null}`。`kyoinban.present` と `level.source` の3分岐（`kyoinban_direct` / `kyoinban_inherited` / `null`）はスキーマの oneOf で強制される。構造の機械検証は `schemas/normalized_grammar.schema.json`。
- **NDS-03（limits.json）**: `{"schema_version", "sentence_word_limits": {A1,A2,B1,B2}, "explanation_char_limits": {brief,detailed}, "distractor_reuse_max", "generation_max", "set_question_max", "review_timeout_seconds"}`。変更可能なのはこのファイルの値のみである（`docs/cefrj-validation-spec.md` VAL-CFG-01）。
- **NDS-04（proper_nouns.json）**: `{"schema_version", "words": [...]}`。`words` の各語は空白を含まない1トークンでなければならない(MUST)（機械検査の allowlist 照合が1トークン単位のため。スキーマのパターンで強制）。
- **NDS-05（正準形）**: `data/normalized/` の3ファイルと `data/config/` の2ファイルは JS-01 の正準形で保存しなければならない(MUST)（正規化ゴールデンのバイト一致テストの前提。`docs/testing-and-acceptance.md`）。
- **NDS-06（出典ヘッダー）**: `data/normalized/` の出典追跡情報は、`lexicon.json` / `grammar.json` の `data_version` と `meta.json.sources` の組で表現する。`lexicon.json` / `grammar.json` にスキーマ外の出典フィールドを追加してはならない(MUST NOT)。

### 7.1 実例

**実例8: normalized_lexicon（抜粋構造。件数は例示）**

<!-- example:normalized_lexicon -->
```json
{
  "schema_version": "1.0.0",
  "data_version": "wl1.6+gp20200220+norm1.0.0",
  "entries": [
    {
      "id": "lex:A.M.:adverb",
      "headword": "A.M.",
      "pos": "adverb",
      "level": "A1",
      "core_inventory_1": null,
      "core_inventory_2": null,
      "threshold": null,
      "is_multiword": false,
      "group_ids": ["grp:a.m.:adverb"]
    },
    {
      "id": "lex:a.m.:adverb",
      "headword": "a.m.",
      "pos": "adverb",
      "level": "A1",
      "core_inventory_1": null,
      "core_inventory_2": null,
      "threshold": null,
      "is_multiword": false,
      "group_ids": ["grp:a.m.:adverb"]
    },
    {
      "id": "lex:abroad:adverb",
      "headword": "abroad",
      "pos": "adverb",
      "level": "A2",
      "core_inventory_1": null,
      "core_inventory_2": null,
      "threshold": null,
      "is_multiword": false,
      "group_ids": []
    },
    {
      "id": "lex:CD player:noun",
      "headword": "CD player",
      "pos": "noun",
      "level": "A1",
      "core_inventory_1": "技術",
      "core_inventory_2": null,
      "threshold": null,
      "is_multiword": true,
      "group_ids": []
    }
  ],
  "groups": [
    {
      "group_id": "grp:a.m.:adverb",
      "headword_joined": "a.m./A.M.",
      "pos": "adverb",
      "level": "A1",
      "member_ids": ["lex:a.m.:adverb", "lex:A.M.:adverb"]
    }
  ]
}
```

**実例9: normalized_grammar（抜粋構造。gp:1 直接付与・gp:1-1 継承・gp:36 未付与）**

<!-- example:normalized_grammar -->
```json
{
  "schema_version": "1.0.0",
  "data_version": "wl1.6+gp20200220+norm1.0.0",
  "efl_corpus": {
    "words": { "A1": 168156, "A2": 283441, "B1": 490788, "B2": 586086, "C1": 273078 },
    "books": { "A1": 17, "A2": 21, "B1": 26, "B2": 23, "C1": 8 }
  },
  "entries": [
    {
      "id": "gp:1",
      "item_list_id": "1",
      "parent_id": null,
      "display_name": "人称代名詞主格(I)+be: I am",
      "target_eligible": true,
      "item_list": {
        "name_ja": "人称代名詞主格(I)+be動詞",
        "sentence_type_ja": null,
        "shorthand_code": "PRP.I.be",
        "grammatical_item_en": "PERSONAL PRONOUNS (SUBJECTIVE) + BE",
        "sentence_type_en": null,
        "note": null,
        "pattern_shorthand": "I + am",
        "regex_treetagger": "\\bI_PP_I am_VBP_be\\b"
      },
      "kyoinban": {
        "present": true,
        "name_ja": "人称代名詞主格(I)+be: I am",
        "name_simple_ja": "人称代名詞主格(I)+be: I am",
        "name_en": "Personal pronouns (subjective) + be",
        "level_raw": "A1.1-A1.2"
      },
      "level": {
        "min": "A1.1",
        "max": "A1.2",
        "source": "kyoinban_direct",
        "inherited_from": null
      },
      "efl": {
        "rel_freq": { "A1": 1200.5, "A2": 900.2, "B1": 700.1, "B2": 500.3, "C1": 300.4 },
        "range": { "A1": 17, "A2": 21, "B1": 26, "B2": 23, "C1": 8 }
      }
    },
    {
      "id": "gp:1-1",
      "item_list_id": "1-1",
      "parent_id": "gp:1",
      "display_name": "人称代名詞主格(I)+be(疑問文)",
      "target_eligible": false,
      "item_list": {
        "name_ja": "人称代名詞主格(I)+be(疑問文)",
        "sentence_type_ja": "疑問文",
        "shorthand_code": "PRP.I.be.q",
        "grammatical_item_en": "PERSONAL PRONOUNS (SUBJECTIVE) + BE",
        "sentence_type_en": "interrogative",
        "note": null,
        "pattern_shorthand": "am + I",
        "regex_treetagger": "\\bam_VBP_be I_PP_I\\b"
      },
      "kyoinban": {
        "present": false,
        "name_ja": null,
        "name_simple_ja": null,
        "name_en": null,
        "level_raw": null
      },
      "level": {
        "min": "A1.1",
        "max": "A1.2",
        "source": "kyoinban_inherited",
        "inherited_from": "gp:1"
      },
      "efl": null
    },
    {
      "id": "gp:36",
      "item_list_id": "36",
      "parent_id": null,
      "display_name": "副詞(準否定)",
      "target_eligible": false,
      "item_list": {
        "name_ja": "副詞(準否定)",
        "sentence_type_ja": null,
        "shorthand_code": "RB.seminegative",
        "grammatical_item_en": "SEMI-NEGATIVE ADVERBS",
        "sentence_type_en": null,
        "note": null,
        "pattern_shorthand": "hardly / rarely / seldom",
        "regex_treetagger": "\\b(hardly|rarely|seldom)_RB\\b"
      },
      "kyoinban": {
        "present": false,
        "name_ja": null,
        "name_simple_ja": null,
        "name_en": null,
        "level_raw": null
      },
      "level": {
        "min": null,
        "max": null,
        "source": null,
        "inherited_from": null
      },
      "efl": null
    }
  ]
}
```

**実例10: config_limits（既定値）**

<!-- example:config_limits -->
```json
{
  "schema_version": "1.0.0",
  "sentence_word_limits": { "A1": 10, "A2": 14, "B1": 20, "B2": 26 },
  "explanation_char_limits": { "brief": 200, "detailed": 400 },
  "distractor_reuse_max": 2,
  "generation_max": 3,
  "set_question_max": 20,
  "review_timeout_seconds": 300
}
```

**実例11: config_proper_nouns**

<!-- example:config_proper_nouns -->
```json
{
  "schema_version": "1.0.0",
  "words": ["Ken", "Emi", "Tom", "Mary", "Tokyo", "Kyoto", "Osaka", "London", "Paris", "Japan"]
}
```

## 8. v2課題の参照

本書に関係するv2課題（localStorage永続化・処理再開・語彙問題への解説拡張・TreeTagger正規表現の機械照合）の正は `docs/requirements.md` のスコープ外/v2リストであり、本書のスキーマにはこれらのためのフィールドを先行追加しない。
