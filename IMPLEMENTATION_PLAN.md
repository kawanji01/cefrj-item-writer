# 実装計画（IMPLEMENTATION_PLAN.md）

## 冒頭ブロック

- **目的**: 設計成果物（`docs/` 10本・`schemas/` 9本・`DECISIONS.md`）を実装へ落とすためのマイルストーンM1〜M8を、実装担当（Codex GPT-5.6 sol）が追加判断なしで順に実行できる粒度で定義する。各マイルストーンの成果物・依存・完了条件(DoD)・参照文書、および未定義事項を発見した場合の行動規則を定める。
- **対象読者**: 実装担当（Codex GPT-5.6 sol）、進行を確認する作問者（教師）。
- **参照文書**: `DECISIONS.md`、`docs/requirements.md`、`docs/architecture.md`、`docs/interaction-flow.md`、`docs/question-generation-spec.md`、`docs/cefrj-validation-spec.md`、`docs/subagent-review-spec.md`、`docs/json-output-spec.md`、`docs/html-output-spec.md`、`docs/cross-agent-compatibility.md`、`docs/testing-and-acceptance.md`、`schemas/`（9本）。
- **規範語彙凡例**: 「しなければならない(MUST)」=絶対要件。「してはならない(MUST NOT)」=絶対禁止。「すべきである(SHOULD)」=正当な理由がない限り従う。「してもよい(MAY)」=任意。
- **この文書が「正」とする範囲**: 実装の順序・各マイルストーンの成果物一覧と完了条件・未定義事項発見時の行動規則。個々の挙動仕様の正は各設計文書であり、本文書は挙動仕様を定義しない。本文書と設計文書が食い違う場合は設計文書が正である（PLN-03）。

---

## 1. 総則

- **PLN-01**: マイルストーンはM1→M2→…→M8の順に実施しなければならない(MUST)。先行マイルストーンのDoDを全て充足するまで、後続マイルストーンの成果物をコミットしてはならない(MUST NOT)。
- **PLN-02**: 各マイルストーンの完了は、当該DoDの全項目を実際にコマンド実行・確認して判定しなければならない(MUST)。DoDに対応する確認結果（実行したコマンドと結果の要約）をコミットメッセージまたは `CHANGELOG.md` に記録する。
- **PLN-03**: 実装と設計文書が矛盾した場合、実装を設計文書に合わせて修正しなければならない(MUST)。設計文書同士が矛盾している場合、およびいずれの文書にも定義がない場合は、未定義事項としてPLN-05の手続きに従う。
- **PLN-04**: 実装担当は `docs/`・`schemas/`・`DECISIONS.md`・本文書を、PLN-05の手続きを経ずに変更してはならない(MUST NOT)。
- **PLN-05（未定義事項発見時の行動規則）**: 実装中に、実装上の判断を要するのに設計文書に定義がない事項（未定義事項）を発見した場合、次の手続きに従わなければならない(MUST)。
  1. 未定義事項を実装上の即席判断で埋めてはならない(MUST NOT)。「なんとなく自然な実装」で穴を埋めて黙って進むことを禁止する。
  2. 確定済み決定（`DECISIONS.md`）と矛盾しない最も保守的な既定案を1つ以上作成する。
  3. 次の様式で `DECISIONS.md` への追記提案を作問者に日本語で提示し、承認を待つ。
     - 【未定義事項】発見箇所（ファイル・節）/ 内容 / 影響範囲（影響するマイルストーンと文書）/ 保守的既定案 / 代替案（ある場合）/ 推奨案とその理由
  4. 承認された決定を `DECISIONS.md` に追記し、影響する設計文書の改訂が必要な場合はその改訂もあわせて行ってから、当該箇所を実装する。
  5. 未定義事項の影響を受けない箇所の作業は、承認待ちの間も継続してよい(MAY)。
- **PLN-06**: 各マイルストーン完了時に `CHANGELOG.md` へ記載し、コミットしなければならない(MUST)。
- **PLN-07**: 実装ランタイムはPython 3.11+・spaCy `en_core_web_sm`・Jinja2とし、決定的処理（正規化・機械検査・スキーマ検証・セット横断検査・確定・HTML生成）は全てPythonで実装しなければならない(MUST)。決定的スクリプトはセットアップ時のspaCyモデル取得を唯一の例外として完全オフラインで動作し、テレメトリを送信してはならない(MUST NOT)。
- **PLN-08**: 全CLIは `docs/architecture.md` のCLI契約一覧（引数・stdin/stdout・終了コード）とエラーコード目録に従い、実行前に前提条件を検査し、定義済みエラーコードと日本語対処手順で停止しなければならない(MUST)。

---

## 2. マイルストーン概観

| M | 名称 | 主な成果物 | 依存 |
|---|---|---|---|
| M1 | 正規化＋doctor | `build_normalized.py` / `doctor.py` / `data/normalized/` / `data/config/` 初版 / セットアップスクリプト | なし |
| M2 | 機械検査 | `machine_check.py` / `lookup.py` | M1 |
| M3 | スキーマ検証 | `validate.py` | M1 |
| M4 | 対話＋生成コア | `agent/author-core.md` / 対話・生成の配線（暫定） | M1〜M3 |
| M5 | レビューループ | `agent/reviewer-core.md` / `set_check.py` / `finalize_set.py` / 再生成ループ | M1〜M4 |
| M6 | HTML生成 | `build_html.py` / Jinja2テンプレート一式 | M3, M5 |
| M7 | アダプタ＋手順書＋NOTICE | `CLAUDE.md` / `.claude/` / `AGENTS.md` / セットアップ手順書 / `NOTICE` / README記載 | M1〜M6 |
| M8 | テスト＋受け入れ | `tests/` 一式 / CI設定 / 受け入れ実施記録 / タグ付きリリース | M1〜M7 |

---

## 3. M1: 正規化＋doctor

- **目的**: 原本xlsxから正規化データを決定的にビルドし、環境・データ整合の一括診断を可能にする。
- **成果物**:
  1. `scripts/build_normalized.py`（原本xlsx→`data/normalized/lexicon.json`・`grammar.json`・`meta.json`。新旧差分レポート機能を含む）
  2. `scripts/doctor.py`（環境・データ一括診断）
  3. セットアップスクリプト `scripts/setup.py` と `requirements.txt`（venv構築・固定版依存導入・spaCyモデル取得。`docs/architecture.md` の運用手順参照）
  4. `data/source/` への原本xlsx配置（`CEFR-J Wordlist Ver1.6.xlsx`・`CEFR-J Grammar Profile full 20200220.xlsx`）とSHA-256記録、および `data/source/sources.json`（原本の入手URL・ダウンロード日）の作成（`docs/architecture.md` OPS-01・E-DATA-01）
  5. ビルド済み `data/normalized/` 3ファイルのコミット（出典ヘッダー付き）
  6. `data/config/limits.json`・`data/config/proper_nouns.json` 初版（値の正は `docs/cefrj-validation-spec.md` と `docs/requirements.md`、固有名詞の選定基準は `docs/cefrj-validation-spec.md` の免除規則）
- **依存**: なし（設計成果物のみを前提とする）。
- **DoD**:
  1. `build_normalized.py` を2回実行し、3ファイルがそれぞれバイト一致する
  2. 3ファイルが `normalized_lexicon.schema.json`・`normalized_grammar.schema.json`（`meta.json` は `docs/cefrj-validation-spec.md` NRM-29 の定義）に適合する（この時点ではjsonschemaライブラリの直接呼び出しで検証してよい(MAY)。`validate.py` はM3）
  3. `docs/testing-and-acceptance.md` の CI-NRM-03 に列挙された件数不変条件（entries=7,988 / レベル別度数 / (headword,pos)ユニーク=7,988 / ALL行数=7,801 / 256 / 501 / 枝番親存在 / 未付与16件ID一致）を満たす
  4. 枝番のレベル継承・教員版範囲値の下限上限分解が `docs/cefrj-validation-spec.md` の正規化仕様どおりである（CI-NRM-05・CI-NRM-07の合否条件で確認）
  5. `doctor.py` が完全環境で終了コード0、原本改変・正規化欠落・config欠落の各模擬環境で `docs/architecture.md` の目録どおりの E-ENV / E-DATA 系コードで停止する（CI-NRM-06・CI-CLI-03の合否条件で確認）
  6. 差分レポートが「原本更新なし」の再ビルドで差分ゼロを報告する
- **参照文書**: `docs/cefrj-validation-spec.md`（正規化仕様の正）、`docs/architecture.md`（CLI契約・エラーコード・運用手順）、`docs/json-output-spec.md`（meta.json・data_version）、`schemas/normalized_lexicon.schema.json`・`schemas/normalized_grammar.schema.json`、`docs/testing-and-acceptance.md` 第2.2節。

## 4. M2: 機械検査

- **目的**: 候補問題JSONに対する決定的機械検査と、対話時の原本照合に使う照会CLIを実装する。
- **成果物**:
  1. `scripts/machine_check.py`（候補JSON＋正規化データ→machine_report。パイプライン各段・spaCy POS→pos15種対応表・照合順序・免除規則・違反判定は `docs/cefrj-validation-spec.md` の機械検査仕様が正）
  2. `scripts/lookup.py`（語彙・文法項目の照会。明示指定照合と提案候補提示の情報源）
- **依存**: M1（正規化データ）。
- **DoD**:
  1. `docs/testing-and-acceptance.md` の CI-MCH-01〜18 の入力条件を満たす手元フィクスチャに対し、各合否条件どおりの出力を返す（pytest化はM8。M2では手動実行で確認し結果を記録する）
  2. CI-LKP-01〜04 の合否条件どおりの出力を返す
  3. `machine_check.py` の出力が `machine_report.schema.json` に適合する（M2ではjsonschemaライブラリの直接呼び出しで確認し、`validate.py` 経由のCI-MCH-12はM3で再確認する）
  4. 同一入力2回で、実行日時フィールド（`docs/testing-and-acceptance.md` CI-R-02）を除きバイト一致する
- **参照文書**: `docs/cefrj-validation-spec.md`（機械検査仕様・検証マトリクスの正）、`docs/question-generation-spec.md`（候補フィールド）、`docs/interaction-flow.md`（照合フローが要求する `lookup.py` の出力内容）、`schemas/candidate.schema.json`・`schemas/machine_report.schema.json`、`docs/testing-and-acceptance.md` 第2.3〜2.4節。

## 5. M3: スキーマ検証

- **目的**: 9スキーマに対する統一検証CLIを実装し、以後の全マイルストーンの契約検証手段を確立する。
- **成果物**: `scripts/validate.py`（対象JSONとスキーマ名を受け、合否・違反パス・E-CONTRACT系コードを返す。未完成セット状態の識別を含む。契約は `docs/architecture.md` のCLI契約一覧が正）。
- **依存**: M1（開発環境。技術的依存は設計成果物のみ）。
- **DoD**:
  1. 9スキーマ全てがdraft 2020-12メタスキーマに適合する（不備を発見した場合はPLN-05の手続きでスキーマ改訂を提案する。無断修正禁止）
  2. CI-SCH-01〜05 の合否条件どおりに動作する（妥当例合格・不当例のコード付き不合格・format判別・ID書式）
  3. CI-CLI-01 の入力不正3種で定義済みコード・日本語対処手順・定義済み終了コードで停止する
  4. M2で直接検証したCI-MCH-12を`validate.py --schema machine_report`で再確認する
- **参照文書**: `schemas/`（9本）、`docs/json-output-spec.md`（フィールドの正）、`docs/architecture.md`（CLI契約・エラーコード）、`docs/testing-and-acceptance.md` 第2.5節。

## 6. M4: 対話＋生成コア

- **目的**: 教師との日本語対話で条件を確定し、スキーマ適合の候補問題を生成できる状態にする。
- **成果物**:
  1. `agent/author-core.md`（作問エージェント指示書。対話状態機械・明示照合/提案フロー・9形式の生成仕様・共通生成規則・生成プロンプト必須制約を、各設計文書を正として集約する。挙動規則の正本文書からの逸脱・追加をしてはならない(MUST NOT)）
  2. 対話→ `lookup.py` 照合→候補生成→ `machine_check.py` → 候補保存、までの暫定配線（正式なアダプタ配線はM7。M4ではいずれか一方のツールで動作すればよい(MAY)）
- **依存**: M1〜M3。
- **DoD**:
  1. 対話が `docs/interaction-flow.md` の状態機械（順序①〜⑦・1ターン1質問・入力検証・不正入力時の再質問文言）どおりに進む
  2. 明示指定のレベル不一致（`abandon` をA1で指定）と辞書外（`Tokyo`）で、その場で指摘し代替を促す（`docs/testing-and-acceptance.md` A-09・A-10の合否条件で確認）
  3. 9形式それぞれで候補が1問以上生成でき、全て `candidate.schema.json` に合格する
  4. 生成プロンプトに `docs/question-generation-spec.md` が列挙する必須制約（例文規則・誤答規則・日本語規則・解説規則・allowlist・選択肢順固定・トピック指定時の制約追加）が全て含まれている
  5. 文法問題のターゲットが教員版256項目に限定され、レベル未付与16項目の明示要求は理由を示して断る
- **参照文書**: `docs/interaction-flow.md`（対話の正）、`docs/question-generation-spec.md`（生成仕様の正）、`docs/cefrj-validation-spec.md`（レベル体系・スケール交差）、`docs/cross-agent-compatibility.md`（コア指示書の位置づけ）、`docs/testing-and-acceptance.md` 第5.3節 A-09・A-10。

## 7. M5: レビューループ

- **目的**: 独立レビュー・再生成・セット横断検査・原子的確定を実装し、対話開始からセット完成までを通す。
- **成果物**:
  1. `agent/reviewer-core.md`（レビュアー指示書。入力封筒・チェックリスト・level_source規則・独立性要件・機械検査誤検出疑い報告様式は `docs/subagent-review-spec.md` と `docs/cefrj-validation-spec.md` が正）
  2. レビュー起動の暫定配線（M4と同じツールでよい(MAY)。review_request組み立て・review_resultスキーマ検証を含む）
  3. 再生成ループ（世代管理 `gen1|gen2|gen3`・構造化指摘の受け渡し・提案モード補充・明示モード教師照会・インフラ障害処理）
  4. `scripts/set_check.py`（セット横断検査）
  5. `scripts/finalize_set.py`（原子的確定。`set.json` はセット完成時のみ書き込み）
  6. 監査ファイル出力（`review/<question_id>.<gen>.candidate.json` / `.machine.json` / `.review.json`）
- **依存**: M1〜M4。
- **DoD**:
  1. `docs/testing-and-acceptance.md` の RPL-01〜10 の各合否条件を、記録済みフィクスチャの手動投入で確認できる（リプレイ自動化はM8）
  2. レビュアーへの入力が候補問題JSON・機械検査レポート・検証仕様・正規化データへの読み取り専用アクセスのみであり、生成側の会話履歴が渡らない構成である（`docs/subagent-review-spec.md` の独立性要件）
  3. 機械検査 `fail` がレビューで覆らない
  4. CI-SET-01〜06 の合否条件どおりに動作する
  5. レビュー出力スキーマ不通過が問題の不合格に数えられず、最大2回再実行→失敗でセット中止となる
- **参照文書**: `docs/subagent-review-spec.md`（レビュアー契約・再生成ループ・監査配置の正）、`docs/cefrj-validation-spec.md`（検証マトリクス・level_source規則）、`docs/json-output-spec.md`（set.json・監査ファイル仕様）、`schemas/review_request.schema.json`・`schemas/review_result.schema.json`・`schemas/set.schema.json`、`docs/testing-and-acceptance.md` 第3節。

## 8. M6: HTML生成

- **目的**: 合格済み `set.json` から自己完結HTMLを決定的に生成する。
- **成果物**:
  1. `scripts/build_html.py`（入力は `set.json` のみ。Python＋Jinja2）
  2. Jinja2テンプレート一式（9形式のインタラクティブUI・共通レイアウト・フッター出典・印刷CSS。仕様の正は `docs/html-output-spec.md`）
- **依存**: M3（スキーマ検証）、M5（実セットの `set.json`）。
- **DoD**:
  1. CI-HTM-01〜06 の合否条件どおりに動作する（決定性・自己完結・選択肢順固定・メジャー不一致拒否・同値リスト埋め込み）
  2. M5で完成した実セットに対し、`docs/testing-and-acceptance.md` A-12（オフライン・375px）・A-13（印刷CSS）・A-14（出典表示）の合否条件を手動確認できる
  3. 9形式全てのHTMLが生成でき、形式別UI（4択即時正誤・フラッシュカードめくり＋自己採点＋サマリー・穴埋め判定・整序タップ順選択・解説開閉）が `docs/html-output-spec.md` のDOM構造・状態遷移・判定規則・文言どおりである
- **参照文書**: `docs/html-output-spec.md`（正）、`docs/json-output-spec.md`（入力フィールド）、`docs/testing-and-acceptance.md` 第2.7節・第5.3節 A-12〜A-14。

## 9. M7: アダプタ＋手順書＋NOTICE

- **目的**: Claude CodeとCodexの両方で同一のコア指示書・CLIが動く配線を完成し、教師向けの導入文書を整える。
- **成果物**:
  1. `CLAUDE.md`・`.claude/`（Skill定義・`.claude/agents/` のレビュアー定義・権限設定。要件の正は `docs/cross-agent-compatibility.md`）
  2. `AGENTS.md`（`codex exec` によるレビュアー起動手順を含むCodex配線）
  3. セットアップ手順書（Claude Code版・Codex版。`docs/cross-agent-compatibility.md` の要件定義に従う）
  4. `NOTICE`（出典・ライセンス条件・再配布注意。`docs/architecture.md` と `docs/requirements.md` の該当要件に従う）
  5. READMEへの記載: LLM送信の明示（生成・レビュー時に正規化データ抜粋や問題文がAnthropic/OpenAIに送信される）と、生成問題の教育利用の最終確認は教師の責任である旨の免責
  6. `CHANGELOG.md` の整備
- **依存**: M1〜M6。
- **DoD**:
  1. アダプタ（`CLAUDE.md`・`.claude/`・`AGENTS.md`）に挙動規則が一切書かれておらず、配線（起動・権限・参照）のみである
  2. 両ツールそれぞれで1セット（`grammar_mcq`・2問）を完走できる
  3. 両ツールの環境で `machine_check.py` の互換用フィクスチャ出力がバイト一致する（CI-CLI-02の合否条件）
  4. クリーンな環境でセットアップ手順書のみに従って構築→`doctor.py` 終了コード0に到達できる
- **参照文書**: `docs/cross-agent-compatibility.md`（正）、`docs/architecture.md`（運用手順）、`docs/testing-and-acceptance.md` 第5.3節 A-01・A-15。

## 10. M8: テスト＋受け入れ

- **目的**: 3層テストを実装・実施し、タグ付きリリースを行う。
- **成果物**:
  1. `tests/unit/`（第1層: CI-NRM / CI-MCH / CI-LKP / CI-SCH / CI-SET / CI-HTM / CI-CLI / CI-FIX の全テストID）
  2. `tests/replay/`（第2層: リプレイハーネスと RPL-01〜10）
  3. `tests/golden/`・`tests/fixtures/`（ゴールデン・フィクスチャ一式。様式と `index.json` は `docs/testing-and-acceptance.md` 第4節）
  4. CI設定（マージ条件として `pytest tests/unit tests/replay` を実行）
  5. 手動受け入れの実施と記録（`tests/acceptance/records/<リリースタグ>.md`）
  6. タグ付きリリース
- **依存**: M1〜M7。
- **DoD**:
  1. `docs/testing-and-acceptance.md` 第2節・第3節の全テストIDが実装され、`pytest tests/unit tests/replay` が全通過する
  2. `tests/golden/cases/` の2ゴールデンケース候補が同文書4.4節の要件（スキーマ合格・機械検査通過・内容条件）を満たす
  3. 手動受け入れ A-01〜A-15 が全項目passし、記録が保存されている
  4. タグ付きリリースが作成され、`CHANGELOG.md` に記載されている
  5. 教師の更新手順（`git pull` → `doctor.py`）が更新後の環境で成功する
- **参照文書**: `docs/testing-and-acceptance.md`（正）、`docs/architecture.md`（リリース手順）。

---

## 11. プロジェクト完了の定義

M8のDoD全充足をもってプロジェクト完了とする。完了時点で次が成立していなければならない(MUST): 第1層・第2層の全テスト通過 / 手動受け入れ全15項目pass / 両ツールでのセット完走実績 / タグ付きリリースと `CHANGELOG.md` / 未解決の未定義事項（PLN-05の承認待ち）がゼロ。
