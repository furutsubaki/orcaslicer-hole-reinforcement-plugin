# ADR 0001: OrcaSlicerプラグインAPIの対応基準を固定する

- Status: Accepted
- Date: 2026-08-20
- Deciders: プロジェクトメンテナー

## 文脈

本プラグインはOrcaSlicer本体を変更せず、Nightly版の実験的なPythonプラグインAPIを使用する。正式版では、スライスパイプライン、モデルスナップショット、3Dメッシュ、座標変換、独自設定UI、設定保存を組み合わせる。これらのI/Fは安定版APIとしての互換性が保証されていないため、「Nightly版」という名称だけでは対応範囲を再現できない。

## 決定

### 対応基準

初期の対応保証対象をOrcaSlicerコミット[`f5f3d2221dd929360407aa2ae6759302a8d2c575`](https://github.com/OrcaSlicer/OrcaSlicer/commit/f5f3d2221dd929360407aa2ae6759302a8d2c575)に固定する。

- 短縮SHA:`f5f3d22`
- コミット日時:`2026-08-19T17:47:34Z`
- これより前後のコミット、Nightly配布物、安定版は、同じI/Fが存在しても検証完了までは未対応とする。
- 配布文書にはOrcaSlicerのバージョン名だけでなく、完全なコミットSHAを記載する。

### スライスパイプライン

プラグインは`orca.slicing.SlicingPipelineCapabilityBase`を継承し、`execute(ctx)`から`orca.ExecutionResult`を返す。

| 項目 | 採用するI/Fと制約 |
| --- | --- |
| 検出タイミング | `Step.posSlice`で3D穴候補を検出する |
| 補強タイミング | `Step.posPrepareInfill`で内部Surfaceを分割、ソリッド化する。このステップは`prepare_infill`後、`make_fills`前であり、変更が後続のfill生成へ反映される |
| 実行スレッド | `execute(ctx)`はスライスワーカースレッドで実行される。デッドロックを避けるため`orca.host.ui.*`を呼ばない |
| キャンセル | 長いオブジェクト、ボリューム、三角形、レイヤーの反復中に`ctx.cancelled()`を確認し、要求後は速やかに処理を打ち切る |
| 参照寿命 | `ctx.print`、`ctx.object`、そこから得たスライスグラフの参照とNumPy viewは、その`execute(ctx)`呼び出し中だけ有効とする |
| 参照無効化 | `SurfaceCollection.set()`などコンテナを置換する操作の前に必要情報をコピーし、操作後に古い要素参照やviewを使わない |

2D補強計画のブーリアン演算には、`ExPolygon.offset()`、`union_ex()`、`diff_ex()`、`intersection_ex()`を使用する。mm単位の純粋な値とscaled整数座標は`orca.slicing.unscale(1)`を基準に相互変換し、外周と穴の所属および向きを`ExPolygon`単位で維持する。

`ctx.object`が存在するオブジェクト単位のステップだけで処理する。`ctx.print`または`ctx.object`が`None`になり得るステップへ処理を拡張する場合は、別途互換性を確認する。

参照:

- [`SlicingPipelinePluginCapability.hpp`](https://github.com/OrcaSlicer/OrcaSlicer/blob/f5f3d2221dd929360407aa2ae6759302a8d2c575/src/slic3r/plugin/pluginTypes/slicingPipeline/SlicingPipelinePluginCapability.hpp)
- [`SlicingPipelinePluginCapability.cpp`](https://github.com/OrcaSlicer/OrcaSlicer/blob/f5f3d2221dd929360407aa2ae6759302a8d2c575/src/slic3r/plugin/pluginTypes/slicingPipeline/SlicingPipelinePluginCapability.cpp)
- [`PluginHostSlicing.cpp`](https://github.com/OrcaSlicer/OrcaSlicer/blob/f5f3d2221dd929360407aa2ae6759302a8d2c575/src/slic3r/plugin/host/PluginHostSlicing.cpp)

### モデルスナップショット、メッシュ、座標変換

ワーカースレッドでは`orca.host.model()`のGUIモデルを参照せず、`ctx.object.model_object()`または`ctx.print.model()`からPrint所有のモデルスナップショットを取得する。

| データ | I/F | 契約 |
| --- | --- | --- |
| モデルオブジェクト | `ctx.object.model_object()` | Print所有のワーカースレッド安定スナップショットへの非所有参照 |
| ボリューム | `ModelObject.volume(index)` | モデルオブジェクト内部の非所有参照。`volume_count()`で範囲を決める |
| メッシュ | `ModelVolume.mesh()` | ローカル座標、mm単位のimmutableな`TriangleMesh`スナップショット |
| 頂点 | `TriangleMesh.vertices()` | 読み取り専用、zero-copyの`float32[N,3]`NumPy view |
| 三角形 | `TriangleMesh.triangles()` | 読み取り専用、zero-copyの`int32[M,3]`NumPy view |
| 面法線 | `TriangleMesh.face_normals()` | 正規化された`float32[M,3]`NumPy配列のコピー |
| volume変換 | `ModelVolume.matrix()` | volumeローカル座標からmodel object座標への4×4行列のコピー |
| print変換 | `ctx.object.trafo()` | model object座標からスライス時のprint座標への4×4行列のコピー |

スライス時の頂点は、列ベクトル表記で`ctx.object.trafo() @ volume.matrix() @ local_vertex`として求める。法線には同じ行列の平行移動を除いた逆転置行列を使い、負のスケールを含む変換では三角形の向きも検証する。`ModelInstance.matrix()`はGUI上のworld配置用であり、このスライス座標変換には混在させない。

メッシュのNumPy viewは元の`TriangleMesh`オブジェクトがbufferを保持するが、本プラグインではワーカースレッドの処理範囲を明確にするため、`execute(ctx)`を越えて保持しない。取得したメッシュを変更してはならない。

参照:

- [`PluginHostModel.cpp`](https://github.com/OrcaSlicer/OrcaSlicer/blob/f5f3d2221dd929360407aa2ae6759302a8d2c575/src/slic3r/plugin/host/PluginHostModel.cpp)
- [`PluginHostMesh.cpp`](https://github.com/OrcaSlicer/OrcaSlicer/blob/f5f3d2221dd929360407aa2ae6759302a8d2c575/src/slic3r/plugin/host/PluginHostMesh.cpp)

### 独自設定UIと設定保存

各capabilityは標準JSONエディタを利用できるが、正式版では次のI/Fで独自設定UIを提供する。

| I/F | 用途と制約 |
| --- | --- |
| `has_config_ui()` | `True`を返し、標準JSONエディタの代わりに独自UIを選択する |
| `get_config_ui()` | sandbox化されたframeへ埋め込むHTML断片を返す。空文字または例外時は標準JSONエディタへフォールバックする |
| `get_config()` | 有効なcapability設定をJSON文字列で取得する。未保存時は`"{}"`を返す |
| `get_config_version()` | 保存時のプラグインバージョンを取得し、設定移行の要否を判断する |
| `save_config(json.dumps(config))` | capability自身のグローバル設定を保存する。JSON不正または書き込み失敗時は`False`を返し、既存値を維持する |
| `get_default_config()` | 「既定値に戻す」で保存するobjectを返す。ホストはプラグイン固有の型、範囲、相関を検証しない |
| `window.orca.getConfig()` / `saveConfig()` | 独自HTMLとPluginsダイアログ間で同じ設定を読み書きするbridge |

設定はcapabilityの`plugin_key`、種別、名前、プラグインバージョンと共にOrcaSlicerのplugin設定へ保存される。プリセット側にcapability overrideがある場合、`get_config()`はoverrideを優先した有効値を返す。UIと実行処理は必ず同じ`get_config()`を起点にし、プラグイン側でスキーマ検証してから使用する。

独自HTMLはframe全体を所有し、保存・復元操作も`window.orca` bridgeで行う。スライス中の`execute(ctx)`からUIを開いたり更新したりしない。

参照:

- [`PythonPluginBridge.cpp`](https://github.com/OrcaSlicer/OrcaSlicer/blob/f5f3d2221dd929360407aa2ae6759302a8d2c575/src/slic3r/plugin/PythonPluginBridge.cpp)
- [`PluginConfig.cpp`](https://github.com/OrcaSlicer/OrcaSlicer/blob/f5f3d2221dd929360407aa2ae6759302a8d2c575/src/slic3r/plugin/PluginConfig.cpp)
- [`PluginsDialog`](https://github.com/OrcaSlicer/OrcaSlicer/tree/f5f3d2221dd929360407aa2ae6759302a8d2c575/resources/web/dialog/PluginsDialog)

## 互換性の判定方針

別のOrcaSlicerコミットを対応対象へ追加する場合は、次の順序で確認する。

1. 基準コミットとの差分から、上記参照ファイル、`PythonPluginInterface.hpp`、`SlicingPipelinePluginCapabilityTrampoline.hpp`、`PluginsDialog.cpp`の変更を抽出する。
2. 本ADRのI/F名、引数、戻り値、実行ステップ、スレッド、参照寿命、座標系、設定の保存先と優先順位が維持されているか確認する。
3. 読み取り専用メッシュ、NumPy view、変換行列の組み合わせが変わった場合は、同じシンボル名でも非互換候補とする。
4. 対象Nightlyへローカルpluginを新規インストールし、起動、設定表示、保存、復元、再起動後の保持を確認する。
5. 変換を含むテストモデルで検出し、`posPrepareInfill`の補強、キャンセル、再スライス、プラグイン無効化を確認する。
6. Python例外、OrcaSlicerのerror／warnログ、スライス失敗、非対象領域のツールパス差分がなければ、完全なコミットSHAと結果を互換性記録へ追加する。

次のいずれかに該当するコミットは非互換とする。

- 必須I/Fが削除、改名、引数変更された
- `posSlice`または`posPrepareInfill`の呼び出し位置、再計算範囲が変わった
- ワーカースレッドまたは参照寿命の契約が変わった
- meshまたは行列の座標系、単位、所有権、可変性が変わった
- 設定UI、保存、復元、プリセットoverrideの意味が変わった
- 実機確認でクラッシュ、デッドロック、形状破損、設定消失、再現不能な差分が発生した

互換性が不明な場合は機能単位の推測で許可せず、未対応として安全に拒否する。対応コミットの追加または削除は、本ADRの追記か後継ADRで記録する。

## 結果

- 開発とテストを再現可能な単一コミットへ固定できる。
- Nightly更新を自動的に互換扱いしないため、API変更による誤検出、破損、設定消失を避けられる。
- 新しいOrcaSlicerへ追従するたびにソース差分監査と実機確認が必要になる。
