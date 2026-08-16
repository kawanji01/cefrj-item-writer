# CHANGELOG

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
