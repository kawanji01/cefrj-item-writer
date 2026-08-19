# M7 コードレビュー R1 対応記録

- R1-01: 承認済みM7D-06として専用`CODEX_HOME`を分離認証し、ユーザー設定・ルール・プロジェクト指示を無効化した固定コマンドへ更新して、実効入力から個人・プロジェクト由来コンテキストが0件であることと実レビューのスキーマ適合を確認した (`DECISIONS.md`, `docs/subagent-review-spec.md`, `docs/cross-agent-compatibility.md`, `AGENTS.md`, `docs/setup-codex.md`, `IMPLEMENTATION_PLAN.md`)
- R1-02: CLIの包括的な末尾ワイルドカード許可を標準引数形へ限定し、Claude CodeのBashサンドボックスをfail-closedで強制して、正常コマンドの許可、`--out-dir`/`--out`による外部出力の実行前拒否、シンボリックリンク経由の外部書込み拒否を`dontAsk`で確認した (`.claude/settings.json`)
- R1-03: 汎用`finalize_set.py`許可を削除し、専用FIN01許可とPreToolUseガードで引用付きヒアドキュメントの固定3行形式だけを許可して、正常確定とsetスキーマ適合、ファイルstdin・非`output/`・コマンド置換・追加コマンドの実行前拒否を`dontAsk`で確認した (`.claude/settings.json`, `.claude/hooks/guard_finalize.py`)
- R1-04: 承認済みM7D-07としてネットワーク例外を固定版依存パッケージとspaCyモデルを取得するセットアップ処理だけに統一し、セットアップ完了後の決定的CLIは完全オフラインであることを要件・設計・両手順書・READMEへ反映した (`DECISIONS.md`, `docs/requirements.md`, `docs/architecture.md`, `docs/cross-agent-compatibility.md`, `docs/setup-claude-code.md`, `docs/setup-codex.md`, `README.md`)
- R1-05: 承認済みM7D-08としてWordlistとGrammar Profileの確認済み利用条件を分離し、Grammar Profileの商用利用・改変・派生データ作成・再配布は明示的な許諾範囲を確認するまで許容済みと案内しない保守的な境界へ改訂した (`DECISIONS.md`, `docs/requirements.md`, `docs/architecture.md`, `NOTICE`, `README.md`)
- R1-06: Codex CLIの更新コマンド`codex update`と、終了コード0・版表示・独立レビュー必須フラグ表示までの成功条件をトラブルシュートへ明記した (`docs/setup-codex.md`)
- R1-07: R1-01対応でAD-28の既定コマンド自体を専用`CODEX_HOME`・コンテキスト分離フラグ・`--ephemeral`を含む現行値へ置換し、旧値との併存を解消した (`DECISIONS.md`)
