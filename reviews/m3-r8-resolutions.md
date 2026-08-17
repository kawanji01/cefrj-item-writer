# M3 コードレビュー R8 解決記録

- R8-01: machine_reportのscopeを文字列型確認して既知値だけ分岐選択し、非文字列・未知値はルートスキーマ検証へフォールバックした。 (`scripts/build_normalized.py`)
