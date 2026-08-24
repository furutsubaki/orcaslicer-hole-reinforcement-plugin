# OrcaSlicer穴補強プラグイン

モデルに空いた小さな穴を自動で見つけて、その周囲の内部インフィルをソリッド化するOrcaSlicerプラグインです。ネジ穴やピン穴のように力が掛かる穴の周りだけを密にできるため、造形物全体のインフィル密度を上げずに強度を稼げます。

OrcaSlicer本体はフォークも改変もしません。Nightly版のPythonプラグインAPIを使い、通常のプラグインとしてインストールします。

## 対応範囲

### OrcaSlicer

| 項目 | 値 |
| --- | --- |
| API基準コミット | [`f5f3d2221dd929360407aa2ae6759302a8d2c575`](https://github.com/OrcaSlicer/OrcaSlicer/commit/f5f3d2221dd929360407aa2ae6759302a8d2c575) |
| 実機検証ビルド | Nightly `2.5.0-dev` / Build `872c660c` |

安定版と、上記以外のNightlyは未対応です。プラグインAPIは実験的で互換性が保証されていないため、同じI/Fが存在しても検証が済むまで対応と扱いません。判定基準は[`docs/adr/0001-orcaslicer-plugin-api-baseline.md`](docs/adr/0001-orcaslicer-plugin-api-baseline.md)にあります。

コミットとビルドを両方載せているのは、**この2つが別体系で、片方だけでは再現できない**ためです。API基準コミットはプラグインI/Fの契約が変わっていないかを判定するためのソース上の基準点、実機検証ビルドは実際に動作を確認したバイナリです。Nightlyビルドは特定のコミットへ一対一で対応しないため、両方を突き合わせる必要があります。

**OrcaSlicerのCLI（`--slice`）ではプラグインが読み込まれません。** 補強を効かせるにはGUIでスライスしてください。

### OS

| 状態 | OS |
| --- | --- |
| 検証済み | macOS 26.6.1（Apple Silicon） |
| 未検証 | Windows、Linux |

配布物はOS非依存のpure Python wheelなので他OSでも動作する可能性はありますが、実機検証をしていないため動作は保証しません。

### 穴

| 項目 | 対応 |
| --- | --- |
| 断面形状 | 円、正六角形、正八角形、正n角形（辺数は設定可能） |
| 穴の向き | 造形プレートに対して`0°`（水平）から`90°`（垂直）の全範囲 |
| 穴端 | 貫通穴、止まり穴（底面が平面のもの） |
| 径 | 設定した下限〜上限の範囲内。円は直径、多角形は対辺寸法で判定 |

判定条件の詳細は[`docs/supported-hole-contract.md`](docs/supported-hole-contract.md)を参照してください。

## インストール

1. wheelを用意します。リリースページから入手するか、[開発者向け](#開発者向け)の手順でビルドします
2. OrcaSlicer Nightlyを起動し、「プラグイン」画面を開きます
3. ローカルプラグインのインストールを選び、`orcaslicer_hole_reinforcement-1-py3-none-any.whl`を指定します
4. OrcaSlicerを再起動します

### 更新するとき

**新しいwheelをインストールするだけです。** 設定もプリセットの設定もそのまま引き継がれ、プラグインを選び直す必要はありません。

wheelのファイル名に入るのは**メジャーバージョンだけ**です（`1.0.0`でも`1.4.2`でも`-1-`）。OrcaSlicerはインストール元ファイル名でプラグインを識別するため、名前が変わると別のプラグインとして扱われ、設定が失われてプリセットの参照も外れてしまいます。判断の経緯は[`docs/adr/0003-fix-wheel-version-for-stable-plugin-key.md`](docs/adr/0003-fix-wheel-version-for-stable-plugin-key.md)にあります。

**OrcaSlicerが表示するのもメジャーバージョンだけです。** プラグイン一覧の`Plugin Version`列と、`Plugin Info`タブの`Installed Version`・`Latest Version`に`1`と出ます。ホストへ完全なバージョンを伝えるI/Fがプラグイン側に無いため、この表示は変えられません。

完全なバージョンは次の3箇所で確認できます。

- プラグインの設定画面（見出しの右に表示）
- スライス完了時のメッセージ
- `diagnostic.jsonl`の各レコードの`plugin_version`

#### メジャーバージョンが上がるとき

破壊的変更のときだけ、ファイル名が`-2-`のように変わります。このときは旧版のアンインストールと、プロセス設定でのプラグインの選び直しが必要です。リリースノートで明示します。

#### 公開前の開発版（`0.0.1`〜`0.2.0`）から更新する場合

ファイル名を固定する前のバージョンから更新するときだけ、次の点にご注意ください。

- 旧版は先にアンインストールしてください。残すと別プラグインとして並存します
- 設定は自動で引き継がれます。更新後の初回読み込み時に旧エントリを読み取り、設定画面にもスライスにも引き継いだ値が使われます
- **プリセット側で上書きした値（プリセットoverride）は引き継げません。** OrcaSlicerがプラグインのバージョンごとに保持し、プラグインへ書き戻すAPIも公開していないためです。更新後に設定し直してください
- 旧バージョン向けのoverrideが残っている間は、設定画面の上部に警告が出て、診断へ`preset_override_stale`が記録されます。該当プリセットのoverrideを設定し直すと消えます
- プロセス設定の「スライスパイプラインプラグイン」でプラグインを選び直し、プリセットを保存してください。開発版のプリセットはプラグインの参照をバージョン込みで持つため、この一度だけ選び直しが必要です

引き継ぎに失敗した場合は既定値で動作し、スライスは妨げません。

## 有効化

プラグイン画面の一覧から「Hole Reinforcement」を有効にします。有効な状態でGUIからスライスすると、検出した穴の数と補強したSurface数がスライス結果に表示されます。

## 設定

プラグイン画面から「Hole Reinforcement」の設定を開くと、専用の設定画面が出ます。OrcaSlicer本体のライト／ダークテーマと表示言語（日本語・英語）に追従します。

有効な変更は入力した時点で自動保存されます。不正な値は保存されず、画面上に修正方法が表示されます。「既定値に戻す」で全項目を初期値へ戻せます。

主な設定項目は次のとおりです。

| 項目 | 既定値 | 単位 | 意味 |
| --- | --- | --- | --- |
| `min_hole_diameter_mm` | `3.0` | mm | 補強対象とする穴径の下限。これより小さい穴は無視する |
| `max_hole_diameter_mm` | `10.0` | mm | 補強対象とする穴径の上限。これより大きい穴は無視する |
| `reinforcement_width_mm` | `3.0` | mm | 穴の周囲をソリッド化する幅。大きくするほど強度と造形時間・材料使用量が増える |
| `min_hole_depth_mm` | `2.0` | mm | 補強対象とする穴の深さの下限。浅い窪みを穴と誤認しないための下限 |
| `enabled_shapes` | 全4種 | — | 対象とする断面形状。`circle`、`hexagon`、`octagon`、`regular_polygon` |
| `enabled_end_kinds` | `through`, `blind` | — | 対象とする穴端。貫通穴のみ、止まり穴のみへ絞れる |
| `solid_reinforcement` | `true` | — | `false`にすると検出だけ行い、スライス結果を変更しない |
| `diagnostics_enabled` | `true` | — | 検出・補強の詳細を`diagnostic.jsonl`へ記録する |

`reinforcement_width_mm`は**穴の壁面から外側へ測る距離**です。直径ではありません。径3.4mmの穴に幅3.0mmなら、ソリッド化される領域の外径は9.4mmになります。

既定値は**0.4mmノズルで、M3〜M8のボルトとナットで固定する部品**を想定しています。

- 径の下限3.0mmはM3のクリアランス穴（3.2〜3.4mm）を含む値です。それより小さい穴は締結に使わないと判断して無視します
- 径の上限10.0mmはM8のクリアランス穴（8.4〜9.0mm）に余裕を持たせた値です
- 補強幅3.0mmは、M8ナットの二面幅13mmが穴壁から張り出す2.0mmを上回り、ワッシャー外径16mmの張り出し3.5mmにほぼ届く値です。座面が乗る範囲をソリッドで支えられます
- 深さの下限2.0mmは、M3が締結として機能する最小板厚です。それより浅い窪みを補強しても強度に寄与しません

ネジを直接ねじ込むタップ穴や、M2・M2.5のような小径ネジを使う場合は`min_hole_diameter_mm`を下げてください。補強幅を広げるほど強度は上がりますが、造形時間と材料使用量も増えます。

形状の許容差（`circle_radial_tolerance_mm`など）を含む全項目の型、有効範囲、互換性方針は[`docs/configuration.md`](docs/configuration.md)にあります。

## 無効化と削除

- **一時的に止める**: プラグイン画面で「Hole Reinforcement」を無効にします。無効にすると通常のスライス結果に戻ります
- **補強だけ止めて検出は続ける**: 設定の`solid_reinforcement`を`false`にします。診断だけ取りたいときに使います
- **削除する**: プラグイン画面からアンインストールし、OrcaSlicerを再起動します

## 既知の制約

- OrcaSlicerの実験的なプラグインAPIに依存しており、対応コミット以外では動作しないか、動作しても結果を保証しません
- CLIスライスではプラグイン機構自体が初期化されないため、補強が掛かりません
- テーパー穴、長円穴、ねじ山付きの穴、星形などの異形穴は対象外です
- 止まり穴の底面は平面のみ対応します。円錐底、ドリル先端形状、段付き穴、座ぐり、皿穴は対象外です
- 両端が閉じた内部空洞、開口が断面の全周に満たない窪みは穴として扱いません
- 非多様体メッシュでは穴端を確定できず、その穴は補強されません
- モディファイヤやサポート用ボリュームに開いた穴は対象外です
- 径や深さが設定範囲を外れた穴は候補にすら入らないため、除外理由が診断ファイルに記録されません（[トラブルシューティング](docs/troubleshooting.md)を参照）

次の2つは、意図してスコープ外にしています。

- **局所インフィル密度を任意の割合に変更する機能**。本プラグインが行うのは内部インフィルのソリッド化だけです。穴の周囲だけを「40%にする」といった中間的な密度指定はできません
- **OrcaSlicer安定版への未対応APIのバックポート**。本体をフォークも改変もしない方針のため、安定版にプラグインAPIが入るまで安定版へは対応しません

## うまく動かないとき

検出されない、想定外の場所が補強される、といった場合の切り分け手順は[`docs/troubleshooting.md`](docs/troubleshooting.md)にまとめています。

## 開発者向け

wheelをビルドします。

```bash
uv build --wheel
```

`dist/orcaslicer_hole_reinforcement-1-py3-none-any.whl`が生成されます。ファイル名の`1`はメジャーバージョンです（[ADR 0003](docs/adr/0003-fix-wheel-version-for-stable-plugin-key.md)）。`src/orcaslicer_hole_reinforcement/version.py`が`__wheel_version__`（メジャー）と`__version__`（完全なバージョン）の両方を持ち、ズレは`tests/test_package_metadata.py`が検証します。

OrcaSlicerなしでテストを実行します。

```bash
PYTHONPATH=src python3 -m unittest discover -s tests -v
```

文書の相対リンクを検証します。

```bash
python3 tools/check_doc_links.py
```

PRを出すと、この2つとwheelのビルドをGitHub Actionsが実行します（[`.github/workflows/pr-check.yml`](.github/workflows/pr-check.yml)）。

パッケージは責務ごとにモジュールを分けています。

| モジュール | 役割 |
| --- | --- |
| `plugin.py` | パッケージ登録 |
| `slicing_capability.py` | OrcaSlicerスライスパイプラインとの接続 |
| `config.py` / `config_ui.py` | 設定スキーマと設定画面 |
| `mesh_extraction.py` / `cylinder_detection.py` / `polygon_detection.py` / `candidate_detection.py` / `end_classification.py` / `detection.py` | 3D穴検出 |
| `reinforcement.py` | 補強領域を各レイヤ平面の2D形状として計画する |
| `solid_reinforcement.py` | 計画した領域のSurfaceを内部ソリッドへ差し替える |
| `orca_geometry.py` | OrcaSlicerのscaled座標2D幾何とmm値を相互変換する |
| `analysis.py` | 解析結果のキャッシュ |
| `diagnostics.py` | 診断出力 |

`orca`をimportするのは`plugin.py`、`slicing_capability.py`、`orca_geometry.py`、`solid_reinforcement.py`の4つです（`__init__.py`も存在確認のためだけに読み込みます）。設定、検出、補強計画、診断は`orca`に依存せず、通常のPythonとしてテストできます。

関連文書:

- [解析コストの計測](docs/performance.md) — 処理時間、メモリ、キャッシュ効果のベンチマーク手順
- [テストフィクスチャ](docs/test-fixtures.md) — 方向・形状・穴端・境界・誤検出用のSTL一覧
- [OrcaSlicer実機での統合検証](docs/orcaslicer-integration-verification.md) — ON/OFF比較によるツールパス差分の検証手順
- [検出アルゴリズム](docs/detection-algorithm.md) — 3Dメッシュから穴を識別する手順
- [公開前チェックリスト](docs/release-checklist.md) — リリース手順

## ライセンス

MIT License。[`LICENSE`](LICENSE)を参照してください。

依存関係と第三者コードの状況は[`docs/third-party-licenses.md`](docs/third-party-licenses.md)にまとめています。
