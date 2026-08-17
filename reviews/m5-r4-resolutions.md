# M5 コードレビュー R4 解決記録

- R4-01: 承認済みM5D-06に従い、CHK-10が解説中の`kyoinban.name_ja`を照合し、平易版名だけの場合は不合格とするよう統一した (`agent/reviewer-core.md`)
- R4-02: CHK-04へ全語連鎖、複数語見出し、未収録表現の推定、および書き換え元文・目標完成文双方の検査を追加した (`agent/reviewer-core.md`)
- R4-03: CHK-16へ目標文の空欄が対象文法操作の核心部分を覆う検査を追加した (`agent/reviewer-core.md`)
- R4-04: MC-07で文として検査するformat別フィールドだけを例文再利用検査へ取り込み、選択肢語と同値表記を除外した (`scripts/set_support.py`)
- R4-05: CHK-03へ書き換え元文・目標完成文双方の全文法構造列挙、上限比較、該当文・スパン記録を追加した (`agent/reviewer-core.md`)
- R4-06: 承認済みM5D-07に従い、開始・不成立・照会表示の世代数、最終世代、監査範囲を`generation_max`から展開するよう変更した (`agent/author-core.md`)
- R4-07: 承認済みM5D-08に従い、受理・保存済みレビューのdispute件数を一度だけ累積し、S80開始後の完了・中止報告へ0件時も固定文言を表示するよう変更した (`agent/author-core.md`)
