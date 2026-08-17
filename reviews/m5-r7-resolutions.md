# M5 R7 対応記録

- R7-01: `--requested-count N`から試行ID上限`min(2N,20)`を導出し、補充・代替IDを条件一致として受理する仕様・実装・回帰条件へ統一した。 (`DECISIONS.md`, `docs/architecture.md`, `docs/question-generation-spec.md`, `docs/cefrj-validation-spec.md`, `docs/testing-and-acceptance.md`, `agent/author-core.md`, `scripts/machine_check.py`)
- R7-02: 全JSON文字列・object keyのstrict UTF-8検証を追加し、review_resultの正準化失敗をAUD-09監査付きINF-01再試行へ統合した。 (`DECISIONS.md`, `docs/architecture.md`, `docs/cross-agent-compatibility.md`, `docs/subagent-review-spec.md`, `docs/json-output-spec.md`, `docs/testing-and-acceptance.md`, `agent/author-core.md`, `scripts/validate.py`)
- R7-03: `created_at`の数値UTCオフセットを分00〜59・絶対値14:00以下・14時は00分だけに制限し、非正規値を`E-CONTRACT-01`で拒否した。 (`DECISIONS.md`, `docs/json-output-spec.md`, `scripts/finalize_set.py`)
