# M1 コードレビュー R11 解決記録

R11-01: metaの`spacy_model.name`と`spacy_model.version`を固定要求値へ照合し、不一致をフィールド名・期待値・実測値付きの`E-DATA-04`としてdoctorで報告するよう修正した。
R11-02: 文書全体のschema合否から独立して型安全な`data_version`を現在値・相互比較へ参加させ、schema違反・meta問題・内部矛盾・現在値不一致を同じ`E-DATA-04`へ集約するよう修正した。
