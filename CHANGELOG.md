# CHANGELOG

## 2026-08-16 — M2 機械検査

### 実装

- `scripts/lookup.py` を追加し、語彙・文法の通常照会、併記グループ展開、複数条件AND、誤答プールのカテゴリ優先順、CEFR-J範囲包含、文脈要求項目除外を、正規化データの決定的順序を保って実装した。
- `scripts/machine_check.py` を追加し、9形式の検査対象抽出、spaCy文数・語数計測、POS 15種対応、複数語最長一致、Wordlist・allowlist・4免除クラス照合、ターゲット・選択肢・誤答由来・整序・穴埋め・書き換え検査、および `machine_report` 生成を実装した。
- 両CLIでCLI-08の【基本】【データ】を実施し、原本xlsx・原本SHA-256・正規化3ファイル・設定2ファイルを処理前に検証するfail-closed境界を共通化した。`machine_check.py` は加えてspaCyモデル版とcandidateスキーマを検証する。
- 正常JSON・定義済みエラーJSONを正準形UTF-8で出力し、`machine_check.py` は検査結果がfailでも終了コード0、定義済み停止は終了コード1、内部例外は2とした。監査ファイルは書き込まない。
- PLN-05で承認されたM2D-01〜M2D-08を `DECISIONS.md` へ記録し、`IMPLEMENTATION_PLAN.md` と影響する設計文書を承認内容どおりに改訂した。`schemas/` は変更していない。

### R1レビュー修正

- `pos_pool_relaxed=true` を、対象自身を除く同レベル・同品詞プールが3語未満で、実在する誤答アンカーに対象と異なる互換品詞を実際に使用した場合だけ許可し、不要・未実施の緩和記録を `V-DIS-02` とするよう修正した。
- `machine_check.py` のUTC生成をPython 3.10でもimport可能な `datetime.timezone.utc` へ変更し、要求版未満では前提検査が両CLIとも `E-ENV-01` を返せるよう修正した。
- 語彙ターゲットがlexiconに存在しなくても、空欄置換結果と `sentence_complete` の不一致、および正解・誤答アンカーIDと宣言 `target.ref` の不一致を独立して列挙するよう修正した。
- `answer` / `answer_equivalents` の重複比較を、MC-24-2どおり前後空白除去・大文字小文字無視だけに限定し、内部空白とNFC/NFDの差を同一視しないよう修正した。MC-26の書き換え比較は従来のNFC・trim・小文字化・連続空白正規化を維持した。
- `lookup.py lex --pos` の `E-INPUT-04` で、受取値とWordlist品詞15値を決定的順序でmessage・detailへ列挙するよう修正した。
- candidate JSONの非標準定数、有限floatへ変換不能な数値、巨大整数を文字列外で走査し、構文エラーと同様に対象・行・列を持つ `E-INPUT-03` として停止するよう修正した。

### R1修正後の再検証（4/4 pass）

1. 機械検査マトリクス（CI-MCH-01〜15）
   - コマンド: `PYTHONPATH=scripts .venv/bin/python - <<'PY' ... machine_check関数と実CLIへ手元候補を投入し、全15条件・machine_reportスキーマ・generated_at除外後の正準バイト一致を検証 ... PY`。
   - 結果: 15/15 pass。CI-MCH-11は緩和なし同品詞・正当な緩和が違反なし、フラグなし品詞不一致・不要な緩和フラグが `V-DIS-02` となった。
2. 照会マトリクス（CI-LKP-01〜04）
   - コマンド: 同上のinline Pythonから `.venv/bin/python scripts/lookup.py` をsubprocess実行。
   - 結果: 4/4 pass。`abandon`、`Tokyo`、`watch`、`gp:13`、`gp:1-1` の件数・属性・継承を再確認した。
3. machine_reportスキーマ適合
   - コマンド: 上記CI-MCH各出力を `jsonschema` で `schemas/machine_report.schema.json` へ直接検証。
   - 結果: 全出力がスキーマ1.0.0に適合した。
4. 決定性
   - コマンド: 同一candidateを2回検査し、`generated_at` を除去して正準JSONのUTF-8バイト列を比較。
   - 結果: バイト一致した。

### R1追加回帰確認

- R1-01〜R1-04: 品詞緩和5条件、欠落ターゲットと独立違反の併存、同値表記の内部空白・前後空白・大小文字・NFC/NFD各条件をinline Pythonで検証し、全期待値に一致した。不要な緩和と正当な緩和は実CLIでも再確認し、出力はmachine_reportスキーマに適合した。
- R1-02: `uv run --no-project --python 3.10`（CPython 3.10.18）で `lookup.py` と `machine_check.py` を実行し、双方がstdout空・終了コード1・`E-ENV-01`、検出3.10.18・要求`>=3.11`・具体的remedyを返した。
- R1-05: `.venv/bin/python scripts/lookup.py lex --pos bogus` がstdout空・終了コード1・`E-INPUT-04`となり、message・detailに受取値、15許容値、具体的remedyを含むことを確認した。
- R1-06: JSON構文不正、`NaN`、`Infinity`、`1e400`、5,000桁整数をstdin・ファイルの両経路で実CLIへ投入し、全10条件がstdout空・終了コード1・`E-INPUT-03`、対象・2行8列・具体的remedyを返すことを確認した。
- `.venv/bin/python scripts/doctor.py` は12 pass / 0 fail・stderr空、`.venv/bin/python -m py_compile scripts/lookup.py scripts/machine_check.py`、`git diff --check` はpassした。`docs/`、`schemas/`、`DECISIONS.md`、`IMPLEMENTATION_PLAN.md` にR1修正差分がないことを確認した。

### R2レビュー修正

- candidate JSONを数値変換なしで先に構文解析し、構文全体が成立した場合だけ標準外定数・有限表現不能数・巨大整数を位置付きで検査するよう修正した。これにより先行する構文不正を後方の不正数値より優先して報告する。
- 語彙ターゲットがlexiconに存在しない場合も、スキーマ適合済み `target.ref` から宣言品詞を復元し、誤答の同品詞・互換品詞群検査と緩和記録検査を継続するよう修正した。
- MC-21の選択肢比較を、日本語はtrim＋NFC、英語はtrim＋小文字化へ分離した。MC-23-1の英語choice/headword照合は双方の小文字化だけに限定し、NFC/NFDを同一視しないよう修正した。

### R2修正後の再検証（4/4 pass）

- CI-MCH-01〜15を手元候補で再実行し15/15 pass、各machine_reportがスキーマ1.0.0に適合し、`generated_at` 除外後の正準JSONがバイト一致した。
- CI-LKP-01〜04を実CLIで再実行し4/4 pass。`abandon`、`Tokyo`、`watch`、`gp:13`、`gp:1-1` の件数・属性・継承を再確認した。
- R2-01: 先行構文不正＋後方 `NaN`、先行構文不正＋後方 `1e400`、単独 `NaN`、単独 `1e400` をstdin・ファイルの実CLIへ投入した。全8条件がstdout空・終了コード1・`E-INPUT-03`となり、最初の構文／数値位置である1行7列を報告した。
- R2-02: target不存在＋緩和falseのA1 verb誤答3件が宣言nounとの不一致として `V-DIS-02` 3件、target不存在＋宣言nounと一致するA1 noun誤答3件が `V-DIS-02` なしとなることを実CLIで確認した。緩和trueの互換群外も3件全てを列挙した。
- R2-03: 英語選択肢のNFC/NFDは区別し、前後空白・大小文字だけの差は重複とすること、日本語選択肢のNFC/NFDと前後空白差は重複とすることを確認した。`vocab_mcq_ja2en` のNFD choiceはNFC headwordと不一致の `V-DIS-01`、大小文字差だけは一致、前後空白差は不一致となった。
- `.venv/bin/python scripts/doctor.py` は12 pass / 0 fail・stderr空、py_compile・`git diff --check` はpassした。CPython 3.10.18で `machine_check.py` が引き続きstdout空・終了コード1・`E-ENV-01`を返した。`docs/`、`schemas/`、`DECISIONS.md`、`IMPLEMENTATION_PLAN.md` にR2修正差分はない。

### R3レビュー修正

- R3-01: candidateのstdinとファイルをともにバイト列で読み、UTF-8を明示デコードするよう修正した。不正UTF-8は対象・行・列付き`E-INPUT-03`とし、`PYTHONIOENCODING`非依存にした。
- R3-02: PLN-05で提案したM2D-09の承認を受け、`--expected-format`・`--expected-level`・`--requested-count`を必須化した。候補の形式・レベル不一致と問題番号上限超過を`V-COND-01`で列挙し、欠問の完全性はSET-07の責務とした。`machine_report.schema.json`はenumの後方互換な追加により1.1.0へマイナー版上げした。
- R3-03: candidate/machine_reportは`format`/`scope`で該当スキーマ分岐を直接検証し、その他の複合スキーマはcontextのleaf errorを全件展開するよう修正した。required・type・additionalProperties・pattern・enum・const等を決定的な日本語理由へ変換する。
- R3-04: Python 3.7で構文解析できない代入式を通常のループへ置換し、Python 3.8以下にない`str.removeprefix()`をスライスへ置換した。`importlib.metadata`もPython要件検査後の動的importとし、要件未満版が定義済みエラーへ到達できる起動境界にした。
- 承認決定M2D-09を`DECISIONS.md`に記録し、GEN-02・CLI-16・MC-01/06/28/30・MAT-01/04・CI-MCH-16・M2 DoDとJSON例を同期した。

### R3修正後の再検証

1. M2 DoD（4/4 pass）
   - コマンド: `PYTHONPATH=scripts .venv/bin/python - <<'PY' ... 実データ・spaCyでmachine_checkを実行し、CI-MCH-01〜16と9形式・スキーマ・決定性を検証 ... PY`、および`.venv/bin/python - <<'PY' ... lookup.pyをsubprocess実行 ... PY`。
   - 結果: CI-MCH-01〜16は16/16 pass、CI-LKP-01〜04は4/4 pass。全9形式のquestion reportが`machine_report.schema.json` 1.1.0に適合し、`generated_at`除去後の正準JSONバイト列が一致した。CI-MCH-16は同条件で`V-COND-01`なし、format・level・question_id上限の各3不一致で該当locationの`V-COND-01`を確認した。
2. R3-01 UTF-8入力
   - コマンド: `.venv/bin/python - <<'PY' ... PYTHONIOENCODING=utf-8|ascii|cp932|utf-16でmachine_check.pyに同一UTF-8 candidateをsubprocess入力 ... PY`。
   - 結果: 4環境で終了コード0・stderr空、`generated_at`除去後のレポートが一致した。不正UTF-8をstdin・一時ファイルに入れた2経路はともに終了コード1・`E-INPUT-03`・2行1列となった。
3. R3-03 スキーマ理由
   - コマンド: `.venv/bin/python - <<'PY' ... grammar_cloze candidateのanswer欠落・型不正・余分フィールドを実CLIへ入力 ... PY`。
   - 結果: 順に`/body`・`/body/answer`・`/body`の各1件を`E-CONTRACT-01`で返し、理由は「必須プロパティがありません」・「型が不正です」・「未定義のプロパティです」の日本語となった。
4. R3-04 要件未満Python
   - コマンド: `uv run --no-project --python 3.8|3.9|3.10 scripts/machine_check.py ...`と同`lookup.py`、および`docker run --rm --platform linux/amd64 ... python:3.7-slim python scripts/machine_check.py ...`と同`lookup.py`。各版で有効引数・未知引数・必須引数欠落を実行した。
   - 結果: Python 3.7.17・3.8.20・3.9.23・3.10.18の全版で、両CLIの有効引数は終了コード1・`E-ENV-01`、未知/欠落引数は終了コード1・`E-INPUT-01`。全件stdout空・tracebackなし。Python 3.7 grammar指定の`ast.parse`もpassした。
5. 契約・環境健全性
   - `--expected-format`・`--expected-level`・`--requested-count`の値域外4条件が`E-INPUT-04`、新必須引数欠落が`E-INPUT-01`となった。`.venv/bin/python scripts/doctor.py`は12 pass / 0 fail、9スキーマのDraft 2020-12自己妥当性、py_compile、`git diff --check`はpassした。

### M2 DoD実行記録（4/4 pass）

1. 機械検査マトリクス（CI-MCH-01〜15）
   - コマンド: `.venv/bin/python - <<'PY' ... 正規化データから実在アンカーを組み立て、machine_checkの手元候補を検査 ... PY`。CLI入出力経路は `.venv/bin/python scripts/machine_check.py --candidate - --set-id 20260816-142530-k7x2 --generation gen1` のsubprocess実行でも確認した。
   - 結果: 15/15 pass。11語で`V-LEN-01`・10語境界で違反なし、`Helsinki`で`V-LEX-01`・`Tokyo`でallowlist、`can't`の`ca`/`n't`レンマ照合と数字・句読点免除、A1文中`abandon`でactual B1の`V-LEX-02`、対象0回/2回と活用形1回、`CD player`の最長一致、POS対応表全行・15品詞被覆、`V-DIS-01/02`、文脈対、`V-ORD-02`を合否条件どおり確認した。
2. 照会マトリクス（CI-LKP-01〜04）
   - コマンド: `.venv/bin/python - <<'PY' ... scripts/lookup.pyをsubprocessでlex/gp照会 ... PY`。
   - 結果: 4/4 pass。`abandon`はB1 verbを返しA1指定は0件、`Tokyo`はWordlist 0件、`watch`はA1 noun/verbの両方、`gp:13`と`gp:1-1`は表示名・パターン略記・レベルを返し、枝番は`gp:1`からの継承を保持した。
3. machine_reportスキーマ適合
   - コマンド: `.venv/bin/python - <<'PY' ... machine_check出力をjsonschema.Draft202012Validatorでschemas/machine_report.schema.jsonへ直接検証 ... PY`。
   - 結果: question scopeの全必須フィールド、token統計、違反・警告列挙を含む出力がスキーマ1.0.0に適合した。`generated_at`はUTC・秒精度・末尾`Z`だった。
4. 決定性
   - コマンド: `.venv/bin/python - <<'PY' ... 同一candidateを2回検査しgenerated_atだけを除去後、sort_keys・indent 2・UTF-8の正準バイト列を比較 ... PY`。
   - 結果: 2回の出力がバイト一致した。

### 追加確認

- 語彙4形式・文法5形式の全9形式で検査対象テキストを抽出し、`machine_report.schema.json` 適合出力を生成できることを確認した。
- `lookup.py` の併記グループ展開、複数条件AND、誤答プールの対象除外・カテゴリ優先順、文法keyword NFC/casefold、先行文脈要求除外、limit適用前totalを確認した。
- 一時リポジトリで原本1バイト改変を両CLIが`E-DATA-02`、config欠落を`E-DATA-05`、正規化データ欠落を`E-DATA-03`で拒否し、stdoutへ結果を出さず終了コード1となることを確認した。
- 両CLIの `--help` は日本語で終了コード0。未知・欠落引数は`E-INPUT-01`、limit・generation・ID値域外は`E-INPUT-04`、set_id不正は`E-INPUT-05`、candidate不存在は`E-INPUT-02`、JSON構文不正は位置情報付き`E-INPUT-03`、candidateスキーマ不通過は`E-CONTRACT-01`で終了コード1となった。
- `.venv/bin/python -m py_compile scripts/lookup.py scripts/machine_check.py`、`.venv/bin/python scripts/doctor.py`（12/12 pass）、`git diff --check` が合格した。

## 2026-08-16 — M1 正規化＋doctor

### 実装

- `scripts/setup.py` と `requirements.txt` を追加し、`.venv`、spaCy 3.8.15、openpyxl 3.1.5、jsonschema 4.26.0、Jinja2 3.1.6、en_core_web_sm 3.8.0を構築可能にした。
- `scripts/build_normalized.py` を追加し、固定名の原本xlsx 2件から正準形の `lexicon.json`、`grammar.json`、`meta.json` を決定的・オフラインで生成できるようにした。`--diff`、`--dry-run`、`--accept-source-change`、原子的書込み、チェックサム拒否を含む。
- `scripts/doctor.py` を追加し、環境・データ・設定・スキーマ・レビュアー配線の12項目を一括診断できるようにした。
- `data/source/sources.json`、`data/config/limits.json`、`data/config/proper_nouns.json` と、ビルド済み `data/normalized/` 3ファイルを追加した。
- PLN-05で承認されたM1D-01〜M1D-17を `DECISIONS.md` へ記録し、影響する設計文書を承認内容どおりに改訂した。スキーマ9本は変更していない。

### R1〜R15レビュー修正

- doctorが正規化データ由来の`CliFailure`を定義済みE-DATAコードのまま報告し、スキーマ違反JSONでも12項目を中断せず完走するよう修正した。
- 原本版を`sources.json.version_label`から構築し、チェックサム変更時の版更新忘れを、期待SHA-256・実測SHA-256・旧版・新版を含む`E-DATA-02`で拒否するよう修正した。
- 原本列検出の決定性と全件報告、ALL併記headwordの原文字列保存、出力先エラーの`E-ENV-05`変換を実装した。
- M1D-12に従い正規化パイプラインを`1.0.1`へ更新し、`data_version`を`wl1.6+gp20200220+norm1.0.1`とした。
- M1D-13に従いdoctor D09で現在の`sources.json.version_label` 2値・実行中パイプライン版と正規化3ファイルを照合し、陳腐化を期待値・実測値付きの`E-DATA-04`で拒否するよう修正した。
- M1D-14に従い、原本同一性の安全根拠を取得できる部分破損metaは通常ビルドで再生成し、取得不能時はgit復元手順付き`E-DATA-04`で停止する安全な復旧経路を追加した。
- doctor D09の`E-DATA-04`メッセージへ、スキーマ違反箇所・理由・総数、内部矛盾、現在値の期待値・実測値を決定的順序で集約するよう修正した。
- metaが欠落してlexiconまたはgrammarが残る既存正規化セットを初回ビルド扱いにせず、git復元remedy付き`E-DATA-04`で停止するよう修正した。
- Git `HEAD`に存在する正規化3ファイルが全て欠落した状態も初回ビルド扱いにせず、git復元remedy付き`E-DATA-04`で停止するよう修正した。
- Grammar Profile枝番の親欠落を数値順に全件収集し、決定的な1件の`E-DATA-06`で報告するよう修正した。
- M1D-16に従い、正規化3ファイル全欠落時にGit・リポジトリ・HEADを照会できなければ`E-ENV-04`で安全側に停止し、有効なHEADで対象meta不在を確認できた場合だけ初回ビルドを許可するよう修正した。
- doctor D12のClaude Code配線検出を`.claude/agents/cefrj-reviewer.md`の固定パスへ限定した。
- Wordlistの値を列名で参照するよう修正し、M1D-12に従って正規化パイプラインを`1.0.2`、`data_version`を`wl1.6+gp20200220+norm1.0.2`へ更新した。
- WordlistとGrammar Profileの複数の不正セルを、シート・行・列の決定的順序で単一の`E-DATA-06`へ全件列挙するよう修正した。
- buildとdoctorの正常・定義済みエラーJSONを、BOMなしUTF-8・LFのバイト列として直接出力するよう修正した。
- case-insensitiveファイルシステムではGit HEADの全追跡パスを大小文字非依存で照合し、出力先casingの変更による追跡済み正規化セットの全削除判定迂回を防止した。
- ITEM LIST・教員版・EFLのID重複と、教員版／EFLからITEM LISTへ結合できないIDを先行走査し、決定的な単一の`E-DATA-06`へ全件列挙するよう修正した。
- Git照会失敗の`E-ENV-04` messageへ実行コマンドを含め、起動失敗時はOSエラー、非0終了時は終了コードとstderr要約を明記するよう修正した。
- Git追跡判定をsymlink非解決の字句パス優先に改め、実体パスも追加照合して出力ディレクトリ別名を検出し、metaパス上のsymlink・非通常ファイルを`E-DATA-04`で拒否するよう修正した。
- JSON読取りを標準JSONへ限定し、非標準数値定数と巨大整数の`ValueError`を対象の定義済み`E-DATA-*`コードへ変換するよう修正した。
- Grammar Profile数値セルの有限性検査と、3成果物を最初の置換前に全て正準直列化する書込み境界を追加した。
- レベルの同値範囲をLVL-05違反として拒否し、ALL併記グループの全variant不整合をgroup_ids反映前に決定的順序で一括報告するよう修正した。
- M1D-17に従い3最終パスを事前検査し、全一時ファイルをflush・fsyncしてから協調置換し、確定途中の失敗時は更新前の正規化セットへ復元するよう修正した。
- doctor D11でschemaのトップレベルobjectを検査し、非objectと型例外を`E-ENV-04`へ変換して12項目を完走するよう修正した。
- 共通JSONローダーで指数オーバーフロー由来の非有限floatを拒否し、対象ごとの定義済み`E-DATA-*`へ変換するよう修正した。
- 3ファイルの`data_version`相互不一致を現在値不一致より前に収集し、meta問題・内部矛盾・現在値不一致を同じ`E-DATA-04`へ集約するよう修正した。
- metaのspaCyモデル名・版を固定要求値へ照合し、不一致をフィールド名・期待値・実測値付きの`E-DATA-04`としてdoctorで報告するよう修正した。
- 文書全体のschema合否から独立して型安全な`data_version`を比較し、複合破損でもschema違反・meta問題・内部矛盾・現在値不一致を同じ`E-DATA-04`へ集約するよう修正した。
- EFLコーパス総語数の原本セル検査へ最小値0を追加し、複数の負数セルを固定列順で単一の`E-DATA-06`へ全件列挙するよう修正した。
- 出力先metaの字句パスとsymlink解決後パスごとに最寄りのGitリポジトリを探索し、別・ネストリポジトリの追跡済み全削除も各HEADから検出するよう修正した。
- metaの各候補パスをfail-closedで検査し、1候補でもGitリポジトリを特定できなければ照会コマンド・終了コード付き`E-ENV-04`で停止するよう修正した。
- 全候補GitリポジトリのHEADを先行して全件検証し、全HEADが有効な場合だけmetaの追跡有無を照合する2段階処理へ修正した。

### 原本と正規化成果物

- 原本 `CEFR-J Wordlist Ver1.6.xlsx`: SHA-256 `e41033a12f92983012a0a6b201d4f1f860b7ba3de700c2c3b89660ea21a390e1`
- 原本 `CEFR-J Grammar Profile full 20200220.xlsx`: SHA-256 `f292ef17a60396797c0da2efea95f2ca3de940571164c93e5488c70029eab1c2`
- `lexicon.json`: SHA-256 `11ac8d1d6b42e5fbd37baa1005b55d7904f42f2753e0720018bbc9edb977c3c7`
- `grammar.json`: SHA-256 `6a435941ff1105a78b76fae0c141288a783d31148449302621d3b42a8ebbff62`
- `meta.json`: SHA-256 `fd8c51b2f664f5eaef04c73936927fcd9cb1eb1c2bae56b65df9ad53ec0f0fd4`

### M1 DoD実行記録（6/6 pass）

1. 決定性
   - コマンド: `.venv/bin/python - <<'PY' ... tempfile内の独立した2出力先へbuild_normalized.pyを各1回実行し、3ファイルのバイト列とリポジトリ内成果物をSHA-256比較 ... PY`。
   - 結果: 2回の3ファイルがそれぞれバイト一致。SHA-256は上記の値で固定。両ビルドのstderrは空、終了コード0。
2. スキーマ・meta適合
   - コマンド: `.venv/bin/python - <<'PY' ... Draft202012Validator ... validate_meta_document ... PY`（jsonschema直接呼出し）。
   - 結果: `lexicon.json` は `normalized_lexicon.schema.json`、`grammar.json` は `normalized_grammar.schema.json` に適合。`meta.json` はNRM-29に適合し、`data_version=wl1.6+gp20200220+norm1.0.2`・`pipeline_version=1.0.2`。終了コード0。
3. 件数不変条件（CI-NRM-03）
   - コマンド: `.venv/bin/python - <<'PY' ... json/openpyxlによる件数・ID集合検証 ... PY`。
   - 結果: entries=7,988、A1=1,200 / A2=1,443 / B1=2,486 / B2=2,859、`(headword,pos)`ユニーク=7,988、ALL行=7,801、groups=179（全member 2件以上）、教員版ターゲット=256、ITEM LIST=501、全枝番の親が存在、未付与親16件のID集合が仕様値と一致。終了コード0。
4. レベル継承・範囲分解（CI-NRM-05 / CI-NRM-07）
   - コマンド: `.venv/bin/python - <<'PY' ... grammar.jsonのlevelブロック検証 ... PY`。
   - 結果: `gp:1-1` / `gp:1-2` / `gp:1-3` が `gp:1` の下限・上限を継承し、`source=kyoinban_inherited`、`inherited_from=gp:1`。教員版は単一値152件、範囲値104件で、単一値は下限=上限。終了コード0。
5. doctor完全環境・異常模擬（CI-NRM-06 / CI-CLI-03）
   - コマンド: `.venv/bin/python - <<'PY' ... 完全環境とtempfile上の正規化欠落・原本改変・config欠落・JSON構文破損・JSON型破損をdoctor.pyのsubprocessで実行し、原本改変はbuild_normalized.pyも実行 ... PY`。
   - 結果: 完全環境は12 pass / 0 fail・終了コード0。正規化欠落はD07〜D09が`E-DATA-03`、原本改変はdoctor/buildが`E-DATA-02`、`limits.json`欠落はD10が`E-DATA-05`で、いずれも終了コード1。構文破損した`lexicon.json`と有効JSONだがトップレベル配列の`lexicon.json`は、どちらも12項目を完走してD09=`E-DATA-04`・終了コード1（内部エラーの2ではない）・stderr空。全fail項目に具体的remedyがある。
6. 差分ゼロ
   - コマンド: `.venv/bin/python scripts/build_normalized.py --diff`（実行前後の3ファイルSHA-256もinline Pythonで比較）。
   - 結果: lexicon / grammarのadded / removed / level_changedが全て `count=0, ids=[]`。`written=[]`、実行前後の3ファイルはバイト一致、終了コード0。

### M2着手前のM1 DoD再検証（2026-08-16、6/6 pass）

1. 決定性
   - コマンド: `.venv/bin/python - <<'PY' ... リポジトリ内の一時出力先2件へbuild_normalized.pyを各1回実行し、3成果物をバイト比較 ... PY`。
   - 結果: 両実行とも終了コード0・stderr空。2組およびコミット済み3成果物がそれぞれバイト一致した。
2. スキーマ・meta適合
   - コマンド: `.venv/bin/python - <<'PY' ... Draft202012Validatorでlexicon/grammarを検証し、validate_meta_documentでmetaを検証 ... PY`。
   - 結果: 3成果物が適合。`data_version=wl1.6+gp20200220+norm1.0.2`、`pipeline_version=1.0.2`。
3. 件数不変条件（CI-NRM-03）
   - コマンド: `.venv/bin/python - <<'PY' ... json/openpyxlで正規化データと原本ALLシートを検証 ... PY`。
   - 結果: entries=7,988、A1=1,200 / A2=1,443 / B1=2,486 / B2=2,859、`(headword,pos)`ユニーク=7,988、ALL行=7,801、groups=179、教員版ターゲット=256、ITEM LIST=501、全枝番の親存在、未付与親16件ID一致。
4. レベル継承・範囲分解（CI-NRM-05 / CI-NRM-07）
   - コマンド: `.venv/bin/python - <<'PY' ... grammar.jsonの継承元・source・min/maxと教員版level_rawを検証 ... PY`。
   - 結果: `gp:1-1` / `gp:1-2` / `gp:1-3` は `gp:1` を継承し、単一値152件・範囲値104件、単一値の下限=上限を確認した。
5. doctor完全環境・異常模擬（CI-NRM-06 / CI-CLI-03）
   - コマンド: `.venv/bin/python - <<'PY' ... tempfileへ必要ファイルを複製し、完全環境・正規化欠落・原本1バイト改変・config欠落でdoctor.pyを実行。原本改変環境ではbuild_normalized.pyも実行 ... PY`。
   - 結果: 完全環境は12 pass・終了コード0。正規化欠落はD08/D09=`E-DATA-03`、原本改変はdoctor D07およびbuild=`E-DATA-02`、config欠落はD10=`E-DATA-05`で、各終了コード1・定義済みremedyあり・doctorのstderr空。
6. 差分ゼロ
   - コマンド: `.venv/bin/python scripts/build_normalized.py --diff` と、続くinline Pythonによる3成果物SHA-256比較。
   - 結果: lexicon / grammarのadded / removed / level_changedは全て0件、`written=[]`、終了コード0。実行後SHA-256はlexicon=`11ac8d1d...c3c7`、grammar=`6a435941...f62`、meta=`fd8c51b2...0fd4`で開始前と一致した。

### 追加確認

- R10〜R15の各修正後にM1 DoD 6項目を全て再実行し、独立2ビルドのバイト一致、schema・NRM-29適合、件数不変条件、レベル継承・範囲分解、doctor正常／異常系、差分ゼロが6/6 passすることを確認。
- `python3 scripts/setup.py`: 固定版依存とen_core_web_sm 3.8.0の導入に成功、終了コード0。
- `python3 -m py_compile scripts/setup.py scripts/build_normalized.py scripts/doctor.py`: pass。
- `git diff --check`: pass。
- `build_normalized.py --help` / `doctor.py --help`: 日本語ヘルプを表示、終了コード0。
- 両CLIの未知引数: `E-INPUT-01`、日本語message/remedy、終了コード1。
- R2-02回帰確認: 版を据え置いてWordlist原本のチェックサムだけを変えた一時環境で`build_normalized.py --accept-source-change`を実行し、終了コード1・`E-DATA-02`、message/detailにファイル名・期待SHA-256・実測SHA-256・旧版・新版が全て含まれることを確認。
- R3-01回帰確認: (a)正規化3ファイルとmetaのpipeline版を`norm1.0.0`へ戻す、(b)`sources.json`のWordlist版だけを`1.6.1`へ進める、の2一時環境でdoctorを実行し、いずれも12項目完走・D09=`E-DATA-04`・終了コード1・stderr空、不一致4フィールドの期待値・実測値列挙を確認。トップレベル配列`[]`の破損JSONもD09=`E-DATA-04`・終了コード1のままであることを再確認。
- R4-01回帰確認: (a)安全根拠を保持したpipeline版不整合metaは通常ビルドで3ファイルを再生成後doctor 12/12、(b)SHA-256を取得不能なmetaはファイルを変更せずgit復元remedy付き`E-DATA-04`、(c)安全根拠がある部分破損metaでも原本変更時は`E-DATA-02`、(d)旧版取得不能の`--accept-source-change`と(e)不適合metaに対する`--diff`はgit復元remedy付き`E-DATA-04`となることを確認。
- R4-02回帰確認: `lexicon.json=[]`でD09 messageに対象・ルートJSONポインタ・理由・総数、51件以上のスキーマ違反で先頭50件・総数、metaのpipeline版のみ不整合でmeta内部矛盾と`meta.pipeline_version`の期待値・実測値、counts不整合で期待件数・実測件数が含まれることを確認。全messageは1行で、doctorは12項目を完走した。
- R5-01回帰確認: (a)完全に空の新規出力先は初回ビルドに成功して正規化正本とバイト一致、(b)lexicon・grammar残存＋meta欠落はファイル無変更・git復元remedy付き`E-DATA-04`、(c)同じ部分欠落と原本チェックサム変更の併存も再生成前に`E-DATA-04`、(d)lexiconだけの残存でも同様に停止することを確認。
- R6-01回帰確認: 一時Gitリポジトリで正規化3ファイルをコミット後に全削除し、原本も変更した状態では再生成前にgit復元remedy付き`E-DATA-04`・終了コード1となり、3ファイルを作成しないことを確認。同じリポジトリ内でもGit `HEAD`に履歴のない空の独自出力先は初回ビルドに成功した。
- R6-02回帰確認: 親が存在しない枝番を2件にした一時原本で`PYTHONHASHSEED=1..30`を変えて実行し、2組を数値順で全件含む同一の`E-DATA-06`・終了コード1となること、および全error JSONのSHA-256が`c5b8da81ebb0889ab3028610e385725f0fb7072d407b8b944a45255c51fa60f3`で一致することを確認。
- R6-03確認: PLN-05承認決定範囲の記録を、`DECISIONS.md`に存在するM1D-01〜M1D-15と一致させた。
- R7-01回帰確認: 正規化3ファイル全欠落時に、(a)有効なHEADの追跡済みmetaは`E-DATA-04`、(b)Git起動不能と(c)HEAD破損は`E-ENV-04`、(d)有効なHEADに履歴のない空出力先は初回ビルド許可となることを確認。
- R7-02回帰確認: PATH上のCodexなしで、無関係な`.claude/agents/*.md`だけならD12=`E-ENV-06`、固定パス`.claude/agents/cefrj-reviewer.md`またはCodexコマンドがあればD12=passとなることを確認。
- R7-03回帰確認: Wordlist全シートの`CoreInventory 1`列と`Threshold`列を列単位で交換しても、列名どおりに読み取ったlexiconと統計が交換前と一致することを確認。現行原本から`norm1.0.2`への差分はlexicon・grammarともadded / removed / level_changedが全て0件だった。
- R7-04回帰確認: Wordlistの不正セル3件とGrammar Profileの不正セル5件を、それぞれ単一の`E-DATA-06`のmessage/detailへシート・行・列の固定順で全件列挙することを確認。
- R7-05回帰確認: UTF-16・CRLF設定の`TextIOWrapper`と`PYTHONIOENCODING=cp932`の環境でも、build・doctorの正常JSONと定義済みエラーJSONがBOMなしUTF-8・LF・末尾改行1個となることを確認。
- R8-01回帰確認: case-insensitiveな一時Gitリポジトリで、既定casingと`DATA/NORMALIZED`の両方が追跡済み3ファイル全削除として`E-DATA-04`になり、HEADに大小文字非依存でも一致する履歴がない空出力先だけが初回ビルド扱いになることを確認。
- R8-02回帰確認: 教員版とEFLへ重複かつITEM LISTに存在しないIDを各2行投入し、重複2組と未結合4行の全6件がシート・行・IDの固定順で単一の`E-DATA-06` message/detailへ現れることを確認。
- R8-03回帰確認: HEAD欠落時の`E-ENV-04` messageにJSON配列表現の`git rev-parse --verify HEAD^{commit}`・終了コード128・stderr要約が、Git起動不能時には実行コマンドとOSエラーが含まれることを確認。
- R9-01回帰確認: 追跡済み正規化セットの通常削除・casing違い・meta自身のbroken symlink・追跡先への出力ディレクトリsymlinkは全て`E-DATA-04`となり、履歴にない通常の空出力先だけが初回ビルド扱いになることを確認。
- R9-02回帰確認: normalizedの`NaN`と5,000桁整数、meta・sources・configの`NaN`を個別に投入し、doctorが全12項目を完走してそれぞれ`E-DATA-04`・`E-DATA-01`・`E-DATA-05`の診断fail、終了コード1となることを確認。
- R9-03回帰確認: EFLのcorpus母数・相対頻度・rangeへ正負の非有限値4件を投入し、固定順の単一`E-DATA-06`・終了コード1となり、出力先へ正規化3ファイルを1件も書かないことを確認。
- R9-04回帰確認: 単一値と正しい昇順範囲は受理し、同値範囲と逆順範囲は「レベル範囲が昇順ではない」`E-DATA-06`として拒否することを確認。
- R9-05回帰確認: ALLの2行へ未解決・重複・空variant計6件を投入し、行・variant出現順の単一`E-DATA-06`へ全件列挙され、`PYTHONHASHSEED=1..10`でerror JSONがバイト一致することを確認。
- R10-01回帰確認: lexicon・grammar・metaの各最終パスをディレクトリにした通常ビルドが書込み前に`E-ENV-05`・終了コード1となり、2件目・3件目の`os.replace`注入失敗では旧3ファイルへバイト一致で復元し一時・退避ファイルを残さないことを確認。
- R10-02回帰確認: schemaをトップレベル配列・null・文字列・数値へ個別に変更してもdoctorが12項目を完走し、D11=`E-ENV-04`・終了コード1・stderr空となることを確認。
- R10-03回帰確認: `1e400`と`-1e400`をnormalized・meta・sources・configへ個別に投入し、doctorが12項目を完走してそれぞれ`E-DATA-04`・`E-DATA-01`・`E-DATA-05`の診断fail・終了コード1となることを確認。
- R10-04回帰確認: lexiconだけ旧版・lexiconとgrammarだけ旧版・meta内部不整合併存の3条件で、3ファイルの`data_version`相互不一致と現在値不一致、該当時のmeta問題が同じ`E-DATA-04`へ集約されることを確認。
- R11-01回帰確認: metaの`spacy_model.version`だけを`0.0.0`へ変更し、doctorが12項目を完走してD03=pass、D07・D09=`E-DATA-04`・終了コード1・stderr空となり、両messageにフィールド名・期待3.8.0・実測0.0.0が含まれることを確認。
- R11-02回帰確認: lexiconまたはgrammarの非`data_version`スキーマ違反と旧版、およびmeta内部不整合との併存条件で、schema違反・3ファイル相互不一致・現在値不一致・該当時のmeta問題が同じD09=`E-DATA-04`へ集約されることを確認。
- R12-01回帰確認: EFLコーパス総語数のG1・H1を`-1`・`-2`にした原本で、両セルが固定列順の単一`E-DATA-06` message/detailへ全件列挙され、終了コード1・成果物未書込みとなることを確認。
- R13-01回帰確認: 同一リポジトリと別の有効なGitリポジトリでは履歴のない空出力先を初回ビルドとして許可し、別リポジトリで追跡済み正規化3ファイルを全削除した出力先は`E-DATA-04`・終了コード1となり再生成しないことを確認。
- R14-01回帰確認: Git管理外出力先と字句・解決後パスの一方だけが管理外となるsymlink出力先は照会コマンド・終了コード付き`E-ENV-04`で停止し、異なる有効Gitリポジトリに属するsymlink両候補は各HEAD確認後に初回ビルドを許可することを確認。
- R15-01回帰確認: 字句側が追跡済み・解決後側がHEAD欠落のsymlinkと、その逆順の両条件で、meta追跡結果よりHEAD欠落が優先され、コマンド・終了コード・stderr付き`E-ENV-04`・成果物未書込みとなることを確認。
