# docs/cross-agent-compatibility.md — Claude Code / Codex 互換仕様

| 項目 | 内容 |
|---|---|
| 目的 | 同一の作問エージェントを Claude Code と Codex の両ツールで同一の手順・契約で動作させるための構造（共通コア＋アダプタ）、両ツールの配線仕様、互換性保証範囲、互換テスト、セットアップ手順書の要件を定める。 |
| 対象読者 | 実装者（Codex GPT-5.6 sol）、両ツールで本エージェントを運用する教師、受け入れ実施者。 |
| 参照文書 | `docs/architecture.md`（コンポーネント・CLI契約・エラーコード目録の正）、`docs/requirements.md`（スコープ外/v2リストの正）、`docs/interaction-flow.md`、`docs/question-generation-spec.md`、`docs/subagent-review-spec.md`（レビュアー契約・入力封筒・監査配置の正）、`docs/json-output-spec.md`、`docs/testing-and-acceptance.md`、`DECISIONS.md` |
| 規範語彙凡例 | 「しなければならない(MUST)」=絶対要件。「してはならない(MUST NOT)」=絶対禁止。「すべきである(SHOULD)」=正当な理由がない限り従う。「してもよい(MAY)」=任意。 |
| この文書が「正」とする範囲 | ①コア/アダプタ分離の規則、②Claude Code配線（CLAUDE.md・Skill定義・`.claude/agents/` レビュアー定義・権限設定の要件）、③Codex配線（AGENTS.md・`.codex/run_reviewer.py`・`codex exec` 固定argv仕様）、④互換性保証範囲、⑤互換テスト、⑥セットアップ手順書（両ツール版）の要件定義。コア指示書の内容（対話手順・生成制約・レビュアー契約）は本書の正ではなく、各担当文書を参照する。 |

---

## 1. コア/アダプタ構造

- **COR-01** 挙動規則は次の2箇所にのみ置かなければならない(MUST)。
  1. 共通コア指示書: `agent/author-core.md`（作問エージェント指示書。内容要件の正は `docs/interaction-flow.md` と `docs/question-generation-spec.md`）、`agent/reviewer-core.md`（レビュアー指示書。内容要件の正は `docs/subagent-review-spec.md`）。
  2. 決定的スクリプト: `scripts/` のCLI 8本（契約の正は `docs/architecture.md` 第5節）。
- **COR-02** アダプタ（Claude Code: `CLAUDE.md`・`.claude/` 配下、Codex: `AGENTS.md`・`.codex/` 配下）は配線のみとし、次を書いてはならない(MUST NOT): 数値制約（語数上限・問題数・世代数）、検証項目・判定規則、対話の質問文テンプレート、生成制約、エラー文言、レベル体系の解釈規則。アダプタに書いてよい(MAY)のは、コア指示書の読込指示・CLI実行の配線・レビュアー起動の配線・ツール固有の設定値のみである。
- **COR-03** 両アダプタは、同一の入力に対して同一のコア指示書と同一のCLIを同一の順序で使わなければならない(MUST)。ツール間で異なってよい(MAY)のは、レビュアーの起動機構（第3節・第4節）とツール固有の設定形式のみである。
- **COR-04** 挙動を変更する場合はコア指示書または決定的スクリプト（と対応する設計文書）を変更しなければならず(MUST)、アダプタ側で挙動差を作ってはならない(MUST NOT)。
- **COR-05** レビュアーの独立性（生成側会話履歴の不可視、入力を候補問題JSON・機械検査レポート・検証仕様・正規化データへの読み取り専用アクセスに限定）は両ツールで同一に成立させなければならない(MUST)。独立性要件の正は `docs/subagent-review-spec.md`。

## 2. レビュアー起動の共通契約（両アダプタ共通）

- **COR-06** レビュアー起動は「1問1独立レビュー・再生成のたび新実行・文脈持ち越しなし」でなければならない(MUST)。両アダプタとも、起動ごとに新しい独立コンテキストを作る非対話サブプロセス（Claude Code=`.claude/run_reviewer.py`が監視する`claude -p`、Codex=`.codex/run_reviewer.py`が監視する`codex exec`）を使う。
- **COR-07** レビュアーへ渡す起動プロンプトは配線文のみで構成しなければならない(MUST)。含める要素は次の3つに限る: ①`agent/reviewer-core.md` を読みそれに完全に従う指示、②入力封筒（review_request 準拠JSON。ファイル名・保存位置の正は `docs/subagent-review-spec.md`）のファイルパス、③最終出力を review_result JSON本文のみとする指示。検証規則・チェック項目を起動プロンプトに書いてはならない(MUST NOT)。
- **COR-08** レビュアーの最終出力の取り込み手順は両ツール共通で次のとおりとする(MUST)。①最終メッセージの生出力をbytesまたはホスト文字列として取得 → ②テキスト全体をJSONとしてパースし、失敗した場合に限り最初のコードフェンス（```json または ``` で囲まれた区間）の内側をパースする → ③`python scripts/validate.py --schema review_result --file -` でスキーマと全string値・object keyのstrict UTF-8表現可能性を検証 → ④同じJSONをJS-01正準形へstrict UTF-8で直列化 → ⑤同じ正準バイト列だけを監査ファイル `review/<question_id>.<gen>.review.json` として保存（配置の正は `docs/subagent-review-spec.md`）。②〜④のいずれかに失敗した場合はインフラ障害（問題の不合格に数えない。同一requestで最大2回再実行→3回目失敗でセット中止）として扱う。invalid監査には、bytes取得済みなら`validation_failure`へ生出力全文と失敗段階の診断、文字列だけ取得してstrict UTF-8化不能なら`utf8_encode_failure`、出力なしなら`process_failure`を保存する。インフラ障害の判定・再実行・中止規則の正は `docs/subagent-review-spec.md`。
- **COR-09** レビュアー実行のタイムアウト値と超過時の扱いの正は `docs/subagent-review-spec.md` とする。両アダプタはその値をレビュアーのサブプロセス全体の壁時計待機に適用し、超過時は実行中のプロセスを停止しなければならない(MUST)。

## 3. Claude Code 配線

### 3.1 CLAUDE.md

- **CCW-01** `CLAUDE.md` は次の項目のみで構成しなければならない(MUST)。
  1. プロジェクトの1段落概要（何をするエージェントか）。
  2. 作問を開始する際は `agent/author-core.md` を読み、それに完全に従う旨の指示。
  3. レビューは必ず `python .claude/run_reviewer.py --request <入力封筒パス>` で新しい独立レビュアーを起動して行い、自分でレビュー判定をしてはならない旨の指示。
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
- **CCW-09** オーケストレータは、レビュー工程で`python .claude/run_reviewer.py --request output/<set_id>/review/<question_id>.<gen>.request.json`を実行しなければならない(MUST)。ラッパーは新規`claude -p`を`--safe-mode`、`--system-prompt-file agent/reviewer-core.md`、`--tools Read,Grep,Glob`、`--permission-mode dontAsk`、`--no-session-persistence`、`--no-chrome`、空の`--strict-mcp-config`で起動し、COR-07の3行だけをstdinへ渡す。生成側の会話内容・過去世代のレビュー内容、CLAUDE.md、ユーザー・プロジェクト設定、skills、plugins、MCPを子へ含めてはならない(MUST NOT)。レビュアーはBash・書込み・ネットワーク系ツールを持たない。Bashサンドボックスは子Claude実行基盤のモデル通信に必要な`api.anthropic.com`だけを許可し、この通信をレビュアーへ付与するネットワークツールとみなさない。他ドメインを許可してはならない(MUST NOT)（M7D-14）。ラッパーは検証済みでセッションスナップショットと一致する現在の`limits.json`から`review_timeout_seconds`を読み、子プロセスグループ全体へ壁時計期限を適用する。超過時は子を停止して非0終了し、INF-07へ返す。ラッパー自身は再実行・中止判定を行わない（M7D-13）。
- **CCW-10** ラッパーが終了コード0で返したstdoutの生テキストだけを最終メッセージとして COR-08 の手順で取り込む(MUST)。終了コード非0、空stdout、期限超過はインフラ障害として扱う。`.claude/settings.json`は固定requestパスのラッパー呼出しだけを許可し、PreToolUseガードがコマンド全文を検査しなければならない(MUST)。

### 3.4 権限設定

- **CCW-11** プロジェクト設定 `.claude/settings.json` の `permissions` は次の要件を満たさなければならない(MUST)。
  - allow: `scripts/` のCLI 8本（`doctor.py` / `build_normalized.py` / `machine_check.py` / `set_check.py` / `finalize_set.py` / `build_html.py` / `validate.py` / `lookup.py`）を `python` で実行するBashコマンド、およびリポジトリ配下のファイル読み取り・`output/` 配下への書き込み。
  - allow: M7D-12の`output/<set_id>/.staging/`固定一時名に対するcandidate/review_request検証と専用削除ヘルパー。candidateは`<question_id>.<gen>.candidate.raw<1|2>.json`、review_requestは`<question_id>.<gen>.request.raw.json`だけを許可し、PreToolUseガードが一時ファイルの新規作成時に既存名との衝突を拒否し、検証コマンドのschemaとパス種別の組合せ、削除コマンド全文を検査する。汎用削除、監査正本の削除、別名・追加引数・複合コマンドを許可してはならない(MUST NOT)。
  - allow: CCW-09の`python .claude/run_reviewer.py --request output/<set_id>/review/<question_id>.<gen>.request.json`だけを許可し、PreToolUseガードが固定相対パスとコマンド全文を検査する。追加引数、環境変数代入、リダイレクト、パイプ、複合コマンドを許可してはならない(MUST NOT)。
  - allow: Bashサンドボックスの`network.allowedDomains`は`api.anthropic.com`だけとし、固定レビュアー子プロセスのモデルAPI通信に使う。他ドメイン、ワイルドカード、汎用ネットワークコマンドを許可してはならない(MUST NOT)（M7D-14）。
  - allow: `finalize_set.py`に限り、`output/`配下のset-dirを指定し、区切り語を単引用符で囲んだ`FIN01`ヒアドキュメントから必須のFIN-01 JSONをstdinへ渡す専用Bashコマンド。パイプ、中間メタデータファイル、コマンド置換、区切り語後の追加コマンドを許可してはならない(MUST NOT)。
  - allow: `validate.py --schema review_result --file -`に限り、区切り語を単引用符で囲んだ`REV01`ヒアドキュメントからCOR-08のreview_result JSONをstdinへ渡す専用Bashコマンド。権限ルールは固定validateコマンドの接頭辞だけを許可し、PreToolUseガードが固定先頭行・終端区切り、本文がJSON object 1個であることをコマンド全文で検査する。パイプ、シェルが解釈する位置のコマンド置換、区切り語後の追加コマンドを許可してはならない(MUST NOT)（M7D-10）。単引用符付きヒアドキュメント本文中の文字列はシェル展開されず、review_resultの非改変データとして扱う。
  - allow: S80開始時の識別子生成に限り、タイムゾーン付きローカル日時を秒精度で1回取得し、同じ日時から`created_at`と`set_id`を生成し、既存`output/<set_id>`との衝突時は同じ日時のまま4文字接尾辞だけを再生成する、`.claude/settings.json`記載の引数なし固定`python -c`コマンド。許可ルールはコマンド全文の完全一致とし、ワイルドカード、追加引数、標準入力、ファイル書込み、ネットワークアクセスを許可してはならない(MUST NOT)。
  - deny: WebFetch・WebSearch を含むネットワークアクセス系ツール（決定的処理の完全オフライン要件。`docs/architecture.md` ARC-05）。
- **CCW-12** 権限設定はセッション中の追加確認なしに標準フロー（対話→生成→一時保存での受理検証→監査保存→機械検査→期限付き独立レビュー→確定→HTML）を完走できる範囲とすべきであり(SHOULD)、リポジトリ外への書き込み許可を含めてはならない(MUST NOT)。完成セットでは`.staging/`が存在しないか空でなければならない(MUST)。セットアップ処理外の決定的CLIは完全オフラインとし、M7D-14のモデルAPI通信を決定的CLIの通信許可へ流用してはならない(MUST NOT)。

## 4. Codex 配線

### 4.1 AGENTS.md

- **CDX-01** `AGENTS.md` は CCW-01 と同じ5項目構成としなければならない(MUST)。ただし第3項は「レビューは必ず第4.2節の固定`.codex/run_reviewer.py`呼出しで監視付き独立サブプロセスとして実行し、自分でレビュー判定をしてはならない」と読み替える。
- **CDX-02** AGENTS.md に COR-02 の禁止対象を書いてはならない(MUST NOT)。

### 4.2 Codex監視ラッパーとcodex exec固定argv仕様

- **CDX-03** 作問側Codexは`codex --sandbox workspace-write --ask-for-approval on-request`で起動しなければならない(MUST)。レビュー1実行では、次の固定ラッパー呼出しを実行するホスト側シェル呼出しだけを親サンドボックス外で申請し、教師の個別承認を得なければならない(MUST)。`<入力封筒パス>`はCOR-07の現在のrequest監査パスへ置換する。追加引数、環境変数代入、リダイレクト、パイプ、複合コマンドを加えた呼出し、別コマンド、または作問側全体のサンドボックス緩和へ承認を広げてはならない(MUST NOT)。

  ```text
  python .codex/run_reviewer.py --request <入力封筒パス>
  ```

  ラッパーは、固定監査名に一致する通常ファイルのrequest 1件だけを受理し、検証済みでセッション設定スナップショットと一致する現在の`limits.json`から`review_timeout_seconds`を読む。次の固定argvをシェル不使用で構築し、COR-07の3行をstdinへ渡して、新しいプロセスグループで1回だけ起動しなければならない(MUST)。`<repo>`、`<codex>`、`<codex-last>`はラッパーが固定規則で解決・導出し、呼出し側から指定させてはならない(MUST NOT)。

  ```text
  CODEX_HOME="${HOME}/.codex-cefrj-reviewer" <codex> exec \
    --ignore-user-config \
    --ignore-rules \
    --disable recommended_plugins \
    --disable apps \
    --disable plugins \
    --disable workspace_dependencies \
    -c project_doc_max_bytes=0 \
    -c include_environment_context=false \
    --ephemeral \
    --cd "<repo>" \
    --sandbox read-only \
    --skip-git-repo-check \
    --output-last-message "<codex-last>" \
    -
  ```

  - `CODEX_HOME="${HOME}/.codex-cefrj-reviewer"`: 作問側と別に認証した専用ホームをラッパーが子環境へ設定する。このホームには認証情報とCodexが生成する実行基盤ファイル以外のユーザー設定・ルール・個人スキル・プラグイン・メモリを置かない。
  - `--ignore-user-config` / `--ignore-rules`: 専用ホームのユーザー設定と、ユーザー・プロジェクトのexecpolicyルールを読み込まない。
  - `--disable recommended_plugins` / `apps` / `plugins` / `workspace_dependencies`: プラットフォームの推奨プラグイン、アプリ、プラグイン、workspace依存コンテキストをレビュアーへ注入しない。
  - `-c project_doc_max_bytes=0` / `-c include_environment_context=false`: `AGENTS.md`等のプロジェクト指示と`environment_context`をuserメッセージへ注入しない。
  - `--ephemeral`: 起動ごとに新しい独立コンテキストを作り、レビュアーのセッション状態を永続化しない。
  - `--cd <repo>` / `--sandbox read-only`: 作業ディレクトリをリポジトリルートに固定し、レビュアーに書込みを許可しない（COR-05）。
  - `--skip-git-repo-check`: git管理状態に依存せず起動可能にする。
  - `--output-last-message <codex-last>`: requestパスからCDX-06の固定名へ導出した作業ファイルに最終メッセージを書き出す。ラッパーは既存の同名作業ファイルだけを起動前に削除してよく(MAY)、成功時に通常ファイル・非シンボリックリンク・非空を確認して生バイト列をstdoutへ移し、処理後に同作業ファイルを削除してよい(MAY)。
  - 末尾の`-`: ラッパーがCOR-07の3行をstdinから渡す。
  - ラッパーは子プロセス全体を壁時計で待機し、`review_timeout_seconds`超過時はプロセスグループへTERM、猶予後も残る場合はKILLを送り、終了コード124で停止しなければならない(MUST)。ラッパー自身は再実行・監査保存・セット中止判定を行ってはならない(MUST NOT)（M7D-16）。
- **CDX-04** モデル指定オプション（`-m` / `--model`）を付けてはならない(MUST NOT)。レビュアーモデルはホストツールの既定モデル（Codex=GPT-5.6 sol）とする（`DECISIONS.md` の派生既定値）。
- **CDX-05** ラッパーがstdinへ渡す起動プロンプトの内容は COR-07 の3要素のみとし、次のテンプレートに従わなければならない(MUST)（`<入力封筒パス>` は実際のパスに置換する。封筒のファイル名・位置の正は `docs/subagent-review-spec.md`）。

  ```
  agent/reviewer-core.md を読み、その指示に完全に従ってください。
  入力封筒: <入力封筒パス>
  最終メッセージは review_result JSON 本文のみとし、JSON以外の文章を出力しないでください。
  ```

- **CDX-06** 起動プロンプトファイルと `--output-last-message` の出力ファイルは、`output/<set_id>/review/` 配下に `<question_id>.<gen>.codex-prompt.txt` / `<question_id>.<gen>.codex-last.txt` の名で置いてもよい(MAY)。標準ラッパーはプロンプトをstdinから渡し、後者だけをrequest名から導出して一時使用する。これらはCodexアダプタ固有の作業ファイルであり、監査正本（candidate / machine / request / review の4種。`docs/subagent-review-spec.md`）ではない。削除してもよい(MAY)が、監査正本を削除してはならない(MUST NOT)。
- **CDX-07** ラッパーまたは子`codex exec`の終了コードが非0の場合、期限超過の場合、および `--output-last-message` の作業ファイルが生成されない・通常ファイルでない・シンボリックリンクである・空である場合は、インフラ障害（COR-08 参照）として扱わなければならない(MUST)。
- **CDX-08** ラッパーが終了コード0で返したstdoutの生テキストだけを COR-08 の手順で取り込む(MUST)。
- **CDX-09** サブプロセス起動時に、生成側セッションの会話履歴・追加の環境変数・ユーザーまたはプロジェクト由来の指示、設定、ルール、スキル、プラグイン、メモリを渡してはならない(MUST NOT)。Codexが不可避に付与する固定system/developer/tool定義と組み込みsystem skill catalogは実行基盤であり、この禁止対象から除外する。`--disable recommended_plugins` / `apps` / `plugins` / `workspace_dependencies`と`-c include_environment_context=false`を省略してはならず(MUST NOT)、実効入力のuserメッセージはCOR-07の3行1件だけでなければならない(MUST)。レビュアーがリポジトリから読めるのは、read-onlyサンドボックス下のCCW-08②と同じ列挙対象のみである（reviewer-core.md が読み取り許可対象を定める。正は `docs/subagent-review-spec.md`）。
- **CDX-10** `codex` コマンドがPATH上に存在することは doctor.py の診断項目D12（`docs/architecture.md` CLI-10）で検出する。セットアップ手順書（第7節）は `codex --help`、`codex exec --help`、`python .codex/run_reviewer.py --help` の実行確認を含め、親起動の`--sandbox workspace-write` / `--ask-for-approval on-request`と、ラッパーが構築する子起動の`--ignore-user-config` / `--ignore-rules` / `--disable recommended_plugins` / `apps` / `plugins` / `workspace_dependencies` / `-c project_doc_max_bytes=0` / `-c include_environment_context=false` / `--ephemeral` / `--cd` / `--sandbox read-only` / `--skip-git-repo-check` / `--output-last-message`が受理されることを確認しなければならない(MUST)。専用`CODEX_HOME`を作問側とは別に認証し、同じコンテキスト無効化設定を付けた`codex debug prompt-input`のJSONを機械検査して、`role="user"`メッセージがちょうど1件、その`content`がCOR-07の3行だけを持つ`input_text` 1件と完全一致することを確認しなければならない(MUST)。不一致時はレビューを起動せずfail-closedとする。インストールされたCodexの版でこれらのオプションが受理されない場合は、セットアップ手順書のトラブルシュートに従いCodexを更新する。

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
  1. 前提環境: 対応OS（macOS / Linux / Windowsホスト上のWSL2 Linux環境。ネイティブPowerShell・コマンドプロンプトは対象外）、Python 3.11+、git、対象ツール本体（インストールと認証はツール公式手順への参照とする）。Windowsではリポジトリ、Python、対象ツール、全作問コマンドをWSL2シェル内で実行する（M7D-11）。
  2. リポジトリ取得: 非公開リポジトリのclone手順（アクセス権の入手先を含む）。
  3. Python環境構築: `python scripts/setup.py` による `.venv` 作成と、パッケージインデックスからの `requirements.txt` 固定版依存取得・導入。この依存取得がセットアップ処理に限定したネットワーク許可範囲であることの明示。
  4. spaCyモデル取得: en_core_web_sm の取得。前項の依存取得と本モデル取得を行うセットアップ処理だけがネットワーク許可範囲であり、完了後の決定的CLIは完全オフラインであることの明示（`docs/architecture.md` ARC-05）。
  5. 診断: `python scripts/doctor.py` の実行と全項目passの確認。fail時はエラーコード目録（`docs/architecture.md` 第6節）の remedy に従う旨。
  6. ツール固有設定: Claude Code版=`.claude/` 配下の配線確認と権限設定（第3節）、Codex版=`codex --help` / `codex exec --help` / `python .codex/run_reviewer.py --help` の実行確認、専用`CODEX_HOME`の分離認証、`codex debug prompt-input`による入力分離確認、親起動・固定ラッパー実行の個別承認と壁時計停止の確認（CDX-03/CDX-10）、AGENTS.md配線確認（第4節）。
  7. LLM送信の明示: 生成・レビュー時に正規化データ抜粋と問題文がAnthropic（Claude Code利用時）またはOpenAI（Codex利用時）に送信されることの説明（`DECISIONS.md` D-22）。
  8. 初回作問チュートリアル: 語彙4択（`vocab_mcq_en2ja`）A1・3問の1セットを対話開始から `index.html` 確認まで通す手順。
  9. 更新手順: `git pull` → `python scripts/doctor.py`（`docs/architecture.md` OPS-04 参照）。
  10. トラブルシュート: エラーコード4系列（E-ENV / E-DATA / E-CONTRACT / E-INPUT）の見方と、`docs/architecture.md` 第6節への参照。Codex版はCodex更新手順（CDX-10）を含める。
  11. 免責: 生成問題の教育利用の最終確認は教師の責任である旨（`DECISIONS.md` D-22）。
- **SUP-03** 手順書は完全日本語とし(MUST)、各手順に実行するコマンド文字列と成功時の期待出力を明記しなければならない(MUST)。
- **SUP-04** 手順書に挙動規則（COR-02 の禁止対象）を書いてはならない(MUST NOT)。

## 8. スコープ外

二重レビュー（将来オプション）・処理再開を含むv2課題の正は `docs/requirements.md` のスコープ外/v2リストであり、本書では定義しない。
