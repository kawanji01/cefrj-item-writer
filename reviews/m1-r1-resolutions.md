# M1 コードレビュー R1 解決記録

R1-01: doctorのD07/D09が`CliFailure.error_code`を保持するよう修正し、正規化欠落時はD07〜D09の全てが`E-DATA-03`となることを確認した。
R1-02: 通常ビルド前の出力先書込み検査と原子的書込みの`OSError`変換を追加し、`/dev/null/cefrj-normalized`が終了コード1・`E-ENV-05`になることを確認した。
R1-03: 承認済みM1D-11に従い`sources.json.version_label`から版を導出し、変更原本の版未更新を`E-DATA-02`、版入力不正を`E-DATA-01`で拒否するガードを追加した。
R1-04: ITEM LIST必須ヘッダーをtuple化して欠落・重複を固定順で全件収集し、`PYTHONHASHSEED=1..4`で同一エラーJSONになることを確認した。
R1-05: ALLのheadwordを原表記保存値とNFC・trim済み照合値に分離し、`headword_joined`はセル文字列を無変更で保持するよう修正した。
