# M3 コードレビュー R3 解決記録

- R3-01: JSON実数を`Decimal`で正確に保持し、Decimalの数学的整数性を判定するDraft 2020-12検証器でアンダーフローによる誤合格を防止した。 (`scripts/validate.py`)
- R3-02: 不正UTF-8より前の有効部分を復号し、CRLF・CR・LFを認識したUnicode文字単位の行・列を報告するよう修正した。 (`scripts/validate.py`)
