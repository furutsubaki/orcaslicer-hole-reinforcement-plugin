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
3. ローカルプラグインのインストールを選び、`orcaslicer_hole_reinforcement-0.1.0-py3-none-any.whl`を指定します
4. OrcaSlicerを再起動します

### 更新するとき

OrcaSlicerはプラグイン設定をバージョン入りのキー（`orcaslicer_hole_reinforcement-<version>-py3-none-any`）で保存するため、更新後は別のエントリになります。本プラグインは、更新後の初回読み込み時（OrcaSlicerの起動時、またはインストール直後）に旧エントリを読み取り、設定を自動で引き継ぎます。設定画面には引き継いだ値が表示され、そのままスライスにも使われます。

引き継げるのはプラグイン設定画面で保存した値だけです。プリセット側で上書きした値（プリセットoverride）は、OrcaSlicerがプラグインのバージョンごとに保持し、プラグインへ書き戻すAPIも公開していないため引き継げません。更新後に設定し直してください。

**更新後は、プロセス設定の「スライスパイプラインプラグイン」でプラグインを選び直し、プリセットを保存してください。** プリセットはプラグインの参照をバージョン込みで記録するため、更新すると参照が外れます。

この状態はOrcaSlicer本体が検知します。モデルを読み込むと「現在のプリセットに必要なローカルプラグインが見つかりません」と通知が出て、**スライスがブロックされます**。プロセス設定のプラグイン設定にも何も表示されません。選び直してプリセットを保存すれば解消します。

旧バージョン向けの設定（プリセットoverride）が残っている場合は、こちらは本体が何も言わないため、プラグインの設定画面の上部に警告を表示し、診断へ`preset_override_stale`を記録します。引き継ぎに失敗した場合は既定値で動作し、スライスは妨げません。

旧版は先にアンインストールしてください。残したままだと別プラグインとして並存し、両方が有効になります。アンインストールしても旧バージョンの設定エントリは残るため、引き継ぎには影響しません。

## 有効化

プラグイン画面の一覧から「Hole Reinforcement」を有効にします。有効な状態でGUIからスライスすると、検出した穴の数と補強したSurface数がスライス結果に表示されます。

## 設定

プラグイン画面から「Hole Reinforcement」の設定を開くと、専用の設定画面が出ます。OrcaSlicer本体のライト／ダークテーマと表示言語（日本語・英語）に追従します。

有効な変更は入力した時点で自動保存されます。不正な値は保存されず、画面上に修正方法が表示されます。「既定値に戻す」で全項目を初期値へ戻せます。

主な設定項目は次のとおりです。

| 項目 | 既定値 | 単位 | 意味 |
| --- | --- | --- | --- |
| `min_hole_diameter_mm` | `0.5` | mm | 補強対象とする穴径の下限。これより小さい穴は無視する |
| `max_hole_diameter_mm` | `10.0` | mm | 補強対象とする穴径の上限。これより大きい穴は無視する |
| `reinforcement_width_mm` | `2.0` | mm | 穴の周囲をソリッド化する幅。大きくするほど強度と造形時間・材料使用量が増える |
| `min_hole_depth_mm` | `1.0` | mm | 補強対象とする穴の深さの下限。浅い窪みを穴と誤認しないための下限 |
| `enabled_shapes` | 全4種 | — | 対象とする断面形状。`circle`、`hexagon`、`octagon`、`regular_polygon` |
| `enabled_end_kinds` | `through`, `blind` | — | 対象とする穴端。貫通穴のみ、止まり穴のみへ絞れる |
| `solid_reinforcement` | `true` | — | `false`にすると検出だけ行い、スライス結果を変更しない |
| `diagnostics_enabled` | `true` | — | 検出・補強の詳細を`diagnostic.jsonl`へ記録する |

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
- 径や深さが設定範囲を外れた穴は候補にすら入らないため、除外理由が診断ファイルに記録されません（[トラブルシューティング](docs/troubleshooting.md)を参照）

## うまく動かないとき

検出されない、想定外の場所が補強される、といった場合の切り分け手順は[`docs/troubleshooting.md`](docs/troubleshooting.md)にまとめています。

## 開発者向け

wheelをビルドします。

```bash
uv build --wheel
```

`dist/orcaslicer_hole_reinforcement-0.1.0-py3-none-any.whl`が生成されます。

OrcaSlicerなしでテストを実行します。

```bash
PYTHONPATH=src python3 -m unittest discover -s tests -v
```

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
- [公開前チェックリスト](docs/release-checklist.md) — リリース手順

## ライセンス

MIT License。[`LICENSE`](LICENSE)を参照してください。

依存関係と第三者コードの状況は[`docs/third-party-licenses.md`](docs/third-party-licenses.md)にまとめています。
