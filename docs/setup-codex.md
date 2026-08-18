# Codex版セットアップ手順書

## 1. 前提環境

対応OSはmacOS、Linux、Windowsです。Python 3.11以上、git、Codex CLI本体、Codexを利用できるアカウントを準備してください。Codex CLIのインストールと認証は[OpenAI公式のCodex CLI手順](https://developers.openai.com/codex/cli/)に従います。

確認コマンド:

```text
python --version
git --version
codex --version
```

成功時は、Python 3.11以上、gitのバージョン、Codex CLIのバージョンがそれぞれ表示されます。初回認証はリポジトリ以外の任意の作業ディレクトリでもよいので `codex` を実行し、公式画面の `Sign in with ChatGPT` または利用可能な認証方法を選んでください。

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

## 6. Codex固有設定

作問側Codexと非対話レビュアーの起動に必要なオプションを確認します。

```text
codex --help
codex exec --help
```

成功時は両ヘルプが終了コード0で表示されます。`codex --help` には`--sandbox`と`--ask-for-approval`、`codex exec --help`には`--ephemeral`、`--cd`、`--sandbox`、`--skip-git-repo-check`、`--output-last-message`が掲載されています。`--ephemeral` は独立レビュアーのセッション状態を永続化しません。リポジトリルートの `AGENTS.md` が存在し、Codexをこのディレクトリから起動したときに読み込まれることも確認してください。モデル指定は追加せず、認証済みCodex環境の既定モデルを使用します。

## 7. LLMへの送信

生成・レビュー時には、正規化CEFR-Jデータの必要な抜粋と問題文・解説・機械検査結果がOpenAIへ送信されます。Pythonの決定的CLIは、前述のspaCyモデル取得を除いてネットワークへ接続しません。

Claude CodeとCodexで同一性を保証するのは、手順、契約、決定的処理、監査・成果物配置です。生成文面、レビュー判断、所要時間の同一性は保証しません。

## 8. 初回作問チュートリアル

リポジトリルートで仮想環境を有効にした状態でCodexを起動します。

```text
codex --sandbox workspace-write --ask-for-approval on-request
```

独立レビューのたびに、`AGENTS.md`記載の固定`codex exec`コマンドを親サンドボックス外で実行する承認が求められます。コマンドに`--ephemeral`と`--sandbox read-only`があり、モデル指定や追加の書込み権限がないことを確認して、その固定コマンドだけを承認してください。作問側Codex全体を`danger-full-access`で起動したり、`~/.codex`を追加の書込み先にしたりしないでください。

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

エラーは `E-ENV`（実行環境）、`E-DATA`（データ整合）、`E-CONTRACT`（JSON・スキーマ・成果物契約）、`E-INPUT`（引数・入力）の4系列です。CLIが表示した `error_code`、`message`、`remedy` を読み、[エラーコード目録](architecture.md#6-エラーコード目録正)の同じコードに従ってください。

`codex exec --help` が失敗する、または必要なオプションが表示されない場合は、[OpenAI公式のCodex CLI手順](https://developers.openai.com/codex/cli/)に従ってCodex CLIを更新し、再度 `codex exec --help` を実行してください。

独立レビュー起動時に`Operation not permitted`やsandbox violationで停止した場合は、作問側Codexを終了し、リポジトリルートから`codex --sandbox workspace-write --ask-for-approval on-request`で再起動してください。再実行時は固定レビュアーコマンドだけを承認し、子の`--sandbox read-only`を変更しないでください。

## 11. 免責

生成された問題には誤りや授業目的に適さない内容が含まれる可能性があります。教育利用に先立つ内容・難度・正確性・権利面の最終確認は、利用する教師の責任です。
