# 第三者コードと依存関係のライセンス

本プラグインのライセンスはMIT License（[`LICENSE`](../LICENSE)）です。本書は配布物へ含まれる第三者コードと、依存関係のライセンス条件を記録します。

## 第三者コードの取り込み

**なし。** `src/orcaslicer_hole_reinforcement/`配下はすべて本プロジェクトで書いたコードで、他プロジェクトから取り込んだソースはありません。wheelへ同梱される第三者コードもありません。

パッケージ内のimportは、Python標準ライブラリと、OrcaSlicerがプラグインへ提供する`orca`モジュールだけです。

## 実行時の依存関係

| 名前 | ライセンス | 配布物への同梱 | 備考 |
| --- | --- | --- | --- |
| Python標準ライブラリ | PSF License | なし | OrcaSlicer同梱のPython 3.12を使用 |
| `orca` | — | なし | OrcaSlicerがプラグインへ提供するホストAPI。独立した配布物ではない |
| NumPy | BSD-3-Clause | なし | `pyproject.toml`の`dependencies`に宣言しているが、実体は同梱・インストールされない（下記） |

### NumPyの扱い

`pyproject.toml`は`dependencies = ["numpy"]`を宣言していますが、**この宣言はインストール時に解決されません**。

OrcaSlicerのプラグイン機構はwheelを展開するだけで、依存関係の解決やインストールを行いません。実機で確認した結果、インストール済みプラグインの展開先（`orca_plugins/<whl>/__whl_extracted__/`）にNumPyは存在せず、OrcaSlicer同梱のPython 3.12にもNumPyは入っていませんでした。

本プラグインのコードは`import numpy`しません。`TriangleMesh.vertices()`などが返すNumPy配列はホスト側から渡されるオブジェクトで、属性アクセスとインデクシングだけで扱います。宣言は、メッシュがNumPy配列として渡される前提を明示するためのものです。

したがって、NumPy（BSD-3-Clause）のコードや著作権表示が本配布物へ含まれることはありません。

## ビルド時のみの依存関係

| 名前 | バージョン | ライセンス | 備考 |
| --- | --- | --- | --- |
| hatchling | 1.27.0 | MIT | `pyproject.toml`の`build-system.requires`で固定。ビルドバックエンドであり成果物へは含まれない |

## OrcaSlicerとの関係

OrcaSlicer本体は[AGPL-3.0](https://github.com/OrcaSlicer/OrcaSlicer/blob/main/LICENSE.txt)で配布されています。本プラグインについて確認できている事実は次のとおりです。

- OrcaSlicerのソースコードを取り込んでいない。フォークも改変もしていない
- 配布物はOrcaSlicerのバイナリやリソースを含まない
- OrcaSlicerが提供するPythonプラグインAPIを通じて、実行時に読み込まれる形で動作する

AGPL-3.0の条項が本プラグインの配布形態にどう適用されるかについては、本書では判断しません。第三者へ再配布する場合は、上記の事実をもとに個別に確認してください。
