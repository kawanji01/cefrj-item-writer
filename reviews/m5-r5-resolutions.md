# M5 コードレビュー R5 解決記録

- R5-01: 承認済みM5D-09に基づき、T3後は2回目のcandidate受理診断だけで次世代を生成し、不成立照会もT3/T8/T11の実在監査を経路別に案内するよう統一した (`DECISIONS.md`, `docs/interaction-flow.md`, `docs/subagent-review-spec.md`, `agent/author-core.md`)
- R5-02: 承認済みM5D-10に基づき、提案モードの続行は現在スロットだけを減数終端し、未処理の初期スロットを補充なしで順次処理してから確定するよう変更した (`DECISIONS.md`, `docs/interaction-flow.md`, `docs/subagent-review-spec.md`, `agent/author-core.md`)
- R5-03: 承認済みM5D-11に基づき、AUD-09を標準・UTF-8符号化失敗・プロセス失敗の3形式へ固定し、全invalid監査をstrict UTF-8と内容契約で検証して不適合をE-CONTRACT-03で拒否した (`DECISIONS.md`, `docs/json-output-spec.md`, `docs/subagent-review-spec.md`, `agent/author-core.md`, `scripts/set_support.py`)
