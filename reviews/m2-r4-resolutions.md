# M2 コードレビュー R4 解決記録

R4-01: candidateと期待レベルのscaleが同じ場合、S4〜S6のレベル依存検査へ期待レベルを渡すよう修正した。これにより、レベル不一致の`V-COND-01`と、期待レベル基準の語数・語彙・ターゲット・誤答違反を同一レポートへ全件列挙する。scaleが異なる場合はcandidateのscaleと値で実行可能な検査を継続する。

R4-02: PLN-05に従ってM2D-10を提案し、作問者の承認後に実装した。`machine_check.py`による`limits.json.set_question_max`参照をS1の`--requested-count`値域検査に限定し、MC-10とCLI-16を同期した。

R4-03: PLN-05に従ってM2D-11を提案し、作問者の承認後に実装した。candidate JSONの整数を符号を除く10進4,300桁以下に固定し、超過を対象・行・列・上限・実測桁数付き`E-INPUT-03`とした。プロセス内の変換上限も4,300桁に固定し、`PYTHONINTMAXSTRDIGITS`による分岐を排除した。
