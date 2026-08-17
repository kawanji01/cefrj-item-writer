# M5 R8 対応記録

- R8-01: CHK-12へ禁止題材・年齢適合・帯内難度の3段階検査を正本どおり追加した。 (`agent/reviewer-core.md`)
- R8-02: CHK-13へ学習者視点の正答到達過程と必要知識全列挙、および語用・文化・教科・正書法／句読法の4分類検査を追加した。 (`agent/reviewer-core.md`)
- R8-03: 通常4監査・増分／最終set_check・slot outcomeの全JSON監査にstrict UTF-8文字列／キー検証とJS-01正準バイト一致を適用し、不一致をファイル名付き`E-CONTRACT-03`で拒否した。 (`scripts/set_support.py`)
- R8-04: FIN-01のstrict UTF-8不適合を未定義キーの生値展開より先に安全な`E-CONTRACT-01`へ変換し、CLI-05正準stderrを保証した。 (`scripts/finalize_set.py`)
