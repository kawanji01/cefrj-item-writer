# 問題生成仕様（question-generation-spec）

## 0. 文書情報

- **目的**: CEFR-J準拠作問エージェントが生成する9形式の問題について、生成規則・候補問題オブジェクトの内容・生成手順・生成プロンプトの必須制約を定義する。
- **対象読者**: 実装担当（Codex GPT-5.6 sol）、作問エージェントのコア指示書（`agent/author-core.md`）の作成者、レビュー仕様・スキーマの作成者。
- **参照文書**:
  - `docs/requirements.md`（機能要件・スコープ外/v2リスト）
  - `docs/cefrj-validation-spec.md`（レベル体系・正規化・機械検査の正）
  - `docs/subagent-review-spec.md`（レビュー契約・再生成ループ）
  - `docs/json-output-spec.md`（set.json・監査ファイル・ID規則の正）
  - `docs/html-output-spec.md`（HTML表示・判定UIの正）
  - `docs/architecture.md`（CLI契約・エラーコード目録の正）
  - `schemas/candidate.schema.json` / `schemas/set.schema.json`
- **規範語彙凡例**: 「しなければならない(MUST)」「してはならない(MUST NOT)」「すべきである(SHOULD)」「してもよい(MAY)」。
- **この文書が「正」とする範囲**:
  1. 共通生成規則（例文規則=Q12、誤答規則=Q11、日本語規則=Q13、解説規則=Q24、選択肢順固定、固有名詞allowlistの生成側利用）。
  2. 9形式それぞれの生成仕様（定義・入力・生成手順・出力フィールドの意味論・制約・JSON例）。
  3. 生成プロンプト（`agent/author-core.md`）が必ず含むべき制約の列挙（要求仕様）。
- **この文書が「正」としない範囲**: フィールドの型・必須性・スキーマ上の厳密定義は `docs/json-output-spec.md` と `schemas/` が正。レベル体系・スケール交差規則・機械検査手順は `docs/cefrj-validation-spec.md` が正。レビュー手順・再生成ループは `docs/subagent-review-spec.md` が正。HTML上の表示・判定は `docs/html-output-spec.md` が正。

### 0.1 形式コード対応表

| 番号 | 形式コード | 名称 | 系統 | level_scale |
|---|---|---|---|---|
| ① | `vocab_mcq_en2ja` | 英単語→日本語の意味4択 | 語彙(Wordlist) | `cefr` |
| ② | `vocab_mcq_ja2en` | 日本語の意味→英単語4択 | 語彙(Wordlist) | `cefr` |
| ③ | `vocab_flashcard_en2ja` | 例文フラッシュカード英→日 | 語彙(Wordlist) | `cefr` |
| ④ | `vocab_flashcard_ja2en` | 例文フラッシュカード日→英 | 語彙(Wordlist) | `cefr` |
| ⑤ | `grammar_mcq` | 選択問題（空欄4択） | 文法(Grammar Profile) | `cefrj` |
| ⑥ | `grammar_cloze` | 穴埋め（空欄自由入力） | 文法(Grammar Profile) | `cefrj` |
| ⑦ | `grammar_reorder` | 語句整序 | 文法(Grammar Profile) | `cefrj` |
| ⑧ | `grammar_rewrite` | 書き換え | 文法(Grammar Profile) | `cefrj` |
| ⑨ | `grammar_example_selfcheck` | 例文問題（訳想起→自己採点） | 文法(Grammar Profile) | `cefrj` |

本文中の丸数字（①〜⑨）は上表の形式コードの略記である。

### 0.2 JSON例の位置づけ

本文書の各JSON例は、生成直後の候補問題（`review/<question_id>.<gen>.candidate.json` に保存される内容）の完全な例である。例中の見出し語・文法項目は原本に実在するもの（Wordlist Ver1.6 / Grammar Profile 教員版）を用いているが、誤答アンカーの一部の語のレベル、および文法項目の「文法項目(平易版)」表示名は執筆時点の参照値である。**本文書のJSON例をテストフィクスチャに転用する場合、実装者は `lookup.py` で全アンカー・全表示名を正規化データと照合し、不一致があればフィクスチャ側を修正しなければならない。** 本文の規範規則が正であり、例は規則の適用結果の説明である。

## 1. 共通生成規則

### 1.1 問題オブジェクト共通骨格

**GEN-01** 生成される候補問題は、次の共通骨格を持つJSONオブジェクトでなければならない。型・必須性の厳密な定義は `docs/json-output-spec.md` と `schemas/candidate.schema.json` が正であり、本節はフィールドの意味論と生成時の値の決め方を定める。

| フィールド | 意味論と生成規則 |
|---|---|
| `question_id` | `q01`〜`q20`。セット内の問題番号。再生成しても変わらない。 |
| `format` | §0.1の形式コード9値のいずれか。セット条件の形式と一致しなければならない。 |
| `level.scale` | 語彙形式(①〜④)は `cefr`、文法形式(⑤〜⑨)は `cefrj`。 |
| `level.value` | セット条件の指定レベル。`cefr`は `A1|A2|B1|B2`、`cefrj`は `A1.1|A1.2|A1.3|A2.1|A2.2|B1.1|B1.2|B2.1|B2.2`。 |
| `target.type` | `lexical`（①〜④）または `grammar`（⑤〜⑨）。 |
| `target.ref` | 語彙: `lex:<headword>:<pos>`（posの空白は`-`に置換）。文法: `gp:<ID>`（教員版ID。枝番は `gp:1-1` 形式）。 |
| `target.display_name` | 語彙: 正規化データの headword をそのまま。文法: 正規化データの `display_name`（「文法項目(平易版)」由来）をそのまま。 |
| `body` | 形式別ペイロード（§2）。 |
| `explanation` | 文法5形式(⑤〜⑨)のみ必須。`{"type": "brief"|"detailed", "text": "..."}`。⑨は `detailed`、⑤⑥⑦⑧は `brief`。語彙4形式(①〜④)ではこのフィールドを出力してはならない（語彙問題への解説拡張は `docs/requirements.md` のv2リスト参照）。 |

`provenance`（合格世代の監査参照）は `finalize_set.py` が `set.json` 構築時に付与する（`docs/json-output-spec.md` SET-06）。生成候補（candidate）に `provenance` を含めてはならない（`candidate.schema.json` は `additionalProperties: false` によりこれを拒否する）。`target` に上表以外のフィールド（原本レベル表記の転記を含む）を追加してはならない。原本レベルは `target.ref` を介して正規化データから常に参照できる。

**GEN-02** `format`・`level`・問題数は1セット内で全問題に共通でなければならない（1セッション=同一条件セット）。セット条件との不一致は `machine_check.py` の違反である（検査手順は `docs/cefrj-validation-spec.md`）。

**GEN-03** `target.ref` が指す項目は正規化データ（`data/normalized/lexicon.json` / `data/normalized/grammar.json`）に実在しなければならない。文法ターゲットは教員版256項目（レベル付与済み）のいずれかでなければならず、教員版レベル未付与の16項目（`docs/cefrj-validation-spec.md` 参照）をターゲットにしてはならない。指定レベルとターゲットの適格判定（範囲値の包含判定を含む）は `docs/cefrj-validation-spec.md` のターゲット適格規則（Q6）が正である。

**GEN-04** （欠番。旧規則「candidate への provenance 先行記載」は `docs/json-output-spec.md` SET-05/SET-06 と矛盾するため削除した。監査ファイル名と `provenance` の決定はオーケストレータと `finalize_set.py` の責務である。）

### 1.2 例文規則（Q12の正）

本節の「例文」とは、問題オブジェクトに含まれる全ての英語の文（①の `stem`、②の `sentence_complete`（`sentence_with_blank` に正答を代入した完成文）、③④の `example.en`、⑤⑥の `sentence_with_blank`（正答代入後の完成文）、⑦の `answer_sentence`、⑧の `source_sentence` と `target_sentence_with_blank`（正答代入後の完成文）、⑨の `example.en`、および `context_sentence`）を指す。9形式すべてが例文を持つ。

**GEN-05（1文原則）** 例文は原則1文でなければならない。複数文の連結・セミコロン接続による実質複文化をしてはならない。

**GEN-06（2文例外と記録）** 対象文法項目のITEM LIST上の文タイプが先行文脈を要求する場合（文タイプ値が `前文が肯定平叙` または `前文が否定平叙` の場合。この2値に限る）のみ、先行文1文を `context_sentence` に置いてもよい。このとき要求元の文タイプ値を `context_required_by` にITEM LISTのセル値そのままで記録しなければならない。先行文脈要求がない場合、`context_sentence` と `context_required_by` は `null` でなければならない。`context_sentence` 自体も本節の全例文規則（語数上限・レベル制約・allowlist）を満たさなければならない。

**GEN-07（語数上限）** 例文1文あたりの語数は次表の上限以内でなければならない。値は `data/config/limits.json` の運用パラメータであり、次表は初期既定値である。語数は句読点を除くトークン数として機械計測する（計測アルゴリズムは `docs/cefrj-validation-spec.md` が正）。空欄を含む文は、正答（`grammar_cloze` は `answer`、`grammar_rewrite` は `answer`）を空欄に代入した完成文で計測する。2文構成（GEN-06）の場合、上限は各文に個別に適用する。

| 帯 | 上限（語） | 適用レベル |
|---|---|---|
| A1 | 10 | `A1`, `A1.1`, `A1.2`, `A1.3` |
| A2 | 14 | `A2`, `A2.1`, `A2.2` |
| B1 | 20 | `B1`, `B1.1`, `B1.2` |
| B2 | 26 | `B2`, `B2.1`, `B2.2` |

**GEN-08（対象の実現）** 語彙形式（①〜④）では、対象語が例文（①は `stem`、②は `sentence_complete`、③④は `example.en`）中にちょうど1回出現しなければならない。活用形・屈折形での出現を認める（レンマ一致で機械照合。照合手順は `docs/cefrj-validation-spec.md`）。出現した表層形を `target_surface` に記録しなければならない。文法形式（⑤〜⑨）では、対象文法構造が例文中に実現していなければならない。実現の判定はLLMレビューがITEM LISTのパターン略記を根拠として行う（TreeTagger正規表現による機械照合は `docs/requirements.md` のv2リスト参照）。

**GEN-09（レベル制約）** 例文中の全語彙・全文法構造、および選択肢の全語は、`docs/cefrj-validation-spec.md` が定めるレベル体系規則（Q3/Q6/Q8: 文法問題Lx.yの例文語彙はWordlistレベル≤Lx、語彙問題Lの例文文法は導入レベル≤Lの最上位枝番、範囲値の下限=導入レベル解釈）に適合するよう生成しなければならない。指定レベル超の前提知識を要求してはならない。

**GEN-10（辞書外語とallowlist）** 例文・選択肢に使用できる語は、(a) Wordlist収録語（指定帯以下のレベル）、(b) `data/config/proper_nouns.json` のallowlist収録固有名詞、(c) 機械的免除対象（数字・記号・句読点・縮約展開で解決される形。免除規則の正は `docs/cefrj-validation-spec.md` のQ10規則）、の3類に限る。allowlist全文は生成プロンプトに制約として渡さなければならない（§3 PRM-04）。allowlist外の人名・地名・言語名・商標を使用してはならない。

**GEN-11（トピック）** セット条件にトピック指定（任意項目）がある場合、例文の題材はそのトピックに沿っていなければならず、生成プロンプトの制約に加えなければならない。トピック指定がない場合、題材は自由である（ただし学習上の適切さの範囲内。検証は `docs/subagent-review-spec.md` の CHK-12）。

**GEN-12（先行文脈要求項目の形式制限）** ⑦(`grammar_reorder`)と⑧(`grammar_rewrite`)では、先行文脈を要求する文タイプ（GEN-06の2値）を持つ項目・枝番をターゲットにしてはならない。これらの形式のbodyは `context_sentence` を持たないためである。対象選定時の対話での除外手順は `docs/interaction-flow.md` が定める。

### 1.3 誤答規則（Q11の正）

**GEN-13（語彙4択の誤答アンカー）** ①②の誤答3つは、それぞれWordlist実在語をアンカーとしなければならない。アンカーは次の全条件を満たさなければならない。

1. セット指定レベルと同一レベル（`anchor.level` == `level.value`）。
2. 正解語と同一品詞（`anchor.pos` == 対象語のpos）。ただしGEN-14の緩和時を除く。
3. 正解語の同義語・正解語と意味の区別が不能な語を用いてはならない。
4. 誤答の由来を `anchor` オブジェクト（`entry_id`・`headword`・`pos`・`level`）としてJSONに記録しなければならない（機械照合対象。照合は `docs/cefrj-validation-spec.md`）。
5. 同一問題内でアンカーが重複してはならない（4選択肢のanchor.entry_idは互いに異なる）。

**GEN-14（意味分野カテゴリ近接の優先）** 誤答アンカーは、対象語と意味分野カテゴリが近い語を優先して選ぶべきである(SHOULD)。優先順位は次のとおりとする: (1) `CoreInventory 1` が対象語と一致する語 → (2) `Threshold` が一致する語 → (3) `CoreInventory 2` が一致する語 → (4) カテゴリ一致のない同レベル・同品詞語。対象側のカテゴリ値が非nullの場合だけ一致として評価し、1候補が複数カテゴリで一致する場合は最上位の順位を採用する。同順位内は正規化lexiconのNRM-13順とする。対象エントリ自身は誤答プールから除外する。上位優先度の候補が3語に満たない場合は次順位から補う。カテゴリ一致が1語もなくても違反ではない。

**GEN-15（品詞プールの緩和）** 同レベル・同品詞のアンカー候補プールが3語未満の場合に限り、同レベルの「文法的互換品詞群」内の品詞へ緩和してもよい。互換品詞群は次の5群で固定し、各posはちょうど1群に属する。

| 群 | 所属pos |
|---|---|
| 名詞群 | noun, number |
| 動詞群 | verb, be-verb, do-verb, have-verb, modal auxiliary |
| 形容詞群 | adjective, determiner |
| 副詞群 | adverb |
| 機能語群 | pronoun, preposition, conjunction, interjection, infinitive-to |

緩和を行った場合、`body.pos_pool_relaxed` を `true` にしなければならない。緩和しなかった場合は `false` を明示しなければならない。緩和時もレベル一致（GEN-13の1）は緩和してはならない。

**GEN-16（文法選択の誤答）** ⑤の誤答3つは、次の全条件を満たさなければならない。

1. 対象文法項目と同一パラダイム内の操作で作られた形であること（例: be動詞の人称・数の交替、時制の交替、原形/活用形の交替、語順の交替）。パラダイム外の無関係語を誤答にしてはならない。
2. 空欄に入れると文法的または意味的に不成立となること（正解の言い換えとして成立する形を誤答にしてはならない＝正解の一意性）。
3. **誤答の排除に指定レベル超の文法・語彙知識を要求してはならない**（レビュー検証項目。検証手順は `docs/subagent-review-spec.md`）。
4. 誤答の語そのものも GEN-09・GEN-10 のレベル制約・辞書制約を満たすこと。

### 1.4 選択肢順固定

**GEN-17（シャッフルと固定保存）** ①②⑤の4選択肢は、生成時に順序をシャッフルし、その結果の順序をJSONの `choices` 配列順としてそのまま保存しなければならない。JSON配列順が表示順の正である。正解が常に同じ位置に来る配置をしてはならない(MUST NOT)。HTML側での再シャッフルは禁止である（表示規則の正は `docs/html-output-spec.md`）。再生成世代ごとにシャッフルは独立に行う。

### 1.5 日本語規則（Q13の正）

**GEN-18（語義）** 語義（①②の選択肢gloss、③④のgloss）は次の全条件を満たさなければならない。

1. 辞書形式で品詞を反映する（動詞=「〜を放棄する」型、形容詞=「異常な」型、名詞=名詞句、副詞=「外国で」型）。
2. 指定レベルでその語を学ぶ際の代表語義を1つ提示する。複数語義の羅列をしてはならない（読点で対をなす2訳語まで、例「外国で、外国へ」はMAY）。
3. ①では、誤答選択肢の語義（誤答アンカー語の語義）が正解語の別義と重なってはならない（レビュー検証項目）。
4. ②では、stemに置く正解語の語義が、いずれかの誤答語の語義としても成立してはならない（レビュー検証項目）。

**GEN-19（例文訳）** 日本語訳（`example.ja`・`example_ja`・`source_ja`・`target_ja`）は、です・ます調を基本とする自然かつ忠実な訳でなければならない。会話文・命令文は発話として自然な文体を用いてもよい(MAY)。原文にない情報の追加、原文にある情報の省略をしてはならない。

**GEN-20（形式④の復元可能性）** ④では、日本語訳から元の英文が復元可能でなければならない。時制・数・人称が訳文に反映されていること（例: 3人称単数現在なら「〜しています/〜します」の主語が単数と分かる訳）をレビュー検証項目とする（検証手順は `docs/subagent-review-spec.md`）。

### 1.6 解説規則（Q24の正）

**GEN-21（解説の対象と詳細度）** 文法5形式(⑤〜⑨)の全問題に解説が必須である。⑨は `type: "detailed"`（本文400字上限）、⑤⑥⑦⑧は `type: "brief"`（本文200字上限）。字数は `explanation.text` のUnicodeコードポイント数（空白・句読点を含む）で機械計測し、上限値は `data/config/limits.json` の運用パラメータとする。

**GEN-22（解説の読者・文体・用語）** 解説の読者は指定レベルの学習者である。です・ます調で書き、中学・高校の標準的な文法用語のみを使用しなければならない（言語学の専門用語を使用してはならない）。解説文中に教員版の文法項目名（「文法項目」列の名称）を明記しなければならない。

**GEN-23（詳細解説の構成）** ⑨の詳細解説は「①項目の機能 → ②この例文での使われ方 → ③注意点・よくある誤り」の3部構成でなければならない。

**GEN-24（簡潔解説の内容要件）** ⑤⑥⑦⑧の簡潔解説の内容は形式ごとに次で固定する。

| 形式 | 必須内容 |
|---|---|
| ⑤ `grammar_mcq` | 正解の理由＋各誤答（3つ全て）の排除理由 |
| ⑥ `grammar_cloze` | 正解形が要求される文法的理由 |
| ⑦ `grammar_reorder` | その語順になる根拠 |
| ⑧ `grammar_rewrite` | 元文と目標文の文法的関係 |

**GEN-25（解説のレベル制約）** 解説中に引用する英語表現は例文・選択肢に現れた語句、および対象文法項目の形そのもの（例: 否定形の語順）に限る。新しい例文を解説内に追加してはならない。全解説はレビュー検証対象である。

### 1.7 空欄の表記

**GEN-26（空欄マーカー）** 空欄を含む文（②⑤⑥の `sentence_with_blank`、⑧の `target_sentence_with_blank`）では、空欄を半角アンダースコア4個 `____` ちょうど1箇所で表さなければならない。1文中に空欄を2箇所以上置いてはならない。空欄は、②では対象語の表層形（`target_surface`）全体を、⑤⑥⑧では対象文法構造の実現部分（複数語にわたってもよい）全体を覆う。

## 2. 形式別生成仕様

各形式について「定義 / 入力 / 生成手順 / 出力フィールド（body） / 制約 / JSON例」を定める。入力は全形式共通で次を含む。

- セット条件: `format`・`level`・対象（`target.ref`）・問題数・トピック（任意）・追加固有名詞の希望（任意、allowlist反映後）。
- 正規化データへの読み取りアクセス: `data/normalized/lexicon.json` / `data/normalized/grammar.json`（`lookup.py` 経由。CLI契約は `docs/architecture.md`）。
- 設定: `data/config/limits.json` / `data/config/proper_nouns.json`。
- 再生成時（gen2/gen3）のみ: 前世代の `review_result` の `violations[]`（受け渡し手順は `docs/subagent-review-spec.md`）。

生成手順の最終段は全形式共通で次の2段である（各形式の手順では省略する）。

- (共通S-1) 自己検査: 当該形式の全GEN規則をチェックリストとして照合し、違反があれば修正する。
- (共通S-2) 候補JSONを組み立て、共通骨格（GEN-01）を付与して出力する。契約検証は呼び出し側が `validate.py` で行う（スキーマ不通過時の扱いは `docs/subagent-review-spec.md` の再生成ループ仕様 T2/T3）。

### 2.1 ① `vocab_mcq_en2ja`（英単語→日本語の意味4択）

**定義**: 対象語を含む英語例文を提示し、その文中での対象語の日本語の意味を4つの語義から選ばせる。正解1つ＋Wordlist実在語アンカー付き誤答3つ。

**GEN-27（①のstem・target_surface・stem_ja）** ①の `stem` は対象語をちょうど1回含む英例文でなければならない（例文規則 GEN-05〜GEN-11 を全て適用する）。`target_surface` には `stem` 中の対象語の表層形（活用形の場合は活用形そのまま）を、`stem_ja` には `stem` の日本語訳（GEN-19。解答後表示用）を必ず出力する。品詞ラベルの表示はHTML生成器が `target.ref` から導出する（表示の正は `docs/html-output-spec.md` UI-04）。

**生成手順**:
1. `lookup.py` で `target.ref` の実在・レベル一致を確認する（対話段階で照合済みの再確認）。
2. 対象語がちょうど1回出現する例文 `stem` を作成し（GEN-08）、`target_surface` を記録し、`stem_ja` を作成する（GEN-27）。
3. 対象語の代表語義（例文中の用法の語義。GEN-18）を正解肢として作成する。
4. 同レベル・同品詞のアンカー候補プールを正規化データから取得し、GEN-14の優先順位で誤答アンカー3語を選ぶ。プールが3語未満の場合のみGEN-15の緩和を適用する。
5. 各誤答アンカー語の代表語義を作成し、GEN-18の3（別義重複禁止）を自己検査する。
6. 正解＋誤答3つをシャッフルし（GEN-17）、`choices` を確定する。

**出力フィールド（body）**:

| フィールド | 内容 |
|---|---|
| `stem` | 対象語をちょうど1回含む英例文（GEN-27） |
| `target_surface` | `stem` 中の対象語の表層形 |
| `stem_ja` | `stem` の日本語訳（解答後表示用） |
| `choices[4]` | 各要素: `text`（表示文字列=日本語語義）・`is_correct`（真偽、trueはちょうど1つ）・`anchor`（`entry_id`/`headword`/`pos`/`level`）・`gloss`（アンカー語の日本語語義） |
| `pos_pool_relaxed` | 緩和フラグ（GEN-15） |

**GEN-28（①のtextとgloss）** ①では各選択肢の `text` は当該アンカー語の日本語語義であり、`gloss` と同一値でなければならない。正解選択肢の `text` は例文中の用法と同じ語義を表さなければならない。正解選択肢の `anchor` は対象語自身を指さなければならない。

**制約**: GEN-05〜GEN-11（例文）、GEN-13〜GEN-15（誤答）、GEN-17（順序）、GEN-18（語義）、GEN-19（訳）。`target_surface` は `stem` の部分文字列でなければならない。

**JSON例**（A2・対象 `accept`）:

```json
{
  "question_id": "q01",
  "format": "vocab_mcq_en2ja",
  "level": { "scale": "cefr", "value": "A2" },
  "target": {
    "type": "lexical",
    "ref": "lex:accept:verb",
    "display_name": "accept"
  },
  "body": {
    "stem": "She decided to accept the new job.",
    "target_surface": "accept",
    "stem_ja": "彼女はその新しい仕事を受け入れることに決めました。",
    "choices": [
      {
        "text": "〜を借りる",
        "is_correct": false,
        "anchor": { "entry_id": "lex:borrow:verb", "headword": "borrow", "pos": "verb", "level": "A2" },
        "gloss": "〜を借りる"
      },
      {
        "text": "〜を受け入れる",
        "is_correct": true,
        "anchor": { "entry_id": "lex:accept:verb", "headword": "accept", "pos": "verb", "level": "A2" },
        "gloss": "〜を受け入れる"
      },
      {
        "text": "〜を集める",
        "is_correct": false,
        "anchor": { "entry_id": "lex:collect:verb", "headword": "collect", "pos": "verb", "level": "A2" },
        "gloss": "〜を集める"
      },
      {
        "text": "〜を招待する",
        "is_correct": false,
        "anchor": { "entry_id": "lex:invite:verb", "headword": "invite", "pos": "verb", "level": "A2" },
        "gloss": "〜を招待する"
      }
    ],
    "pos_pool_relaxed": false
  }
}
```

### 2.2 ② `vocab_mcq_ja2en`（日本語の意味→英単語4択）

**定義**: 日本語の語義と、対象語部分を空欄にした英語例文を提示し、空欄（=語義）に対応する英単語を4つの見出し語から選ばせる。

**GEN-29（②のstem・例文・choices）** ②では次を全て満たさなければならない。

1. `stem` は対象語の代表語義（GEN-18準拠の日本語文字列）である。
2. `sentence_with_blank` は対象語の表層形部分を空欄 `____`（GEN-26）にした英例文である。`sentence_complete` は空欄を `target_surface` で置換した完成文であり、例文規則（GEN-05〜GEN-11）は `sentence_complete` に適用する（対象語は `sentence_complete` 上でちょうど1回出現する。GEN-08）。
3. `target_surface` は空欄に入る表層形であり、本形式では headword と同一でなければならない（活用形を空欄にしてはならない。語義→英単語の対応を一意にするため）。
4. `sentence_ja` は完成文の日本語訳（GEN-19。解答後表示用）である。
5. 各選択肢の `text` はアンカー語のheadwordそのもの、`gloss` はアンカー語の日本語語義でなければならない（学習フィードバック用。表示は `docs/html-output-spec.md`）。

**生成手順**: ①の手順1〜6に準じる。ただし手順2では `sentence_with_blank` / `sentence_complete` / `target_surface` / `sentence_ja` を作成し、手順5の自己検査はGEN-18の4（stem語義が誤答語の語義として成立しないこと）を用いる。

**出力フィールド（body）**:

| フィールド | 内容 |
|---|---|
| `stem` | 対象語の代表語義（設問として提示） |
| `sentence_with_blank` | 空欄 `____` を1箇所含む英例文 |
| `sentence_complete` | 空欄を `target_surface` で置換した完成文 |
| `target_surface` | 空欄に入る表層形（headword と同一） |
| `sentence_ja` | 完成文の日本語訳（解答後表示用） |
| `choices[4]` | 各要素: `text`（headword）・`is_correct`・`anchor`・`gloss` |
| `pos_pool_relaxed` | 緩和フラグ（GEN-15） |

**制約**: GEN-05〜GEN-11（例文。`sentence_complete` 上で適用）、GEN-13〜GEN-15、GEN-17、GEN-18、GEN-19、GEN-26、GEN-29。

**JSON例**（A2・対象 `ability`）:

```json
{
  "question_id": "q01",
  "format": "vocab_mcq_ja2en",
  "level": { "scale": "cefr", "value": "A2" },
  "target": {
    "type": "lexical",
    "ref": "lex:ability:noun",
    "display_name": "ability"
  },
  "body": {
    "stem": "能力",
    "sentence_with_blank": "He has the ____ to speak three languages.",
    "sentence_complete": "He has the ability to speak three languages.",
    "target_surface": "ability",
    "sentence_ja": "彼には3つの言語を話す能力があります。",
    "choices": [
      {
        "text": "advice",
        "is_correct": false,
        "anchor": { "entry_id": "lex:advice:noun", "headword": "advice", "pos": "noun", "level": "A2" },
        "gloss": "助言"
      },
      {
        "text": "culture",
        "is_correct": false,
        "anchor": { "entry_id": "lex:culture:noun", "headword": "culture", "pos": "noun", "level": "A2" },
        "gloss": "文化"
      },
      {
        "text": "ability",
        "is_correct": true,
        "anchor": { "entry_id": "lex:ability:noun", "headword": "ability", "pos": "noun", "level": "A2" },
        "gloss": "能力"
      },
      {
        "text": "accident",
        "is_correct": false,
        "anchor": { "entry_id": "lex:accident:noun", "headword": "accident", "pos": "noun", "level": "A2" },
        "gloss": "事故"
      }
    ],
    "pos_pool_relaxed": false
  }
}
```

### 2.3 ③ `vocab_flashcard_en2ja`（例文フラッシュカード英→日）

**定義**: 表面に対象語を含む英語例文、裏面に日本語対訳と語義を示すフラッシュカード。対象語はHTML表示でハイライトされる（表示の正は `docs/html-output-spec.md`。JSONは `target_surface` でハイライト位置を supply する）。

**生成手順**:
1. `lookup.py` で `target.ref` の実在・レベル一致を確認する。
2. 対象語の代表語義（GEN-18）を作成する。
3. 対象語がちょうど1回出現する例文を作成する（GEN-08）。語数上限（GEN-07）・レベル制約（GEN-09）・辞書制約（GEN-10）・トピック（GEN-11）を満たすこと。語彙問題のため例文の文法は導入レベル≤指定レベル帯の最上位枝番（A1→A1.3, A2→A2.2, B1→B1.2, B2→B2.2。規則の正は `docs/cefrj-validation-spec.md`）。
4. 例文中の対象語の表層形を `target_surface` に記録する。
5. 例文の日本語訳を作成する（GEN-19）。

**出力フィールド（body）**:

| フィールド | 内容 |
|---|---|
| `headword` | 対象語のheadword（正規化データと一致） |
| `pos` | 対象語のpos（Wordlist 15種の値そのまま） |
| `gloss` | 代表語義（GEN-18） |
| `example.en` | 英語例文（対象語をちょうど1回含む） |
| `example.ja` | 例文の日本語訳（GEN-19） |
| `target_surface` | 例文中の対象語の表層形（活用形の場合は活用形そのまま） |

**制約**: GEN-05〜GEN-11（例文）、GEN-18（語義）、GEN-19（訳）。`target_surface` は `example.en` の部分文字列でなければならない。

**JSON例**（B1・対象 `abandon`）:

```json
{
  "question_id": "q01",
  "format": "vocab_flashcard_en2ja",
  "level": { "scale": "cefr", "value": "B1" },
  "target": {
    "type": "lexical",
    "ref": "lex:abandon:verb",
    "display_name": "abandon"
  },
  "body": {
    "headword": "abandon",
    "pos": "verb",
    "gloss": "〜を捨てる、〜を断念する",
    "example": {
      "en": "They had to abandon their car in the heavy snow.",
      "ja": "彼らは大雪の中で車を乗り捨てなければなりませんでした。"
    },
    "target_surface": "abandon"
  }
}
```

### 2.4 ④ `vocab_flashcard_ja2en`（例文フラッシュカード日→英）

**定義**: 表面に日本語訳、裏面に英語例文と語義を示すフラッシュカード。学習者は日本語から英文を想起する。

**生成手順**: ③の手順1〜5と同一。ただし手順5の訳はGEN-20（復元可能性: 時制・数・人称の反映）を追加で満たさなければならない。

**出力フィールド（body）**: ③と同一構造（`headword` / `pos` / `gloss` / `example{en, ja}` / `target_surface`）。表裏の割当（表=`example.ja`、裏=`example.en`）はHTML生成器が `format` で決定する。

**制約**: ③の全制約＋GEN-20。

**JSON例**（A2・対象 `abroad`）:

```json
{
  "question_id": "q01",
  "format": "vocab_flashcard_ja2en",
  "level": { "scale": "cefr", "value": "A2" },
  "target": {
    "type": "lexical",
    "ref": "lex:abroad:adverb",
    "display_name": "abroad"
  },
  "body": {
    "headword": "abroad",
    "pos": "adverb",
    "gloss": "外国で、外国へ",
    "example": {
      "en": "My sister wants to study abroad next year.",
      "ja": "私の姉は来年、外国で勉強したいと思っています。"
    },
    "target_surface": "abroad"
  }
}
```

### 2.5 ⑤ `grammar_mcq`（選択問題・空欄4択）

**定義**: 対象文法構造の実現部分を空欄にした英文を提示し、空欄に入る形を4択から選ばせる。

**生成手順**:
1. `lookup.py` で `target.ref` の実在・指定レベルの適格（Q6包含判定）を確認する。
2. 対象構造が実現する例文を作成し（GEN-08）、実現部分の全体または判別に必要な部分を `____` に置換する（GEN-26）。例文はGEN-05〜GEN-07・GEN-09〜GEN-11を満たすこと。
3. 先行文脈要求（GEN-06）がある場合のみ `context_sentence` を作成し `context_required_by` を記録する。ない場合は両方 `null`。
4. 正解1つと、同一パラダイム内操作の誤答3つ（GEN-16）を作成する。
5. 4択をシャッフルして固定する（GEN-17）。
6. 完成文の日本語訳 `example_ja` を作成する（GEN-19）。
7. 簡潔解説（GEN-21・GEN-22・GEN-24の⑤行: 正解理由＋各誤答の排除理由）を作成する。

**出力フィールド（body）**:

| フィールド | 内容 |
|---|---|
| `sentence_with_blank` | 空欄 `____` を1箇所含む英文（GEN-26） |
| `choices[4]` | 各要素: `text`（空欄に入る文字列）・`is_correct`（trueはちょうど1つ） |
| `example_ja` | 正答代入後の完成文の日本語訳 |
| `context_sentence` | 先行文（GEN-06の場合のみ。それ以外は `null`） |
| `context_required_by` | 要求元文タイプ値（GEN-06の場合のみ。それ以外は `null`） |

**制約**: GEN-05〜GEN-11、GEN-16、GEN-17、GEN-19、GEN-21〜GEN-26。正解を空欄に代入した完成文で語数を計測する（GEN-07）。

**JSON例**（A1.1・対象 `gp:58` 時制・相(現在)(be動詞)）:

```json
{
  "question_id": "q01",
  "format": "grammar_mcq",
  "level": { "scale": "cefrj", "value": "A1.1" },
  "target": {
    "type": "grammar",
    "ref": "gp:58",
    "display_name": "be動詞の現在の文"
  },
  "body": {
    "sentence_with_blank": "My brother ____ a student.",
    "choices": [
      { "text": "am", "is_correct": false },
      { "text": "is", "is_correct": true },
      { "text": "are", "is_correct": false },
      { "text": "be", "is_correct": false }
    ],
    "example_ja": "私の兄は学生です。",
    "context_sentence": null,
    "context_required_by": null
  },
  "explanation": {
    "type": "brief",
    "text": "この問題の文法項目は「時制・相(現在)(be動詞)」です。主語の My brother は3人称単数なので、be動詞の現在形は is を使います。am は主語が I のときの形、are は主語が you または複数のときの形なので、この文では使えません。be は原形で、そのままでは現在の文の述語になれません。"
  }
}
```

### 2.6 ⑥ `grammar_cloze`（穴埋め・空欄自由入力）

**定義**: 対象文法構造の実現部分を空欄にした英文と日本語訳を提示し、空欄を自由入力させる。

**GEN-30（空欄と正答）** ⑥の空欄は対象文法構造の実現部分でなければならない（GEN-26）。`answer` は空欄に入る正答文字列、`answer_equivalents` は正答と同値として受理する表記の完全な列挙（縮約形・非縮約形の対応する表記に限る。0件なら空配列）でなければならない。`answer` 自身を `answer_equivalents` に重複して入れてはならない。HTML側の判定（大文字小文字無視＋前後空白除去＋同値リスト照合）の正は `docs/html-output-spec.md`。

**GEN-30a（cue）** ⑥の `cue` は空欄に入る内容語の原形ヒントである。空欄の正答が内容語（動詞・名詞・形容詞・副詞）の活用・派生を含む場合、その内容語の原形1語を `cue` に記録しなければならない（例: 正答 `is washing` → `cue: "wash"`。学習者に語の選択でなく文法形式を問うため）。正答が機能語（be動詞・助動詞・冠詞・代名詞・前置詞）のみで構成され原形ヒントが不要な場合は `cue = null` とする。`cue` の表示規則は `docs/html-output-spec.md` UI-13 が正である。

**生成手順**:
1. ⑤の手順1〜3と同一（4択作成を除く）。
2. `answer` と `answer_equivalents` を確定する（GEN-30）。
3. `cue` を確定する（GEN-30a）。
4. 完成文の日本語訳 `example_ja` を作成する（GEN-19）。訳は空欄部分を含む文全体の訳であり、学習者が訳から正答を導出できる情報（人称・時制・数）を含まなければならない。
5. 簡潔解説（GEN-24の⑥行: 正解形が要求される文法的理由）を作成する。

**出力フィールド（body）**:

| フィールド | 内容 |
|---|---|
| `sentence_with_blank` | 空欄 `____` を1箇所含む英文 |
| `cue` | string \| null。空欄に入る内容語の原形ヒント（GEN-30a）。機能語のみの正答では `null` |
| `answer` | 正答文字列 |
| `answer_equivalents` | 同値表記の配列（完全列挙。なければ `[]`） |
| `example_ja` | 完成文の日本語訳 |
| `context_sentence` / `context_required_by` | GEN-06に同じ |

**制約**: GEN-05〜GEN-11、GEN-19、GEN-21〜GEN-26、GEN-30、GEN-30a。

**JSON例**（A1.2・対象 `gp:1` 人称代名詞主格(I)+be: I am。教員版レベルは範囲値 `A1.1-A1.2` であり、指定レベル A1.2 は範囲に包含されるため適格）:

```json
{
  "question_id": "q01",
  "format": "grammar_cloze",
  "level": { "scale": "cefrj", "value": "A1.2" },
  "target": {
    "type": "grammar",
    "ref": "gp:1",
    "display_name": "I am の文"
  },
  "body": {
    "sentence_with_blank": "____ very happy today.",
    "cue": null,
    "answer": "I am",
    "answer_equivalents": ["I'm"],
    "example_ja": "私は今日とてもうれしいです。",
    "context_sentence": null,
    "context_required_by": null
  },
  "explanation": {
    "type": "brief",
    "text": "この問題の文法項目は「人称代名詞主格(I)+be: I am」です。日本語訳の主語「私」に合わせて人称代名詞の主格 I を使い、主語 I に対応するbe動詞の現在形 am を続けます。I am は短縮形 I'm と書くこともできます。"
  }
}
```

### 2.7 ⑦ `grammar_reorder`（語句整序）

**定義**: 正解文のトークンをシャッフルして提示し、タップ順選択で正しい語順に並べさせる（操作UIの正は `docs/html-output-spec.md`）。

**GEN-31（トークン化とシャッフル）** ⑦の `tokens_shuffled` は次の全条件を満たさなければならない。

1. `answer_sentence` から句読点（文末のピリオド・疑問符・感嘆符、文中のカンマを含む全句読点）を除いたトークン列であること。
2. 全トークンを小文字化すること（文頭ヒントを与えないため）。縮約形（`I'm` 型）はアポストロフィを保持したまま1トークンとして扱う。
3. シャッフル結果の並びが正解語順と同一であってはならない。
4. `answer_sentence` は正書法（大文字・句読点）どおりの正解文であり、解答表示に用いる。

**GEN-32（別解の不存在）** 提示トークン集合から組み立てられる、正解文以外の文法的に正しい英文（語義が通る並び）が存在してはならない。生成時にこれを自己検査し、別解の余地がある文（前置可能な副詞句を含む文、対等な並列構造を含む文、平叙文と疑問文の両方に並べられるbe動詞文を含む）を避けなければならない。別解不存在の最終検証はLLMレビューが行う（`docs/subagent-review-spec.md`）。

**生成手順**:
1. `lookup.py` で `target.ref` の実在・適格を確認する。GEN-12（先行文脈要求項目の除外）を確認する。
2. 対象構造が実現し、かつGEN-32を満たす語順が一意な例文を作成する（GEN-05〜GEN-11）。
3. GEN-31に従いトークン化・小文字化し、正解順と異なる順序にシャッフルする。
4. 日本語訳 `example_ja` を作成する（GEN-19）。
5. 簡潔解説（GEN-24の⑦行: その語順になる根拠）を作成する。

**出力フィールド（body）**:

| フィールド | 内容 |
|---|---|
| `tokens_shuffled` | シャッフル済み小文字トークン配列（GEN-31） |
| `answer_sentence` | 正書法どおりの正解文 |
| `example_ja` | 正解文の日本語訳 |

**制約**: GEN-05〜GEN-12、GEN-19、GEN-21〜GEN-25、GEN-31、GEN-32。

**JSON例**（A1.1・対象 `gp:117` 肯定命令文(一般動詞)）:

```json
{
  "question_id": "q01",
  "format": "grammar_reorder",
  "level": { "scale": "cefrj", "value": "A1.1" },
  "target": {
    "type": "grammar",
    "ref": "gp:117",
    "display_name": "命令文（〜しなさい）"
  },
  "body": {
    "tokens_shuffled": ["tree", "look", "big", "at", "that"],
    "answer_sentence": "Look at that big tree.",
    "example_ja": "あの大きな木を見なさい。"
  },
  "explanation": {
    "type": "brief",
    "text": "この問題の文法項目は「肯定命令文(一般動詞)」です。命令文は主語を置かず、動詞の原形 Look で文を始めます。look at で「〜を見る」という意味のまとまりを作り、見る対象の that big tree を後ろに続けます。形容詞 big は名詞 tree の前に置きます。"
  }
}
```

### 2.8 ⑧ `grammar_rewrite`（書き換え）

**定義**: 元文と書き換えの指示を提示し、対象文法構造を用いた目標文の空欄部分を入力させる（部分入力方式）。

**GEN-33（書き換えの構成）** ⑧は次の全条件を満たさなければならない。

1. `instruction`（書き換えの指示）は、何を使って書き換えるかを日本語・です・ます調で明示しなければならない（例: 「受動態の文に書き換えなさい」）。指示なしの自由書き換えをしてはならない。
2. `source_sentence`（元文）と目標文（`target_sentence_with_blank` に `answer` を代入した完成文）の**両方**が、指定レベルのレベル制約（GEN-09）・語数上限（GEN-07）・辞書制約（GEN-10）を満たさなければならない。
3. 目標文の空欄は対象文法構造の実現部分を覆う（GEN-26）。`answer` / `answer_equivalents` の規則はGEN-30に同じ。
4. `source_ja` / `target_ja` は元文・目標文それぞれの日本語訳（GEN-19）。
5. 元文が対象文法構造をすでに含んでいてはならない（書き換え前後で構造が変化すること）。

**生成手順**:
1. `lookup.py` で `target.ref` の実在・適格を確認する。GEN-12を確認する。
2. 対象構造を含まない元文と、対象構造を用いた目標文の対を作成する（GEN-33）。
3. 目標文の構造実現部分を `____` に置換し、`answer` / `answer_equivalents` を確定する。
4. `instruction`・`source_ja`・`target_ja` を作成する。
5. 簡潔解説（GEN-24の⑧行: 元文と目標文の文法的関係）を作成する。

**出力フィールド（body）**:

| フィールド | 内容 |
|---|---|
| `source_sentence` | 元文（対象構造を含まない） |
| `instruction` | 書き換え指示（日本語） |
| `target_sentence_with_blank` | 空欄 `____` を1箇所含む目標文 |
| `answer` | 空欄の正答文字列 |
| `answer_equivalents` | 同値表記の配列（完全列挙。なければ `[]`） |
| `source_ja` | 元文の日本語訳 |
| `target_ja` | 目標文（完成形）の日本語訳 |

**制約**: GEN-05〜GEN-12、GEN-19、GEN-21〜GEN-26、GEN-30（3項に準用）、GEN-33。

**JSON例**（B2.2・対象 `gp:84` 受動態(助動詞+完了)）:

```json
{
  "question_id": "q01",
  "format": "grammar_rewrite",
  "level": { "scale": "cefrj", "value": "B2.2" },
  "target": {
    "type": "grammar",
    "ref": "gp:84",
    "display_name": "助動詞+have been+過去分詞（受動態）"
  },
  "body": {
    "source_sentence": "You should have finished the report by Friday.",
    "instruction": "The report を主語にして、受動態の文に書き換えなさい。",
    "target_sentence_with_blank": "The report ____ by Friday.",
    "answer": "should have been finished",
    "answer_equivalents": ["should've been finished"],
    "source_ja": "あなたは金曜日までにその報告書を終えるべきでした。",
    "target_ja": "その報告書は金曜日までに終えられているべきでした。"
  },
  "explanation": {
    "type": "brief",
    "text": "この問題の文法項目は「受動態(助動詞+完了)」です。元の文の目的語 the report を主語にして受動態にします。助動詞 should のあとには動詞の原形が続くため、have + been + 過去分詞 finished の形になり、should have been finished で「終えられているべきだった」という過去のことへの評価を表します。"
  }
}
```

### 2.9 ⑨ `grammar_example_selfcheck`（例文問題・訳想起→自己採点）

**定義**: 対象文法構造を含む英語例文を提示し、学習者が日本語訳を想起したのち、正解訳と詳細解説を開いて自己採点する。入力・自動判定はない（画面遷移の正は `docs/html-output-spec.md`）。

**生成手順**:
1. `lookup.py` で `target.ref` の実在・適格を確認する。
2. 対象構造が実現する例文を作成する（GEN-05〜GEN-11）。先行文脈要求がある場合のみ `context_sentence` / `context_required_by` を設定する（GEN-06）。
3. 日本語訳 `example.ja` を作成する（GEN-19）。
4. 詳細解説（GEN-21の `detailed` 400字上限・GEN-22・GEN-23の3部構成）を作成する。

**出力フィールド（body）**:

| フィールド | 内容 |
|---|---|
| `example.en` | 対象構造を含む英語例文 |
| `example.ja` | 日本語訳 |
| `context_sentence` / `context_required_by` | GEN-06に同じ |

**制約**: GEN-05〜GEN-11、GEN-19、GEN-21〜GEN-23、GEN-25。解説は `type: "detailed"` でなければならない。

**JSON例**（B2.2・対象 `gp:97` so as to）:

```json
{
  "question_id": "q01",
  "format": "grammar_example_selfcheck",
  "level": { "scale": "cefrj", "value": "B2.2" },
  "target": {
    "type": "grammar",
    "ref": "gp:97",
    "display_name": "so as to+動詞の原形"
  },
  "body": {
    "example": {
      "en": "They left early so as to avoid the heavy traffic.",
      "ja": "彼らはひどい渋滞を避けるために早く出発しました。"
    },
    "context_sentence": null,
    "context_required_by": null
  },
  "explanation": {
    "type": "detailed",
    "text": "この問題の文法項目は「so as to」です。①機能: so as to+動詞の原形は「〜するために」という目的を表す、to不定詞のややあらたまった言い方です。in order to とほぼ同じ意味で、書き言葉やフォーマルな場面でよく使われます。②この例文での使われ方: so as to avoid the heavy traffic が「ひどい渋滞を避けるために」という目的を表し、主節 They left early（彼らは早く出発しました）の行動の目的を説明しています。③注意点・よくある誤り: 否定の目的を表すときは so as not to+動詞の原形の語順になり、not の位置を to の前に置く点に注意してください。また、in order to は文頭にも置けますが、so as to を文頭に置く使い方は通常しません。"
  }
}
```

## 3. 生成プロンプトの必須制約（`agent/author-core.md` の要求仕様）

コア指示書 `agent/author-core.md`（実装物）は、生成LLMに渡すプロンプトとして次のPRM-01〜PRM-14を全て含まなければならない。各項目は本文書・参照文書の規則を転記または要約なしの全文列挙で埋め込む（生成LLMは正規化データ全体を読まない前提で、判断に必要な制約は全てプロンプト内で完結させる）。挙動規則をアダプタ（CLAUDE.md / AGENTS.md）に書いてはならない（`docs/cross-agent-compatibility.md`）。

| ID | 必須制約 | 根拠 |
|---|---|---|
| PRM-01 | セット条件の全項目（形式コード・`level.scale`/`level.value`・対象の `target.ref` と `display_name`（および参考情報としての原本レベル表記）・問題数・トピック指定の有無と内容）を明示する。 | GEN-01, GEN-02, GEN-11 |
| PRM-02 | レベル制約の転記: 指定レベルに対する例文語彙の許容Wordlist帯（≤Lx）、例文文法の許容導入レベル（文法問題は≤Lx.y、語彙問題は帯最上位枝番 A1→A1.3, A2→A2.2, B1→B1.2, B2→B2.2）、範囲値の下限=導入レベル解釈。指定レベル超の前提知識の禁止。 | GEN-09, `docs/cefrj-validation-spec.md` |
| PRM-03 | 語数上限: 当該セットの帯に適用される上限値（`data/config/limits.json` の現在値）と計測規則（句読点除くトークン数・空欄は正答代入後・2文時は各文適用）。 | GEN-07 |
| PRM-04 | 固有名詞allowlist: `data/config/proper_nouns.json` の全語の列挙と、リスト外固有名詞の使用禁止、機械的免除（数字・記号・句読点・縮約展開）の説明。 | GEN-10 |
| PRM-05 | 例文規則: 1文原則、2文例外の条件（先行文脈要求の文タイプ2値）と `context_sentence`/`context_required_by` の記録義務、対象語ちょうど1回出現（語彙）、対象構造の実現（文法。当該項目のパターン略記を添付）、トピック制約（指定時のみ）。 | GEN-05, GEN-06, GEN-08, GEN-11 |
| PRM-06 | 出力形式: 当該形式のbodyフィールド一覧（§2）と共通骨格（GEN-01）、空欄マーカー `____` 1箇所規則、出力はJSONオブジェクト1個のみで前後に説明文を付けないこと。 | GEN-01, GEN-26, §2 |
| PRM-07 | 誤答規則（①②⑤のみ）: 語彙4択はアンカー必須・同レベル同品詞・カテゴリ近接優先順位・同義語/区別不能語禁止・anchor記録・緩和条件と `pos_pool_relaxed` 記録。文法選択は同一パラダイム・不成立必須・排除にレベル超知識を要求しない。 | GEN-13〜GEN-16 |
| PRM-08 | 日本語規則: 語義の辞書形式・品詞反映・代表語義・別義重複禁止、訳のです・ます調と忠実性、④の復元可能性（時制・数・人称）。 | GEN-18〜GEN-20 |
| PRM-09 | 解説規則（⑤〜⑨のみ）: 詳細度（⑨=detailed 400字/⑤⑥⑦⑧=brief 200字。`limits.json` の現在値）、読者・文体・用語、教員版文法項目名の明記、⑨の3部構成、⑤⑥⑦⑧の形式別内容要件、新規英語例文の追加禁止。 | GEN-21〜GEN-25 |
| PRM-10 | 選択肢順（①②⑤のみ）: 生成時シャッフル・JSON配列順=表示順・正解位置の固定化禁止。⑦のトークン小文字化・シャッフル・正解順と同一禁止・別解不存在。 | GEN-17, GEN-31, GEN-32 |
| PRM-11 | 禁止事項: 正規化データにない語・項目の使用、教員版レベル未付与16項目のターゲット化、独自のレベル判断による制約の緩和、⑦⑧での先行文脈要求項目のターゲット化、語彙形式への `explanation` の付与。 | GEN-03, GEN-12, GEN-01 |
| PRM-12 | 再生成指示（gen2/gen3のみ）: 前世代の `review_result.violations[]`（`code`・`location`・`evidence`・`expected_level`・`actual_level`・`suggestion`）を提示し、指摘された違反を全て解消した新候補を作ること、指摘のない部分の不必要な変更を避けること。 | `docs/subagent-review-spec.md` |
| PRM-13 | 自己検査チェックリスト: 出力前に当該形式に適用される全GEN規則を1項目ずつ確認する指示（§2各形式の「制約」欄の規則IDを列挙）。 | 共通S-1 |
| PRM-14 | 出典の非改変: 原本の見出し語・pos・レベル・文法項目名を変えて引用してはならないこと（`target` と `anchor` は正規化データの値をそのまま転記）。 | GEN-01, GEN-13 |

## 4. 検証との関係（参照）

本文書の規則の検証は次に委ねる。重複記述を避けるため、判定手順は参照先が正である。

- 機械検査（覆せない自動不合格）: レベル照合・辞書照合・語数・スキーマ整合・anchor実在照合・選択肢構成 → `docs/cefrj-validation-spec.md`。
- LLMレビュー（追加不合格のみ可）: 例文の自然さ・学習上の適切さ・正解の一意性・別解不存在（⑦）・語義の別義重複（①②）・復元可能性（④）・解説内容（⑤〜⑨）・対象構造の実現（パターン略記照合）・誤答排除のレベル超知識（⑤） → `docs/subagent-review-spec.md`。
- 検証項目×担当×形式の対応表 → `docs/cefrj-validation-spec.md` の検証マトリクス。
