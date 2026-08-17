# docs/cross-agent-compatibility.md — Claude Code / Codex 互換仕様

| 項目 | 内容 |
|---|---|
| 目的 | 同一の作問エージェントを Claude Code と Codex の両ツールで同一の手順・契約で動作させるための構造（共通コア＋アダプタ）、両ツールの配線仕様、互換性保証範囲、互換テスト、セットアップ手順書の要件を定める。 |
| 対象読者 | 実装者（Codex GPT-5.6 sol）、両ツールで本エージェントを運用する教師、受け入れ実施者。 |
| 参照文書 | `docs/architecture.md`（コンポーネント・CLI契約・エラーコード目録の正）、`docs/requirements.md`（スコープ外/v2リストの正）、`docs/interaction-flow.md`、`docs/question-generation-spec.md`、`docs/subagent-review-spec.md`（レビュアー契約・入力封筒・監査配置の正）、`docs/json-output-spec.md`、`docs/testing-and-acceptance.md`、`DECISIONS.md` |
| 規範語彙凡例 | 「しなければならない(MUST)」=絶対要件。「してはならない(MUST NOT)」=絶対禁止。「すべきである(SHOULD)」=正当な理由がない限り従う。「してもよい(MAY)」=任意。 |
| この文書が「正」とする範囲 | ①コア/アダプタ分離の規則、②Claude Code配線（CLAUDE.md・Skill定義・`.claude/agents/` レビュアー定義・権限設定の要件）、③Codex配線（AGENTS.md・`codex exec` 起動コマンドライン仕様）、④互換性保証範囲、⑤互換テスト、⑥セットアップ手順書（両ツール版）の要件定義。コア指示書の内容（対話手順・生成制約・レビュアー契約）は本書の正ではなく、各担当文書を参照する。 |

---

## 1. コア/アダプタ構造

- **COR-01** 挙動規則は次の2箇所にのみ置かなければならない(MUST)。
  1. 共通コア指示書: `agent/author-core.md`（作問エージェント指示書。内容要件の正は `docs/interaction-flow.md` と `docs/question-generation-spec.md`）、`agent/reviewer-core.md`（レビュアー指示書。内容要件の正は `docs/subagent-review-spec.md`）。
  2. 決定的スクリプト: `scripts/` のCLI 8本（契約の正は `docs/architecture.md` 第5節）。
- **COR-02** アダプタ（Claude Code: `CLAUDE.md`・`.claude/` 配下、Codex: `AGENTS.md`）は配線のみとし、次を書いてはならない(MUST NOT): 数値制約（語数上限・問題数・世代数）、検証項目・判定規則、対話の質問文テンプレート、生成制約、エラー文言、レベル体系の解釈規則。アダプタに書いてよい(MAY)のは、コア指示書の読込指示・CLI実行の配線・レビュアー起動の配線・ツール固有の設定値のみである。
- **COR-03** 両アダプタは、同一の入力に対して同一のコア指示書と同一のCLIを同一の順序で使わなければならない(MUST)。ツール間で異なってよい(MAY)のは、レビュアーの起動機構（第3節・第4節）とツール固有の設定形式のみである。
- **COR-04** 挙動を変更する場合はコア指示書または決定的スクリプト（と対応する設計文書）を変更しなければならず(MUST)、アダプタ側で挙動差を作ってはならない(MUST NOT)。
- **COR-05** レビュアーの独立性（生成側会話履歴の不可視、入力を候補問題JSON・機械検査レポート・検証仕様・正規化データへの読み取り専用アクセスに限定）は両ツールで同一に成立させなければならない(MUST)。独立性要件の正は `docs/subagent-review-spec.md`。

## 2. レビュアー起動の共通契約（両アダプタ共通）

- **COR-06** レビュアー起動は「1問1独立レビュー・再生成のたび新実行・文脈持ち越しなし」でなければならない(MUST)。両アダプタとも、起動ごとに新しい独立コンテキストを作る機構（Claude Code=サブエージェントのTask起動、Codex=`codex exec` 非対話サブプロセス）を使う。
- **COR-07** レビュアーへ渡す起動プロンプトは配線文のみで構成しなければならない(MUST)。含める要素は次の3つに限る: ①`agent/reviewer-core.md` を読みそれに完全に従う指示、②入力封筒（review_request 準拠JSON。ファイル名・保存位置の正は `docs/subagent-review-spec.md`）のファイルパス、③最終出力を review_result JSON本文のみとする指示。検証規則・チェック項目を起動プロンプトに書いてはならない(MUST NOT)。
- **COR-08** レビュアーの最終出力の取り込み手順は両ツール共通で次のとおりとする(MUST)。①最終メッセージの生出力をbytesまたはホスト文字列として取得 → ②テキスト全体をJSONとしてパースし、失敗した場合に限り最初のコードフェンス（```json または ``` で囲まれた区間）の内側をパースする → ③`python scripts/validate.py --schema review_result --file -` でスキーマと全string値・object keyのstrict UTF-8表現可能性を検証 → ④同じJSONをJS-01正準形へstrict UTF-8で直列化 → ⑤同じ正準バイト列だけを監査ファイル `review/<question_id>.<gen>.review.json` として保存（配置の正は `docs/subagent-review-spec.md`）。②〜④のいずれかに失敗した場合はインフラ障害（問題の不合格に数えない。同一requestで最大2回再実行→3回目失敗でセット中止）として扱う。invalid監査には、bytes取得済みなら`validation_failure`へ生出力全文と失敗段階の診断、文字列だけ取得してstrict UTF-8化不能なら`utf8_encode_failure`、出力なしなら`process_failure`を保存する。インフラ障害の判定・再実行・中止規則の正は `docs/subagent-review-spec.md`。
- **COR-09** レビュアー実行のタイムアウト値と超過時の扱いの正は `docs/subagent-review-spec.md` とする。両アダプタはその値を各起動機構（Taskの待機、サブプロセスの待機）に適用しなければならない(MUST)。

## 3. Claude Code 配線

### 3.1 CLAUDE.md

- **CCW-01** `CLAUDE.md` は次の項目のみで構成しなければならない(MUST)。
  1. プロジェクトの1段落概要（何をするエージェントか）。
  2. 作問を開始する際は `agent/author-core.md` を読み、それに完全に従う旨の指示。
  3. レビューは必ずサブエージェント `cefrj-reviewer` を Task で起動して行い、自分でレビュー判定をしてはならない旨の指示。
  4. 決定的処理は必ず `scripts/` のCLIで行い、CLIの結果（検査違反・エラーコード）をLLM判断で上書きしてはならない旨の指示。
  5. 本書 COR-02 の禁止事項（このファイルに挙動規則を追記しない）の注意書き。
- **CCW-02** CLAUDE.md に COR-02 の禁止対象（数値制約・検証規則・質問文テンプレート・生成制約・エラー文言・レベル解釈規則）を書いてはならない(MUST NOT)。

### 3.2 Skill 定義

- **CCW-03** 作問開始用のSkillを1つ定義しなければならない(MUST)。パスは `.claude/skills/cefrj-author/SKILL.md`、スキル名は `cefrj-author` とする。
- **CCW-04** SKILL.md のフロントマターは `name: cefrj-author` と、日本語の `description`（起動条件: 教師がCEFR-J準拠の問題作成・作問開始を求めたとき）を持たなければならない(MUST)。本文は「`agent/author-core.md` を読み、その対話フローの最初の質問から開始する」旨の配線文のみとする(MUST)。
- **CCW-05** SKILL.md 本文に対話フローの内容・質問文・制約を転記してはならない(MUST NOT)。

### 3.3 レビュアー・サブエージェント定義

- **CCW-06** レビュアー定義ファイルは `.claude/agents/cefrj-reviewer.md` としなければならない(MUST)（doctor.py の診断項目D12（`docs/architecture.md` CLI-10）はこのパスを検査する）。
- **CCW-07** フロントマターは次を満たさなければならない(MUST)。
  - `name: cefrj-reviewer`
  - `description`: 日本語。「生成済み候補問題のCEFR-J適合性を独立に厳格検証する専用レビュアー。作問オーケストレータがレビュー工程で必ず使用する」という役割と使用契機を含める。
  - `tools`: `Read, Grep, Glob` のみを許可する。Write・Edit・Bash・ネットワーク系ツールを許可してはならない(MUST NOT)（レビュアーは読み取り専用。出力は最終メッセージのJSONのみ）。
- **CCW-08** 定義ファイル本文は配線文のみとし(MUST)、次の3点で構成する: ①`agent/reviewer-core.md` を読みそれに完全に従う指示、②読み取りを許可する対象の列挙（入力封筒ファイル・`agent/reviewer-core.md`・`docs/cefrj-validation-spec.md`・`docs/subagent-review-spec.md`・`data/normalized/` 配下・`data/config/` 配下。これ以外のファイルを読んではならない旨）、③最終メッセージは review_result JSON本文のみとし、JSON以外の文章を出力しない指示。
- **CCW-09** オーケストレータは、レビュー工程で Task ツールにより `cefrj-reviewer` を起動し、プロンプトには COR-07 の3要素のみを渡さなければならない(MUST)。生成側の会話内容・過去世代のレビュー内容をプロンプトに含めてはならない(MUST NOT)（過去世代の指摘は入力封筒の中で渡す。封筒内容の正は `docs/subagent-review-spec.md`）。
- **CCW-10** サブエージェントの最終メッセージは COR-08 の手順で取り込む(MUST)。

### 3.4 権限設定

- **CCW-11** プロジェクト設定 `.claude/settings.json` の `permissions` は次の要件を満たさなければならない(MUST)。
  - allow: `scripts/` のCLI 8本（`doctor.py` / `build_normalized.py` / `machine_check.py` / `set_check.py` / `finalize_set.py` / `build_html.py` / `validate.py` / `lookup.py`）を `python` で実行するBashコマンド、およびリポジトリ配下のファイル読み取り・`output/` 配下への書き込み。
  - deny: WebFetch・WebSearch を含むネットワークアクセス系ツール（決定的処理の完全オフライン要件。`docs/architecture.md` ARC-05）。
- **CCW-12** 権限設定はセッション中の追加確認なしに標準フロー（対話→生成→機械検査→レビュー→確定→HTML）を完走できる範囲とすべきであり(SHOULD)、リポジトリ外への書き込み許可を含めてはならない(MUST NOT)。

## 4. Codex 配線

### 4.1 AGENTS.md

- **CDX-01** `AGENTS.md` は CCW-01 と同じ5項目構成としなければならない(MUST)。ただし第3項は「レビューは必ず第4.2節の `codex exec` 起動手順で独立サブプロセスとして実行し、自分でレビュー判定をしてはならない」と読み替える。
- **CDX-02** AGENTS.md に COR-02 の禁止対象を書いてはならない(MUST NOT)。

### 4.2 codex exec 起動コマンドライン仕様

- **CDX-03** レビュアー起動は非対話サブプロセスとして、次のコマンドラインで実行しなければならない(MUST)。

  ```
  codex exec \
    --cd "<リポジトリルートの絶対パス>" \
    --sandbox read-only \
    --skip-git-repo-check \
    --output-last-message "<最終メッセージ出力ファイルの絶対パス>" \
    - < "<起動プロンプトファイルのパス>"
  ```

  - `--cd`: 作業ディレクトリをリポジトリルートに固定する。
  - `--sandbox read-only`: レビュアーに書き込みを許可しない（読み取り専用アクセスの強制。COR-05）。
  - `--skip-git-repo-check`: git管理状態に依存せず起動可能にする。
  - `--output-last-message`: レビュアーの最終メッセージをファイルに書き出させ、COR-08 の①のテキスト取得に使う。
  - 末尾の `-` と標準入力リダイレクト: 起動プロンプトをstdinから渡す。
- **CDX-04** モデル指定オプション（`-m` / `--model`）を付けてはならない(MUST NOT)。レビュアーモデルはホストツールの既定モデル（Codex=GPT-5.6 sol）とする（`DECISIONS.md` の派生既定値）。
- **CDX-05** 起動プロンプトファイルの内容は COR-07 の3要素のみとし、次のテンプレートに従わなければならない(MUST)（`<入力封筒パス>` は実際のパスに置換する。封筒のファイル名・位置の正は `docs/subagent-review-spec.md`）。

  ```
  agent/reviewer-core.md を読み、その指示に完全に従ってください。
  入力封筒: <入力封筒パス>
  最終メッセージは review_result JSON 本文のみとし、JSON以外の文章を出力しないでください。
  ```

- **CDX-06** 起動プロンプトファイルと `--output-last-message` の出力ファイルは、`output/<set_id>/review/` 配下に `<question_id>.<gen>.codex-prompt.txt` / `<question_id>.<gen>.codex-last.txt` の名で置いてもよい(MAY)。これらはCodexアダプタ固有の作業ファイルであり、監査正本（candidate / machine / request / review の4種。`docs/subagent-review-spec.md`）ではない。削除してもよい(MAY)が、監査正本を削除してはならない(MUST NOT)。
- **CDX-07** サブプロセスの終了コードが非0の場合、および `--output-last-message` の出力ファイルが生成されない・空である場合は、インフラ障害（COR-08 参照）として扱わなければならない(MUST)。
- **CDX-08** 終了コード0の場合、出力ファイルのテキストを COR-08 の手順で取り込む(MUST)。
- **CDX-09** サブプロセス起動時に、生成側セッションの会話履歴・環境変数経由の追加コンテキストを渡してはならない(MUST NOT)。レビュアーが読めるのは、read-onlyサンドボックス下のリポジトリファイルのうち、CCW-08②と同じ列挙対象のみである（reviewer-core.md が読み取り許可対象を定める。正は `docs/subagent-review-spec.md`）。
- **CDX-10** `codex` コマンドがPATH上に存在することは doctor.py の診断項目D12（`docs/architecture.md` CLI-10）で検出する。セットアップ手順書（第7節）は `codex exec --help` の実行確認を含めなければならない(MUST)。インストールされたCodexの版で CDX-03 のオプションが受理されない場合は、セットアップ手順書のトラブルシュートに従いCodexを更新する。

## 5. 互換性保証範囲

- **GUA-01** 両ツール間で同一であることを保証する(MUST)のは次の4点である。
  1. 手順の同一性: 対話フローの状態・順序・確認事項（`agent/author-core.md` 経由。正は `docs/interaction-flow.md`）。
  2. 契約の同一性: CLI 8本の入出力契約・エラーコード・スキーマ（`docs/architecture.md`・`schemas/`）。
  3. 決定的処理の同一性: 同一入力に対するCLI出力のバイト一致（`docs/architecture.md` CLI-04 の正準形）。
  4. 監査・成果物配置の同一性: `output/<set_id>/` 配下のファイル構成と命名（Codexアダプタ固有の作業ファイル CDX-06 を除く）。
- **GUA-02** LLM出力の同一性（生成される問題文・訳・解説の文面、レビューの合否判断・指摘内容、所要時間）は保証範囲外であることを、成果物の利用者向け文書（README・セットアップ手順書）に明記しなければならない(MUST)。
- **GUA-03** レビュアーモデルはホストツールの既定モデル（Claude Code=Claude、Codex=GPT-5.6 sol）であり、ツール間でレビュー判断の傾向が異なりうる。この差は不合格方向の安全側にのみ現れることを設計上の前提とし、合格基準そのもの（検証マトリクス・機械検査）はツール非依存の共通仕様（`docs/cefrj-validation-spec.md`）に従う(MUST)。
- **GUA-04** 非機能の目標時間（10問セット30分以内）は参考値であり保証しない。ツール別の目標時間の記載の正は `docs/requirements.md` の非機能要件。

## 6. 互換テスト

- **CAT-01 決定的CLI一致テスト**: 同一フィクスチャ入力に対し、CLI 8本の出力（stdout JSONおよび生成ファイル）がバイト一致することを検証しなければならない(MUST)。ただし machine_report 系出力（`machine_check.py` / `set_check.py`）は、実行毎に変わる `generated_at` フィールドを除去した正準形で比較する（除外規定の正は `docs/testing-and-acceptance.md` CI-R-02）。このテストは決定的pytest CIに含め（テスト定義の正は `docs/testing-and-acceptance.md`）、さらに手動受け入れ時に Claude Code 環境と Codex 環境の両方で同一フィクスチャを実行し、出力のSHA-256が一致することを確認する。
- **CAT-02 アダプタ純度検査**: 手動受け入れチェックリストに、アダプタファイル（`CLAUDE.md`・`.claude/skills/cefrj-author/SKILL.md`・`.claude/agents/cefrj-reviewer.md`・`.claude/settings.json`・`AGENTS.md`）の目視検査を含めなければならない(MUST)。判定基準: COR-02 の禁止対象（数値制約・検証項目・判定規則・質問文テンプレート・生成制約・エラー文言・レベル解釈規則）の記載が1つでもあれば不合格。
- **CAT-03 両ツール完走テスト**: 手動受け入れで、両ツールそれぞれで実LLMによるセット作成を完走し、`set.json` がスキーマ検証を通過し、同一 `set.json` を両環境の build_html.py に与えた出力がバイト一致することを確認しなければならない(MUST)。チェックリスト項目の正は `docs/testing-and-acceptance.md`。
- **CAT-04** 互換テストの合否条件は正しさ（一致・純度・完走）のみとし、実行時間を合否条件にしてはならない(MUST NOT)。

## 7. セットアップ手順書の要件定義

- **SUP-01** セットアップ手順書は2冊とし、`docs/setup-claude-code.md`（Claude Code版）と `docs/setup-codex.md`（Codex版）として実装時に作成しなければならない(MUST)（手順書自体は実装物であり、本書はその要件のみ定める）。
- **SUP-02** 両手順書は次の11項目をこの順で含まなければならない(MUST)。
  1. 前提環境: 対応OS（macOS / Linux / Windows）、Python 3.11+、git、対象ツール本体（インストールと認証はツール公式手順への参照とする）。
  2. リポジトリ取得: 非公開リポジトリのclone手順（アクセス権の入手先を含む）。
  3. Python環境構築: `python scripts/setup.py` による `.venv` 作成と `requirements.txt` の固定版依存導入。
  4. spaCyモデル取得: en_core_web_sm の取得。ここが唯一のネットワーク許可点であることの明示（`docs/architecture.md` ARC-05）。
  5. 診断: `python scripts/doctor.py` の実行と全項目passの確認。fail時はエラーコード目録（`docs/architecture.md` 第6節）の remedy に従う旨。
  6. ツール固有設定: Claude Code版=`.claude/` 配下の配線確認と権限設定（第3節）、Codex版=`codex exec --help` の実行確認（CDX-10）とAGENTS.md配線確認（第4節）。
  7. LLM送信の明示: 生成・レビュー時に正規化データ抜粋と問題文がAnthropic（Claude Code利用時）またはOpenAI（Codex利用時）に送信されることの説明（`DECISIONS.md` D-22）。
  8. 初回作問チュートリアル: 語彙4択（`vocab_mcq_en2ja`）A1・3問の1セットを対話開始から `index.html` 確認まで通す手順。
  9. 更新手順: `git pull` → `python scripts/doctor.py`（`docs/architecture.md` OPS-04 参照）。
  10. トラブルシュート: エラーコード4系列（E-ENV / E-DATA / E-CONTRACT / E-INPUT）の見方と、`docs/architecture.md` 第6節への参照。Codex版はCodex更新手順（CDX-10）を含める。
  11. 免責: 生成問題の教育利用の最終確認は教師の責任である旨（`DECISIONS.md` D-22）。
- **SUP-03** 手順書は完全日本語とし(MUST)、各手順に実行するコマンド文字列と成功時の期待出力を明記しなければならない(MUST)。
- **SUP-04** 手順書に挙動規則（COR-02 の禁止対象）を書いてはならない(MUST NOT)。

## 8. スコープ外

二重レビュー（将来オプション）・処理再開を含むv2課題の正は `docs/requirements.md` のスコープ外/v2リストであり、本書では定義しない。
