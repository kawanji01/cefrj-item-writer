# requirements.md — 要件定義

## 冒頭ブロック

- **目的**: CEFR-J準拠作問エージェントの利用者・利用場面・ユースケースを定義し、機能要件（FR-xx）・非機能要件（NFR-xx）・スコープ外/v2課題リスト・前提環境を確定する。
- **対象読者**: 実装担当（Codex GPT-5.6 sol）、作問者（教師・教授）、設計文書の執筆者・検査者。
- **参照文書**: `DECISIONS.md`（決定記録）、`docs/architecture.md`、`docs/interaction-flow.md`、`docs/question-generation-spec.md`、`docs/cefrj-validation-spec.md`、`docs/subagent-review-spec.md`、`docs/json-output-spec.md`、`docs/html-output-spec.md`、`docs/cross-agent-compatibility.md`、`docs/testing-and-acceptance.md`、`IMPLEMENTATION_PLAN.md`。
- **規範語彙凡例**: 「しなければならない(MUST)」=絶対要件。「してはならない(MUST NOT)」=絶対禁止。「すべきである(SHOULD)」=正当な理由がある場合のみ逸脱可（逸脱は構造化出力または実装ノートに記録する）。「してもよい(MAY)」=任意。
- **この文書が「正」とする範囲**: 利用者・利用場面・ユースケース（第2〜3節）、機能要件FR-01〜FR-41（第4節）、非機能要件NFR-01〜NFR-11（NFR-01aを含む。第5節）、**スコープ外/v2課題リストV2-01〜V2-09（第6節。全文書はv2課題をこのリストへの参照で示し、独自にv2課題を定義してはならない(MUST NOT)）**、前提環境ENV-01〜ENV-07（第7節）。各FR/NFRの詳細規則（条文・数値・手順・スキーマ）の正は各FR/NFRに記した参照先文書である。本文書は要件の存在と受け入れ観点のみを定義する。

---

## 1. プロジェクト概要

本プロジェクトは、CEFR-J Wordlist Ver1.6 と CEFR-J Grammar Profile（full 20200220）を根拠として、教師との日本語対話で作問条件を確定し、英語学習問題を生成し、生成とは独立したコンテキストのサブエージェントでCEFR-J適合性を厳格検証し、JSON正本と自己完結HTMLを出力する作問エージェントである（`DECISIONS.md` P-01〜P-10）。実装ランタイムは Claude Code または Codex 上のLLMエージェント＋Python決定的スクリプト群である。

## 2. 利用者と利用場面

- **U-01 作問者（一次利用者）**: 教師・教授。Claude Code または Codex を自分の環境で実行し、日本語対話で作問する。プログラミング専門家であることを前提としない（`DECISIONS.md` D-01, D-02）。
- **U-02 生徒（最終受益者）**: 作問者から配布された単一HTMLファイルをブラウザ（PC・スマートフォン）または印刷物で利用する。本システムを直接操作しない（D-17）。
- **U-03 第三者利用者**: 研究発表会を通じて本システムを知り、非公開リポジトリの共有を受けてU-01と同じ手順で利用する教師・研究者（D-01, D-02）。
- **利用場面**: 授業・宿題・小テスト用教材の作成、および研究発表でのデモンストレーション。1回の利用は「1セット（形式1つ+レベル1つ+対象複数+問題数）の作成」を単位とする（D-04）。

## 3. ユースケース

- **UC-01 明示指定による作問**: 教師が対象語彙/文法項目を明示指定し、即時の原本照合を経て、1セットを生成・検証・出力する。正常系の主ユースケース。フローの正: `docs/interaction-flow.md`。
- **UC-02 提案による作問**: 教師が対象を明示せず、エージェントの提案（語彙=Wordlist、文法=教員版256項目）から選んで1セットを作成する。フローの正: `docs/interaction-flow.md`。
- **UC-03 不一致・不成立時の対話**: 明示指定が原本と不一致（レベル違い・辞書外）の場合の指摘と代替促し、および3世代不合格による不成立時の教師照会。フローの正: `docs/interaction-flow.md`。
- **UC-04 HTML教材の配布・利用**: 教師が `output/<set_id>/index.html` を生徒に配布し、生徒が画面操作または印刷で利用する。仕様の正: `docs/html-output-spec.md`。
- **UC-05 環境診断**: 教師が `doctor.py` で環境・データ整合を一括診断し、日本語の対処手順を得る。仕様の正: `docs/architecture.md`。
- **UC-06 原本データの更新**: 管理者が新版xlsxを配置し、正規化ビルド・差分確認・data_version更新を行う。手順の正: `docs/architecture.md`。
- **UC-07 リリースと受け入れ**: 管理者がタグ付きリリース時に手動受け入れチェックリストを実施する。手順の正: `docs/testing-and-acceptance.md`。

## 4. 機能要件（FR）

各FRの記法: 要件文（規範語彙）＋詳細規則の正となる参照先。参照先文書と本文書が矛盾する場合、詳細規則については参照先文書を正とし、要件の存在については本文書を正とする。

### 4.1 対話・条件確定

- **FR-01 完全日本語対話**: 作問者との対話は全て日本語で行わなければならない(MUST)。1ターンに1質問のみ行わなければならない(MUST)（P-02）。正: `docs/interaction-flow.md`。
- **FR-02 対話フロー順序**: 対話は ①形式→②レベル→③対象指定方法→④問題数→⑤トピック[任意]→⑥固有名詞の追加希望[任意]→⑦条件サマリー確認 の順で進めなければならない(MUST)（DD-01）。正: `docs/interaction-flow.md`。
- **FR-03 レベル指定**: レベルは作問者が指定しなければならず(MUST)、エージェントが代行決定してはならない(MUST NOT)（P-03）。粒度は語彙=A1/A2/B1/B2の4段階、文法=A1.1〜B2.2の9段階とし、対応範囲はA1〜B2のみとする(MUST)（D-03）。Pre-A1およびC1以上は本文書第6節 V2-07 によりスコープ外。レベル体系の正: `docs/cefrj-validation-spec.md`。
- **FR-04 明示指定の即時照合**: 教師の明示指定対象は受領時に正規化データと照合しなければならない(MUST)。レベル不一致・辞書外・多品詞曖昧の場合はその場で指摘し、代替を促さなければならない(MUST)（D-05）。正: `docs/interaction-flow.md`。
- **FR-05 提案モード**: エージェント提案による対象選定に対応しなければならない(MUST)。語彙の提案では品詞・カテゴリによる絞り込みを任意で受け付け、文法の提案元は教員版256項目に限定しなければならない(MUST)（D-05, DD-01）。正: `docs/interaction-flow.md`。
- **FR-06 教員版未付与項目の拒否**: 教員版にCEFR-Jレベルが付与されていない文法項目（16件）を教師が明示要求した場合、理由を示して断らなければならない(MUST)（D-19）。文言の正: `docs/interaction-flow.md`。
- **FR-07 セット単位**: 1セッションは同一条件セット（形式1つ+レベル1つ+対象複数+問題数）を扱い、1セット=1正本JSON=1HTMLとしなければならない(MUST)（D-04）。問題数は1〜20問（上限は `data/config/limits.json` の運用パラメータ、DD-11）。単一セット内の形式・レベル混在は V2-06 によりスコープ外。

### 4.2 問題生成

- **FR-08 9形式の生成**: `vocab_mcq_en2ja` / `vocab_mcq_ja2en` / `vocab_flashcard_en2ja` / `vocab_flashcard_ja2en` / `grammar_mcq` / `grammar_cloze` / `grammar_reorder` / `grammar_rewrite` / `grammar_example_selfcheck` の9形式を生成できなければならない(MUST)（P-10）。各形式の生成仕様の正: `docs/question-generation-spec.md`。
- **FR-09 例文制約**: 例文は原則1文、レベル別語数上限（A1≤10 / A2≤14 / B1≤20 / B2≤26語、句読点除くトークン数）、語彙問題では対象語ちょうど1回出現（活用形可）の制約に従わなければならない(MUST)（D-12）。正: `docs/question-generation-spec.md`（生成規則）、`docs/cefrj-validation-spec.md`（機械計測）。
- **FR-10 誤答制約**: 語彙4択の誤答は同レベル・同品詞のWordlist実在語とし、由来（headword+pos+level）をJSONに記録しなければならない(MUST)。文法選択の誤答は同一パラダイム内操作で空欄に入れると不成立となるものとし、誤答の排除に指定レベル超の知識を要求してはならない(MUST NOT)（D-11）。正: `docs/question-generation-spec.md`。
- **FR-11 日本語規則**: 語義・例文訳・解説はD-13の文体・形式規則に従わなければならない(MUST)。正: `docs/question-generation-spec.md`。
- **FR-12 解説**: 文法5形式すべてに解説を付さなければならない(MUST)。`grammar_example_selfcheck` は詳細解説（400字上限）、他4形式は簡潔解説（200字上限）とし、内容要件はD-24に従う(MUST)。字数は機械計測とする(MUST)。語彙問題への解説拡張は V2-05 によりスコープ外。正: `docs/question-generation-spec.md`。
- **FR-13 固有名詞allowlist**: 生成は `data/config/proper_nouns.json` のallowlist・数字・記号・句読点・縮約展開以外の辞書外語を使用してはならない(MUST NOT)。allowlistは生成側にも制約として渡さなければならない(MUST)（D-10）。免除規則の正: `docs/cefrj-validation-spec.md`。

### 4.3 検証

- **FR-14 ハイブリッド検証**: 全候補問題は決定的機械検査と独立LLMレビューの両方を通過しなければならない(MUST)。機械検査違反は自動不合格であり、レビューはこれを上書きしてはならない(MUST NOT)。レビューは追加不合格のみ可能とする(MUST)（D-07）。レビューによる機械検査上書きは V2-08 により恒久的にスコープ外。正: `docs/cefrj-validation-spec.md`、`docs/subagent-review-spec.md`。
- **FR-15 機械検査**: 機械検査は例文中の全語彙のWordlist照合（レンマ化・複数語見出しのトークン列マッチ）、語数計測、対象語出現回数、誤答由来照合、辞書外語検出（免除規則適用）、スキーマ検証を決定的に実行しなければならない(MUST)（D-07, D-09, D-10, D-12）。正: `docs/cefrj-validation-spec.md`。
- **FR-16 スケール交差**: 文法問題Lx.yの例文語彙はWordlistレベル≤Lx、語彙問題Lの例文文法は導入レベル≤Lの最上位枝番（A1→A1.3、A2→A2.2、B1→B1.2、B2→B2.2）の規則で検証しなければならない(MUST)（D-08）。正: `docs/cefrj-validation-spec.md`。
- **FR-17 範囲値解釈**: 教員版の範囲値レベルは下限=導入レベル、上限=定着レベルとして解釈しなければならない(MUST)（D-06）。正: `docs/cefrj-validation-spec.md`。
- **FR-18 level_source**: レビュアーは列挙した各文法構造に `level_source`（`kyoinban` / `reviewer_estimate`）を必須付与しなければならない(MUST)。推定の導入レベルが許容超なら不合格としなければならない(MUST)（D-19）。正: `docs/cefrj-validation-spec.md`（規則）、`docs/subagent-review-spec.md`（記録様式）。
- **FR-19 レビュー独立性**: レビューは1問1独立実行とし、生成側の会話履歴をレビュアーから不可視にしなければならない(MUST)。レビュアーの入力は候補問題JSON・機械検査レポート・検証仕様・正規化データへの読み取り専用アクセスのみとする(MUST)（P-04, D-15）。正: `docs/subagent-review-spec.md`。
- **FR-20 セット横断検査**: 対象重複・例文使い回し・誤答の過度な再利用のセット横断検査は決定的スクリプト（`set_check.py`）で実行しなければならない(MUST)（D-15）。正: `docs/cefrj-validation-spec.md`（検査規則）、`docs/architecture.md`（CLI契約）。
- **FR-21 機械検査誤検出疑いの報告**: レビュアーは機械検査の誤検出（レンマ化誤りを含む）が疑われる場合、定義された様式で報告しなければならない(MUST)。報告があっても当該セットでは不合格を維持しなければならない(MUST)（D-07）。正: `docs/subagent-review-spec.md`。

### 4.4 再生成・不成立処理

- **FR-22 再生成ループ**: 1問は最大3世代（初回+再生成2）とし、再生成にはレビューの構造化指摘を渡し、再レビューは毎回独立に実行しなければならない(MUST)（D-14）。正: `docs/subagent-review-spec.md`。
- **FR-23 不成立処理**: 3世代不合格の問題は不成立とする(MUST)。提案モードでは候補プールから自動補充（セット試行対象総数≤要求数の2倍）、明示モードでは自動代替せず理由を示して教師照会としなければならない(MUST)（D-14）。正: `docs/subagent-review-spec.md`（補充規則）、`docs/interaction-flow.md`（照会フロー）。
- **FR-24 全試行の監査記録**: 全世代の候補・機械検査・レビューJSONを `output/<set_id>/review/` に試行単位で保存しなければならない(MUST)（D-14, D-16）。正: `docs/json-output-spec.md`。

### 4.5 出力（JSON・HTML）

- **FR-25 正本set.json**: 合格問題のみを含む `output/<set_id>/set.json` を正本として出力しなければならない(MUST)。schema_version・セットメタデータ・問題ごとの原本参照・設定スナップショット・data_version＋原本チェックサム・CEFR-J出典ブロック（`attribution`）を必須とする(MUST)（D-16）。正: `docs/json-output-spec.md`。
- **FR-26 監査ファイル配置**: 監査ファイルは正本から相対参照とし、監査が欠けても正本が自立解釈可能でなければならない(MUST)（D-16）。正: `docs/json-output-spec.md`。
- **FR-27 スキーマ検証**: 全JSON成果物は `schemas/` の9スキーマ（JSON Schema draft 2020-12、semver付き）で検証されなければならない(MUST)（D-16, D-23）。正: `docs/json-output-spec.md`、`schemas/`。
- **FR-28 原子的完成**: `set.json` はセット完成時のみ書き込まなければならない(MUST)。中断セットは監査のみが残り、未完成であることが自明でなければならない(MUST)（D-20）。中断セットの再開機能は V2-03 によりスコープ外。正: `docs/architecture.md`。
- **FR-29 自己完結HTML**: 1セット=1ファイルの単一自己完結HTML（CSS/JS全インライン、外部リソース・CDN・Webフォント・画像URLゼロ、オフライン動作）を生成しなければならない(MUST)。フッターにCEFR-J出典を常時表示しなければならない(MUST)（D-17）。正: `docs/html-output-spec.md`。
- **FR-30 形式別UIと印刷**: HTMLは形式別インタラクティブUI（D-17の画面仕様）と印刷CSS（問題ワークシート+改ページ後の解答・解説）を備えなければならない(MUST)。採点状態の永続化は V2-01 によりスコープ外。正: `docs/html-output-spec.md`。
- **FR-31 HTML決定性**: HTML生成は同一の `set.json` からバイト一致の出力を生成しなければならない(MUST)。選択肢順序はJSON保存時に固定し、HTML側で再シャッフルしてはならない(MUST NOT)（D-21, DD-07, DD-08）。正: `docs/html-output-spec.md`。

### 4.6 データ・CLI・運用

- **FR-32 正規化データ**: 原本xlsxから `data/normalized/`（lexicon.json / grammar.json / meta.json）を決定的にビルドし、出典ヘッダー付きでコミットしなければならない(MUST)。原本と正規化の整合はSHA-256チェックサムで起動時検証しなければならない(MUST)（D-22, DD-02）。正: `docs/cefrj-validation-spec.md`（変換規則）、`docs/architecture.md`（運用）。
- **FR-33 CLI群**: `doctor.py` / `build_normalized.py` / `machine_check.py` / `set_check.py` / `finalize_set.py` / `build_html.py` / `validate.py` / `lookup.py` の8本のPython CLIを提供し、全てJSON入出力・定義済み終了コードに従わなければならない(MUST)（D-09, D-18）。契約の正: `docs/architecture.md`。
- **FR-34 doctor診断**: `doctor.py` は環境・依存・データ整合を一括診断し、日本語の対処手順を提示しなければならない(MUST)（D-09, D-20）。正: `docs/architecture.md`。
- **FR-35 エラー処理**: 全CLIは実行前に前提条件を検査し、定義済みエラーコード（接頭辞 `E-ENV-` / `E-DATA-` / `E-CONTRACT-` / `E-INPUT-`）＋日本語対処手順で停止しなければならない(MUST)。データ不整合（原本欠落・チェックサム不一致・正規化陳腐化）は処理を拒否しなければならない(MUST)（D-20）。エラーコード目録の正: `docs/architecture.md`。
- **FR-36 レビュアー出力のインフラ障害扱い**: レビュアー出力のスキーマ不通過はインフラ障害として扱い、問題の不合格に数えてはならない(MUST NOT)。最大2回再実行し、なお失敗ならセットを中止しなければならない(MUST)（D-20）。正: `docs/subagent-review-spec.md`。
- **FR-37 生成候補スキーマ不通過**: 生成候補のスキーマ不通過は同一世代内で1回再指示し、失敗なら世代を消費しなければならない(MUST)（D-20）。正: `docs/subagent-review-spec.md`。
- **FR-38 互換構造**: 挙動規則は共通コア指示書（`agent/`）と決定的スクリプトに集約し、アダプタ（Claude Code / Codex）は配線のみとしなければならない(MUST)。アダプタに挙動規則を書いてはならない(MUST NOT)（D-18）。正: `docs/cross-agent-compatibility.md`。
- **FR-39 版管理**: 全スキーマはsemverを持ち、破壊的変更でメジャーを上げなければならない(MUST)。HTML生成器は現行メジャーのみ対応し、不一致は定義済みエラーで拒否しなければならない(MUST)。data_versionを正規化データと全成果物に記録しなければならない(MUST)（D-23）。正: `docs/architecture.md`。
- **FR-40 テスト**: 決定的pytest CI・フィクスチャ・リプレイ・リリース時手動受け入れチェックリストの3層テストを備えなければならない(MUST)（D-21）。正: `docs/testing-and-acceptance.md`。
- **FR-41 法務・透明性文書**: NOTICE（原本ごとに分離した出典・確認済みの利用条件・再配布注意）、LLM送信の明示（生成・レビュー時に正規化データ抜粋や問題文がAnthropic/OpenAIに送信されること）、生成問題の教育利用の最終確認が教師の責任である旨の免責を文書化しなければならない(MUST)。一次資料で確認できない利用権を、引用だけで許容されると案内してはならない(MUST NOT)（D-22、M7D-08）。要件の正: `docs/architecture.md`（運用文書要件）、`docs/cross-agent-compatibility.md`（手順書要件）。

## 5. 非機能要件（NFR）

- **NFR-01 完走時間（参考目標）**: 10問セットの完走（対話開始からHTML出力まで、再生成込み）は両ツールで30分以内を目標とすべきである(SHOULD)。時間は参考目標であり、テスト・受け入れの合否条件にしてはならない(MUST NOT)（DD-10, D-21）。
- **NFR-01a レビュー実行時間（参考目標）**: 独立レビュー1実行あたりの目標時間は、Claude Code（`.claude/run_reviewer.py`が監視する`claude -p`サブプロセス）=3分以内、Codex（`.codex/run_reviewer.py`が監視する`codex exec`サブプロセス）=3分以内とすべきである(SHOULD)。参考目標であり、テスト・受け入れの合否条件にしてはならない(MUST NOT)（D-15, D-21, M7D-13, M7D-16）。実行に適用する強制タイムアウトの正は `docs/subagent-review-spec.md` INF-07（`data/config/limits.json` の `review_timeout_seconds`、既定300秒）である。
- **NFR-02 最悪コスト上限**: 1セットの生成+レビューの実行回数は最悪で要求問題数の6倍（試行対象総数≤要求数の2倍 × 各3世代）を超えてはならない(MUST NOT)（D-14）。
- **NFR-03 決定性**: 正規化・機械検査・スキーマ検証・セット横断検査・HTML生成は決定的でなければならない(MUST)。同一入力に対し同一出力（HTMLはバイト一致）を返さなければならない(MUST)（D-09, D-21）。
- **NFR-04 オフライン動作とテレメトリ**: セットアップ完了後の決定的スクリプトは完全オフラインで動作しなければならない(MUST)。唯一の例外処理はセットアップであり、固定版依存パッケージとspaCyモデルの取得に限りネットワーク接続してもよい(MAY)。テレメトリ送信をしてはならない(MUST NOT)（D-22、M7D-07）。LLM呼び出し（生成・レビュー）はホストツール経由のネットワーク通信を伴い、この要件の対象外である。
- **NFR-05 言語**: 対話・エラー文言・運用文書・設計文書は日本語でなければならない(MUST)（D-02, DD-10）。問題の英文・JSONキー（英語snake_case）はこの要件の対象外である。
- **NFR-06 対応環境**: macOS / Linux、およびWindowsホスト上のWSL2 Linux環境でPython 3.11+が動作する環境をサポートしなければならない(MUST)。ネイティブWindowsのPowerShell・コマンドプロンプト上の作問実行はサポート対象外とする（DD-10、M7D-11）。
- **NFR-07 互換性保証範囲**: Claude Code と Codex の間で手順・契約・決定的処理の同一性を保証しなければならない(MUST)。LLM出力（生成文・レビュー判断）の同一性は保証対象外であることを文書に明記しなければならない(MUST)（D-18）。
- **NFR-08 出典表示**: 全正本JSONとHTMLフッターにCEFR-J出典（Wordlist・Grammar Profile両引用）を含めなければならない(MUST)（D-16, D-17, D-22）。
- **NFR-09 透明性（LLM送信）**: 正規化データ抜粋・問題文が生成・レビュー時にLLM事業者（Anthropic / OpenAI）に送信されることを、教師向け文書で明示しなければならない(MUST)（D-22）。
- **NFR-10 監査可能性**: 全試行（全世代の候補・機械検査・レビュー）が監査JSONとして残り、正本は監査が欠けても自立解釈可能でなければならない(MUST)（D-14, D-16）。
- **NFR-11 障害時の安全性**: 全異常は定義済みエラーコードで停止し、部分的に完成した `set.json` を残してはならない(MUST NOT)（D-20）。

## 6. スコープ外 / v2課題リスト（正）

本節が本プロジェクト全体のスコープ外事項の唯一の正である。他文書はスコープ外事項を本節のIDへの参照（例: 「`docs/requirements.md` の V2-01」）で示さなければならず(MUST)、独自にスコープ外事項を定義してはならない(MUST NOT)。v1実装はこれらの機能を実装してはならない(MUST NOT)。

| ID | 項目 | 内容 | 由来決定 |
|---|---|---|---|
| V2-01 | localStorage永続化 | HTMLでの採点状態・学習履歴のlocalStorage保存。v1は永続化なし | D-17 |
| V2-02 | 二重レビュー | 複数レビュアー（クロスモデルを含む）による多重検証。v1は1問1独立レビュー | D-15 |
| V2-03 | 中断セットの再開機能 | 中断したセットの途中再開。v1は中断セット=未完成（監査のみ残る）とし、新規セットとしてやり直す | D-20 |
| V2-04 | TreeTagger正規表現による機械照合 | 文法対象構造の実現をITEM LISTの正規表現で機械照合すること。v1はLLMレビューがパターン略記を根拠に照合 | D-12 |
| V2-05 | 語彙問題への解説拡張 | 語彙4形式への解説付与。v1は文法5形式のみ解説必須 | D-24 |
| V2-06 | 混在セット | 単一セット内での形式・レベルの混在。v1は複数セットの合成で対応 | D-04 |
| V2-07 | Pre-A1 / C1以上への対応 | A1未満・B2超レベルの作問・検証。原本（Wordlist 4段階・教員版A1.1〜B2.2）が根拠を提供しないため対応しない | D-03 |
| V2-08 | レビューによる機械検査上書き | LLMレビューが機械検査違反を合格に覆すこと。v2でも実装予定はなく恒久的スコープ外。機械検査の誤検出は報告様式（`docs/subagent-review-spec.md`）と運用修正で扱う | D-07 |
| V2-09 | HTMLダークモード対応 | `prefers-color-scheme` による配色切替。v1はライト単一テーマ（`docs/html-output-spec.md` STY-01） | D-17 |

補足: V2-01〜V2-06 および V2-09 は将来のv2で検討する課題、V2-07〜V2-08 は原本の制約および検証アーキテクチャの原則による恒久的スコープ外である。

## 7. 前提環境

- **ENV-01 実行ホスト**: Claude Code または Codex（GPT-5.6 sol）が動作し、教師のアカウントで各ツールのLLMを利用できること（D-02, DD-09）。
- **ENV-02 Python**: Python 3.11以上がインストールされていること。決定的スクリプトはvenv内で実行する（D-09）。
- **ENV-03 spaCy**: spaCy と en_core_web_sm がセットアップスクリプトで導入されること。固定版依存パッケージとモデルの取得時にネットワーク接続を要する（D-09, NFR-04）。
- **ENV-04 OS**: macOS / Linux / Windowsホスト上のWSL2 Linux環境のいずれか。Windowsではリポジトリ、Python、Claude CodeまたはCodex、全作問コマンドをWSL2シェル内で実行しなければならない(MUST)。ネイティブPowerShell・コマンドプロンプトから作問フローを実行してはならない(MUST NOT)（NFR-06、M7D-11）。
- **ENV-05 リポジトリ**: 非公開リポジトリのクローンを保持し、git pull が実行できること。原本xlsxは `data/source/` に配置済みであること（P-01, D-23）。
- **ENV-06 ブラウザ（生徒側）**: 生成HTMLは配布時点で追加インストールなしにモダンブラウザ（PC・スマートフォン）で動作すること。ブラウザ要件の正: `docs/html-output-spec.md`。
- **ENV-07 セットアップ手順書**: 両ツール向けセットアップ手順書（実装物）に従い、`doctor.py` が全項目正常を報告する状態で利用を開始すること（D-02, FR-34）。手順書の要件定義の正: `docs/cross-agent-compatibility.md`。
