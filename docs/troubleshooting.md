# トラブルシューティング

穴が検出されない、想定外の場所が補強される、といった場合の切り分け手順です。

## まず設定値を実寸と突き合わせる

**重要**: 径と深さが設定範囲を外れた穴は、候補に入る前の段階で捨てられます。除外理由は診断ファイルに記録されないため、「診断に何も出ない＝検出処理が動いていない」とは限りません。

診断を見る前に、対象の穴について次を確認してください。

| 設定 | 確認すること |
| --- | --- |
| `min_hole_diameter_mm` / `max_hole_diameter_mm` | 穴径がこの範囲に収まっているか。円は直径、多角形は対辺寸法で判定する |
| `min_hole_depth_mm` | 穴の深さがこの値以上か |
| `enabled_shapes` | その穴の断面形状が有効になっているか |
| `enabled_end_kinds` | 貫通穴・止まり穴の該当する側が有効になっているか |
| `solid_reinforcement` | `false`だと検出だけ行い、スライス結果を変更しない |

寸法は**造形座標**で評価されます。モデルを拡大縮小して配置している場合は、拡縮後の実寸で比較してください。

## 診断ファイルを読む

### 有効化と場所

設定の`diagnostics_enabled`を`true`にすると、実行ごとの構造化ログがJSON Lines形式で記録されます。macOSでの場所は次のとおりです。

```
~/Library/Application Support/OrcaSlicer/orca_plugins/orcaslicer_hole_reinforcement-1-py3-none-any.whl/__whl_extracted__/orcaslicer_hole_reinforcement/orcaslicer_hole_reinforcement/diagnostic.jsonl
```

単一ファイルを5MiB上限で再利用します。上限へ達すると先頭から書き直すため、古い記録は残りません。切り分けたいスライスの**直前にファイルを退避**してから実行すると読みやすくなります。

書き込みに失敗した場合は診断だけを破棄してスライスを続行するため、権限の問題でファイルが増えないこともあります。

### レコードの形

1行が1イベントです。

```json
{"timestamp":"...","level":"info","code":"hole_end_classified","message":"穴端を分類しました","details":{...}}
```

`level`は`info`、`warning`、`error`のいずれかです。現在の実装が実際に出すのは`info`と`warning`だけなので、まず`warning`の行から見てください。

`code`が`diagnostic_event_truncated`の行は、詳細が大きすぎて省略されたイベントです。`details.original_code`に元のイベント名が入ります。

### イベント一覧

| `code` | `level` | 意味と主な`details` |
| --- | --- | --- |
| `volume_detection_skipped` | info | 検出対象外のボリュームを除外した。`reason`（例: `unsupported_volume_role`） |
| `volume_detection_completed` | info | ボリューム単位の検出完了。`candidate_count`、`accepted_count`、`excluded_count`、`analysis_seconds`、`vertex_count`、`triangle_count`、`cache_hit` |
| `hole_end_classified` | info / warning | 穴端を分類した。`accepted`が`false`なら`warning`になる |
| `hole_end_uncertain` | warning | 穴端を確定できなかった |
| `object_detection_completed` | info | オブジェクト単位の検出完了。`volume_count`、`candidate_count`、`accepted_count`、`excluded_count` |
| `reinforcement_completed` | info | ソリッド補強の完了。`reinforced_layer_count`、`target_region_count`、`solid_surface_count`、`changed_collection_count`、`reinforced_layers` |
| `config_migrated` | info | 旧バージョンの設定を引き継いだ。`source_plugin_key`、`source_plugin_version`、`rejected_count`、`stored`（保存できたか） |
| `config_migration_skipped` | info | 引き継ぎ元が見つからず既定値で動作する。`reason`（`no_host_config` / `no_donor`）、`rejected_count` |
| `config_migration_failed` | warning | ホストの設定ファイルを読めず既定値で動作する。`reason`（`unreadable`） |
| `preset_override_stale` | warning | プリセットに旧バージョン向けの設定が残っており参照されていない。`plugin_keys` |
| `preset_scan_completed` | info | 設定画面を開いたときのプリセット読み取り結果。`own_plugin_key`、`preset_count`、`values`（項目ごとの型と先頭120文字）、`stale_overrides`、失敗時は`error` |

`hole_end_classified`と`hole_end_uncertain`の`details`には、候補の`shape`、`side_count`、`diameter_mm`、`depth_mm`、`center_mm`、`axis`、`confidence`に加え、`start_state`、`end_state`、`end_kind`、`accepted`、`reason`が入ります。`center_mm`で「モデルのどの穴の話か」を特定できます。

`reinforcement_completed`の`reinforced_layers`には、補強したレイヤごとに`layer_index`、`print_z_mm`、`region_count`、`bbox_mm`が入ります。プレビューで補強が見当たらないときは、ここの`print_z_mm`とプレビューのレイヤ高さを突き合わせてください。

どのイベントにも、対象オブジェクトを特定するための`print_object_id`と`model_object_id`が付きます。名前を取得できたときは`model_object_name`が、取得できなかったときは代わりに`model_object_attributes`（ホスト側で参照できた属性名の一覧）が入ります。配置座標を取得できたときは`object_origin_mm`も付きます。

`model_object_id`は実行時IDで3mfのidとは別体系なので、モデルとの対応付けには`model_object_name`か`object_origin_mm`を使ってください。

ボリューム単位のイベント（`volume_detection_skipped`、`volume_detection_completed`と、その配下の`hole_end_*`）には、さらに`volume_id`、`volume_index`、`volume_role`が付きます。

### 除外理由コード

`hole_end_classified`と`hole_end_uncertain`の`details.reason`に入ります。

| `reason` | 意味 | 対処 |
| --- | --- | --- |
| `both_ends_open` | 両端が開いた貫通穴として分類した | 採用時の理由。`accepted`が`false`なら`enabled_end_kinds`を確認 |
| `one_end_closed` | 一端が閉じた止まり穴として分類した | 同上 |
| `both_ends_closed` | 両端が閉じている | 内部空洞であり穴として扱わない。仕様どおり |
| `incomplete_or_non_manifold_rim` | 穴の縁が全周にわたって多様体接続していない | メッシュの破損。CADから再エクスポートするか、メッシュ修復を掛ける |
| `through_disabled` | 貫通穴として分類したが設定で無効 | `enabled_end_kinds`に`through`を追加する |
| `blind_disabled` | 止まり穴として分類したが設定で無効 | `enabled_end_kinds`に`blind`を追加する |

## 症状別の切り分け

### 穴が検出されない

1. 設定値と実寸を突き合わせる（本書冒頭）。ここで外れていれば診断には何も出ない
2. `object_detection_completed`の`candidate_count`を見る
   - `0`なら形状検出の段階で候補が立っていない。断面が真円・正多角形から許容差以上にずれている可能性がある。`circle_radial_tolerance_mm`、`polygon_edge_length_tolerance_percent`、`polygon_angle_tolerance_deg`を緩めて再試行する
   - `0`でなく`accepted_count`が`0`なら穴端分類で落ちている。`hole_end_*`の`reason`を見る
3. `volume_detection_skipped`が出ていれば、そのボリュームが検出対象外（モディファイヤやサポート用ボリュームなど）と判断されている

### 穴ではない窪みまで補強される

- `min_hole_depth_mm`を上げて浅い窪みを除外する
- `max_hole_diameter_mm`を下げて大きな座ぐりを除外する
- 形状の許容差を締める。許容差を緩めていると、丸みを帯びた凹形状が円と判定されやすくなる
- `hole_end_classified`の`center_mm`と`diameter_mm`で、実際にどこが拾われたかを特定してから設定を調整する

### 補強がプレビューに現れない

1. `solid_reinforcement`が`true`か確認する
2. `reinforcement_completed`の`solid_surface_count`を見る。`0`なら補強対象のSurfaceがなかった
3. GUIでスライスしているか確認する。CLIではプラグインが読み込まれない
4. 穴の周囲がもともとOrcaSlicer標準の内部ソリッドやブリッジで埋まっている場合、補強を掛けても見た目が変わらないことがある。この場合`solid_surface_count`は`0`より大きいのにプレビュー差分が出ない

### スライスが`FatalError`で止まる

設定が不正な状態です。UIの入力制御とは別に、スライス処理の入口でも同じ検証を行うため、設定ファイルを直接編集した場合などに起こります。設定画面で「既定値に戻す」を実行してください。

### 更新後に「現在のプリセットに必要なローカルプラグインが見つかりません」と出る

**現在のバージョンではこの症状は起きません。** wheelのファイル名を固定し、プラグインの識別キーがリリース間で変わらないようにしたためです（[ADR 0003](adr/0003-fix-wheel-version-for-stable-plugin-key.md)）。以下は、ファイル名を固定する前の開発版（`0.0.1`〜`0.2.0`）から更新した場合にだけ該当します。

プリセットはプラグインの参照を`plugins`項目へバージョン込みで記録します（`orcaslicer_hole_reinforcement-<version>-py3-none-any;;Hole Reinforcement`）。更新するとこの参照が外れ、OrcaSlicerの`PluginResolver`が解決できないプラグインとして扱います。

- モデルを読み込むと通知が出て、**スライスがブロックされます**
- プロセス設定の「プラグイン設定」にも何も表示されません

プロセス設定の「スライスパイプラインプラグイン」でプラグインを選び直し、プリセットを保存してください。`plugins`は保存時に再生成されます。

これはOrcaSlicer本体の挙動で、プラグイン側からは検知も通知もしていません。

### 更新後に設定が既定値へ戻っている

更新後の初回読み込み時に旧バージョンのエントリから設定を引き継ぎますが、次の場合は引き継がれません。`config_migration_*`は`diagnostics_enabled`の設定に依らず記録されるため、診断が無効のままでも`diagnostic.jsonl`を確認できます。

1. `diagnostic.jsonl`に`config_migrated`があるか確認する。あれば引き継ぎは成功しており、`source_plugin_key`が引き継ぎ元を示す
2. `config_migration_skipped`で`reason`が`no_host_config`の場合、`orca_plugins/config.json`が見つからない。どのプラグインもまだ設定を保存していない環境ではファイル自体が無いため、旧バージョンで設定を保存した覚えがなければ正常である。心当たりがある場合は、プラグインをwheelから正規の手順でインストールしたか確認する
3. `reason`が`no_donor`の場合、引き継ぎ元のエントリが無い。`orca_plugins/config.json`に`"capability": "Hole Reinforcement"`のエントリが残っているか確認する。`rejected_count`が`1`以上なら、エントリはあるが現在のスキーマで検証を通らなかった（設定ファイルを直接編集した、または未対応の新しい形式）。`config.json`はあるが`config`配列を持たない場合もここに入る
4. `config_migration_failed`の場合、`config.json`が壊れているか読み取れない

プリセット側で上書きした値（プリセットoverride）は引き継ぎの対象外です。OrcaSlicerはoverrideもプラグインのバージョンごとに保持しますが、プラグインへ公開されているプリセットAPIは読み取り専用で、書き戻して復元できません。更新後に設定し直してください。

旧バージョン向けのoverrideが残っていると、設定画面の上部に警告が出て、診断へ`preset_override_stale`（対象の`plugin_keys`付き）が記録されます。値そのものはプリセットに残っているため、`user/<プロファイル>/process/<プリセット>.json`の`print_plugin_config_overrides`を開けば元の値を確認できます。

### `preset_override_stale`の警告が消えない

**プラグインの設定画面で値を直しても、この警告は消えません。** 設定画面が書き込むのは`orca_plugins/config.json`で、プリセットのoverrideとは別の保存先だからです。

消すには**プリセットのプラグイン設定**（プロセス設定側）で値を入力し直してください。現在の`plugin_key`でエントリが追加され、警告は出なくなります。

古いエントリ自体はプリセットに残り続けます。OrcaSlicerの`prune_unreferenced()`は型と名前で判定するため刈り取られず、プラグインへ公開されているプリセットAPIは読み取り専用で削除もできません。ただし現在のキーのエントリがあれば、失われる値は無いためプラグインは警告しません。完全に消したい場合は`user/<プロファイル>/process/<プリセット>.json`の`print_plugin_config_overrides`から該当エントリを手で削除してください。

## 報告するとき

不具合を報告する場合は次を添えてください。

- OrcaSlicerのバージョンとビルド、OS
- プラグインのバージョン（設定画面の見出し、スライス完了時のメッセージ、`diagnostic.jsonl`の`plugin_version`のいずれかで確認できます。プラグイン一覧や`Plugin Info`タブに出るのはメジャーバージョンだけなので、そちらの値では足りません）
- 該当スライスの`diagnostic.jsonl`（`diagnostics_enabled`を`true`にして再現させたもの）
- 再現するモデル（STLまたは3mf）と、設定値
