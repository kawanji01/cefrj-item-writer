# HTML出力仕様（docs/html-output-spec.md）

## 冒頭ブロック

- **目的**: 合格済み正本 `set.json` から最終成果物である単一自己完結HTML（`output/<set_id>/index.html`）を決定的に生成するための、生成器契約・画面UI・印刷レイアウト・スマホ対応・アクセシビリティの全規則を固定する。
- **対象読者**: 実装者（Codex GPT-5.6 sol）、HTML生成器（`build_html.py`）とテンプレートの実装・保守を行う者、受け入れ試験の実施者。
- **参照文書**:
  - `docs/json-output-spec.md` … `set.json` の物理フィールド定義の正
  - `docs/architecture.md` … CLI契約一覧・エラーコード目録の正・バージョン管理
  - `docs/question-generation-spec.md` … 9形式の問題内容（生成仕様）の正
  - `docs/cefrj-validation-spec.md` … レベル体系・検証規則の正
  - `docs/testing-and-acceptance.md` … HTML決定性テスト（バイト一致）の実施定義
  - `docs/requirements.md` … スコープ外/v2リストの正
- **規範語彙凡例**: 「しなければならない(MUST)」「してはならない(MUST NOT)」「すべきである(SHOULD)」「してもよい(MAY)」。
- **この文書が「正」とする範囲**: HTML生成器の入出力契約と決定性要件、生成されるHTMLのDOM構造・状態遷移・画面上の判定規則・表示文言（UI固定文言）・印刷CSS・スマホ対応基準・アクセシビリティ最低要件・スタイル定数。`set.json` のフィールド定義、問題内容の生成規則、CLIのエラーコード目録は本文書の正ではない（各参照文書を正とする）。

## 1. 生成器契約（CON）

### 1.1 入出力

- **CON-01** HTML生成器は `build_html.py`（CLI契約の正は `docs/architecture.md`）であり、入力は正本 `output/<set_id>/set.json` **のみ**でなければならない(MUST)。`review/` 配下の監査ファイル、正規化データ、設定ファイル、ネットワーク、環境変数のいずれも出力内容の入力にしてはならない(MUST NOT)。
- **CON-02** 出力は `output/<set_id>/index.html` の1ファイルでなければならない(MUST)。1セット=1HTML。他のファイル（CSS・JS・画像・フォント）を出力してはならない(MUST NOT)。
- **CON-03** 生成器は実行前に `set.json` を `schemas/set.schema.json` で検証し、`schema_version` のメジャーが生成器の対応メジャーと一致しない場合は定義済みエラー（`E-CONTRACT-xx` 系。目録は `docs/architecture.md`）で停止しなければならない(MUST)。部分的なHTMLを書き出してはならない(MUST NOT)。
- **CON-04** 生成器はPython 3.11+ ＋ Jinja2 で実装しなければならない(MUST)。テンプレートファイル自体は実装物であり、その挙動仕様は本文書が固定する。
- **CON-05** 生成器は完全オフラインで動作しなければならない(MUST)。ネットワークアクセスを行ってはならない(MUST NOT)。

### 1.2 自己完結性

- **CON-06** 出力HTMLは単一ファイルで自己完結しなければならない(MUST)。CSSとJavaScriptは全て `<style>` / `<script>` としてインライン記述する。外部リソース参照（CDN・Webフォント・画像URL・外部CSS/JS・iframe・fetch/XHR）はゼロでなければならない(MUST NOT: 1件も含めない)。
- **CON-07** 機械検査可能な基準: 出力HTML内の全要素の `src` / `href` 属性に `http://` または `https://` で始まる値が存在しないこと(MUST)。フッター出典内のURLは**リンクにせずテキストとして**表示する（CON-06と両立させるため。`<a>` 要素を使わない）。
- **CON-08** 出力HTMLはJavaScript無効環境でも、ヘッダー・全問題の印刷用紙面（第7節）・フッター出典が閲覧・印刷可能でなければならない(MUST)。対話UIのみJavaScriptに依存してよい(MAY)。

### 1.3 データ受け渡し

- **CON-09** 本文書は `set.json` の内容を**論理名**で参照する。論理名と物理フィールド名の対応は `docs/json-output-spec.md` および `schemas/set.schema.json` を正とし、実装時はそちらの物理名に読み替えなければならない(MUST)。本文書で使う論理名は次の通り:

| 論理名 | 内容 |
|---|---|
| 形式 | `format`（§6共通定数の9値） |
| レベル | `level_scale` と レベル値 |
| セットID | `set_id` |
| 作成日時 | セットメタデータの作成日時文字列 |
| 出典ブロック | `attribution`（Wordlist・Grammar Profile両引用、URL、ダウンロード日） |
| 問題ID | `question_id`（`q01`〜`q20`） |
| 問題文 | 各問のstem（空欄マーカーを含みうる英文または日本語文） |
| 選択肢配列 | 4択の選択肢4件（JSONに保存された固定順） |
| 正解位置 | 選択肢配列中の正解のインデックス |
| 例文 | 対象語・対象構造を含む英文（1文、例外的に2文） |
| 日本語訳 | 例文の日本語訳 |
| 語義 | 語彙問題の対象語の辞書形式語義 |
| 対象語出現位置 | 例文中の対象語の位置（物理表現は `docs/json-output-spec.md` が正） |
| 解説 | 文法5形式の解説文（簡潔=200字上限/詳細=400字上限） |
| 正答 | 穴埋め・書き換えの正解表記（正書法） |
| 同値表記リスト | 正答と同値と認める表記の列挙（縮約形の別表記を含む。生成規則の正は `docs/question-generation-spec.md`） |
| トークン列 | 整序のシャッフル済み提示トークン（全て小文字、句読点除く、JSONに固定順保存） |
| 正解トークン順 | 整序の正解となるトークンの並び |
| 正解文 | 整序の正書法での正解文 |
| 元文 | 書き換えの元の英文 |
| 書き換え指示 | 何を使って書き換えるかの日本語指示文 |
| 目標文 | 書き換え後の英文（空欄マーカーを含む部分入力方式） |

- **CON-10** JavaScriptが判定に用いるデータ（正解位置・同値表記リスト・正解トークン順）は、各問題要素の `data-*` 属性にJSON文字列として埋め込まなければならない(MUST)。埋め込み時の直列化は第2節 DET-06 に従う。`<script>` 内へのデータ二重埋め込みをしてはならない(MUST NOT)（単一情報源の維持）。

## 2. 決定性要件（DET）

- **DET-01** 同一の `set.json`（バイト同一）と同一版の生成器・テンプレートから生成した `index.html` は**バイト一致**しなければならない(MUST)。何回実行しても、どのOS（macOS/Linux/Windows）で実行しても同一であること。CIでの検証は `docs/testing-and-acceptance.md` に従う。
- **DET-02** 禁止事項（出力内容に影響させてはならない(MUST NOT)）:
  1. 実行時刻の取得と埋め込み（`datetime.now()` 等）。画面に表示する作成日時は `set.json` の作成日時の**転記のみ**。
  2. 乱数の使用（`random`、`uuid`、ハッシュシード依存の順序）。
  3. 選択肢・トークン列の**再シャッフル**。選択肢配列とトークン列は `set.json` に保存された順序のまま描画する。
  4. 実行環境依存の値（ロケール・環境変数・ホスト名・ファイルシステム列挙順・生成器のバージョン文字列）の埋め込み。
  5. `set.json` に由来しないコンテンツの動的決定（テンプレート固定文言は許可される。固定文言の正は第5節）。
- **DET-03** 出力の文字コードはUTF-8（BOMなし）、改行はLFでなければならない(MUST)。ファイル末尾は改行1個で終わる。Windows上でもCRLFに変換されないよう、バイナリモードまたは `newline=""` で書き出す(MUST)。
- **DET-04** `set.json` の読み込みは `json.loads` で行い、オブジェクトのキー挿入順を保持しなければならない(MUST)（Python標準の `dict` は挿入順を保持する。順序を変えるソートを行ってはならない(MUST NOT)）。
- **DET-05** Jinja2環境は次の設定で固定しなければならない(MUST): `autoescape=True`、`trim_blocks=True`、`lstrip_blocks=True`、`keep_trailing_newline=True`。テンプレート内で辞書順ソート・集合・時刻関数を使ってはならない(MUST NOT)。
- **DET-06** `data-*` 属性へのJSON直列化は `json.dumps(value, ensure_ascii=False, separators=(",", ":"))` で行い、キー順は入力順を保持しなければならない(MUST)（`sort_keys` を使わない）。属性値のHTMLエスケープはJinja2の `autoescape` に委ねる。
- **DET-07** HTML内でのユーザー操作（フラッシュカードのリセット、整序のやり直し）は**JSONに保存された順序への復帰**でなければならない(MUST)。閲覧時に新たなシャッフルを行ってはならない(MUST NOT)。
- **DET-08** 採点状態・進捗の永続化（localStorage・Cookie・IndexedDB）を行ってはならない(MUST NOT)。ページ再読み込みで全状態が初期化される（永続化は `docs/requirements.md` のv2リスト参照）。

## 3. 共通レイアウトとDOM骨格（LAY）

### 3.1 文書骨格

- **LAY-01** 出力HTMLは次の骨格に従わなければならない(MUST)。クラス名・id名は下記の通り固定する。

```html
<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>CEFR-J {形式表示名} {レベル値}（{セットID}）</title>
<style>/* 全CSSインライン（第4・7・8節の規則を実装） */</style>
</head>
<body>
<header class="site-header">
  <h1>{形式表示名}（{レベル値}）</h1>
  <p class="set-meta">セットID: {セットID} ／ 問題数: {N}問 ／ 作成日: {作成日時}{トピック断片（LAY-14）}</p>
</header>
<noscript><p class="noscript-note">この教材の対話機能を使うにはJavaScriptを有効にしてください。印刷用の紙面はJavaScriptなしで利用できます。</p></noscript>
<main id="screen-ui" class="screen-only"><!-- 第6節: 形式別インタラクティブUI --></main>
<section id="worksheet" class="print-only"><!-- 第7節: 印刷用ワークシート --></section>
<section id="answer-key" class="print-only"><!-- 第7節: 印刷用 解答・解説 --></section>
<footer id="attribution"><!-- 3.3 出典フッター --></footer>
<script>/* 全JSインライン（依存ライブラリなしのプレーンJavaScript） */</script>
</body>
</html>
```

- **LAY-02** `<html lang="ja">` を必須とする(MUST)。英語のテキスト（例文・見出し語・選択肢の英単語・トークン）を含む要素には `lang="en"` を付与しなければならない(MUST)。付与単位は当該英文・英語句を直接囲む最小の要素（`<span lang="en">` / `<p lang="en">` / `<button lang="en">`）とする。
- **LAY-03** `<title>` は `CEFR-J {形式表示名} {レベル値}（{セットID}）` の形式で固定する(MUST)。例: `CEFR-J 語彙4択（英語→日本語） A1（20260816-142530-k7x2）`。
- **LAY-04** 作成日時は `set.json` の作成日時文字列を**整形せずそのまま転記**しなければならない(MUST)（整形処理はロケール依存・実装依存の差異を生むため禁止）。
- **LAY-05** 形式コード→形式表示名の対応は次の表で固定する(MUST)。本表はHTML内表示名の正である（対話中の形式名文言は `docs/interaction-flow.md` を正とする）。

| 形式コード | 形式表示名 |
|---|---|
| `vocab_mcq_en2ja` | 語彙4択（英語→日本語） |
| `vocab_mcq_ja2en` | 語彙4択（日本語→英語） |
| `vocab_flashcard_en2ja` | 例文フラッシュカード（英語→日本語） |
| `vocab_flashcard_ja2en` | 例文フラッシュカード（日本語→英語） |
| `grammar_mcq` | 文法選択問題 |
| `grammar_cloze` | 文法穴埋め問題 |
| `grammar_reorder` | 語句整序問題 |
| `grammar_rewrite` | 書き換え問題 |
| `grammar_example_selfcheck` | 文法例文問題（自己採点） |

### 3.2 共通表示規則

- **LAY-06** 問題番号の画面・印刷表示は「問1」〜「問20」（`question_id` の数値部から先頭ゼロを除いた値）で固定する(MUST)。
- **LAY-07** 問題文・例文中の空欄マーカーは、画面表示（入力欄を置く場合を除く）・印刷とも半角アンダースコア7文字 `_______` を `<span class="blank" role="img" aria-label="空欄">` で囲んで表示する(MUST)。
- **LAY-08** 語彙形式（①③④）の例文中の対象語（`target_surface` で示される範囲）は `<strong class="target">` で囲んで強調表示しなければならない(MUST)。文法形式にはスパン情報がないため適用しない（⑨は UI-24）。色のみによる強調をしてはならない(MUST NOT)（太字＋下線で表現。ACC-05参照）。
- **LAY-09** 4択の選択肢ラベルは表示順に `A` `B` `C` `D` で固定する(MUST)。表示順は選択肢配列の保存順（DET-02-3）。
- **LAY-10** 対話UI（`#screen-ui`）内の各問題は `<section class="question" id="{question_id}" data-format="{形式コード}">` とし、内部に見出し `<h2>問{n}</h2>` を置く(MUST)。フラッシュカード（③④）のみデッキUI（6.3）とし、問題ごとのセクション見出しを持たない。

### 3.3 出典フッター

- **LAY-11** フッター `#attribution` は画面・印刷の**両方で常時表示**しなければならない(MUST)（`screen-only` / `print-only` を付けない）。開閉UIにしてはならない(MUST NOT)。
- **LAY-12** フッターの内容は次で固定する(MUST):
  1. 見出し `<h2>出典</h2>`
  2. `set.json` の出典ブロックにあるWordlist引用文（日本語書式・URL・ダウンロード日を含む）を1段落として**そのまま転記**
  3. 同 Grammar Profile引用文を1段落として**そのまま転記**
  4. 固定文 `本教材は上記CEFR-J資料に基づいて生成されたものです。内容の教育利用にあたっては指導者が最終確認を行ってください。`
- **LAY-13** フッター内のURLはテキスト表示とし、`<a>` によるリンクにしてはならない(MUST NOT)（CON-07）。
- **LAY-14（トピック表示）** `set.json` の `topic` が非 `null` の場合のみ、`.set-meta` 行の末尾に `／ トピック: {topic}` の断片（先頭に全角スラッシュと半角スペースを含むこの実文）を追加する(MUST)。`null` の場合はこの断片を一切出力してはならない(MUST NOT)。

## 4. スタイル定数（STY）

- **STY-01** 配色は次のCSSカスタムプロパティで固定する(MUST)。ライト単一テーマとし、ダークモード対応（`prefers-color-scheme` による切替）を実装してはならない(MUST NOT)（決定性と検証容易性のため。将来対応は `docs/requirements.md` の V2-09）。

```css
:root {
  --color-bg: #ffffff;        /* 背景 */
  --color-text: #1f2328;      /* 本文（白背景でコントラスト比 約15:1） */
  --color-muted: #57606a;     /* 補助テキスト（約4.6:1） */
  --color-accent: #0a58ca;    /* 操作要素・フォーカス（約5.5:1） */
  --color-correct: #0f5132;   /* 正解テキスト（白背景 約9.9:1） */
  --color-correct-bg: #d1e7dd;/* 正解背景（上の文字色との比 約7.9:1） */
  --color-wrong: #842029;     /* 不正解テキスト（白背景 約8.4:1） */
  --color-wrong-bg: #f8d7da;  /* 不正解背景（上の文字色との比 約6.9:1） */
  --color-border: #d0d7de;    /* 枠線（装飾。コントラスト要件の対象外） */
}
```

- **STY-02** フォントはシステムフォントのみを使い、次のスタックで固定する(MUST)。Webフォントを使ってはならない(MUST NOT)。

```css
font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto,
  "Hiragino Sans", "Noto Sans CJK JP", "Yu Gothic", Meiryo, sans-serif;
```

- **STY-03** 基本フォントサイズは `16px` 以上(MUST)。例文・問題文は `1.125rem` 以上とすべきである(SHOULD)。
- **STY-04** テキストと背景の全ての組み合わせは STY-01 のトークンのみから構成し、新しい色値をテンプレートに直書きしてはならない(MUST NOT)。

## 5. UI固定文言目録（STR）

- **STR-01** 対話UIの固定文言は次の目録の実文で固定する(MUST)。表記ゆれ（句読点・カギ括弧・スペースの差異）を作ってはならない(MUST NOT)。`{…}` はJavaScriptが埋める可変部。

| ID | 文言（実文） | 用途 |
|---|---|---|
| S-01 | `答え合わせ` | 穴埋め・整序・書き換えの判定ボタン |
| S-02 | `答えを見る` | フラッシュカードのめくり・例文問題の開示ボタン |
| S-03 | `正解です` | 正誤フィードバック（正解） |
| S-04 | `不正解です` | 正誤フィードバック（不正解） |
| S-05 | `正解: ` | 正解提示の前置きラベル |
| S-06 | `解説` | 解説開閉（`<summary>`）ラベル |
| S-07 | `覚えた` | フラッシュカード自己採点 |
| S-08 | `まだ` | フラッシュカード自己採点 |
| S-09 | `できた` | 例文問題の自己採点 |
| S-10 | `できなかった` | 例文問題の自己採点 |
| S-11 | `もう一度最初から` | フラッシュカードのリセットボタン |
| S-12 | `あなたの解答: ` | 判定後の入力・並びの再掲ラベル |
| S-13 | `正解数: {c} / {n}` | 4択・穴埋め・整序・書き換えの集計行 |
| S-14 | `覚えた: {c} / {n}` | フラッシュカードのサマリー集計 |
| S-15 | `まだのカード` | サマリー内の「まだ」一覧見出し |
| S-16 | `できた: {c} / {n}` | 例文問題の集計行 |
| S-17 | `やり直す` | 整序の並びを全消去するボタン |
| S-18 | `結果` | フラッシュカードのサマリー見出し |
| S-19 | `日本語訳: ` | 例文問題・カード裏の訳ラベル |
| S-20 | `語義: ` | フラッシュカード裏の語義ラベル |
| S-21 | `元の文: ` | 書き換えの元文ラベル |
| S-22 | `指示: ` | 書き換え指示ラベル |
| S-23 | `書き換え後: ` | 書き換え目標文ラベル |
| S-24 | `{i} / {n}` | フラッシュカードの進捗表示（i=現在のカード番号） |
| S-25 | `（正解）` | 判定後に正解選択肢へ付す明示ラベル |
| S-26 | `（あなたの選択）` | 判定後に選択した不正解選択肢へ付すラベル |

- **STR-02** 形式別の固定指示文（各形式のUI冒頭に1回表示する）は次で固定する(MUST):

| 形式コード | 指示文（実文） |
|---|---|
| `vocab_mcq_en2ja` | `英単語の正しい意味を選びましょう。` |
| `vocab_mcq_ja2en` | `意味に合う英単語を選びましょう。` |
| `vocab_flashcard_en2ja` | `英文の意味を思い浮かべてから、カードをめくりましょう。` |
| `vocab_flashcard_ja2en` | `日本語に合う英文を思い浮かべてから、カードをめくりましょう。` |
| `grammar_mcq` | `空欄に入る最も適切なものを選びましょう。` |
| `grammar_cloze` | `空欄に入る語句を入力しましょう。` |
| `grammar_reorder` | `意味が通る英文になるように、語句を順にタップしましょう。` |
| `grammar_rewrite` | `指示に従って、書き換えた文の空欄を埋めましょう。` |
| `grammar_example_selfcheck` | `英文の意味を思い浮かべてから、答えを見て自己採点しましょう。` |

- **STR-03** 印刷紙面の固定文言は次で固定する(MUST): ワークシート見出し `問題`、解答見出し `解答・解説`、氏名欄 `名前：`（後続に記入用下線）。
- **STR-04** 本目録にない表示文言をテンプレートに追加してはならない(MUST NOT)。追加が必要になった場合は本文書の改訂（`CHANGELOG.md` 記載）を経る。

## 6. 形式別画面UI仕様（UI）

共通事項:

- **UI-00a** 全ての操作要素は `<button type="button">` で実装しなければならない(MUST)。`<div>` への clickハンドラ付与で代替してはならない(MUST NOT)。
- **UI-00b** 正誤・開示のフィードバック領域は各問につき1つの `<p class="feedback" role="status">` とし、JavaScriptがテキストを書き込む(MUST)。`role="status"`（暗黙の `aria-live="polite"`）によりスクリーンリーダーへ通知する。
- **UI-00c** 集計行（S-13/S-14/S-16）はページ最下部（フラッシュカードはサマリー画面内）の `<p class="score" role="status">` に表示し、判定確定のたびに更新する(MUST)。
- **UI-00d** 一度判定が確定した問題は再操作不可（ボタン `disabled`・入力 `disabled`）とする(MUST)。ページ全体のやり直しはブラウザの再読み込みで行う（状態は永続化されない。DET-08）。フラッシュカードのみ S-11 でリセット可能。

### 6.1 語彙4択 ①`vocab_mcq_en2ja` ②`vocab_mcq_ja2en`

- **UI-01** DOM骨格（1問分。①の `.stem` は `body.stem` の英例文で、`body.target_surface` の出現範囲を LAY-08 でハイライトし、品詞ラベル（UI-04）を後置する。②は `.stem` が日本語の語義（`lang` なし）＋空欄入り英例文 `body.sentence_with_blank`（LAY-07 の空欄マーカー表示、`lang="en"`）、選択肢ボタンが英単語（`lang="en"`）になる）:

```html
<section class="question" id="q01" data-format="vocab_mcq_en2ja" data-answer-index="2">
  <h2>問1</h2>
  <p class="stem"><span lang="en">She decided to <strong class="target">abandon</strong> the plan.</span> <span class="pos">[動詞]</span></p>
  <ul class="choices" role="list">
    <li><button type="button" class="choice" data-index="0"><span class="choice-label">A</span> <span class="choice-text">〜を達成する</span></button></li>
    <li><button type="button" class="choice" data-index="1">…</button></li>
    <li><button type="button" class="choice" data-index="2">…</button></li>
    <li><button type="button" class="choice" data-index="3">…</button></li>
  </ul>
  <p class="feedback" role="status"></p>
  <p class="translation-line" hidden><span class="label">日本語訳: </span>{①: stem_ja ／ ②: sentence_complete と sentence_ja}</p>
</section>
```

②の `.stem` は次の2段構成とする: `<p class="stem">能力</p><p class="stem-sentence" lang="en">He has the <span class="blank" role="img" aria-label="空欄">_______</span> to speak three languages.</p>`。

- **UI-02** 状態遷移:

| 状態 | イベント | 遷移先 | 表示変化 |
|---|---|---|---|
| `unanswered`（初期） | 選択肢ボタンをタップ | `answered` | 下記の判定表示。全選択肢ボタンを `disabled` |
| `answered`（終端） | — | — | 再操作不可（UI-00d） |

- **UI-03** 判定（JDG-01）: タップされた `data-index` が `data-answer-index` と一致すれば正解。判定表示は次を全て行う(MUST):
  1. `.feedback` に S-03 または S-04 を表示。
  2. 正解の選択肢ボタンに class `is-correct`（`--color-correct-bg` 背景・`--color-correct` 文字）を付与し、選択肢テキスト末尾に S-25 を追記。
  3. 不正解を選んだ場合、その選択肢ボタンに class `is-wrong`（`--color-wrong-bg` / `--color-wrong`）を付与し、末尾に S-26 を追記。
  4. `.translation-line` を表示する: ①は S-19 ラベル＋`body.stem_ja`。②は `body.sentence_complete`（`lang="en"`）と `body.sentence_ja` を併記。
  5. 集計行（S-13）を更新。
- **UI-04** ①の `.stem` には例文（対象語を LAY-08 でハイライト）と品詞ラベルを表示する(MUST)。品詞ラベルは `target.ref`（`lex:<headword>:<pos'>`）の `<pos'>` 部分（`-` を空白に復元した pos 15種）から次の固定対応表で導出する(MUST)。本表はテンプレート固定文言（DET-02-5 の許可範囲）である。

| pos | ラベル | pos | ラベル | pos | ラベル |
|---|---|---|---|---|---|
| noun | [名詞] | verb | [動詞] | adjective | [形容詞] |
| adverb | [副詞] | pronoun | [代名詞] | preposition | [前置詞] |
| determiner | [限定詞] | conjunction | [接続詞] | number | [数詞] |
| modal auxiliary | [助動詞] | be-verb | [be動詞] | do-verb | [do動詞] |
| have-verb | [have動詞] | interjection | [間投詞] | infinitive-to | [不定詞to] |

### 6.2 文法選択問題 ⑤`grammar_mcq`

- **UI-05** DOM骨格は UI-01 に準じ、次の差分を持つ(MUST): `.stem` は空欄マーカー（LAY-07）入り英文（`lang="en"`）、選択肢は英語の語句（`lang="en"`）。`.feedback` の直後に解説を置く:

```html
  <details class="explanation"><summary>解説</summary><p>{解説（簡潔・200字上限）}</p></details>
```

- **UI-06** 状態遷移は UI-02 と同一。判定表示（UI-03。⑤の `.translation-line` には判定確定時に `body.example_ja` を S-19 ラベルで表示する）に加え、判定確定時に `.explanation` の `open` 属性を付与して自動展開する(MUST)。展開後も `<details>` の開閉操作は可能のままにする。判定確定まで `.explanation` は `hidden` 属性で非表示とする(MUST)（先に解説が読める状態にしない）。

### 6.3 例文フラッシュカード ③`vocab_flashcard_en2ja` ④`vocab_flashcard_ja2en`

- **UI-07** デッキUI。DOM骨格:

```html
<section class="deck" data-format="vocab_flashcard_en2ja">
  <p class="deck-progress" role="status">1 / 10</p>
  <div class="card" id="q01" data-state="front">
    <div class="card-front">
      <p class="sentence" lang="en">I usually <strong class="target">watch</strong> TV after dinner.</p>
    </div>
    <div class="card-back" hidden>
      <p class="translation"><span class="label">日本語訳: </span>私はふだん夕食後にテレビを見ます。</p>
      <p class="gloss"><span class="label">語義: </span><span lang="en">watch</span> [動詞] 〜を見る</p>
    </div>
    <div class="card-actions">
      <button type="button" class="flip">答えを見る</button>
      <button type="button" class="mark-known" hidden>覚えた</button>
      <button type="button" class="mark-unknown" hidden>まだ</button>
    </div>
  </div>
  <!-- 2枚目以降のカードは hidden で後続配置 -->
  <div class="deck-summary" hidden>
    <h2>結果</h2>
    <p class="score" role="status">覚えた: 0 / 10</p>
    <h3>まだのカード</h3>
    <ul class="unknown-list" role="list"></ul>
    <button type="button" class="restart">もう一度最初から</button>
  </div>
</section>
```

④は `.card-front` に日本語訳、`.card-back` に英例文（対象語ハイライト付き、`lang="en"`）＋語義を置く。

- **UI-08** 表面の表示内容(MUST): ③=英例文（対象語を LAY-08 でハイライト）。④=日本語訳。裏面(MUST): ③=日本語訳＋語義（S-19/S-20 ラベル）。④=英例文（ハイライト付き）＋語義。
- **UI-09** 状態遷移（カード単位＋デッキ単位）:

| 状態 | イベント | 遷移先 | 表示変化 |
|---|---|---|---|
| カード `front`（初期） | S-02 ボタン、またはカード面のタップ | `back` | `.card-back` を表示、S-02 を隠し S-07/S-08 ボタンを表示 |
| カード `back` | S-07 タップ | 次カード `front` | 当該カードを「覚えた」に記録して `hidden`、次カードを表示、進捗（S-24）更新 |
| カード `back` | S-08 タップ | 次カード `front` | 当該カードを「まだ」に記録（同上） |
| 最終カードの `back` | S-07/S-08 タップ | `summary` | 全カード `hidden`、`.deck-summary` 表示 |
| `summary` | S-11 タップ | 1枚目 `front` | 全記録を消去し、**JSON保存順のまま**1枚目から再開（DET-07） |

- **UI-10** カードは1枚ずつ表示し(MUST)、「まだ」のカードの再キュー（同一周回内での再出題）は行わない(MUST NOT)。1周のみで `summary` に至る。
- **UI-11** サマリー(MUST): S-14 の集計行、S-15 見出しの下に「まだ」と記録されたカードの表面テキストを保存順で `<li>` 列挙、S-11 ボタン。「まだ」が0件のときは S-15 見出しとリストを `hidden` にする。
- **UI-12** カード面のタップでもめくれるようにしてよい(MAY)が、キーボード操作は S-02 ボタンで必ず可能でなければならない(MUST)（ACC-06）。

### 6.4 文法穴埋め ⑥`grammar_cloze`

- **UI-13** DOM骨格:

```html
<section class="question" id="q01" data-format="grammar_cloze"
         data-accepted='["did not","didn&#39;t"]'>
  <h2>問1</h2>
  <p class="stem" lang="en">She <span class="cloze-slot"><label class="visually-hidden" for="q01-input">空欄に入る語句</label><input id="q01-input" type="text" autocomplete="off" autocapitalize="off" spellcheck="false" lang="en"></span><span class="cue">（<span lang="en">go</span>）</span> go to school yesterday.</p>
  <button type="button" class="check" disabled>答え合わせ</button>
  <p class="feedback" role="status"></p>
  <p class="answer-line" hidden><span class="label">正解: </span><span lang="en">{正答（正書法）}</span></p>
  <details class="explanation" hidden><summary>解説</summary><p>{解説（簡潔・200字上限）}</p></details>
</section>
```

`data-accepted` は正答＋同値表記リストの全要素の配列（CON-10、DET-06）。`.cue` は `body.cue`（内容語の原形ヒント。生成規則の正は `docs/question-generation-spec.md` GEN-30a）が非 `null` の場合のみ、空欄直後に全角括弧で囲んで出力する(MUST)。`cue` が `null` の場合は `.cue` 要素自体を出力してはならない(MUST NOT)。

- **UI-14** 状態遷移:

| 状態 | イベント | 遷移先 | 表示変化 |
|---|---|---|---|
| `input`（初期） | 入力欄のテキスト変化 | `input` | 正規化後（JDG-02）に空でなければ S-01 ボタンを有効化、空なら無効化 |
| `input` | S-01 タップ、または入力欄でEnterキー（ボタン有効時のみ） | `judged` | 下記の判定表示 |
| `judged`（終端） | — | — | 入力欄・ボタン `disabled` |

- **UI-15** 判定表示(MUST): `.feedback` に S-03/S-04。`.answer-line`（S-05 ラベル＋正答の正書法）を表示。不正解時は S-12 ラベルで入力値をそのまま再掲する行を `.feedback` の後に追加。`.explanation` を `open` 付きで表示（UI-06と同じ規則）。集計行更新。判定規則は JDG-02。

### 6.5 語句整序 ⑦`grammar_reorder`

- **UI-16** DOM骨格:

```html
<section class="question" id="q01" data-format="grammar_reorder"
         data-answer-tokens='["i","did","not","go","to","school"]'>
  <h2>問1</h2>
  <p class="ja-hint">{日本語訳}</p>
  <div class="answer-row" role="group" aria-label="並べた語句"></div>
  <div class="token-bank" role="group" aria-label="語句の候補">
    <button type="button" class="token" lang="en" data-token="school">school</button>
    <!-- トークン列の保存順どおりに全トークンをボタンとして配置 -->
  </div>
  <div class="reorder-actions">
    <button type="button" class="reset">やり直す</button>
    <button type="button" class="check" disabled>答え合わせ</button>
  </div>
  <p class="feedback" role="status"></p>
  <p class="answer-line" hidden><span class="label">正解: </span><span lang="en">{正解文（正書法）}</span></p>
  <details class="explanation" hidden><summary>解説</summary><p>{解説（簡潔・200字上限）}</p></details>
</section>
```

- **UI-17** 操作規則(MUST):
  1. `token-bank` のトークンをタップすると、そのボタンは bank 内で `disabled`＋class `is-used` になり、同じテキストのトークンボタンが `answer-row` の末尾に追加される。
  2. `answer-row` 内のトークンをタップすると、そのトークンは `answer-row` から除去され、対応する bank 内ボタン（`is-used` のうち**最も左**のもの）が再度有効になる。
  3. S-17（やり直す）は `answer-row` を空にし、bank を初期状態（保存順・全て有効）に戻す。
  4. ドラッグ＆ドロップを実装してはならない(MUST NOT)（タップ順選択のみ）。
  5. 全トークンが `answer-row` に置かれたときのみ S-01 ボタンを有効化する。
- **UI-18** 状態遷移:

| 状態 | イベント | 遷移先 | 表示変化 |
|---|---|---|---|
| `building`（初期） | トークン移動（UI-17-1/2/3） | `building` | S-01 の有効/無効を UI-17-5 で更新 |
| `building`（全トークン配置済み） | S-01 タップ | `judged` | 下記の判定表示 |
| `judged`（終端） | — | — | 全トークン・S-17・S-01 を `disabled` |

- **UI-19** 判定表示(MUST): `.feedback` に S-03/S-04。`.answer-line`（S-05＋正解文の正書法）を表示。不正解時は S-12 ラベルで並べた順のトークンを半角スペース区切りで再掲。`.explanation` を `open` 付きで表示。集計行更新。判定規則は JDG-03。
- **UI-20** 日本語訳（`.ja-hint`）は問題提示時から常時表示する(MUST)（並べ替えの意味的手がかりとして設計上必須。`docs/question-generation-spec.md` の整序仕様と対応）。

### 6.6 書き換え ⑧`grammar_rewrite`

- **UI-21** DOM骨格:

```html
<section class="question" id="q01" data-format="grammar_rewrite"
         data-accepted='["was written"]'>
  <h2>問1</h2>
  <p class="source-line"><span class="label">元の文: </span><span lang="en">{元文}</span></p>
  <p class="instruction-line"><span class="label">指示: </span>{書き換え指示}</p>
  <p class="stem"><span class="label">書き換え後: </span><span lang="en">This book <span class="cloze-slot"><label class="visually-hidden" for="q01-input">空欄に入る語句</label><input id="q01-input" type="text" autocomplete="off" autocapitalize="off" spellcheck="false" lang="en"></span> by a famous author.</span></p>
  <button type="button" class="check" disabled>答え合わせ</button>
  <p class="feedback" role="status"></p>
  <p class="answer-line" hidden><span class="label">正解: </span><span lang="en">{目標文の完成形（正書法）}</span></p>
  <details class="explanation" hidden><summary>解説</summary><p>{解説（簡潔・200字上限）}</p></details>
</section>
```

- **UI-22** 状態遷移・判定表示・判定規則は穴埋め（UI-14・UI-15・JDG-02）と同一とする(MUST)。相違点は表示のみ: S-21/S-22/S-23 ラベルで元文・指示・目標文を提示し、`.answer-line` には空欄部分だけでなく**目標文の完成形**を表示する。

### 6.7 例文問題（自己採点） ⑨`grammar_example_selfcheck`

- **UI-23** 全問を一覧表示（デッキUIにしない）。DOM骨格（1問分）:

```html
<section class="question" id="q01" data-format="grammar_example_selfcheck">
  <h2>問1</h2>
  <p class="sentence" lang="en">She has been living in Tokyo since 2020.</p>
  <button type="button" class="reveal">答えを見る</button>
  <div class="answer-area" hidden>
    <p class="translation"><span class="label">日本語訳: </span>{日本語訳}</p>
    <div class="explanation-full"><h3>解説</h3><p>{解説（詳細・400字上限）}</p></div>
    <div class="selfcheck-actions">
      <button type="button" class="mark-ok">できた</button>
      <button type="button" class="mark-ng">できなかった</button>
    </div>
  </div>
  <p class="feedback" role="status"></p>
</section>
```

- **UI-24** 本形式は**英文を提示し、学習者が日本語訳を想起してから開示・自己採点する**方向で固定する(MUST)。対象構造のハイライトは行わない(MUST NOT)（⑨のペイロードには対象構造のスパン情報が存在せず、`set.json` のみから決定的に導出できないため。CON-01/DET-02-5）。
- **UI-25** 状態遷移:

| 状態 | イベント | 遷移先 | 表示変化 |
|---|---|---|---|
| `question`（初期） | S-02 タップ | `revealed` | `.answer-area` 表示、S-02 を `disabled` |
| `revealed` | S-09 または S-10 タップ | `done` | `.feedback` にタップした文言（S-09/S-10）を表示、両ボタン `disabled`、集計行（S-16）更新 |
| `done`（終端） | — | — | 再操作不可 |

- **UI-26** 詳細解説は `<details>` ではなく常時表示ブロック（`.explanation-full`）とする(MUST)（開示操作は S-02 で既に行われており、二重の開閉を設けない）。

## 7. 印刷CSS仕様（PRN）

### 7.1 共通

- **PRN-01** 印刷は `@media print` で制御する(MUST)。`#screen-ui`・`noscript` は `display: none`、`#worksheet`・`#answer-key` は `display: block` とする。画面では逆に `#worksheet`・`#answer-key` を `display: none` とする（class `screen-only` / `print-only` で実装）。
- **PRN-02** ページ設定は `@page { size: A4; margin: 15mm; }` で固定する(MUST)。
- **PRN-03** `#answer-key`（解答・解説）は `break-before: page`（互換のため `page-break-before: always` を併記）でワークシートから必ず改ページする(MUST)。
- **PRN-04** 1問のブロックには `break-inside: avoid`（併記: `page-break-inside: avoid`）を指定する(MUST)。
- **PRN-05** 印刷紙面は白黒印刷で成立しなければならない(MUST)。正誤・強調を色のみで表現してはならない(MUST NOT)（太字・下線・記号で表現）。
- **PRN-06** ワークシート冒頭に次を置く(MUST): `<h2>問題</h2>`、形式表示名とレベル値の行、指示文（STR-02 と同文）、氏名欄（STR-03 の `名前：` ＋ 下線）。解答部冒頭は `<h2>解答・解説</h2>`。
- **PRN-07** フッター出典（`#attribution`）は印刷にも含める(MUST)（LAY-11）。

### 7.2 形式別ワークシート

- **PRN-08** ①②（語彙4択）: 問題ごとに「問n」＋stem（①=例文。対象語は太字下線＋品詞ラベル。②=語義＋空欄マーカー入り英例文）＋選択肢4行（`A` 〜 `D` ラベル＋テキスト、行頭に手書きチェック用の `（　）` を置かない。選択記入は問題番号右の解答欄 `答え（　　）` に書く）。解答部: `問n　{正解ラベル}　{正解テキスト}` に続けて、①は `stem_ja`、②は `sentence_complete` と `sentence_ja` を併記して列挙。
- **PRN-09** ⑤（文法選択）: PRN-08 と同一レイアウト。解答部は正解ラベル＋正解語句＋解説全文（簡潔）。
- **PRN-10** ③④（フラッシュカード）: 印刷では**リスト形式に退化**する(MUST)。ワークシート=「問n」＋表面テキストのみの番号付きリスト（③は英例文＋対象語太字下線、④は日本語訳）。解答部=番号＋表面＋裏面（対訳・語義）を1問1ブロックで列挙。カード状のレイアウト・切り取り線を実装してはならない(MUST NOT)（v1では退化リストのみ）。
- **PRN-11** ⑥（穴埋め）: ワークシート=空欄マーカー（LAY-07）入り英文＋記入用下線（空欄マーカーがそのまま記入欄を兼ねる。追加の記入枠は置かない）。解答部=正答（正書法）＋同値表記リストがあれば `（別解: {同値表記を「, 」区切り}）` ＋解説。
- **PRN-12** ⑦（整序）: ワークシート=「問n」＋日本語訳＋トークン列を保存順のまま `[ token / token / … ]` 形式（半角スラッシュ区切り、全体を角括弧）で提示＋記入用下線1行。解答部=正解文（正書法）＋解説。
- **PRN-13** ⑧（書き換え）: ワークシート=S-21/S-22/S-23 と同じラベルで元文・指示・空欄入り目標文を提示（空欄は LAY-07 マーカー）。解答部=目標文の完成形＋解説。
- **PRN-14** ⑨（例文問題）: ワークシート=「問n」＋英文（対象構造太字下線）＋訳記入用の下線2行。解答部=日本語訳＋詳細解説全文。

## 8. スマホ対応基準（MOB）

- **MOB-01** `<meta name="viewport" content="width=device-width, initial-scale=1">` を必須とする(MUST)（LAY-01 の実文どおり。`user-scalable=no` や `maximum-scale` の指定を追加してはならない(MUST NOT)＝ピンチ拡大を妨げない）。
- **MOB-02** 全ての操作要素（ボタン・入力欄・`<summary>`）のタップ領域は **最小 44×44 CSS px** でなければならない(MUST)（`min-height: 44px` と十分なパディングで担保）。隣接する操作要素の間隔は 8px 以上とすべきである(SHOULD)。
- **MOB-03** ビューポート幅 **375px** において横スクロールが発生してはならない(MUST NOT)。担保する実装規則: コンテンツ最大幅のコンテナ（`max-width: 720px; margin-inline: auto; padding-inline: 16px`）、全要素 `box-sizing: border-box`、長い英単語・URLに `overflow-wrap: break-word`、トークンバンクは `flex-wrap: wrap`。
- **MOB-04** 単一カラムレイアウトを基本とする(MUST)。375px〜デスクトップまでメディアクエリなしで成立するフルードレイアウトとすべきである(SHOULD)（印刷用 `@media print` を除き、レイアウト分岐を増やさない）。
- **MOB-05** 4択の選択肢ボタンはコンテナ幅いっぱい（`width: 100%`）の縦積みとする(MUST)。
- **MOB-06** 入力欄（⑥⑧）の `font-size` は 16px 以上とする(MUST)（iOS Safariのフォーカス時自動ズームを防ぐ）。

## 9. アクセシビリティ最低要件（ACC）

- **ACC-01** `lang` 属性: 文書は `lang="ja"`、英語コンテンツは最小要素単位で `lang="en"`（LAY-02）(MUST)。
- **ACC-02** コントラスト: 全てのテキストとその背景のコントラスト比は **4.5:1 以上**でなければならない(MUST)。STY-01 の配色トークンはこれを満たすよう選定済みであり、トークン外の色を使わないこと（STY-04）で担保する。装飾的な枠線（`--color-border`）は対象外。
- **ACC-03** キーボード操作: 全ての対話機能（選択・めくり・自己採点・答え合わせ・トークン選択/除去・やり直し・解説開閉・リセット）はキーボードのみ（Tab移動＋Enter/Space）で完結しなければならない(MUST)。UI-00a により `<button>` を使うことでネイティブ挙動を得る。独自のキーボードイベント処理は⑥⑧のEnter判定（UI-14）のみとする。
- **ACC-04** フォーカス表示: `:focus-visible` に `outline: 3px solid var(--color-accent); outline-offset: 2px;` を指定し(MUST)、`outline: none` で消してはならない(MUST NOT)。
- **ACC-05** 色以外の手がかり: 正誤・正解位置・対象語強調は、色に加えてテキストラベル（S-03/S-04/S-25/S-26）または書体（太字＋下線）で表現しなければならない(MUST)。
- **ACC-06** 状態通知: 正誤フィードバックと集計は `role="status"` の要素への書き込みで行う(MUST)（UI-00b/UI-00c）。
- **ACC-07** 非表示テキスト用に class `visually-hidden`（画面外配置で読み上げのみ可能にする標準手法）を定義し、⑥⑧の入力欄ラベルに使う(MUST)。`display: none` をラベルに使ってはならない(MUST NOT)。
- **ACC-08** 見出し階層は `h1`（ページタイトル）→ `h2`（問n・出典・結果・問題/解答・解説）→ `h3`（サマリー内小見出し・詳細解説見出し）とし、レベルを飛ばしてはならない(MUST NOT)。

## 10. 画面上の判定規則（JDG）

- **JDG-01 4択（①②⑤）**: 選択された選択肢のインデックスが正解位置と一致すれば正解。それ以外は不正解。判定は1問1回で確定（UI-00d）。
- **JDG-02 穴埋め・書き換え（⑥⑧）**: 次の正規化関数 `normalize` を入力値と受理配列（`data-accepted` の各要素）の両方に適用し、`normalize(入力)` が受理配列のいずれかの `normalize` 結果と完全一致すれば正解:
  1. Unicode正規化 NFC（`String.prototype.normalize("NFC")`）
  2. 前後空白の除去（trim）
  3. 連続する空白文字（タブ・改行を含む）を半角スペース1個に置換
  4. 全体を小文字化（`toLowerCase()`）

  受理配列の内容（正答＋同値表記リスト）の生成規則は `docs/question-generation-spec.md` を正とする。HTML側で同値表記を追加生成してはならない(MUST NOT)（例: アポストロフィの異体字変換を勝手に加えない）。
- **JDG-03 整序（⑦）**: `answer-row` に並んだトークンのテキスト列（配列）が、`data-answer-tokens` の配列と**要素ごとに完全一致**すれば正解。トークンは保存時点で全て小文字（派生既定値）のため追加の正規化は行わない。同一表記のトークンが複数ある場合、テキスト列比較により互いに交換可能として扱われる（正しい挙動として仕様化する）。別解となる正しい並びが存在しないことは生成・レビュー段階で保証済み（`docs/subagent-review-spec.md` 参照）であり、HTML側は単一の正解トークン順のみ照合する。
- **JDG-04 フラッシュカード（③④）・例文問題（⑨）**: 機械判定なし。学習者の自己申告（S-07/S-08、S-09/S-10）を集計にのみ使う。
- **JDG-05** 全判定はブラウザ内のJavaScriptのみで完結し(MUST)、判定結果の送信・保存を行ってはならない(MUST NOT)（DET-08、テレメトリなし）。

## 11. テスト・受け入れとの対応

- **TST-01** 本文書の機械検証可能な規則は `docs/testing-and-acceptance.md` の決定的CIでテストする: DET-01（同一 `set.json` からのバイト一致）、CON-07（外部URL参照ゼロ）、LAY-01（骨格要素の存在）、DET-03（UTF-8/LF）。
- **TST-02** 目視・実機確認が必要な規則（MOB-03 の375px横スクロールなし、ACC-03 のキーボード完結、PRN系の印刷レイアウト）は手動受け入れチェックリストの対象とする（項目定義は `docs/testing-and-acceptance.md` が正）。
- **TST-03** 対応ブラウザの参考目標: 2024年以降にリリースされた Safari / Chrome / Firefox / Edge。合否条件は本文書の各規則の充足のみであり、特定ブラウザバージョンでの動作は参考目標とする。
