# OrcaSlicer穴補強プラグイン

## 正式版パッケージ

正式版は`src/orcaslicer_hole_reinforcement/`にあり、次のコマンドでOrcaSlicerへローカルインストールできるwheelを生成します。

```bash
uvx --from 'hatchling==1.27.0' hatchling build -t wheel
```

生成された`dist/orcaslicer_hole_reinforcement-<version>-py3-none-any.whl`を、OrcaSlicerのプラグイン画面から選択します。対応保証対象はコミット`f5f3d2221dd929360407aa2ae6759302a8d2c575`です。

正式公開までは配布バージョンを`0.0.1`に固定します。

OrcaSlicerなしのテストは次のコマンドで実行します。

```bash
PYTHONPATH=src python3 -m unittest discover -s tests -v
```

正式版は責務ごとにモジュールを分けています。

- `plugin.py`:パッケージ登録
- `slicing_capability.py`:OrcaSlicerスライスI/F
- `config.py`:設定I/F
- `detection.py`:3D穴検出I/F
- `reinforcement.py`:2D補強計画I/F
- `diagnostics.py`:診断出力I/F

設定、検出、補強、診断の各モジュールは`orca`をimportせず、通常のPythonでテストできます。現時点の正式版capabilityはパッケージ構成だけを提供し、検出や補強を行わず`skipped`を返します。機能は後続issueで追加します。

設定の型、既定値、有効範囲、互換性方針は[`docs/configuration.md`](docs/configuration.md)を参照してください。

## PoC

OrcaSlicer Nightly版`f5f3d22`向けに、垂直円穴の検出条件を検証する試作です。現段階ではスライス形状を変更しません。

## 検証する問い

`Step.posSlice`で得られる各レイヤーの穴輪郭から、直径10mm以下の垂直円穴を、円形度と3レイヤー以上の連続性によって安定して識別できるかを確認します。

## テストモデル

次の1コマンドで`test-models/vertical-hole-test.stl`を生成します。

```bash
python3 tools/generate_test_model.py
```

モデルは高さ12mmの円筒を3個並べたもので、穴径は4mm、9mm、14mmです。既定値では4mmと9mmの2穴だけが検出対象です。スライス設定による穴補正後の輪郭で判定するため、上限と同じ10mmは境界値テストに使いません。

## Nightly版への導入

1. OrcaSlicer Nightly版で「プラグイン」画面を開く
2. ローカルプラグインのインストールを選ぶ
3. `hole_reinforcement_detector_poc.py`を選ぶ
4. 「Hole Reinforcement Detector PoC」を有効化する
5. テストモデルを読み込み、スライスする

通常の実行結果は検出数と補強Surface数だけを簡潔に返します。診断を有効にすると、モデル・ボリューム識別子、候補の形状・寸法・軸・穴端・信頼度・除外理由、補強レイヤー数・Surface数・対象領域数を、インストール済みプラグインと同じディレクトリの`diagnostic.jsonl`へJSON Lines形式で記録します。ファイルは5MiBを上限に再利用し、書き込み失敗はスライス処理へ影響させません。

## 既定値

- `max_hole_diameter_mm`:10.0
- `reinforcement_width_mm`:2.0（形状変更段階で使用予定）
- `min_continuous_layers`:3
- `circularity_tolerance`:0.10
- `solid_reinforcement`:0.0（`1.0`で穴周辺をソリッド化）
- `extra_perimeters`:0（未実装）

## 参照したI/F

実装はOrcaSlicer公式ソースの`f5f3d22`に固定して確認しています。

- [Insetサンプル](https://github.com/OrcaSlicer/OrcaSlicer/blob/f5f3d22/sandboxes/orca_inset_plugin_any.py)
- [形状I/F](https://github.com/OrcaSlicer/OrcaSlicer/blob/f5f3d22/src/slic3r/plugin/host/PluginHostGeometry.cpp)
- [スライスI/F](https://github.com/OrcaSlicer/OrcaSlicer/blob/f5f3d22/src/slic3r/plugin/host/PluginHostSlicing.cpp)
- [ローカルインストール処理](https://github.com/OrcaSlicer/OrcaSlicer/blob/f5f3d22/src/slic3r/GUI/PluginsDialog.cpp#L802-L815)
