# M1 コードレビュー R7 解決記録

R7-01: 承認済みM1D-16に従い、Git起動・リポジトリ・HEAD照会の失敗を`E-ENV-04`で安全側に停止し、有効なHEADで対象meta不在を確認できた場合だけ初回ビルドを許可するよう修正した。
R7-02: doctor D12のClaude Code配線検出を仕様の固定パス`.claude/agents/cefrj-reviewer.md`へ限定し、無関係なMarkdownをpass扱いしないよう修正した。
R7-03: Wordlist全対象シートのヘッダー位置を保持し、ALL_sepとALLの各値を物理列番号ではなく列名に対応するインデックスで読み取るよう修正した。
R7-04: WordlistとGrammar Profileのセル値検査を先行走査し、複数の不正値をシート・行・列の固定順で単一の`E-DATA-06`へ全件列挙するよう修正した。
R7-05: buildとdoctorの正常・定義済みエラーJSONをテキストストリーム設定に依存せずBOMなしUTF-8・LFのバイト列として直接出力するよう修正した。
