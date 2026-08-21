# 公開前チェックリスト

初回公開（GitHubリポジトリ作成とIssues移行）と、以降の各リリースで実施する手順です。

## 初回公開のみ

### 1. GitHubリポジトリを作成する

ローカルの`git init`は実施済みで、`git remote`は未設定です。

- [ ] リポジトリ`furutsubaki/orcaslicer-hole-reinforcement-plugin`を作成する（Public、README・.gitignore・LICENSEの自動生成はすべてオフ。ローカルに実体があるため）
- [ ] Issuesを有効にする
- [ ] `git remote add origin git@github.com:furutsubaki/orcaslicer-hole-reinforcement-plugin.git`
- [ ] `develop`と`main`をpushし、`main`をデフォルトブランチにする
- [ ] `CHANGELOG.md`末尾のcompare/releaseリンクが実際のリポジトリURLと一致していることを確認する

### 2. ローカルissueをGitHub Issuesへ移行する

現在は`.scratch/formal-plugin/`配下のMarkdownで管理しています（[`docs/agents/issue-tracker.md`](agents/issue-tracker.md)）。

- [ ] `.scratch/formal-plugin/PRD.md`の内容をGitHubへ移す（Issue、Discussion、`docs/`配下のいずれか。実装済みの正式版仕様は`docs/`配下の各文書が正のため、PRDは経緯の記録として扱う）
- [ ] `.scratch/formal-plugin/issues/01`〜`16`をGitHub Issuesへ起票する。全件`completed`のため、本文とコメントを移したうえでcloseする。`Category:`は`bug` / `enhancement`ラベルへ、`Status:`はopen/closeへ対応させる
- [ ] ラベルを整備する（[`docs/agents/triage-labels.md`](agents/triage-labels.md)の定義に合わせる）
- [ ] `docs/agents/issue-tracker.md`を、GitHub Issues運用へ書き換える
- [ ] 移行が完了したら`.scratch/formal-plugin/`を削除し、`.gitignore`の`.scratch`の扱いを見直す

## 各リリース共通

### 3. 変更内容を確定する

- [ ] `CHANGELOG.md`の`[Unreleased]`へ変更を書き、新しいバージョン見出しへ移す
- [ ] バージョンを更新する。`src/orcaslicer_hole_reinforcement/version.py`が唯一の定義元だが、次のハードコードも合わせて更新する
  - `tests/test_package_boundaries.py`（バージョンのアサーション2箇所）
  - `tools/compare_slice_output.py`の`--plugin-version`既定値
  - `README.md`のwheelファイル名
  - `docs/orcaslicer-integration-verification.md`の手順中のパスと`plugin_key`
  - `docs/troubleshooting.md`の`diagnostic.jsonl`のパス

### 4. 検証する

- [ ] `PYTHONPATH=src python3 -m unittest discover -s tests`が全件成功する
- [ ] `uv build --wheel`が成功し、`dist/orcaslicer_hole_reinforcement-<version>-py3-none-any.whl`が生成される
- [ ] README・docsの相対リンクがすべて実在するファイルを指している
- [ ] 実機スモーク: OrcaSlicer Nightlyへ新しいwheelをインストールし、フィクスチャ1件をGUIでスライスして、検出結果の表示と`diagnostic.jsonl`の出力を確認する。**旧版は先にアンインストールする**（ファイル名にバージョンが入るため、残すと別プラグインとして並存する）
- [ ] OrcaSlicerのAPI基準コミットを変更した場合は、[`docs/adr/0001-orcaslicer-plugin-api-baseline.md`](adr/0001-orcaslicer-plugin-api-baseline.md)の互換性判定手順を実施し、結果をADRへ追記する
- [ ] 対応範囲（OrcaSlicerのビルド、OS、穴形状・方向・穴端）に変更があれば`README.md`の対応範囲表を更新する

### 5. ライセンスを確認する

- [ ] 依存関係を追加・変更した場合、[`docs/third-party-licenses.md`](third-party-licenses.md)を更新する
- [ ] 第三者コードを取り込んだ場合、そのライセンスと著作権表示を配布物へ含める

### 6. リリースする

- [ ] `main`へマージする
- [ ] `git tag v<version>`を打ち、pushする
- [ ] GitHub Releaseを作成し、`CHANGELOG.md`の該当セクションを本文にする
- [ ] ビルドしたwheelをReleaseへ添付する
- [ ] 対応するOrcaSlicerのビルドと、検証済みOSをRelease本文に明記する
- [ ] バージョンを上げた場合、更新後にプロセス設定でプラグインを選び直す必要がある旨をRelease本文に明記する（プリセットの`plugins`が版込みの参照を持つため、選び直さないとOrcaSlicerがスライスをブロックする）
- [ ] バージョンを上げた場合、実機で設定の引き継ぎを確認する（旧バージョンで設定を保存した状態から更新し、設定画面に旧値が出ることと`diagnostic.jsonl`へ`config_migrated`が出ることを確認する）。引き継ぎ対象外のプリセットoverrideがある場合はRelease本文に明記する
