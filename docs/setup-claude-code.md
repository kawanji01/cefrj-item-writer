# Claude Code版セットアップ手順書

## 1. 前提環境

対応OSはmacOS、Linux、Windowsです。Python 3.11以上、git、Claude Code本体、Claude Codeを利用できるアカウントを準備してください。Claude Codeのインストールと認証は[公式セットアップ手順](https://code.claude.com/docs/en/setup)に従います。

確認コマンド:

```text
python --version
git --version
claude --version
```

成功時は、Python 3.11以上、gitのバージョン、Claude Codeのバージョンがそれぞれ表示されます。初回認証は `claude` を実行し、ブラウザに表示される公式の案内に従ってください。

## 2. リポジトリ取得

本リポジトリは非公開です。アクセス権とclone URLは、リポジトリを共有した管理者から入手してください。

```text
git clone <共有された非公開リポジトリURL>
cd cefrj-item-writer
```

成功時はcloneが完了し、カレントディレクトリ直下に `agent/`、`data/`、`schemas/`、`scripts/` が存在します。

## 3. Python環境構築

リポジトリルートで次を実行します。

```text
python scripts/setup.py
```

このコマンドは `.venv` を作成し、`requirements.txt` に固定された依存を導入します。成功時は最後に `セットアップが完了しました。` とdoctorの実行案内が表示されます。

続いて仮想環境を有効にします。

macOS / Linux:

```text
source .venv/bin/activate
```

Windows PowerShell:

```text
.venv\Scripts\Activate.ps1
```

Windowsコマンドプロンプト:

```text
.venv\Scripts\activate.bat
```

成功時は、以後の `python` が `.venv` 内のPythonを指します。

## 4. spaCyモデル取得

前節の `python scripts/setup.py` は、依存導入後に `en_core_web_sm` 3.8.0も取得します。このモデル取得が、セットアップ後の決定的処理を含めて唯一許可されるネットワーク取得です。

確認コマンド:

```text
python -m spacy validate
```

成功時は `en_core_web_sm` がインストール済みかつ互換と表示されます。

## 5. 診断

```text
python scripts/doctor.py
```

成功時は終了コード0でJSONが表示され、`summary` が `{"pass": 12, "fail": 0}` になります。failがある場合は、各項目の `error_code` と `remedy` を確認し、[エラーコード目録](architecture.md#6-エラーコード目録正)の対処手順に従ってください。

## 6. Claude Code固有設定

次の配線ファイルが存在することを確認します。

```text
claude
```

Claude Codeが起動したら、プロジェクトを信頼し、`/agents` を開きます。成功時はLibraryにプロジェクトサブエージェント `cefrj-reviewer` が表示されます。続いて `/permissions` を開き、`.claude/settings.json` が読み込まれ、リポジトリ読取り、`output/` 書込み、8本のPython CLI実行、`finalize_set.py`へ引用付き`FIN01`ヒアドキュメントで必須JSONを渡す専用呼出し、およびS80開始時の識別子生成だけを行う引数なし固定コマンドが標準フロー用に許可され、Web取得・検索が拒否されていることを確認してください。finalize専用許可はパイプ・中間ファイル・追加コマンドを許可せず、識別子生成コマンドの許可は全文完全一致で、汎用`python -c`や追加引数を許可しません。`.claude/skills/cefrj-author/SKILL.md` と `.claude/agents/cefrj-reviewer.md` はリポジトリに同梱されています。

## 7. LLMへの送信

生成・レビュー時には、正規化CEFR-Jデータの必要な抜粋と問題文・解説・機械検査結果がAnthropicへ送信されます。Pythonの決定的CLIは、前述のspaCyモデル取得を除いてネットワークへ接続しません。

Claude CodeとCodexで同一性を保証するのは、手順、契約、決定的処理、監査・成果物配置です。生成文面、レビュー判断、所要時間の同一性は保証しません。

## 8. 初回作問チュートリアル

リポジトリルートで仮想環境を有効にした状態でClaude Codeを起動します。

```text
claude
```

次のように作問開始を依頼します。

```text
CEFR-J準拠の問題作成を開始してください。
```

画面の質問に1つずつ回答し、形式は `vocab_mcq_en2ja`、レベルは `A1`、問題数は `3` を選びます。対象選定、任意項目、最終確認は画面の案内に従って回答します。完了報告に表示された `<set_id>` を使って次を確認してください。

```text
python scripts/validate.py --schema set --file output/<set_id>/set.json
python scripts/build_html.py --set output/<set_id>/set.json
```

成功時は1つ目が `"valid": true` を返し、2つ目が `html_path` を返します。`output/<set_id>/index.html` をブラウザで開き、問題が表示されることを確認します。

## 9. 更新

```text
git pull
python scripts/doctor.py
```

成功時は更新が取り込まれ、doctorが終了コード0と12項目passを返します。

## 10. トラブルシュート

エラーは `E-ENV`（実行環境）、`E-DATA`（データ整合）、`E-CONTRACT`（JSON・スキーマ・成果物契約）、`E-INPUT`（引数・入力）の4系列です。CLIが表示した `error_code`、`message`、`remedy` を読み、[エラーコード目録](architecture.md#6-エラーコード目録正)の同じコードに従ってください。Claude Code本体の導入・認証・更新で失敗した場合は[Claude Code公式セットアップ手順](https://code.claude.com/docs/en/setup)の診断と更新手順を使用します。

## 11. 免責

生成された問題には誤りや授業目的に適さない内容が含まれる可能性があります。教育利用に先立つ内容・難度・正確性・権利面の最終確認は、利用する教師の責任です。
