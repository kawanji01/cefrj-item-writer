# CEFR-J Item Writer

CEFR-J Wordlist Version 1.6 と CEFR-J Grammar Profileを根拠に、教師との日本語対話から英語学習問題を作成するClaude Code / Codex向けエージェントです。候補問題を決定的なPython CLIと独立LLMレビューで検査し、JSON正本と自己完結HTMLを出力します。

## セットアップ

- Claude Code: [docs/setup-claude-code.md](docs/setup-claude-code.md)
- Codex: [docs/setup-codex.md](docs/setup-codex.md)

いずれもPython 3.11以上、git、対象ツールのインストールと認証が必要です。環境構築後は、リポジトリルートで仮想環境を有効にして `python scripts/doctor.py` を実行し、12項目すべてがpassすることを確認してください。

## LLMへのデータ送信

作問と独立レビューはホストツールのLLM通信を利用します。生成・レビュー時には、正規化したCEFR-Jデータの必要な抜粋と、生成中の問題文・解説・機械検査結果が、Claude Code利用時はAnthropic、Codex利用時はOpenAIへ送信されます。決定的Python CLIは、セットアップ時のspaCyモデル取得を除いて外部ネットワークへ接続しません。

Claude CodeとCodexの間で保証するのは、手順、JSON/CLI契約、決定的処理、監査・成果物配置の同一性です。LLMが生成する文面、レビュー判断、所要時間の同一性は保証しません。

## 出典と利用上の注意

CEFR-J原本の出典、利用条件、再配布時の注意は [NOTICE](NOTICE) を参照してください。生成された問題には誤りや授業目的に適さない内容が含まれる可能性があります。教育利用に先立つ内容・難度・正確性・権利面の最終確認は、利用する教師の責任です。

## 更新

```bash
git pull
python scripts/doctor.py
```

doctorがfailを報告した場合は、出力されたエラーコードと日本語の対処手順に従ってください。
