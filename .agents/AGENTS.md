<!-- ⚠️ この共通設定ファイルを編集してください。各AIツール向けの設定ファイルは、このファイルを参照するだけにしてください。 -->
<!-- ⚠️ Edit this shared config file. AI-tool-specific config files should only reference this file. -->

# AGENTS.md

このファイルは、OrcaSlicer穴補強プラグインを扱う複数のAIコーディングエージェント（Claude Code、Codex CLI等）に共通で適用するガイダンスです。

## Agent skills

### Issue tracker

正式公開までは`.scratch/`のローカルMarkdownで管理し、公開後はGitHub Issuesへ移行します。詳細は`docs/agents/issue-tracker.md`を参照してください。

### Triage labels

既定の5状態を使用します。詳細は`docs/agents/triage-labels.md`を参照してください。

### Domain docs

単一コンテキスト構成として、`CONTEXT.md`と`docs/adr/`を使用します。詳細は`docs/agents/domain.md`を参照してください。

## 禁止事項

- `develop`および`main`ブランチで直接作業しない
