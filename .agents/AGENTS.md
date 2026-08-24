<!-- ⚠️ この共通設定ファイルを編集してください。各AIツール向けの設定ファイルは、このファイルを参照するだけにしてください。 -->
<!-- ⚠️ Edit this shared config file. AI-tool-specific config files should only reference this file. -->

# AGENTS.md

このファイルは、OrcaSlicer穴補強プラグインを扱う複数のAIコーディングエージェント（Claude Code、Codex CLI等）に共通で適用するガイダンスです。

## Agent skills

### Issue tracker

GitHub Issuesで管理します。詳細は`docs/agents/issue-tracker.md`を参照してください。

### Triage labels

既定の5状態を使用します。詳細は`docs/agents/triage-labels.md`を参照してください。

### Domain docs

設計判断は`docs/adr/`のADRへ記録します。仕様と契約は`docs/`配下の各文書が正であり、`README.md`の「開発者向け」節が入口です。

## 禁止事項

- `develop`および`main`ブランチで直接作業しない
