# OrcaSlicer穴補強プラグイン

## 目的

OrcaSlicer本体をフォークせず、一定サイズ以下の穴を自動検出し、穴周辺のインフィルや壁を補強するNightly版向けプラグインを試作する。

手動でモディファイアを配置する作業をなくし、モデルを更新して再読み込みした場合も、スライス時に補強領域を再生成できる状態を目指す。

## 想定する対象

- 円柱状のネジ穴
- 六角穴・八角穴などの多角柱状の穴
- 指定した最大径以下の穴
- 原則として複数レイヤーに連続する穴

初期PoCでは、造形方向とほぼ平行な貫通穴または止まり穴を対象とする。横穴、傾斜穴、複雑な異形穴は対象外としてよい。

正式版の公開前には、垂直穴だけでなく横穴・傾斜穴を含む穴方向別の検証を行う。方向ごとに検出可否、補強領域の連続性、ブリッジ・サポート・オーバーハングへの影響を確認し、対応範囲外となる方向や角度があれば明示する。

## 採用候補の方式

OrcaSlicerのNightly版に含まれるPythonプラグイン機構の`SlicingPipelineCapabilityBase`を使用する。

`Step.posSlice`では、各レイヤーの`Surface.expolygon`から穴輪郭を取得できる。断面変更後に`Layer.make_slices()`を呼ぶことで、後続のパリメーター・インフィル・サポート生成へ変更を反映できる。

`Step.posPrepareInfill`では、インフィル生成前の`LayerRegion.fill_surfaces`を操作できる。初期PoCでは、穴周辺にリング状領域を作り、その範囲をソリッドインフィルとして扱う方法を優先して検証する。

## 現在判明している制約

- 安定版v2.4.2にはSlicing Pipelineプラグインが含まれていないため、標準Nightly版が必要
- プラグインAPIは新しく、今後変更される可能性がある
- 公開されている設定I/Fは主に読み取り用で、局所的な任意インフィル密度を直接設定するI/Fは確認できていない
- `Surface.extra_perimeters`は書き換え可能だが、穴周辺だけへ適用するには断面領域の分割など追加検証が必要
- モディファイアボリュームをGUIモデルへ自動追加する公開I/Fは確認できていない
- そのため、最初は任意密度への変更ではなく、穴周辺のソリッド化を狙う

## 初期PoCの仕様案

設定値は次を候補とする。

- `max_hole_diameter_mm`: 補強対象とする穴の最大径
- `reinforcement_width_mm`: 穴の輪郭から外側へ補強する幅
- `min_continuous_layers`: 穴として扱うために必要な連続レイヤー数
- `circularity_tolerance`: 円形判定の許容誤差
- `polygon_sides`: 対象とする多角形の辺数。初期値は`[6]`
- `solid_reinforcement`: 穴周辺をソリッド化するか
- `extra_perimeters`: 追加壁数。API上の局所適用を検証できるまでは実験扱い

誤検出を確認できるよう、検出数・対象径・対象レイヤー範囲を実行結果またはログへ出す。

## 穴検出の案

1. 各レイヤーの`ExPolygon.holes`を列挙する
2. 各輪郭について面積、周長、外接寸法、重心を計算する
3. 円形度`4πA / P²`と最大径から円穴候補を抽出する
4. 直線近似後の辺数と辺長・角度のばらつきから六角穴候補を抽出する
5. 隣接レイヤー間で重心と寸法が近い候補を連結する
6. 連続レイヤー数を満たす候補だけを補強対象にする
7. 穴輪郭を外側へ`reinforcement_width_mm`分オフセットして補強領域を作る

円形度だけでは曲線を含む意匠上の抜き形状を誤検出するため、レイヤー間の連続性を必須条件にする。

## 参照先

- OrcaSlicerリポジトリ: https://github.com/OrcaSlicer/OrcaSlicer
- Nightly版: https://github.com/OrcaSlicer/OrcaSlicer/releases/tag/nightly-builds
- Slicing Pipeline導入コミット: https://github.com/OrcaSlicer/OrcaSlicer/commit/b0bacdd00b8748062b60d56bade4ed9c352e9544
- 断面変更サンプル: https://github.com/OrcaSlicer/OrcaSlicer/blob/main/sandboxes/orca_inset_plugin_any.py
- 穴輪郭を含む形状変更サンプル: https://github.com/OrcaSlicer/OrcaSlicer/blob/main/sandboxes/orca_fuzzy_slices_plugin_any.py
- Python側のスライスI/F: https://github.com/OrcaSlicer/OrcaSlicer/blob/main/src/slic3r/plugin/host/PluginHostSlicing.cpp

## 次のセッションで行うこと

1. 使用中のOSとNightly版の導入状況を確認する
2. Nightly版でローカルPythonプラグインを読み込む手順と配置先を、現行ソースまたは実機で確認する
3. 公式のInsetサンプルを最小構成で動かし、プラグイン実行環境を検証する
4. 円形の垂直貫通穴だけを検出する最小PoCを実装する
5. 検出結果を形状変更せずログ出力し、誤検出を確認する
6. 穴周辺のソリッド化を追加する
7. スライスプレビューで壁・インフィル・エラーを確認する

## PoC結果

- macOS 26.6.1とOrcaSlicer Nightly`f5f3d22`で検証した
- 垂直円穴の検出とレイヤー間追跡を確認した
- 4mm・9mm穴だけを補強し、14mm穴を対象外にできた
- `posPrepareInfill`で穴周辺をリング状の内部ソリッドインフィルへ変更できた
- モデル更新後の再スライスで補強領域を再生成できる構成を確認した

## 正式版公開までの追加要件

- 六角形・八角形を含む多角形穴を検出する
- 多角形の辺数、辺長、内角の許容差を設定可能にする
- 垂直貫通穴と垂直止まり穴を検証する
- 横穴と傾斜穴を角度別に検証する
- 穴方向ごとにソリッド補強、ブリッジ、サポート、オーバーハングへの影響を確認する
- 対応できない穴方向・角度・形状を公開仕様へ明記する

## 未決事項

- 対象OS
- 使用するNightlyビルドのバージョンまたはコミット
- 初期PoCで使用するテストモデル
- 対象穴径の既定値
- 補強幅の既定値
- 止まり穴を対象に含めるか
- 六角穴を初期PoCに含めるか、円穴の検証後に追加するか
- ソリッド化と追加壁のどちらを優先するか
