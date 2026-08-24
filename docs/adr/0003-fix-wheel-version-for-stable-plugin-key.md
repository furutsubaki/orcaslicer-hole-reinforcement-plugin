# ADR 0003: wheelメタデータのバージョンをメジャーだけにしてplugin_keyを安定させる

- Status: Accepted
- Date: 2026-08-24
- Deciders: プロジェクトメンテナー

## 文脈

OrcaSlicerはローカル導入したプラグインの`plugin_key`を、インストール元ファイルのstemから決める（`assign_local_plugin_key`）。PEP 427に従うwheelのファイル名は`{name}-{version}-{python}-{abi}-{platform}.whl`であり、バージョンを含む。したがってリリースのたびに`plugin_key`が変わり、更新すると別プラグインとして扱われる。

これによる不具合は2つある。

1. **設定が既定値へ戻る**。設定は`plugin_key`で識別されるエントリに保存されるため、更新すると新しい空のエントリになる。ADR 0002の引き継ぎで救済済み
2. **プリセットの`plugins`参照が外れる**。プリセットはcapability参照を`<plugin_name>;<cloud_uuid>;<capability_name>`で持ち、ローカル導入では`plugin_name`が版込みの`plugin_key`になる。更新するとこの参照が解決できなくなり、`PluginResolver.refresh_missing_plugins()`が未解決として検知して`has_missing_plugins()`でスライスをブロックする（`Plater.cpp`）。**利用者は更新のたびにプラグインを選び直してプリセットを保存し直す必要がある**

ADR 0002はこの2つ目を「ホストが扱う領域」として対象外に置き、代替案「本体側の改善」として「OrcaSlicerが`plugin_key`ではなくプラグイン名で設定を保持するよう提案する」を挙げたうえで、本体の変更を待つことになるため採らないと結論していた。

`plugin_key`がwheelのファイル名だけで決まるのであれば、ファイル名を変えなければキーは変わらない。本体の変更を待たずにプラグイン側で解決できる。

## 決定

wheelメタデータ上のバージョンを**実バージョンのメジャーだけ**にする。`version.py`が2つの値を持ち、`pyproject.toml`は前者を読む。

```python
__wheel_version__ = "1"   # wheelメタデータとファイル名に入る
__version__ = "1.0.0"     # プラグインの実バージョン
```

- `[tool.hatch.version]`の`pattern`で`__wheel_version__`を読む。`dynamic = ["version"]`は維持する
- 配布物は`orcaslicer_hole_reinforcement-1-py3-none-any.whl`、`plugin_key`は`orcaslicer_hole_reinforcement-1-py3-none-any`。`1.0.1`でも`1.4.0`でも変わらない
- **メジャーを上げるときだけ`plugin_key`が変わる**。破壊的変更の節目であり、旧版のアンインストールとプラグインの選び直しをリリースノートで案内できる。マイナー・パッチ更新では何も壊れない
- 2つの値がズレないよう、`tests/test_package_metadata.py`が`__wheel_version__`と`__version__`のメジャーの一致を検証する
- 初回公開を`1.0.0`とする。メジャーが`0`だとOrcaSlicerの表示が`0`になるうえ、`config_migration.py`の`_version_key()`が`"0"`を`(0,)`と評価して旧`0.x.y`エントリの`(0, 1, 0)`より低く並べるため、引き継ぎ元の選択順に影響しうる
- 実バージョンは、設定画面の見出し、スライス完了時にホストへ返す実行結果メッセージ、診断レコードの`plugin_version`の3経路で確認できるようにする。ホストが`config.json`へ書く`plugin_version`はwheelメタデータ由来のため、メジャーしか示さない
- ADR 0002の設定引き継ぎは撤回しない。固定化前のバージョンから更新する利用者のために、引き継ぎ経路として有効なまま残す。固定化後は自分のエントリが常に存在するため、引き継ぎは固定化リリースへの更新時に1回だけ発火してその後スキップされる

## 根拠

`src/`に「`plugin_key`がバージョンを含む」ことを前提としたコードは存在しない。

- `config_migration.py`の`current_plugin_key()`は`orca_plugins/`直下のディレクトリ名から`.whl`を落とすだけで、バージョン文字列を解析しない
- 引き継ぎ元の候補判定（`_is_donor_candidate()`）が使うのは`capability`名と`plugin_key`の不一致であり、バージョンの中身を見ない
- 診断ファイルの出力先は`__file__`相対で解決する

したがって固定化による実装変更は`pyproject.toml`と診断への`plugin_version`追加に限られる。

副次的に、診断ファイルのパスがリリース間で不変になる。展開先が`orca_plugins/<wheel名>/__whl_extracted__/`配下のため、従来はリリースごとにパスが変わっていた。

## 採用しなかった選択肢

**`pyproject.toml`へ固定値を直接書く**: `dynamic`を外して`version = "1"`と静的に書く。単純だが、実バージョンとの対応が失われ、メジャーを上げるときに2箇所を手で合わせることになる。`pattern`方式なら`version.py`が唯一の定義元のまま保て、ズレをテストで縛れる。

**カスタムversion sourceプラグイン**: 常に`1`を返すフックを自作する。静的値に対する利点がなく、依存とビルドの複雑さだけが増える。

**バージョンをファイル名に残したまま運用で回避する**: 更新手順に「旧版をアンインストールし、プラグインを選び直す」を明記して利用者へ委ねる。これまでの方針だが、更新のたびに手作業を強い、忘れるとスライスがブロックされる。プラグイン側で解決できる以上、採らない。

**PyPIでの配布と両立させる**: PyPIは同一バージョンの再アップロードを拒否するため、バージョン固定と両立しない。本プラグインはGitHub Releaseへwheelを添付する配布のみで、PyPIへは公開しない。将来PyPIへ出す必要が生じた場合は本ADRの再検討が必要になる。

## 制約

- **配布物のファイル名からメジャーしか読めない**。GitHub Releaseのタグと本文で完全なバージョンを示す
- **OrcaSlicerがメジャーしか表示しない**。プラグイン一覧の`Plugin Version`列、`Plugin Info`タブの`Installed Version`と`Latest Version`の3箇所に出る。ホストはwheelメタデータのバージョンを表示し、プラグイン側からバージョンを供給するI/F（`get_plugin_info()`相当）が存在しないため、この表示は変えられない。設定画面の見出しへ実バージョンを表示し、その旨の注記を添えることで補う
- **`Latest Version`は更新の有無を判断できない**。ローカル導入では`Installed Version`と同じ値が出るうえ、メジャーが同じ限り動かない
- **固定化前に保存されたプリセットoverrideのエントリはプリセットに残り続ける**。ホストの`prune_unreferenced()`は型と名前で判定するため刈り取らず、プラグインAPIにoverrideのsetterも無い（ADR 0002の制約）。固定化後は自分のキーが恒久的に`orcaslicer_hole_reinforcement-1-py3-none-any`になるため、旧キーのエントリは二度と一致しない。

  そのため`find_stale_preset_overrides()`は、**同じプリセットに現在のキーのoverrideがあれば警告しない**。利用者が入力し直した時点で失われる値は無く、それでも報告し続けると消す手段の無い警告になるため。実機のプリセットで、入力し直したあとも旧`0.1.0`のエントリが残ったまま新しい`1`のエントリが並ぶことを確認している
- **ホストの`plugin_version`が常に`1`になる**。将来「設定スキーマ移行の要否をホストの`plugin_version`で判断する」ことはできない。現在スキーマ移行は`cap_config`内の`schema_version`で独立に扱っており、依存は無い

## 実機検証手順

固定化リリースを公開する前に、対応Nightlyで次を確認する。

1. 公開前の開発版のwheel（`orcaslicer_hole_reinforcement-0.2.0-py3-none-any.whl`など）をアンインストールする
2. `orcaslicer_hole_reinforcement-1-py3-none-any.whl`をインストールし、GUIのログに`[AUDIT] plugin=orcaslicer_hole_reinforcement-1-py3-none-any`が出ることを確認する
3. 旧バージョンで保存した設定が引き継がれ、`diagnostic.jsonl`に`config_migrated`が1回出ることを確認する
4. `__version__`を`1.0.1`へ一時的に上げて再ビルド・再インストールする。**wheelのファイル名が変わらないこと**、**設定画面の値が更新前のまま残ること**、**設定画面の見出しと診断の`plugin_version`が`1.0.1`になること**を確認する。これが本決定の核心である

   このとき`config_migrated`系の診断は出ない。`_migrate_on_load()`は自分の`plugin_key`のエントリが空でなければ何も記録せず即returnするためである。イベントが無いことが正常であり、出ていたら`plugin_key`が変わってしまっている
5. プリセットでプラグインを選択して保存した状態から4を実施し、**スライスがブロックされないこと**を確認する
6. 確認後、`__version__`を元へ戻す

### 検証結果（2026-08-24、Nightly `2.5.0-dev` / Build `872c660c`）

手順4を実施し、本決定が成立することを確認した。

- `__version__`を`1.0.1`へ上げてビルドしても、wheelのファイル名は`orcaslicer_hole_reinforcement-1-py3-none-any.whl`のまま変わらない
- 同名ファイルの上書きインストールで中身は再展開される。展開先の`version.py`が`1.0.1`になり、設定画面の文言と挙動も新しいwheelのものへ変わった
- `orca_plugins/config.json`のエントリは4件のまま増えず、`plugin_key`は`orcaslicer_hole_reinforcement-1-py3-none-any`のまま。利用者が変更していた`reinforcement_width_mm`の`5.9`を含め、設定はすべて保持された
- 展開ディレクトリは1つのままで、旧版との並存は起きない
- プリセットからのスライスはブロックされない

従来の方式であれば`-1.0.1-`という新しい`plugin_key`が生まれ、設定は初期値へ戻り、プリセットの`plugins`参照が外れてスライスがブロックされていた場面である。
