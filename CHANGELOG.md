# 変更履歴

本ファイルの形式は[Keep a Changelog](https://keepachangelog.com/ja/1.1.0/)に基づき、バージョン番号は[セマンティックバージョニング](https://semver.org/lang/ja/)に従います。

## [Unreleased]

## [1.0.0] - 2026-08-24

初回公開。OrcaSlicer Nightly `2.5.0-dev` / Build `872c660c`で実機検証しました。

配布物は`orcaslicer_hole_reinforcement-1-py3-none-any.whl`です。ファイル名に入るのはメジャーバージョンだけで、`1.0.1`でも`1.4.0`でもファイル名は変わりません。OrcaSlicerはインストール元ファイル名でプラグインを識別するため、こうすることで更新しても設定とプリセットの参照が保たれます。

公開前の開発版（`0.0.1`〜`0.2.0`）を入れている場合は、先に旧版をアンインストールしてください。設定は自動で引き継がれます。

### 追加

- 3D穴検出。円、正六角形、正八角形、正n角形の穴を、造形座標での寸法と軸から検出する
- 穴の向きは造形プレートに対して`0°`（水平）から`90°`（垂直）の全範囲に対応
- 穴端分類。貫通穴と止まり穴を判別し、両端が閉じた内部空洞や縁が非多様体の候補を除外する
- ソリッド補強。`posPrepareInfill`で穴周囲の内部インフィルをソリッド化する
- 独自の設定画面。OrcaSlicer本体のテーマと表示言語（日本語・英語）へ追従し、入力時の自動保存と既定値への復帰に対応する。見出しにプラグインの実バージョンを表示する（プラグイン一覧の表示`1`はwheelファイル名由来の固定値のため）
- 設定スキーマの検証。UIとスライス処理の入口の両方で型、範囲、相関を検証する
- 構造化診断。`diagnostics_enabled`が有効なとき、検出候補の形状・寸法・軸・穴端・信頼度・除外理由と、補強レイヤ・Surface数を`diagnostic.jsonl`へ記録する。各レコードには`plugin_version`が入る
- 解析キャッシュ。メッシュ内容と検出設定をキーにしたLRUで、同一形状の複数インスタンスの再解析を避ける
- プラグイン更新後の設定引き継ぎ。更新後の初回読み込み時に、OrcaSlicerの`orca_plugins/config.json`から旧バージョンのエントリを読み取り、設定を自動で復元します。引き継ぎの成否は診断へ`config_migrated` / `config_migration_skipped` / `config_migration_failed`として記録します
  - 引き継げるのはプラグイン設定画面で保存した値だけです。プリセットoverrideは、ホストのプリセットAPIが読み取り専用で書き戻せないため対象外です
- プリセットに旧バージョン向けの設定（override）が残っている場合の警告。設定画面の上部に表示し、診断へ`preset_override_stale`を記録します
  - 同じプリセットに現在のキーのoverrideがあれば警告しません。OrcaSlicerは旧エントリを削除しないため、入力し直したあとも警告し続けると消す手段が無くなるためです
  - 警告はプリセットの設定を入力し直すと消えます。プラグインの設定画面は保存先が別のため、そこで直しても消えません
  - 引き継ぎに失敗した場合は既定値で動作し、スライスは妨げません
- 公開用文書一式（README、`LICENSE`、[検出アルゴリズム](docs/detection-algorithm.md)、トラブルシューティング、第三者ライセンス、公開前チェックリスト、ADR）

### 既定値について

既定値は**0.4mmノズルで、M3〜M8のボルトとナットによる固定に使う部品**を想定しています。

| キー | 既定値 |
| --- | --- |
| `min_hole_diameter_mm` | `3.0` |
| `max_hole_diameter_mm` | `10.0` |
| `reinforcement_width_mm` | `3.0` |
| `min_hole_depth_mm` | `2.0` |

根拠は[`docs/configuration.md`](docs/configuration.md)の「既定値の根拠」にあります。M2・M2.5やタップ穴の下穴を対象にする場合は`min_hole_diameter_mm`を下げてください。

### 削除

- PoC実装（`hole_reinforcement_detector_poc.py`）と、その専用ツール（`tools/generate_test_model.py`、`tools/run_detector_harness.py`）。正式版へ統合済みのため

[Unreleased]: https://github.com/furutsubaki/orcaslicer-hole-reinforcement-plugin/compare/v1.0.0...HEAD
[1.0.0]: https://github.com/furutsubaki/orcaslicer-hole-reinforcement-plugin/releases/tag/v1.0.0
