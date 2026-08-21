# 設定スキーマ

正式版の設定はJSON objectとして保存し、`schema_version`で互換性を判定する。現在のスキーマバージョンは`2`である。

OrcaSlicerのプラグイン設定画面では独自GUIを使用する。有効な変更は入力直後に自動保存する。不正値は保存せず、画面上に修正方法と未保存状態を表示する。「既定値に戻す」は下表の値を全項目へ復元する。UIとは別に、スライス処理の入口でも同じスキーマを検証する。

プラグインを更新すると、OrcaSlicerは設定をバージョン入りの`plugin_key`で保持するため新しいエントリになる。更新後の初回読み込み時（`on_load()`）に、`orca_plugins/config.json`から`capability`が一致する旧エントリを読み取り、本スキーマの検証を通った最新バージョンの値を引き継いで保存する。OrcaSlicerはこの直後に既定値を初期投入するが、引き継ぎで保存済みならスキップされる。引き継ぎ元が無い、読めない、検証を通らない場合は既定値で動作する。引き継げるのはプラグイン設定画面で保存した値だけで、プリセットoverrideは対象外である（ホストのプリセットAPIは読み取り専用で書き戻せない）。旧バージョン向けのoverrideが残っている場合は設定画面へ警告を出し、診断へ`preset_override_stale`を記録する。プリセットの`plugins`もcapability参照をバージョン込みで持つが、こちらはOrcaSlicer本体の`PluginResolver`が検知して通知し、スライスをブロックするため、プラグイン側では扱わない。判断の経緯は`docs/adr/0002-preserve-config-across-plugin-updates.md`を参照。

独自GUIはOrcaSlicer本体のライト／ダークテーマへ追従する。表示言語は本体の言語設定から取得し、日本語には日本語、英語には英語を使用する。未対応言語または言語取得失敗時は英語を使用する。

| キー | 型 | 既定値 | 有効範囲・候補 | 単位 |
| --- | --- | --- | --- | --- |
| `schema_version` | integer | `2` | `1`、`2`（`1`は読込時に`2`へ移行） | なし |
| `min_hole_diameter_mm` | number | `0.5` | `0.1`〜`100.0` | mm |
| `max_hole_diameter_mm` | number | `10.0` | `0.1`〜`100.0` | mm |
| `reinforcement_width_mm` | number | `2.0` | `0.1`〜`20.0` | mm |
| `min_hole_depth_mm` | number | `1.0` | `0.1`〜`1000.0` | mm |
| `enabled_shapes` | string array | `circle, hexagon, octagon, regular_polygon` | 1つ以上の`circle`、`hexagon`、`octagon`、`regular_polygon` | なし |
| `enabled_end_kinds` | string array | `through, blind` | 1つ以上の`through`、`blind` | なし |
| `circle_radial_tolerance_mm` | number | `0.1` | `0.0`〜`1.0` | mm |
| `polygon_edge_length_tolerance_percent` | number | `5.0` | `0.0`〜`25.0` | % |
| `polygon_angle_tolerance_deg` | number | `2.0` | `0.0`〜`15.0` | ° |
| `min_polygon_sides` | integer | `3` | `3`〜`64` | なし |
| `max_polygon_sides` | integer | `64` | `3`〜`64` | なし |
| `axis_tolerance_deg` | number | `2.0` | `0.0`〜`15.0` | ° |
| `solid_reinforcement` | boolean | `true` | `true`、`false` | なし |
| `diagnostics_enabled` | boolean | `true` | `true`、`false` | なし |

`diagnostics_enabled`が`true`の場合、実行ごとの構造化診断をインストール済みプラグインと同じディレクトリの`diagnostic.jsonl`へ記録する。単一ファイルを5MiB上限で再利用し、書き込み不能な環境では診断だけを破棄してスライスを継続する。`false`の場合は診断ファイルへアクセスしない。

すべての数値境界を含む。`min_hole_diameter_mm`は`max_hole_diameter_mm`以下、`min_polygon_sides`は`max_polygon_sides`以下でなければならない。JSONの`true`と`false`だけをbooleanとして扱い、`0`、`1`、文字列への暗黙変換は行わない。NaNとInfinityも拒否する。

対応穴の契約における`Dmin`、`Dmax`、`Lmin`、`Tc`、`Te`、`Ta`は、それぞれ`min_hole_diameter_mm`、`max_hole_diameter_mm`、`min_hole_depth_mm`、`circle_radial_tolerance_mm`、`polygon_edge_length_tolerance_percent`、`polygon_angle_tolerance_deg`に対応する。

## 不正値の扱い

- 欠落キーは現在の既定値で補う。
- 未知キー、未知の選択肢、空または重複した配列は拒否する。
- 型違い、範囲外、相関違反が1つでもあれば設定全体を不採用にする。
- 不正設定を検出した`posSlice`または`posPrepareInfill`は`FatalError`を返し、検出や補強へ進まない。
- UIの入力制御だけに依存せず、スライス処理の入口で同じ検証を行う。

## バージョン方針

- `schema_version`欠落は現在のスキーマとして扱う。`1`は正多角形設定を既定値で補い、`2`へ移行する。
- 現在値と異なるバージョンは自動解釈せず拒否する。
- 後方互換なキー追加でもスキーマを更新し、欠落時の既定値を定義する。
- 名前変更、型変更、単位変更、意味変更では明示的な移行関数と旧バージョンの回帰テストを追加する。
- 移行に失敗した設定は上書きせず、スライス処理を開始しない。
