# M3 コードレビュー R4 解決記録

- R4-01: set_id・semverの内部正規表現をASCII数字へ限定し、スキーマの`\d`をECMA-262どおりASCII数字として評価する検証器へ変更した。 (`scripts/validate.py`)
- R4-02: validate.pyのJSON出力境界で孤立サロゲートを可視な`\uXXXX`へ再帰変換し、違反結果とエラーを常にUTF-8で直列化可能にした。 (`scripts/validate.py`)
- R4-03: スキーマパスによる決定的整列へ変更して違反の重複除去を廃止し、contains違反へ欠落したCHK番号を記録した。 (`scripts/validate.py`)
