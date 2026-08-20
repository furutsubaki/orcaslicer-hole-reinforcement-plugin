# 3D穴検出フィクスチャ

`test-models/fixtures/`には、issue 01で定義した形状・穴端・方向の30通り、方向境界2件、径と深さの境界6件、円半径偏差・多角形辺長偏差・多角形角度偏差の境界9件、誤検出・破損メッシュ6件を収録しています。

各ASCII STLの期待属性は`manifest.json`に記録されています。内容はケースID、ファイル名、形状、軸、径または対辺寸法、深さ、穴端分類、期待結果、除外理由です。

## 再生成

```bash
PYTHONPATH=src python3 tools/fixture_suite.py
```

同じPython実装ではバイト単位で同一のSTLとマニフェストを生成します。通常の全テストには、生成結果とコミット済みファイルの一致検証も含まれます。

## OrcaSlicerなしの検証

```bash
PYTHONPATH=src python3 tools/run_fixture_harness.py
```

ハーネスはSTLを読み戻し、正式版の候補検出器と穴端分類器へ渡してマニフェストの期待属性と比較します。プロジェクト全体の幾何回帰テストは次の1コマンドで実行できます。

```bash
PYTHONPATH=src python3 -m unittest discover -s tests -v
```
