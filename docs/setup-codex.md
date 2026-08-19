# Codex版セットアップ手順書

## 1. 前提環境

対応環境はmacOS、Linux、およびWindowsホスト上のWSL2 Linux環境です。ネイティブWindowsのPowerShell・コマンドプロンプト上の作問実行はサポート対象外です。Python 3.11以上、git、Codex CLI本体、Codexを利用できるアカウントを準備してください。Codex CLIのインストールと認証は[OpenAI公式のCodex CLI手順](https://developers.openai.com/codex/cli/)に従います。WindowsではWSL2を有効化し、リポジトリ、Python、Codex、以後の全コマンドをWSL2シェル内で扱ってください。

確認コマンド:

```text
python --version
git --version
codex --version
```

成功時は、Python 3.11以上、gitのバージョン、Codex CLIのバージョンがそれぞれ表示されます。初回認証はリポジトリ以外の任意の作業ディレクトリでもよいので `codex` を実行し、公式画面の `Sign in with ChatGPT` または利用可能な認証方法を選んでください。

Windowsホストでは、先にPowerShellで`wsl --status`を実行して既定バージョンが2であることを確認し、`wsl`でWSL2シェルへ入ってから上記3コマンドを実行します。成功時はWSL2ディストリビューション内の各バージョンが表示されます。

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

このコマンドは `.venv` を作成し、パッケージインデックスから`requirements.txt`に固定された依存を取得・導入します。この取得にはネットワーク接続が必要です。成功時は各パッケージの導入完了後、最後に `セットアップが完了しました。` とdoctorの実行案内が表示されます。

続いて仮想環境を有効にします。

macOS / Linux / Windowsホスト上のWSL2:

```text
source .venv/bin/activate
```

成功時は、以後の `python` が `.venv` 内のPythonを指します。

## 4. spaCyモデル取得

前節の `python scripts/setup.py` は、依存導入後に `en_core_web_sm` 3.8.0も取得します。固定版依存とこのモデルの取得を行うセットアップ処理だけがネットワーク許可範囲です。セットアップ完了後の決定的Python CLIは外部ネットワークへ接続しません。

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
python .codex/run_reviewer.py --help
```

成功時は3コマンドが終了コード0でヘルプを表示します。`codex --help` には`--sandbox`と`--ask-for-approval`、`codex exec --help`には`--ignore-user-config`、`--ignore-rules`、`--disable`、`--config`、`--ephemeral`、`--cd`、`--sandbox`、`--skip-git-repo-check`、`--output-last-message`が掲載されています。ラッパーのヘルプには必須の`--request`だけが表示されます。`--ephemeral` は独立レビュアーのセッション状態を永続化しません。リポジトリルートの `AGENTS.md` と `.codex/run_reviewer.py` が存在することも確認してください。モデル指定は追加せず、認証済みCodex環境の既定モデルを使用します。

独立レビュアー専用の`CODEX_HOME`を作成し、作問側とは別に認証します。このディレクトリへユーザー設定、ルール、個人スキル、プラグイン、メモリを追加してはいけません。

macOS / Linux / Windowsホスト上のWSL2:

```text
mkdir -p "${HOME}/.codex-cefrj-reviewer"
env CODEX_HOME="${HOME}/.codex-cefrj-reviewer" codex login
env CODEX_HOME="${HOME}/.codex-cefrj-reviewer" codex login status
```

成功時は認証画面での操作後、`codex login status`がログイン済みであることを表示します。既存の作問側`CODEX_HOME`から認証ファイルをコピーしてはいけません。

初回セットアップ時とCodex更新後は、専用ホームに追加userコンテキストが混入していないことを次の機械検査で診断します。`prompt`の3行へ任意の文を追加してはいけません。

macOS / Linux / Windowsホスト上のWSL2:

```text
python - <<'PY'
import json
import os
from pathlib import Path
import subprocess
import sys

prompt = """agent/reviewer-core.md を読み、その指示に完全に従ってください。
入力封筒: output/example/review/q01.gen1.request.json
最終メッセージは review_result JSON 本文のみとし、JSON以外の文章を出力しないでください。"""
command = [
    "codex", "debug", "prompt-input",
    "-c", "project_doc_max_bytes=0",
    "-c", "include_environment_context=false",
    "--disable", "recommended_plugins",
    "--disable", "apps",
    "--disable", "plugins",
    "--disable", "workspace_dependencies",
    prompt,
]
env = os.environ.copy()
env["CODEX_HOME"] = str(Path.home() / ".codex-cefrj-reviewer")
completed = subprocess.run(command, env=env, capture_output=True, text=True)
if completed.returncode != 0:
    print(completed.stderr, file=sys.stderr)
    raise SystemExit(completed.returncode)
try:
    messages = json.loads(completed.stdout)
except json.JSONDecodeError as exc:
    print(f"実効入力JSONを解析できません: {exc}", file=sys.stderr)
    raise SystemExit(1)
users = [m for m in messages if isinstance(m, dict) and m.get("role") == "user"]
expected = [{"type": "input_text", "text": prompt}]
matched = len(users) == 1 and users[0].get("content") == expected
print(json.dumps({
    "user_message_count": len(users),
    "user_prompt_exact_match": matched,
}, ensure_ascii=False, sort_keys=True))
raise SystemExit(0 if matched else 1)
PY
```

成功時は終了コード0で`{"user_message_count": 1, "user_prompt_exact_match": true}`が表示されます。1件でも追加userメッセージがある、または本文が3行と完全一致しない場合は終了コード1となります。その場合は独立レビューを起動せず、Codexを更新し、専用ホームから認証情報以外の追加物を取り除いて再診断してください。Codexが固定で付与するsystem/developer/tool定義と専用ホーム配下の組み込み`.system`スキル一覧は、このuserメッセージ検査の対象外です。

## 7. LLMへの送信

生成・レビュー時には、正規化CEFR-Jデータの必要な抜粋と問題文・解説・機械検査結果がOpenAIへ送信されます。セットアップ処理は固定版依存とspaCyモデルの取得にネットワークを使いますが、セットアップ完了後の決定的Python CLIはネットワークへ接続しません。

Claude CodeとCodexで同一性を保証するのは、手順、契約、決定的処理、監査・成果物配置です。生成文面、レビュー判断、所要時間の同一性は保証しません。

## 8. 初回作問チュートリアル

リポジトリルートで仮想環境を有効にした状態でCodexを起動します。

```text
codex --sandbox workspace-write --ask-for-approval on-request
```

独立レビューのたびに、`AGENTS.md`記載の`python .codex/run_reviewer.py --request output/<set_id>/review/<question_id>.<gen>.request.json`という固定ラッパー呼出しを親サンドボックス外で実行する承認が求められます。requestパス以外の追加引数、環境変数代入、リダイレクト、パイプ、複合コマンドがないことを確認し、その1回の固定呼出しだけを承認してください。ラッパーは専用`CODEX_HOME`、全コンテキスト無効化引数、`--ephemeral`、`--sandbox read-only`、モデル無指定の固定`codex exec`を構築し、設定済み壁時計期限を超えた子プロセスグループを停止します。作問側Codex全体を`danger-full-access`で起動したり、作問側`~/.codex`を子へ渡したりしないでください。

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

`codex exec --help` が失敗する、または必要なオプションが表示されない場合は、次を実行してCodex CLIを更新します。

```text
codex update
codex --version
codex exec --help
```

独立レビューが終了コード124になった場合は、`review_timeout_seconds`の壁時計期限を超えたためラッパーが子プロセスグループを停止しています。エージェントは同じrequestを変更せず既定のインフラ障害再実行へ進みます。3実行とも終了コード124なら`set.json`を作らずセットを中止します。ラッパーを迂回して`codex exec`を直接再実行しないでください。

成功時は各コマンドが終了コード0となり、`codex update`は更新完了または既に最新版である旨、`codex --version`は`codex-cli <version>`を表示します。最後のヘルプに`--ignore-user-config`、`--ignore-rules`、`--disable`、`--config`、`--ephemeral`、`--cd`、`--sandbox`、`--skip-git-repo-check`、`--output-last-message`がすべて表示されることを確認してください。更新コマンド自体が利用できない場合は、[OpenAI公式のCodex CLI手順](https://developers.openai.com/codex/cli/)に従い、現在の導入方式に対応する最新版を再インストールしてから同じ確認を行ってください。

独立レビュー起動時に`Not logged in`と表示された場合は、第6節の専用`CODEX_HOME`認証だけを再実行してください。入力分離診断にユーザー・プロジェクト由来コンテキストが表示された場合はレビューを起動せず、専用ホームから認証情報以外の追加物を取り除いて再診断してください。

独立レビュー起動時に`Operation not permitted`やsandbox violationで停止した場合は、作問側Codexを終了し、リポジトリルートから`codex --sandbox workspace-write --ask-for-approval on-request`で再起動してください。再実行時は専用`CODEX_HOME`を使う固定レビュアーコマンドだけを承認し、子の`--sandbox read-only`を変更しないでください。

## 11. 免責

生成された問題には誤りや授業目的に適さない内容が含まれる可能性があります。教育利用に先立つ内容・難度・正確性・権利面の最終確認は、利用する教師の責任です。
