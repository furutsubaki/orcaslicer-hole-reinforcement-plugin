# OrcaSlicer実機での統合検証

issue15の受け入れ条件を満たすため、matrixフィクスチャ30件をプラグインON/OFFでスライスし、ツールパス差分と診断出力を突き合わせます。

issue15の検証はプラグイン`0.0.1`で実施しました。本書のログ抜粋はそのときの実測値です。手順部分は現在のバージョン`0.1.0`で記載しています。

## OrcaSlicer CLIの制約

CLIモードではプラグイン機構が初期化されません。CLIのログには`orca_plugins`も`AUDIT`も現れず、診断ファイルも生成されないため、**スライス自体をCLIで自動化することはできません**。GUIのログには`[AUDIT] plugin=orcaslicer_hole_reinforcement-0.0.1-py3-none-any`が多数出力されます。

CLIは3mfプロジェクトの生成と、プラグインを読み込まないベースラインG-codeの生成に使います。これにより、GUIでの操作をON/OFF各1回のスライスとG-code書き出しに抑えられます。

CLIはプラグインを一切読まないため、CLIが出力するG-codeは**プラグイン完全無効時の出力**そのものです。GUI-OFFと一致することを確認できれば、以降はGUI操作をON側の1回だけに減らせます。

## 準備

### 1. wheelを再ビルドして再インストールする

診断へモデル名と補強対象レイヤを記録する改修が入っているため、GUI検証の前に1回必要です。

```bash
uv build --wheel
```

wheelのファイル名にバージョンが入るため、旧版を残したまま入れると別プラグインとして並存します。次の順で入れ替えます。

1. OrcaSlicerで「Hole Reinforcement」をアンインストールする
2. OrcaSlicerを終了する
3. `dist/orcaslicer_hole_reinforcement-0.1.0-py3-none-any.whl`をインストールする
4. OrcaSlicerを再起動する

プラグイン設定の`plugin_key`は`orcaslicer_hole_reinforcement-0.1.0-py3-none-any`です。

### 2. 検証用3mfを生成する

```bash
python3 tools/build_verification_project.py --work-dir <作業ディレクトリ>
```

`manifest.json`から`printable: true`のmatrixフィクスチャ30件を選び、1プレートに配置した`verify-matrix.3mf`と、フィクスチャ名との対応表`objects.json`、そしてCLIベースライン`baseline-cli/plate_1.gcode`を出力します。GUI起動中でも競合しないよう、datadirは作業ディレクトリへ複製してから使います。

作業ディレクトリはリポジトリ外を指定してください。生成物が約37MB（大半はdatadirの複製）になり、リポジトリ内だと`.gitignore`の変更が必要になります。実datadirの内側や親を指定するとエラーで止まります。複製先を消してから作るため、重なっていると本体を消してしまうためです。

既定のプリセットはシステムプリセットです。ユーザープリセットは`type`フィールドを持たず`unknown config type`になるため使えません。

| 種別 | 既定値 |
| --- | --- |
| machine | `system/Creality/machine/Creality K2 Plus 0.4 nozzle.json` |
| process | `system/Creality/process/0.20mm High Quality @Creality K2 Plus 0.4 nozzle.json` |
| filament | `system/Creality/filament/CR-PLA @K2 Plus-all.json` |

いずれも`--machine` / `--process` / `--filament`で差し替えられます。

## GUIでの検証手順

### 3. 実行前の状態を控える

診断は追記されるため、前回分と混ざらないよう空にします。あわせてPythonログの現在サイズを控えます。控えたサイズは手順6で`--python-log-offset`へ渡し、過去実行の解消済みエラーを今回の失敗として拾わないようにします。

```bash
DATADIR="$HOME/Library/Application Support/OrcaSlicer"
DIAG="$DATADIR/orca_plugins/orcaslicer_hole_reinforcement-0.1.0-py3-none-any.whl/__whl_extracted__/orcaslicer_hole_reinforcement/orcaslicer_hole_reinforcement/diagnostic.jsonl"
: > "$DIAG"
ls -l "$DATADIR/log/"python_*.log
```

### 4. プラグインONでスライスする

1. プラグイン設定で`solid_reinforcement`と診断出力を有効にする
2. `verify-matrix.3mf`を開く
3. 全プレートをスライスする
4. G-codeを書き出す（`on.gcode`とする）
5. `diagnostic.jsonl`を別名で回収する

### 5. プラグインOFFでスライスする

1. プラグイン設定で`solid_reinforcement`のチェックを外す
2. 同じ3mfをスライスする
3. G-codeを書き出す（`off.gcode`とする）

**正式なON/OFF判定の基準はこのGUI-OFFです。** CLIベースラインが生成できた場合でも、GUI-OFFと一致することを確認できるまで基準には使いません。一致を確認できたら、以降の反復ではCLIベースラインで代用でき、GUI操作を1回に減らせます。その場合は`--baseline-kind`へ実際の取得方法を記録してください。

同一条件で2回スライスして出力が一致することも、最初に一度確認しておきます。決定性がなければ差分比較自体が成立しません。

## 6. 比較とレポート生成

```bash
python3 tools/compare_slice_output.py \
  --on-gcode on.gcode \
  --off-gcode off.gcode \
  --diagnostics diagnostic.jsonl \
  --objects <作業ディレクトリ>/objects.json \
  --python-log "$DATADIR/log/python_<実行時のファイル>.log" \
  --python-log-offset <手順3で控えたバイト数> \
  --output report.md \
  --json-output report.json
```

終了コードは、受け入れ条件をすべて満たせば0、満たさない条件があれば2、入力に不備があれば1です。

レポートには次を出力します。

- 検証環境（OrcaSlicerバージョンとビルド、対応保証コミットとの差異、プリセット、プラグインバージョン）
- 受け入れ条件ごとの判定
- 形状・端種別・角度ごとの検出数と補強レイヤ数
- 押出種別ごとのON/OFF差分（`Internal solid infill`、`Bridge`、`Internal Bridge`、`Overhang wall`、サポート系を含む）
- 補強対象レイヤ以外に生じた差分
- Python例外と診断の警告・エラー

## 判定の考え方

補強対象レイヤは**診断が記録した`reinforced_layers`から確定**します。G-codeの差分があるレイヤを対象とみなすと循環論法になるためです。診断に`model_object_name`がない場合はエラーとして扱います。`print_object_id`の出現順で対応付けると、スライスの並列実行や内部順序の変更で別のフィクスチャへ結果を割り当てる恐れがあるためです。

差分判定はレイヤ単位です。診断には補強領域のbboxも記録していますが、これはモデル座標系のため、G-codeのプレート座標系へ対応付けないとレイヤ内の領域単位判定はできません。現時点では未対応で、レポートにもその旨を明記しています。

診断ログにはモデルオブジェクト名がプレーンテキストで記録されます。ログを外部へ共有する際は、ファイル名に含まれる情報にご注意ください。

診断ログは5MiBを超えると先頭が捨てられます。切り詰められたファイルは残った部分だけ見ると正常なJSONLに見えるため、`--objects`で渡した30件分のイベントが揃っているかを検査し、欠けていれば失敗させます。

## G-code解析について

押出量と経路長は状態機械で集計します。実測したG-codeは相対押出（`M83`）で`G92 E`が101回現れ、`enable_arc_fitting`によるG2/G3も含まれるため、前行との単純差分では誤集計します。円弧はI/Jオフセットから弧長を求めます。R指定形式は出力されないため未対応とし、現れた場合はエラーにします。

オブジェクトの切り分けには`EXCLUDE_OBJECT_START` / `END`を使います。どちらにも囲まれない区間（brimやプレート間移動）は非対象領域として別に集計します。マーカーの欠落や不整合は黙って無視せず失敗させます。

比較前に落とすのは2種類の行です。1つは実行ごとに変わるもので、生成日時、絶対パスを含むコメント、サムネイルのペイロードが該当します。もう1つはツールパスが変われば必ず変わる派生値で、`M73`（残時間）、フィラメント使用量、印刷時間見積りが該当します。

`M73`は各レイヤへ残時間を書き込むため（実測で107行）、残すと補強と無関係なレイヤまで差分と判定され、判定が常に失敗します。派生値の増減は差分の有無ではなく、押出種別ごとの集計とレポートの「印刷サマリーの比較」で評価します。

レイヤごとの一致判定には行の実体ではなくダイジェストを使います。30オブジェクト規模（約8MB、30万行）の解析は約4.7秒、ピークメモリ約29MBです。
