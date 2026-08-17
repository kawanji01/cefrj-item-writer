# M3 コードレビュー R1 解決記録

- R1-01: 通常入力の`stat`・読取りと状態確認入力の`lstat`・種別判定・読取りを各OSError捕捉境界へ統合し、読取り不能を`E-INPUT-02`、`set.json`の`FileNotFoundError`だけを未完成状態へ変換した。 (`scripts/validate.py`)
