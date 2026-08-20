# 変更履歴

本ファイルの形式は[Keep a Changelog](https://keepachangelog.com/ja/1.1.0/)に基づき、バージョン番号は[セマンティックバージョニング](https://semver.org/lang/ja/)に従います。

## [Unreleased]

## [0.1.0] - 2026-08-21

初回公開。OrcaSlicer Nightly `2.5.0-dev` / Build `872c660c`で実機検証しました。

公開前の`0.0.1`を入れている場合は、先に旧版をアンインストールしてください。OrcaSlicerはプラグイン設定をバージョン入りのキーで保存するため、**設定は引き継がれず既定値に戻ります**。

### 追加

- 3D穴検出。円、正六角形、正八角形、正n角形の穴を、造形座標での寸法と軸から検出する
- 穴の向きは造形プレートに対して`0°`（水平）から`90°`（垂直）の全範囲に対応
- 穴端分類。貫通穴と止まり穴を判別し、両端が閉じた内部空洞や縁が非多様体の候補を除外する
- ソリッド補強。`posPrepareInfill`で穴周囲の内部インフィルをソリッド化する
- 独自の設定画面。OrcaSlicer本体のテーマと表示言語（日本語・英語）へ追従し、入力時の自動保存と既定値への復帰に対応する
- 設定スキーマの検証。UIとスライス処理の入口の両方で型、範囲、相関を検証する
- 構造化診断。`diagnostics_enabled`が有効なとき、検出候補の形状・寸法・軸・穴端・信頼度・除外理由と、補強レイヤ・Surface数を`diagnostic.jsonl`へ記録する
- 解析キャッシュ。メッシュ内容と検出設定をキーにしたLRUで、同一形状の複数インスタンスの再解析を避ける
- 公開用文書一式（README、`LICENSE`、トラブルシューティング、第三者ライセンス、公開前チェックリスト）

### 削除

- PoC実装（`hole_reinforcement_detector_poc.py`）と、その専用ツール（`tools/generate_test_model.py`、`tools/run_detector_harness.py`）。正式版へ統合済みのため

[Unreleased]: https://github.com/furutsubaki/orcaslicer-hole-reinforcement-plugin/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/furutsubaki/orcaslicer-hole-reinforcement-plugin/releases/tag/v0.1.0
