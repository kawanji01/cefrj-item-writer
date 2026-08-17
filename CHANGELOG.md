# CHANGELOG

## 2026-08-17 — M5 レビューループ

### 実装

- `agent/reviewer-core.md` を追加し、1問1独立レビュー、候補・機械レポート・検証仕様・正規化データだけを読む境界、CHK-01〜19、`level_source`、機械検査誤検出疑いの構造化報告、review_result自己検証を定義した。
- `agent/author-core.md` をM5へ拡張し、review_request組み立て、毎世代の独立レビュー、直前世代の構造化指摘だけを渡す再生成、提案モード補充、明示モード教師照会、レビュー系インフラ障害、増分・最終set_check、finalizeまでを配線した。M6未実装のHTML生成とS90完了報告は行わない境界を維持した。
- `scripts/set_support.py` と `scripts/set_check.py` を追加し、監査命名・対応関係、machine/review両方の合格世代、対象重複 `V-SET-01`、例文使い回し `V-SET-02`、誤答再利用 `V-SET-03` を決定的に検査するようにした。
- `scripts/finalize_set.py` を追加し、FIN-01入力、合格集合、保存済み最終レポートと内部再検査、出典、原本チェックサム、設定スナップショット、provenance、整序問題の`answer_tokens`を検証し、排他的な予測不能一時ファイルから上書き不能なハードリンク公開で正本を原子的に確定するようにした。
- 承認済みM5D-01〜03に基づき、監査上書き衝突を`E-DATA-07`、セッション設定ドリフトを`E-DATA-08`とし、`generation_max`は現行世代列挙で表現できる1〜3だけを運用上許可した。3超はdoctor D10と正規化データ利用CLIの共通事前検査で`E-DATA-05`となる。
- 設計文書と`DECISIONS.md`は承認内容だけを反映し、`schemas/`は変更していない。

### M5着手前のM1 DoD再検証（2026-08-17、6/6 pass）

1. 決定性
   - コマンド: `PYTHONPATH=scripts .venv/bin/python - <<'PY' ... 独立一時出力先2件へbuild_normalized.pyを実行し、2組とコミット済み3成果物をバイト比較 ... PY`。
   - 結果: 2回とも終了コード0で、`lexicon.json`・`grammar.json`・`meta.json`は相互およびコミット済み成果物とバイト一致した。SHA-256は順に`11ac8d1d6b42e5fbd37baa1005b55d7904f42f2753e0720018bbc9edb977c3c7`、`6a435941ff1105a78b76fae0c141288a783d31148449302621d3b42a8ebbff62`、`fd8c51b2f664f5eaef04c73936927fcd9cb1eb1c2bae56b65df9ad53ec0f0fd4`。
2. スキーマ・meta適合
   - コマンド: `PYTHONPATH=scripts .venv/bin/python - <<'PY' ... lexicon/grammarスキーマとNRM-29 metaを検証 ... PY`。
   - 結果: 3成果物が適合し、`data_version=wl1.6+gp20200220+norm1.0.2`、正規化パイプライン版`1.0.2`だった。
3. 件数不変条件
   - コマンド: `.venv/bin/python - <<'PY' ... json/openpyxlで正規化データと原本ALL・教員版・ITEM LISTを照合 ... PY`。
   - 結果: 語彙7,988件（A1=1,200 / A2=1,443 / B1=2,486 / B2=2,859）、`(headword,pos)`一意7,988件、ALL 7,801行、併記179群（全群2件以上）、文法501件（親263・枝番238）、教員版・target eligible 256件、未付与親16件が仕様値と一致した。
4. レベル継承・範囲分解
   - コマンド: `.venv/bin/python - <<'PY' ... grammar.jsonの継承、単一値、範囲値を全件検証 ... PY`。
   - 結果: `gp:1-1` / `gp:1-2` / `gp:1-3`を含む継承項目が親値を保持し、教員版の単一値152件・範囲値104件が全て正しく分解されていた。
5. doctor完全環境・異常模擬
   - コマンド: `.venv/bin/python - <<'PY' ... 一時コピーで完全環境、normalized欠落、原本1バイト改変、config欠落をdoctor.pyで検査し、原本改変環境でbuild_normalized.pyも実行 ... PY`。
   - 結果: 完全環境は12 pass / 0 fail。normalized欠落はD08/D09=`E-DATA-03`、原本改変はD07とbuild=`E-DATA-02`、config欠落はD10=`E-DATA-05`となり、全停止に具体的remedyがあった。
6. 差分ゼロ
   - コマンド: `.venv/bin/python scripts/build_normalized.py --diff` と実行前後の3成果物SHA-256比較。
   - 結果: lexicon / grammarの`added`・`removed`・`level_changed`は全区分`count=0, ids=[]`、`written=[]`、終了コード0で、3成果物は実行前後バイト一致した。

### M5 DoD検証（2026-08-17、5/5 pass）

- コマンド: `PYTHONPATH=scripts .venv/bin/python - <<'PY' ... 一時setディレクトリへRPL-01〜10とCI-SET-01〜06の監査フィクスチャを投入し、set_check.py・finalize_set.py・validate.pyをsubprocess実行 ... PY`。
- DoD 1: RPL-01〜10は10/10 pass。3問gen1完走、gen1 review fail→gen2合格と直前指摘6フィールド移送、提案補充2N上限、明示3世代後の教師照会、review invalid初回＋再実行2回で中止、candidate invalid同一世代2回後の世代消費、machine fail非上書き、例文使い回し後の確定拒否、監査参照と正本自立性、最悪コスト`2n×3`を確認した。
- DoD 2: review_requestがcandidate全体・machine_report全体・実効制約・RC-10の8リソースだけを含み、`reviewer-core.md`が生成側会話、他問、過去世代、許可外ファイル、書き込み、ネットワークを禁止することを確認した。Codexアダプタの許可された作業ファイルも監査正本と混同せず受理した。
- DoD 3: machine fail＋review passのgen1は合格世代に選ばれず、gen2のmachine/review/set_check全passだけが採用された。
- DoD 4: CI-SET-01〜06は6/6 pass。3違反を個別検出し、合格3問は原子的確定、不合格残存は`E-CONTRACT-04`かつ`set.json`なし、監査命名・相対参照・正本全必須ブロックも合格した。
- DoD 5: review_result不正は問題不合格にも世代消費にも数えず、同一封筒で最大2回再実行し、初回を含む3失敗を`review.invalid1`〜`3`へ保存後にセット中止、`set.json`なしとなった。

### 追加回帰確認

- `docs/question-generation-spec.md`の公式candidate 9形式を個別の監査セットへ投入し、全形式で増分set_check、最終set_check、finalize、setスキーマ検証が9/9 passした。`grammar_reorder`の`answer_tokens`はcandidate非改変のまま確定時だけ導出された。
- `generation_max=4`の隔離コピーではdoctor D10と`lookup.py`共通事前検査がともに`E-DATA-05`となり、`/generation_max`、受取値、許容1〜3を報告した。
- `set_check.py` / `finalize_set.py`の日本語help、必須引数欠落`E-INPUT-01`、不正set_id `E-INPUT-05`、finalizeの不正stdin優先`E-INPUT-03`を確認した。
- `.venv/bin/python -m py_compile scripts/doctor.py scripts/lookup.py scripts/set_support.py scripts/set_check.py scripts/finalize_set.py`、`git diff --check`、`doctor.py` 12 pass / 0 failを確認した。

### M5 R1〜R2対応（2026-08-17）

- R1-01/R1-02: FIN-01列挙値の不正型を`E-CONTRACT-01`へ統一し、setディレクトリを実リポジトリの`output/`直下へ限定してset/review/監査のシンボリックリンクを拒否した。
- 承認済みM5D-04: `slot.<slot_question_id>.outcome.json`の手動検証契約を追加し、要求Nスロット、全試行ID、世代の連続性、`generation_max`までの消費、T10採用、S6教師承認済み減数を`finalize_set.py`の確定境界で検証するようにした。監査形式・対応関係は`E-CONTRACT-03`、終端条件未達は`E-CONTRACT-04`とした。
- 承認済みM5D-05: 固定`set.json.tmp`＋`os.replace`を、排他的・シンボリックリンク非追跡の一時ファイルと上書き不能なハードリンク公開へ変更した。並行finalizeは1件だけが成功し、後続は`E-CONTRACT-05`となる。
- R2-01/R2-03/R2-04: reviewer-coreのCHK-07へ3誤答それぞれの同一パラダイム性検査を追加し、review_resultの必須トップレベルを9フィールドへ訂正、直接読取りをRC-10の8リソースへ限定した。
- R2-02: 検証済み`generation_max`を`set_check.py`と`finalize_set.py`から監査収集へ渡し、上限超過世代を`E-CONTRACT-03`で拒否した。
- `reviews/m5-r1-resolutions.md`と`reviews/m5-r2-resolutions.md`に全指摘の対応内容を記録した。`schemas/`は変更していない。

### M5 R2対応後のDoD再検証（2026-08-17、5/5 pass）

- DoD 1（RPL-01〜10）
  - コマンド: `PYTHONPATH=scripts .venv/bin/python - <<'PY' ... 3問gen1確定、review fail→gen2採用、candidate.invalid1/2→gen2採用、machine fail＋review pass非採用、V-SET-02、監査参照を合成監査と実CLIで検証 ... PY`、および `PYTHONPATH=scripts .venv/bin/python - <<'PY' ... author-coreの2N補充・教師照会・review再試行と不正review_resultを検証 ... PY`。
  - 結果: RPL-01〜10は10/10 pass。3問の`set.json`はsetスキーマ適合、gen2採用3経路は終端監査と一致、machine failは覆らず、例文重複は`V-SET-02`、provenance参照は9/9解決した。提案補充は2N、n=3の最悪境界は18試行、明示不成立は教師照会、レビュー不正は同一requestで2回再実行後中止となる固定契約を確認した。
- DoD 2（独立性）
  - コマンド: `PYTHONPATH=scripts .venv/bin/python - <<'PY' ... reviewer-coreとreview_requestの読取り境界を照合 ... PY`。
  - 結果: 入力封筒とRC-10の8リソースだけを読み、生成側会話・他問・過去世代・書込み・ネットワークを禁止する構成だった。
- DoD 3（機械fail優越）
  - コマンド: DoD 1のmachine fail＋review pass→gen2合格合成監査。
  - 結果: gen1は採用集合に入らず、machine/review/set_checkが全passのgen2だけがprovenanceへ採用された。
- DoD 4（CI-SET-01〜06）
  - コマンド: `PYTHONPATH=scripts .venv/bin/python - <<'PY' ... build_set_reportの3横断違反、3問finalize、監査目録、set必須ブロックを検証 ... PY`、および `PYTHONPATH=scripts .venv/bin/python - <<'PY' ... 固定一時名シンボリックリンク下で並行finalizeを2プロセス実行 ... PY`。
  - 結果: CI-SET-01〜06は6/6 pass。`V-SET-01/02/03`を個別検出し、正常確定・setスキーマ・監査名・参照・正本内容が適合した。並行処理は1件成功・1件`E-CONTRACT-05`で、リンク先と確定済み`set.json`は不変だった。
- DoD 5（レビュー出力不正）
  - コマンド: `validate.py --schema review_result`への必須フィールド欠落JSON投入と、author-coreのT6/T7監査・遷移照合。
  - 結果: 不正出力は`E-CONTRACT-01`となり、問題不合格・世代消費に数えず、`review.invalid1`〜`3`を保存して初回＋再実行2回の失敗後にセット中止し、`set.json`を書かない契約だった。
- 追加コマンド: `generation_max=1/2`の隔離コピーで上限内gen1/gen2と上限超過gen2/gen3を`set_check.py`・`finalize_set.py`へ投入、`.venv/bin/python -m py_compile scripts/doctor.py scripts/lookup.py scripts/set_support.py scripts/set_check.py scripts/finalize_set.py scripts/validate.py scripts/machine_check.py`、`.venv/bin/python scripts/doctor.py`、`git diff --check`。
- 追加結果: 上限内世代は受理、上限超過は`E-CONTRACT-03`かつ`set.json`なし。構文検査と差分検査はpass、doctorは12 pass / 0 fail、試験用`output/`残留物は0件だった。

### M5 R3対応とDoD再検証（2026-08-18、5/5 pass）

- R3-01/R3-02: review_requestの`level_limits`・実効limits・固有名詞allowlistをformat/levelと設定から再導出して照合し、finalize時にtopicをFIN-01へ照合した。終端監査の一意な試行ID数は`2 * requested_count`以下に制限した。
- 承認済みM5D-06: 文法解説に必須の教員版項目名を`kyoinban.name_ja`へ統一し、生成・レビュー両coreを同期した。R3-04/R3-05として、CHK-04へ全語連鎖・未収録表現・⑧両文の検査、CHK-16へ対象文法操作の核心を空欄が覆う検査を追加した。
- 承認済みM5D-07/M5D-08: 進捗・不成立表示と監査範囲を`generation_max`でパラメータ化した。保存済みreview_resultの`machine_check_disputes[]`件数を保存時に一度だけ累積し、S80開始後の完了・中止報告へ0件でも固定表示する契約を追加した。
- DoD 1（RPL-01〜10）
  - コマンド: `PYTHONPATH=scripts .venv/bin/python - <<'PY' ... 3問gen1確定、gen1 review fail→gen2採用、2N境界、candidate/review不正、machine fail非上書き、横断違反、監査参照を実監査ファイルとCLIで検証 ... PY`。
  - 結果: RPL-01〜10は10/10 pass。3問とgen2採用セットを`finalize_set.py`で実確定し、setスキーマ、監査参照、構造化指摘6フィールド、補充・教師照会・再試行・最悪コスト境界を確認した。
- DoD 2（独立性）
  - コマンド: 同上のreview_requestと`agent/reviewer-core.md`の読み取り・禁止境界照合。
  - 結果: 入力封筒とRC-10の8リソースだけを読み、前世代・他問・生成側会話・許可外ファイル・書込み・ネットワークを禁止する構成だった。
- DoD 3（機械fail優越）
  - コマンド: 同上のmachine fail＋review passのgen1と全検査passのgen2を`accepted_attempts`へ投入。
  - 結果: gen1は採用されず、gen2だけが採用された。
- DoD 4（CI-SET-01〜06）
  - コマンド: 同上の`build_set_report`違反3種、正常・不完全setのfinalize、固定一時名シンボリックリンク下での並行finalize 2プロセス実行。
  - 結果: CI-SET-01〜06は6/6 pass。`V-SET-01/02/03`を個別検出し、正常確定・不完全状態の確定拒否・監査命名/参照・正本必須ブロックを確認した。並行処理は1件成功・1件`E-CONTRACT-05`で、リンク先と確定済み`set.json`は不変だった。
- DoD 5（レビュー出力不正）
  - コマンド: `{}`を`validate.py --schema review_result --file -`へ投入し、author coreのT6/T7遷移と`review.invalid1`〜`3`を照合。
  - 結果: stdoutは`valid=false`、stderrは`E-CONTRACT-01`となり、問題不合格・世代消費に数えず初回＋再実行2回の失敗後にセット中止する契約だった。
- 追加コマンド: `.venv/bin/python scripts/doctor.py`、`.venv/bin/python -m py_compile scripts/*.py`、`git diff --check`。
- 追加結果: doctor 12 pass / 0 fail、全Python構文検査と差分検査はpass、試験用`output/`残留物は0件だった。

### M5 R7対応とDoD再検証（2026-08-18、5/5 pass）

- 承認済みM5D-15: `machine_check.py`が`--requested-count N`から試行ID上限`min(2N,20)`を導出し、N=3の補充・代替`q04`〜`q06`を許可しつつ`q07`を`V-COND-01`で拒否するようにした。q20の全体上限とfinalize側のスロット・2N立証は維持した。
- 承認済みM5D-16: `validate.py`が全JSON string値とobject keyのstrict UTF-8表現可能性を再帰検証し、孤立サロゲートを`E-INPUT-03`で拒否するようにした。review_resultの後段JS-01正準化失敗も、AUD-09監査を残す同一requestのINF-01再試行へ統一した。
- 承認済みM5D-17: FIN-01 `created_at`の数値UTCオフセットを分00〜59・絶対値14:00以下・14時は00分だけに制限した。`+09:00`・`Z`・`+14:00`を許可し、`+09:99`・`+14:01`を`E-CONTRACT-01`で拒否した。
- DoDコマンド: `PYTHONPATH=scripts .venv/bin/python .m5_r7_dod_tmp.py`（実行後に一時ハーネスを削除）。実リポジトリ`output/`直下へ記録済み監査フィクスチャを一時投入し、`machine_check.py`・`validate.py`・`set_check.py`・`finalize_set.py`と監査読込みを実行した。
- DoD 1: RPL-01〜10は10/10 pass。3問gen1確定、review fail後のgen2採用、補充・代替ID境界、review/candidate受理失敗、machine fail非上書き、横断違反、監査参照、`min(2N,20)`最悪境界を確認した。
- DoD 2: review_requestは候補・machine report・実効制約とRC-10の8リソースだけを含み、reviewer coreは生成側会話・他問・過去世代・書込み・ネットワークを禁止していた。
- DoD 3: review passでもmachine failの世代は採用されず、machine/review/set_checkが全passの世代だけが採用された。
- DoD 4: CI-SET-01〜06は6/6 pass。`V-SET-01/02/03`の個別検出、正常確定、不完全確定拒否、監査命名・参照・正本必須内容、固定一時名symlink不変、並行finalizeの1成功/1 `E-CONTRACT-05`を確認した。
- DoD 5: schema-validなescaped lone surrogate review_resultを3回とも`E-INPUT-03`とし、AUD-09 `validation_failure`封筒3件が妥当で、問題不合格・世代消費に数えず同一requestの3失敗後にT7/S99へ進み`set.json`を書かない契約を確認した。
- 追加コマンド: `.venv/bin/python -m py_compile scripts/*.py`、`.venv/bin/python scripts/doctor.py`、`git diff --check b146041bb3a78c2eb62f9fcafe1294bb63e22c4e`、`git diff --quiet -- reviews/m5-r7.md`。
- 追加結果: 全Python構文検査と差分検査はpass、doctorは12 pass / 0 fail、R7レビュー原本は不変、試験用`output/`残留物は0件だった。

### M5 R8対応とDoD再検証（2026-08-18、5/5 pass）

- R8-01/R8-02: reviewer coreのCHK-12へ禁止題材・年齢適合・帯内難度、CHK-13へ学習者視点の正答到達過程・必要知識全列挙・語用／文化／教科／正書法・句読法の4分類を正本どおり追加した。
- R8-03: 通常candidate/machine/request/review、増分・最終set_check、slot outcomeの全JSON監査を、strict UTF-8文字列・object keyとJS-01正準バイト一致で検証し、不一致をファイル名付き`E-CONTRACT-03`で拒否するようにした。
- R8-04: FIN-01に孤立サロゲートの未定義キーがある場合、生キーをエラーへ展開する前に安全な`E-CONTRACT-01`を返し、終了コード1・CLI-05正準stderr・`set.json`なしを保証した。
- 個別回帰コマンド: `PYTHONPATH=scripts .venv/bin/python - <<'PY' ... 7種類のJSON監査へescaped lone surrogate、review監査へ非正準キー順・CRLF・末尾改行欠落、FIN-01へ孤立サロゲート追加キーを投入 ... PY`。
- 個別回帰結果: 7種類すべてが`E-CONTRACT-03`、3種類の非正準バイトも`E-CONTRACT-03`となった。schema-validな孤立サロゲート入りreview監査は`set_check.py`と`finalize_set.py`の両方で`E-CONTRACT-03`・`set.json`なし、FIN-01は終了コード1・`E-CONTRACT-01`の正準stderrのみを返し、reviewer coreのCHK-12/13必須手順も全件存在した。
- DoDコマンド: `PYTHONPATH=scripts .venv/bin/python .m5_r8_dod_tmp.py`（実行後に一時ハーネスを削除）。正準監査フィクスチャを実`output/`直下へ一時投入し、`machine_check.py`・`validate.py`・`set_check.py`・`finalize_set.py`を実行した。
- DoD結果: M5 DoD 5/5、RPL-01〜10 10/10、CI-SET-01〜06 6/6 pass。3問正常確定、gen2採用、machine fail非上書き、補充・代替境界、candidate/review受理失敗、横断3違反、不完全確定拒否、監査参照、固定symlink不変、並行finalizeの1成功/1 `E-CONTRACT-05`、独立レビュー境界を確認した。
- 追加コマンド: `.venv/bin/python -m py_compile scripts/*.py`、`.venv/bin/python scripts/doctor.py`、`git diff --check b146041bb3a78c2eb62f9fcafe1294bb63e22c4e`。
- 追加結果: 全Python構文検査と差分検査はpass、doctorは12 pass / 0 fail、試験用ハーネス・`output/`残留物は0件だった。

### M5 R9対応（2026-08-18）

- R9-01: set directory名からの副作用なしset_id抽出と、directoryの存在・配置検証を分離した。`finalize_set.py`はFIN-01内容検証、config snapshot照合、directory実体検証の順に進み、CLI-21のエラー優先順位へ一致した。
- 回帰コマンド: `PYTHONPATH=scripts .venv/bin/python - <<'PY' ... 同じ不存在set directoryへ空FIN-01、設定不一致FIN-01、正常FIN-01を順に投入 ... PY`。
- 回帰結果: 空FIN-01は`E-CONTRACT-01`、設定不一致は`E-DATA-08`、内容と設定が正常な場合だけdirectory不存在の`E-INPUT-02`となった。
- 追加確認: `.venv/bin/python -m py_compile scripts/*.py`と`git diff --check b146041bb3a78c2eb62f9fcafe1294bb63e22c4e`はpass、doctorは12 pass / 0 fail。R9はblocker/major 0件のため、`m-fix`の条件に基づくM5 DoD全件再実行の対象外だった。

### M5レビューサイクル収束（R1〜R9）

- 独立レビューを9ラウンド実施し、blocker 0件、major 29件、minor 10件の全39件を解消して各ラウンドの`reviews/m5-r1-resolutions.md`〜`reviews/m5-r9-resolutions.md`へ対応を記録した。最新R9はblocker/major 0件でコミット可と判定され、残ったminor R9-01も解消した。
- M5の最終成果として、1問1独立レビュー、世代別監査、構造化指摘による再生成、補充・教師照会、集合横断検査、正本の上書き不能な原子的確定までを一貫した契約として実装し、M6未実装のHTML生成との境界を維持した。
- 最終の全件DoDはR8対応後にM5 DoD 5/5、RPL-01〜10 10/10、CI-SET-01〜06 6/6 pass。R9対応後はCLI-21優先順位の個別回帰、全Python構文検査、doctor 12 pass / 0 fail、差分検査をpassし、試験用ファイルを残していない。

## 2026-08-17 — M4 対話＋生成コア

### 実装

- `agent/author-core.md` を追加し、S00〜S99の状態遷移、1ターン1質問、入力検証と固定再質問、停止・戻る・修正フローを定義した。
- `lookup.py` を唯一の照合経路とし、語彙・文法の明示指定、レベル不一致、辞書外、多品詞、形式不適合、提案モードを対話フローへ配線した。
- 承認済みM4D-01に基づき、文法名の部分一致が複数件の場合は全適格候補をlookup返却順で提示し、教師の番号選択を待つ仕様を `DECISIONS.md` と `docs/interaction-flow.md` に反映した。
- 9形式のcandidate JSON骨格と、PRM-01〜PRM-14の必須制約を生成プロンプト構築仕様へ反映した。
- M4の暫定配線として、candidateを `validate.py`、`machine_check.py`、machine reportスキーマの順に検証し、正規パスへ保存する手順を定義した。正式な対話ランタイムアダプタは計画どおりM7の範囲とした。
- 承認済みM4D-03に基づき、品詞プール緩和の要否をGEN-13の意味的除外後の有効候補数で判断し、機械検査は同レベル・互換品詞・異品詞誤答の実使用、CHK-06は意味的除外と緩和の必要性を担当する境界へ改訂した。
- 承認済みM4D-04に基づき、candidate生出力をホスト側のパース前に検証し、生成起因のUTF-8・標準JSON・スキーマ・厳格パース・JS-01正準化失敗をinvalid監査付きT2/T3へ統一した。
- 承認済みM4D-05/M4D-06に基づき、明示対象集合の1〜`set_question_max`件不変条件と原子的な追加・削除を定義し、S00後に固定した同じ上限値を質問、再質問、受理境界、残容量、S80のCLIへ反映した。
- 承認済みM4D-07/M4D-08に基づき、対象出現フィールドでは同長の一般複数語候補より宣言ターゲットを優先し、`vocab_mcq_ja2en`の選択肢では実値が一致する宣言アンカーの全トークン区間を同じentryとして照合するようにした。非対象フィールドの最長一致・ID順と、不正アンカーの通常照合は維持した。
- `schemas/` は変更していない。

### レビューサイクル

- R1〜R7の7ラウンドを実施し、検出されたblocker 0件・major 10件・minor 2件を全て解消した。R7は未解消blocker 0件・major 0件・minor 0件で収束し、コミット可となった。

### M4 DoD検証（2026-08-17、5/5 pass）

- コマンド: `PYTHONPATH=scripts .venv/bin/python - <<'PY' ... author-core・interaction-flowの静的契約、lookup.py、validate.py、machine_check.py、各JSON Schemaを実データで一括検証 ... PY`。
- DoD 1: 全状態と遷移順、1ターン1質問、入力検証、固定再質問、およびM4D-01の複数一致選択を確認した。`be` / A1.2 の複数一致ではlookup返却順を保持した。
- DoD 2: `abandon` / A1 は実データの `verb/B1` と不一致のため拒否し、`Tokyo` はWordlist一致0件のため辞書外として拒否した。
- DoD 3: 公式例を基にした9形式すべてでcandidateスキーマ、`validate.py`、`machine_check.py`、machine reportスキーマに適合し、機械判定は9/9 passだった。
- DoD 4: PRM-01〜PRM-14、現行 `limits.json`、実行時に全件展開する `data/config/proper_nouns.json` の50語の固有名詞allowlistを確認した。
- DoD 5: 9レベルすべてで教師版の直接割当だけが提案対象となった。適格件数はA1.1=28、A1.2=50、A1.3=61、A2.1=65、A2.2=63、B1.1=76、B1.2=67、B2.1=53、B2.2=34。未割当16 IDと `gp:47` は拒否した。

### M4 R4対応後の再検証（2026-08-17）

- R4-01回帰コマンド: `PYTHONPATH=scripts .venv/bin/python - <<'PY' ... do/haveの生プール、互換品詞緩和candidate、不正フラグ、CHK-06境界を検証 ... PY`。
- R4-01回帰結果: `do` / `have` は生の同品詞候補が各3件でも、異品詞誤答を実使用した `pos_pool_relaxed=true` candidateがともに `verdict=pass`・`V-DIS-02`なし。フラグfalseの異品詞使用と、異品詞を使わないフラグtrueは `V-DIS-02`。CHK-06は `does` / `has` を区別不能語として有効候補から除外し、有効候補3件以上の不要な緩和をfailにする手順を持つ。
- DoDコマンド: `PYTHONPATH=scripts .venv/bin/python - <<'PY' ... 状態機械、lookup実データ、正本文書内9形式例の正準化、validate.py、machine_check.py、設定、文法9レベルを一括検証 ... PY`。
- DoD 1: S00〜S99の16状態、1ターン1質問、固定再質問、`be` / A1.2の10件をlookup順で扱うM4D-01分岐がpass。
- DoD 2: `abandon`は実値verb/B1のためA1で拒否、`Tokyo`はWordlist一致0件として拒否しpass。
- DoD 3: 正準化した9形式すべてでcandidateスキーマ、`machine_check.py`のverdict=pass、machine reportスキーマが9/9 pass。
- DoD 4: PRM-01〜PRM-14、現行limits、50語の固有名詞allowlist全件実行時展開指示がpass。
- DoD 5: 9レベルすべてで教員版直接割当だけを返し、親レベル継承枝番と未付与16項目を拒否してpass。適格件数はA1.1=28、A1.2=50、A1.3=61、A2.1=65、A2.2=63、B1.1=76、B1.2=67、B2.1=53、B2.2=34。
- 結果: M4 DoD 5/5 pass。Python構文検査と `git diff --check` もpassし、`doctor.py` は12 pass / 0 failだった。

### M4 R5対応後の再検証（2026-08-17）

- R5-01回帰コマンド: `PYTHONPATH=scripts .venv/bin/python - <<'PY' ... 1e400、NaN、Infinity、孤立サロゲートの生出力受理、T2/T3分類、invalid監査を検証 ... PY`。
- R5-01回帰結果: 巨大指数は`E-CONTRACT-01`、`NaN` / `Infinity` は`E-INPUT-03`、エスケープされた孤立サロゲートはJS-01正準化失敗、UTF-8化不能文字列はstrict UTF-8失敗として、全て未処理例外なしでT2/T3監査経路へ分類された。
- R5-02/R5-03回帰コマンド: `.venv/bin/python - <<'PY' ... 20+1、19+1、重複追加、19+2、全件削除、1件残す削除、set_question_max=10/20の表示・受理境界を検証 ... PY`。
- R5-02/R5-03回帰結果: 上限超過追加と全件削除は元集合を保持し、上限内追加と1件以上残す削除だけが受理された。上限10/20の質問表示、境界受理、上限+1の拒否理由も一致した。
- DoD最終コマンド: `PYTHONPATH=scripts .venv/bin/python - <<'PY' ... 16状態と固定再質問、lookup実データ、9形式candidateとmachine report、PRM-01〜14、現行設定、固有名詞allowlist、文法9レベル適格件数、未付与16項目と継承枝番を検証 ... PY`。
- DoD 1: 16状態、1ターン1質問、固定再質問、動的件数境界、`be` / A1.2の10件複数一致分岐がpass。
- DoD 2: `abandon` / A1と`Tokyo`辞書外の実lookup拒否がpass。
- DoD 3: 9形式candidateスキーマ、機械判定、machine reportスキーマが9/9 pass。
- DoD 4: PRM-01〜14、現行limits、50語の固有名詞allowlistがpass。
- DoD 5: 教員版直接割当の9レベル適格件数、未付与16項目、`gp:1-1`の拒否がpass。適格件数はA1.1=28、A1.2=50、A1.3=61、A2.1=65、A2.2=63、B1.1=76、B1.2=67、B2.1=53、B2.2=34。
- 結果: M4 DoD 5/5 pass。Python構文検査と `git diff --check` もpassし、`doctor.py` は12 pass / 0 failだった。

### M4 R6対応後の再検証（2026-08-17）

- R6-01回帰コマンド: `PYTHONPATH=scripts .venv/bin/python - <<'PY' ... 同一複数語キー8組の後順位ターゲット、非対象ID順、最長一致、wedの対象文・選択肢、不正アンカー、'mの分割を実データで検証 ... PY`。
- R6-01回帰結果: 8組すべてで後順位の宣言ターゲットを対象回数1・対象IDで採用した。非対象の`all right`は従来どおりadjectiveのID順を維持し、短い`right`ターゲットより長い`all right`を優先した。`wed`は完成文と正解選択肢の各2トークンを同じ`lex:wed:verb`として採用して`verdict=pass`となり、記録pos不一致では宣言アンカー照合を使わず`V-DIS-01` / `V-LEX-01`となった。`'m`の2トークンも同じ宣言アンカーで採用した。
- DoD最終コマンド: `PYTHONPATH=scripts .venv/bin/python - <<'PY' ... 16状態と固定再質問、lookup実データ、正本内9形式例の正準化、validate.py、machine_check.py、machine reportスキーマ、PRM-01〜14、現行設定、固有名詞allowlist、文法9レベル適格件数、未付与16項目と継承枝番を検証 ... PY`。
- DoD 1: 16状態、1ターン1質問、固定再質問、動的件数境界、`be` / A1.2の10件複数一致分岐がpass。
- DoD 2: `abandon` / A1と`Tokyo`辞書外の実lookup拒否がpass。
- DoD 3: 9形式candidateスキーマ、`validate.py`、機械判定、machine reportスキーマ、machine reportの`validate.py`再検証が9/9 pass。
- DoD 4: PRM-01〜14、現行limits、50語の固有名詞allowlistがpass。
- DoD 5: 教員版直接割当の9レベル適格件数、未付与16項目、`gp:1-1`の拒否がpass。適格件数はA1.1=28、A1.2=50、A1.3=61、A2.1=65、A2.2=63、B1.1=76、B1.2=67、B2.1=53、B2.2=34。
- 結果: M4 DoD 5/5 pass。`.venv/bin/python -m py_compile scripts/machine_check.py scripts/lookup.py scripts/validate.py scripts/doctor.py`と`git diff --check`はpassし、`doctor.py`は12 pass / 0 failだった。

### M4着手前のM1 DoD再検証（2026-08-17、6/6 pass）

1. 決定性
   - コマンド: `.venv/bin/python - <<'PY' ... リポジトリ内の独立した一時出力先2件へbuild_normalized.pyを各1回実行し、2組とコミット済み3成果物をバイト比較 ... PY`。
   - 結果: 2回とも終了コード0・stderr空。3ファイルは各組およびコミット済み成果物とバイト一致した。SHA-256はlexicon=`11ac8d1d6b42e5fbd37baa1005b55d7904f42f2753e0720018bbc9edb977c3c7`、grammar=`6a435941ff1105a78b76fae0c141288a783d31148449302621d3b42a8ebbff62`、meta=`fd8c51b2f664f5eaef04c73936927fcd9cb1eb1c2bae56b65df9ad53ec0f0fd4`。
2. スキーマ・meta適合
   - コマンド: `PYTHONPATH=scripts .venv/bin/python - <<'PY' ... jsonschema.validator_forとvalidate_meta_documentで3成果物を検証 ... PY`。
   - 結果: `lexicon.json`・`grammar.json` は対応するDraft 2020-12スキーマ、`meta.json` はNRM-29に適合した。`data_version=wl1.6+gp20200220+norm1.0.2`、`pipeline_version=1.0.2`。
3. 件数不変条件（CI-NRM-03）
   - コマンド: `.venv/bin/python - <<'PY' ... json/openpyxlで正規化データと原本ALLシートを検証 ... PY`。
   - 結果: entries=7,988、A1=1,200 / A2=1,443 / B1=2,486 / B2=2,859、`(headword,pos)`ユニーク=7,988、ALL行=7,801、groups=179（全member 2件以上）、grammar=501（親263・枝番238）、target_eligible=256、全枝番の親が存在し、未付与親16件のID集合が仕様値と一致した。
4. レベル継承・範囲分解（CI-NRM-05 / CI-NRM-07）
   - コマンド: `.venv/bin/python - <<'PY' ... grammar.jsonの全継承項目と教員版level_rawを検証 ... PY`。
   - 結果: 継承項目220件が親の下限・上限を保持し、`gp:1-1` / `gp:1-2` / `gp:1-3` は `gp:1` のレベルを継承した。教員版は単一値152件・範囲値104件で、全単一値の下限=上限、全範囲値が`min-max`へ分解されていた。
5. doctor完全環境・異常模擬（CI-NRM-06 / CI-CLI-03）
   - コマンド: `.venv/bin/python - <<'PY' ... 一時コピーで完全環境・正規化欠落・原本1バイト改変・config欠落をdoctor.pyで検査し、原本改変環境ではbuild_normalized.pyも実行 ... PY`。
   - 結果: 完全環境は12 pass / 0 fail・終了コード0。正規化欠落はD08/D09=`E-DATA-03`、原本改変はdoctor D07およびbuild=`E-DATA-02`、`limits.json`欠落はD10=`E-DATA-05`で各終了コード1となり、doctorのstderrは空だった。
6. 差分ゼロ
   - コマンド: `.venv/bin/python - <<'PY' ... scripts/build_normalized.py --diffを実行し、前後の3成果物SHA-256を比較 ... PY`。
   - 結果: lexicon / grammarのadded / removed / level_changedは全て`count=0, ids=[]`、`written=[]`、終了コード0・stderr空。実行前後の3ファイルSHA-256は一致した。

## 2026-08-17 — M3 スキーマ検証

### 実装

- `scripts/validate.py` を追加し、`set` / `candidate` / `machine_report` / `review_request` / `review_result` / `normalized_lexicon` / `normalized_grammar` / `config_limits` / `config_proper_nouns` の9識別子を統一CLIで検証できるようにした。
- 妥当時は検証結果JSONと終了コード0、不当時は違反JSONポインタ・日本語理由を持つ検証結果をstdout、`E-CONTRACT-01`をstderrへ出力して終了コード1とした。違反は決定的順序で最大50件を返し、総数をエラーdetailへ記録する。
- stdin・ファイルをUTF-8バイト列として標準JSON構文で解析し、非標準数値定数を位置付き`E-INPUT-03`で拒否する。標準JSON数値はbinary64へ丸めず、正規化係数と任意精度の10進指数で保持してスキーマの数値制約で判定する。正常・エラーJSONはいずれも正準形UTF-8・LFで出力する。
- PLN-05で承認されたM3D-01を `DECISIONS.md` へ記録し、通常検証と排他的な `--set-dir` 状態確認モードを追加した。`set.json` がなければ `status=incomplete`、存在すればsetスキーマ検証を伴う `status=complete` を返す契約を関連設計文書へ反映した。
- `schemas/` 9本は変更していない。

### M3着手前のM1 DoD再検証（2026-08-17、6/6 pass）

1. 決定性
   - コマンド: `.venv/bin/python - <<'PY' ... リポジトリ内の独立した一時出力先2件へbuild_normalized.pyを各1回実行し、2組とコミット済み3成果物をバイト比較 ... PY`。
   - 結果: 2回とも終了コード0・stderr空。3ファイルは各組およびコミット済み成果物とバイト一致した。SHA-256はlexicon=`11ac8d1d...c3c7`、grammar=`6a435941...f62`、meta=`fd8c51b2...0fd4`。
2. スキーマ・meta適合
   - コマンド: `PYTHONPATH=scripts .venv/bin/python - <<'PY' ... schema_errorsとvalidate_meta_documentで3成果物を検証 ... PY`。
   - 結果: `lexicon.json`・`grammar.json` は対応スキーマ、`meta.json` はNRM-29に適合した。`data_version=wl1.6+gp20200220+norm1.0.2`、`pipeline_version=1.0.2`。
3. 件数不変条件（CI-NRM-03）
   - コマンド: `.venv/bin/python - <<'PY' ... json/openpyxlで正規化データと原本ALLシートを検証 ... PY`。
   - 結果: entries=7,988、A1=1,200 / A2=1,443 / B1=2,486 / B2=2,859、`(headword,pos)`ユニーク=7,988、ALL行=7,801、groups=179（全member 2件以上）、教員版=256、ITEM LIST=501、全枝番の親が存在し、未付与親16件のID集合が仕様値と一致した。
4. レベル継承・範囲分解（CI-NRM-05 / CI-NRM-07）
   - コマンド: `.venv/bin/python - <<'PY' ... grammar.jsonの全継承項目と教員版level_rawを検証 ... PY`。
   - 結果: 継承項目220件が親の下限・上限を保持し、`gp:1-1` / `gp:1-2` / `gp:1-3` は `gp:1` を継承した。教員版は単一値152件・範囲値104件で、全単一値の下限=上限だった。
5. doctor完全環境・異常模擬（CI-NRM-06 / CI-CLI-03）
   - コマンド: `.venv/bin/python - <<'PY' ... 一時コピーで完全環境・正規化欠落・原本1バイト改変・config欠落をdoctor.pyで検査し、原本改変環境ではbuild_normalized.pyも実行 ... PY`。
   - 結果: 完全環境は12 pass / 0 fail・終了コード0。正規化欠落はD08/D09=`E-DATA-03`、原本改変はdoctor D07およびbuild=`E-DATA-02`、`limits.json`欠落はD10=`E-DATA-05`で各終了コード1・具体的remedyあり・doctorのstderr空だった。
6. 差分ゼロ
   - コマンド: `.venv/bin/python - <<'PY' ... scripts/build_normalized.py --diffを実行し、前後の3成果物SHA-256を比較 ... PY`。
   - 結果: lexicon / grammarのadded / removed / level_changedは全て0件、`written=[]`、終了コード0。実行前後の3ファイルはバイト一致した。

### M3 DoD実行記録（4/4 pass）

1. 9スキーマの自己妥当性（CI-SCH-01）
   - コマンド: `.venv/bin/python - <<'PY' ... validator_for(schema).check_schema(schema)と$id書式を9ファイルで検証 ... PY`。
   - 結果: 9/9がJSON Schema draft 2020-12メタスキーマに適合し、`$id`は規定URL＋semver書式だった。machine_reportは1.1.0、他8本は1.0.0。
2. CI-SCH-01〜05
   - コマンド: `.venv/bin/python - <<'PY' ... 設計文書内の公式JSON例を一時ファイル化し、scripts/validate.pyをsubprocessで実行 ... PY`。
   - 結果: 9スキーマの妥当例は9/9合格。各スキーマの必須欠落・型不正・additionalProperties違反は27/27が`E-CONTRACT-01`と違反パスを返した。candidateの9形式は9/9合格し、format/body不整合は不合格。妥当IDに加え、set_id不正・`q21`・`gen4`・不正lex ID・不正gp IDを全て不合格とした。
3. CI-CLI-01入力不正3種
   - コマンド: `.venv/bin/python - <<'PY' ... 必須引数欠落・不存在ファイル・不正JSON stdinでvalidate.pyをsubprocess実行 ... PY`。
   - 結果: 順に`E-INPUT-01` / `E-INPUT-02` / `E-INPUT-03`、stdout空、終了コード1、日本語message・具体的remedyとなった。不正JSONは行・列をdetailへ記録した。
4. CI-MCH-12再確認
   - コマンド: `.venv/bin/python - <<'PY' ... 公式candidate例をmachine_check.pyへ投入し、そのstdoutをvalidate.py --schema machine_report --file -へ入力 ... PY`。
   - 結果: machine_check.pyはスキーマ1.1.0のreportを終了コード0で出力し、validate.pyは`valid=true`・終了コード0・stderr空で受理した。

### 追加確認

- `validate.py --set-dir` は監査のみのディレクトリを `status=incomplete`・終了コード0・stderrなしで識別した。妥当な`set.json`は`status=complete`かつvalid、不当な`set.json`はcomplete状態を保持して`E-CONTRACT-01`、不存在ディレクトリは`E-INPUT-02`、不正set_idは`E-INPUT-05`となった。
- 60件の違反を持つ入力でstdoutとstderrの違反列挙が先頭50件、`detail.total_errors=60`となり、同一入力2回の出力がバイト一致した。
- `PYTHONIOENCODING=ascii|cp932|utf-16`の各環境で同じUTF-8 stdinを受理した。不正UTF-8はstdin・ファイルとも対象・行・列付き`E-INPUT-03`、リポジトリルート外からの実行は`E-ENV-04`となった。
- `.venv/bin/python - <<'PY' ... 公式config_limitsのdistractor_reuse_maxを1e400と1e9223372036854775806へ個別に置換し、stdin・通常ファイルの両経路を実CLIで検証 ... PY` は4/4条件で`valid=true`・終了コード0・stderrなしとなり、任意精度指数を数学上の整数値として判定した。

### レビューサイクル収束（R1〜R10）

- 独立レビューを10ラウンド実施し、R1〜R10で検出したblocker 0件・major 9件・minor 8件は全件解消した。最新R10の省略オプション3条件は`E-INPUT-01`、日本語ヘルプはUTF-8・ASCII・CP932・Cロケールの4環境で同一UTF-8出力・終了コード0となった。
- 最終DoDは4/4 pass: 9スキーマのDraft 2020-12自己妥当性9/9、公式妥当例9/9、必須欠落・型不正・additionalProperties違反27/27、candidate 9形式9/9、ID不正5/5、CI-CLI-01入力不正3/3、実`machine_check.py`のmachine_report再検証が`valid=true`となった。

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

### R4レビュー修正（2026-08-17）

- R4-01: candidateと期待レベルのscaleが同じ場合、S4〜S6のレベル依存検査を期待レベル基準で実行するよう修正した。scaleが異なる場合は`V-COND-01`を維持し、candidateのscaleと値で実行可能な検査を継続する。
- R4-02: PLN-05で承認されたM2D-10を`DECISIONS.md`へ記録し、`machine_check.py`による`set_question_max`参照をS1の`--requested-count`値域検査だけに限定するようMC-10とCLI-16を同期した。
- R4-03: PLN-05で承認されたM2D-11を`DECISIONS.md`へ記録し、candidate JSON整数の上限を符号を除く10進4,300桁に固定した。4,301桁以上は対象・行・列・上限・実測桁数付き`E-INPUT-03`とし、`PYTHONINTMAXSTRDIGITS`に依存しない出力へ修正した。
- CI-MCH-17・18を`docs/testing-and-acceptance.md`とM2 DoDへ追加した。`schemas/`は変更していない。

### R4修正後のM2 DoD再検証（4/4 pass）

1. 機械検査マトリクス
   - コマンド: `PYTHONPATH=scripts .venv/bin/python - <<'PY' ... 実データ・spaCy・実CLIでCI-MCH-01〜18、9形式例、期待レベル全件列挙、整数桁数境界を検証 ... PY`。
   - 結果: CI-MCH-01〜18は18/18 pass。`docs/question-generation-spec.md`の9形式例はcandidateスキーマに全件適合し、検査で生成した36件のquestion reportは全て`machine_report.schema.json` 1.1.0に適合した。
2. 照会マトリクス
   - コマンド: `.venv/bin/python - <<'PY' ... scripts/lookup.pyをsubprocess実行しCI-LKP-01〜04を検証 ... PY`。
   - 結果: CI-LKP-01〜04は4/4 pass。`abandon`のB1 verbとA1不一致、`Tokyo`の辞書外、`watch`のA1 noun/verb、`gp:13`とレベル継承済み`gp:1-1`の表示名・パターン略記・レベルを確認した。
3. machine_reportスキーマ適合
   - コマンド: 上記CI-MCHハーネスから`jsonschema.Draft202012Validator`を直接呼び出し、各出力を`schemas/machine_report.schema.json`へ検証した。
   - 結果: CI-MCHフィクスチャと9形式例から生成した全36レポートがスキーマ1.1.0に適合した。
4. 決定性
   - コマンド: 上記CI-MCHハーネスで同一candidateを2回検査し、CI-R-02の実行日時フィールド`generated_at`を除外して正準UTF-8バイト列を比較した。
   - 結果: 2回の出力がバイト一致した。5,000桁整数の同一入力も`PYTHONINTMAXSTRDIGITS=4300|0`で、対象・位置・上限4,300・実測5,000桁を持つ`E-INPUT-03`の正準JSONがバイト一致した。

### R4追加回帰確認

- CI-MCH-17: B1 `abandon`候補＋期待A1で、`V-COND-01`・`V-LEN-01`・`V-LEX-02`・`V-TGT-03`を同一レポートへ列挙した。B2.2 `gp:97`候補＋期待A1.1は`V-COND-01`・`V-TGT-01`、A2語彙4択＋期待A1は`V-COND-01`・`V-DIS-02`を併記した。format不一致かつscale相違でもcandidate scaleの検査を完遂した。
- CI-MCH-18: トップレベルの余分フィールド値が4,300桁なら整数桁数を理由とする`E-INPUT-03`にならず`E-CONTRACT-01`のスキーマ検証へ進み、4,301桁・5,000桁は構造化された桁数情報付き`E-INPUT-03`となった。
- `scripts/machine_check.py`の`set_question_max`参照が`validate_set_conditions()`内の1箇所だけであることを検査した。
- `.venv/bin/python scripts/doctor.py`は12 pass / 0 fail、9スキーマのDraft 2020-12自己妥当性は9/9 pass、Python 3.7 grammar指定の`ast.parse`は4スクリプト全件pass、py_compile・`git diff --check`もpassした。
- M2着手前のM1 DoD 6項目は本ファイル「M2着手前のM1 DoD再検証」に6/6 passとして記録済みであり、M1マイルストーンコミット`18841cc`で確定している。

### レビューサイクル収束（R1〜R5）

- 独立レビューを5ラウンド実施した。R1〜R4で検出したblocker 0件・major 5件・minor 11件は全件解消し、R5は新規指摘なし（blocker 0件・major 0件・minor 0件）で収束した。
- M2成果物は`machine_check.py`・`lookup.py`、承認済み決定M2D-01〜M2D-11、関連設計文書、R1〜R5のレビュー・解決記録で確定した。`schemas/`は承認範囲外の変更を行っていない。
- 最終DoDは4/4 pass: CI-MCH-01〜18が18/18、CI-LKP-01〜04が4/4、検査したmachine report 36件がスキーマ1.1.0に適合し、`generated_at`除外後の同一入力2回の正準UTF-8バイト列が一致した。

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
