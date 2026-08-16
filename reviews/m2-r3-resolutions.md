# M2 コードレビュー R3 解決記録

R3-01: stdin・ファイルとも入力をバイト列で読み、UTF-8を明示デコードするよう修正した。不正UTF-8は対象・行・列付き`E-INPUT-03`に変換した。

R3-02: PLN-05に従ってM2D-09を提案し、作問者の承認後に実装した。期待format・level・依頼問題数をCLI必須入力とし、候補との不一致を`V-COND-01`で報告する。欠問の完全性はSET-07に維持し、machine_reportスキーマを1.1.0へ版上げした。

R3-03: discriminatorからcandidate/machine_reportの対応分岐を検証し、複合エラーはleafまで展開するよう修正した。主要バリデータの理由を決定的な日本語で返す。

R3-04: 代入式、`str.removeprefix()`、トップレベルの`importlib.metadata`依存を除き、Python 3.7〜3.10で起動契約の定義済みJSONエラーに到達できるよう修正した。
