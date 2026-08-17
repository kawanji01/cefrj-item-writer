# M3 コードレビュー R10 解決記録

- R10-01: argparseの長いオプション省略を無効化し、未定義の接頭辞をE-INPUT-01で拒否するようにした。 (`scripts/validate.py`)
- R10-02: 日本語ヘルプを環境エンコーディングに依存しないUTF-8バイト列で出力するようにした。 (`scripts/validate.py`)
