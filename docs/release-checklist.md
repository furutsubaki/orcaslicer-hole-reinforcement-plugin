# 公開前チェックリスト

初回公開（GitHubリポジトリ作成）と、以降の各リリースで実施する手順です。

## 初回公開のみ

### 1. GitHubリポジトリを作成する

- [ ] リポジトリ`furutsubaki/orcaslicer-hole-reinforcement-plugin`を作成する（Public、README・.gitignore・LICENSEの自動生成はすべてオフ。ローカルに実体があるため）
- [ ] Issuesを有効にし、マージ後のブランチ削除を有効にする
- [ ] `git remote add origin git@github.com:furutsubaki/orcaslicer-hole-reinforcement-plugin.git`
- [ ] `main`と`develop`をpushし、`main`をデフォルトブランチにする
- [ ] `CHANGELOG.md`末尾のcompare/releaseリンクが実際のリポジトリURLと一致していることを確認する

### 2. ブランチ保護を設定する

ルールセット（classic branch protectionではない）で`main`と`develop`を保護します。

- [ ] 対象を`refs/heads/main`と`refs/heads/develop`にする
- [ ] ブランチの削除とforce pushを禁止する
- [ ] ステータスチェック`check`の成功を必須にし、strict（ベースブランチへの追従）を有効にする。`check`は[`.github/workflows/pr-check.yml`](../.github/workflows/pr-check.yml)のジョブ名であり、**変えるとチェックを通さずマージできてしまう**
- [ ] 管理者のbypassはPR経由のみに限定する

### 3. Issuesを整備する

正式公開前のローカルissue（`.scratch/formal-plugin/`）は全件completeで、設計判断の根拠は`docs/`配下へ転記済みのため削除しました。GitHubへ移行する対象はありません。

- [ ] ラベルを整備する（[`docs/agents/triage-labels.md`](agents/triage-labels.md)の定義に合わせる）

## 各リリース共通

### 4. 変更内容を確定する

- [ ] `CHANGELOG.md`の`[Unreleased]`へ変更を書き、新しいバージョン見出しへ移す
- [ ] `src/orcaslicer_hole_reinforcement/version.py`の`__version__`を更新する。ここが唯一の定義元で、他にバージョンのハードコードは無い
- [ ] **メジャーを上げる場合のみ**、同ファイルの`__wheel_version__`も合わせる。マイナー・パッチでは触らない（`tests/test_package_metadata.py`がズレを検出する）

  wheelのファイル名にはメジャーしか入らないため、マイナー・パッチ更新ではdocsのパスや`plugin_key`の記載を追随させる必要はありません（[ADR 0003](adr/0003-fix-wheel-version-for-stable-plugin-key.md)）。

### 5. 検証する

PRを出せば[`check`ワークフロー](../.github/workflows/pr-check.yml)が次の3つを自動で実行します。手元で先に確認する場合のコマンドを併記します。

- [ ] `PYTHONPATH=src python3 -m unittest discover -s tests`が全件成功する
- [ ] `python3 tools/check_doc_links.py`が通る（README・docsの相対リンクが実在する）
- [ ] `uv build --wheel`が成功し、`dist/orcaslicer_hole_reinforcement-<メジャー>-py3-none-any.whl`が生成される
- [ ] 既定値を変更した場合、`tools/fixture_suite.py`の寸法境界を追随させ、`PYTHONPATH=src python3 tools/fixture_suite.py`でフィクスチャを再生成する
- [ ] 実機スモーク: OrcaSlicer Nightlyへ新しいwheelをインストールし、フィクスチャ1件をGUIでスライスして、検出結果の表示と`diagnostic.jsonl`の出力を確認する。**`diagnostic.jsonl`の`plugin_version`が今回のバージョンであることを必ず確認する**（インストールが反映されていないまま検証すると偽の合格を出す）
- [ ] OrcaSlicerのAPI基準コミットを変更した場合は、[`docs/adr/0001-orcaslicer-plugin-api-baseline.md`](adr/0001-orcaslicer-plugin-api-baseline.md)の互換性判定手順を実施し、結果をADRへ追記する
- [ ] 対応範囲（OrcaSlicerのビルド、OS、穴形状・方向・穴端）に変更があれば`README.md`の対応範囲表を更新する

### 6. ライセンスを確認する

- [ ] 依存関係を追加・変更した場合、[`docs/third-party-licenses.md`](third-party-licenses.md)を更新する
- [ ] 第三者コードを取り込んだ場合、そのライセンスと著作権表示を配布物へ含める

### 7. リリースする

- [ ] `main`へマージする
- [ ] `git tag v<version>`を打ち、pushする

  [`release`ワークフロー](../.github/workflows/release.yml)が起動し、タグと`version.py`の一致を確認したうえでテストとビルドを回し、`CHANGELOG.md`の該当セクションを本文にしたReleaseを作成してwheelを添付します。タグと`__version__`がズレていると失敗します。

- [ ] Releaseの内容を確認する。対応するOrcaSlicerのビルドと検証済みOSが本文に含まれていなければ追記する
- [ ] 実機で更新後も設定が保持されることを確認する（旧バージョンで設定を保存した状態から更新し、設定画面に同じ値が出ることを確認する）
- [ ] **メジャーを上げたリリースでは**、旧版のアンインストールとプロセス設定でのプラグインの選び直しが必要な旨をRelease本文に明記する。`plugin_key`が変わり、プリセットの参照が外れてスライスがブロックされるため（[ADR 0003](adr/0003-fix-wheel-version-for-stable-plugin-key.md)）
- [ ] 既定値を変更した場合、更新した利用者の設定は引き継がれるため**新しい既定値は適用されない**旨をRelease本文に明記する（新しい既定値を使うには設定画面で「既定値に戻す」が必要）
