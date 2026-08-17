# M3 コードレビュー R5 解決記録

- R5-01: ECMA-262の終端アンカー`$`をPythonの厳密終端`\Z`へ変換し、末尾改行を持つID・semver・単語を拒否した。 (`scripts/validate.py`)
- R5-02: 数値走査でDecimal変換不能を位置付きJSONエラーへ変換し、JSONデコーダの再帰超過も決定的な位置を持つ`E-INPUT-03`として処理した。 (`scripts/validate.py`)
- R5-03: Pythonの`splitlines()`が認識する全行区切りを1行要約内で可視なエスケープへ変換した。 (`scripts/validate.py`)
