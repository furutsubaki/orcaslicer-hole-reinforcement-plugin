# ADR 0002: プラグイン更新をまたいで設定を維持する

- Status: Accepted
- Date: 2026-08-21
- Deciders: プロジェクトメンテナー

## 文脈

OrcaSlicerはプラグイン設定を`<data_dir>/orca_plugins/config.json`へ保存し、エントリを`plugin_key`で識別する。ローカル導入の`plugin_key`はインストール元ファイルのstem（`orcaslicer_hole_reinforcement-0.1.0-py3-none-any`）であり、バージョンを含む。したがってプラグインを更新すると別エントリになり、利用者が変更した設定は既定値へ戻る。

ADR 0001の対応コミット`f5f3d2221dd929360407aa2ae6759302a8d2c575`で、ホスト側の実装を次のとおり確認した。

- `capability_get_config()`は`active_capability_config().config`を返し、保存が無ければ空オブジェクトになる
- **ホストは`plugin_loader::load()`の直後に`get_default_config()`の戻り値を保存する**（`PluginManager.cpp`）。`has_config(id)`が真ならスキップするため初期投入は新しい`plugin_key`につき1回だけだが、**設定画面を一度も開いていなくてもエントリは必ず存在する**。したがって「`get_config()`が空」は、通常の実行時点では未保存の判定に使えない
- 初期投入は`plugin_loader::load()`の**後**に走り、`on_load()`はその**中**で呼ばれる。`on_load()`の時点ではまだエントリが無く、`get_config()`は空を返す。ここで`save_config()`すればホスト側の初期投入は`has_config(id)`でスキップされる。**引き継ぎ元を適用できるのはこの一点だけである**
- `on_load()`はPythonへ転送される（`PyPluginTrampoline.hpp`）。`AuditMode::Loading`で実行され、読み取りは無条件に許可される。`on_load()`が例外を送出するとプラグインの読み込み自体が失敗する
- `save_config(str)`はPythonへ公開されている（`PythonPluginBridge.cpp`）。JSON文字列を受け取り、不正なら`False`を返して既存の保存値を変更しない
- `PluginCapabilityId`は`plugin_key`を含む。プラグインAPIから参照できるのは自分のキーのエントリだけで、旧バージョンのエントリへは到達できない
- `erase_capability_config()`には呼び出し元が存在せず、プラグイン削除の経路にも設定を消す処理がない。旧エントリは削除されない。実機の`config.json`にPoC版と`0.0.1`が並存しているのが実例である
- `PluginConfig::get_config_response()`は`get_config_ui()`を呼ぶ前に保存済み設定を読み終える。設定UIへ渡る値をプラグイン側から差し替える経路は無い
- `restore_config_response()`（「既定値に戻す」）は`get_default_config()`の戻り値を保存し、保存した値をそのままページへ返す。本プラグインの`get_default_config()`は全キーを持つdictを返すため、復元後にページが受け取る設定は必ず非空になる
- `PluginConfig::get_config_response()`は設定をJSON文字列ではなくJSON値として載せる（"Config is sent as a JSON value, not text ... a custom UI receives it as-is through window.orca"）。`window.orca`側で受け取るのはオブジェクトであり、文字列ではない
- CPythonの監査フック（`PluginAuditManager::install_hook`）は`data_dir()`をグローバル許可ルートとし、拒否ファイル名は`OrcaSlicer.conf`／`.ini`、`OrcaSlicer-gcodeviewer.conf`／`.ini`、ユーザーシークレットのみ。`orca_plugins/config.json`の読み取りは許可されている
- `CapabilityConfigDocument::find()`は`capability_type`を持たないレガシーエントリを名前だけで解決する分岐を持つ。型を欠くエントリは実在しうる

## 決定

`on_load()`でホストの`config.json`を読み、旧エントリから設定を引き継いで`save_config()`で確定させる。

- 引き継ぎは`on_load()`で、`get_config()`が空のときだけ行う。ホストの初期投入より前のこの一点以外に機会は無い
- 引き継ぎ元は、`capability`が`Hole Reinforcement`と完全一致し、`capability_type`が`slicing-pipeline`または欠落、`cap_config`が非空、`plugin_key`が自分と異なるエントリとする。`plugin_version`の降順に走査し、`parse_config()`の検証を通った最初のものを採用する
- スキーマ検証の通過を同一性の二次的な根拠とする。`parse_config()`は未知キーを拒否するため、別プラグインの設定やPoC版の`cap_config`は弾かれる
- 引き継いだ値は`save_config()`で保存する。ホストが所有するファイルへ直接書かず、公式I/F経由で書く。保存に成功すればホストの初期投入がスキップされ、設定UIもスライスも同じ値を読む
- 保存に失敗しても引き継ぎは中断しない。ホストが既定値を初期投入し、既定値で動作する。失敗は診断の`stored: false`として残す
- `on_load()`は例外を外へ出さない。送出するとプラグインの読み込み自体が失敗する
- 設定UIには、ホスト設定が空のときだけ引き継いだ値を初期表示として埋め込む（`__INITIAL_CONFIG__`）。`on_load()`の保存が成功していれば通常は発火しない、保存と初期投入の双方が失敗したときの退避路である。ホストは設定UIより先に保存済み設定を読み終えるため、これ以外に初回表示へ届ける手段が無い
- 引き継ぎ元が無い、読めない、検証を通らない場合は既定値で動作する。移行処理全体を`except Exception`で包み、スライスを妨げない
- 引き継ぎの成否は`config_migrated`／`config_migration_skipped`／`config_migration_failed`として診断へ1回だけ記録する。これらは`diagnostics_enabled`に依らず記録する。引き継いだ設定で診断が無効だと、診断を有効化するために設定を保存した時点で引き継ぎが発火しなくなり、原因を追う手掛かりが残らないため

## 採用しなかった選択肢

**バージョン非依存の保存先へ複製**: プラグイン側で設定のコピーを独自パスへ保存し、ホスト設定が空のときに復元する。展開先（`__whl_extracted__`配下）はバージョンに依存するため保存先にできず、`data_dir()`直下に独自ファイルを置くことになる。ホストが管理しないファイルが増え、アンインストールしても残る。旧エントリが実際には削除されないと確認できた以上、二重の保存先を持つ利点がない。

**引き継ぎを保存せず、読むたびに導出する**: ホストが所有するファイルへ書き込む経路を一切作らずに済む。当初はこれを採ったが、ホストが読み込み時に既定値を初期投入すると判明して成立しなくなった。初期投入後は`get_config()`が空でなくなり、引き継ぎを発火させる手掛かりが残らない。

**保存済みの設定が`get_default_config()`と一致することを引き継ぎの合図にする**: 初期投入直後は保存値が既定値と完全一致するため、これを「未変更」とみなす案。採らない。利用者が意図して「既定値に戻す」を実行した状態と区別できず、次回起動で旧バージョンの値を勝手に復元してしまう。

**設定のエクスポート／インポート**: 設定UIへ手動の書き出し・読み込みを追加する。ホストの挙動に依存しない反面、利用者が更新のたびに手作業を強いられる。自動の引き継ぎが成立する以上、これを主たる手段にはしない。

**`get_config_version()`を使う**: ADR 0001が「設定移行の要否を判断する」I/Fとして記録しているが、返るのは自分の`plugin_key`のエントリに保存されたバージョンだけである。更新直後は自分のエントリが存在せず空文字になるため、`plugin_key`をまたぐ引き継ぎには使えない。

**本体側の改善**: OrcaSlicerが`plugin_key`ではなくプラグイン名で設定を保持するよう提案する。`.install_state.json`はバージョンを含まない`plugin_name`を持つため、キーの候補は存在する。ただし本体の変更を待つことになり、本プラグイン側で完結しない。将来提案する場合も、本ADRの引き継ぎは互換のために残す。

> **追記（ADR 0003）**: この選択肢が目指した「`plugin_key`を不変にする」状態は、本体を変更せずに実現できると判明した。`plugin_key`はインストール元wheelのファイル名だけで決まるため、wheelメタデータのバージョンを固定すればキーは動かない。[`0003-fix-wheel-version-for-stable-plugin-key.md`](0003-fix-wheel-version-for-stable-plugin-key.md)を参照。本ADRの引き継ぎは撤回せず、固定化前のバージョンから更新する利用者のために残す。

## 制約

- 引き継げるのはプラグイン設定画面で保存した値だけである。プリセットoverride（`print_plugin_config_overrides`ほか、`Preset::plugin_overrides_key()`）も`plugin_key`込みで保持され、更新すると`CapabilityConfigDocument::find()`が一致しなくなって参照されない。`prune_unreferenced()`は`(型, 名前)`で判定するため刈り取られず、プリセットに残り続ける
- ホストがPythonへ公開するプリセットAPI（`PluginHostPresets.cpp`）は`config_keys()`と`config_value()`だけで、setterが無い。overrideを書き戻して復元する手段は存在しない。**読み取って検知し、設定画面と診断（`preset_override_stale`）で知らせるに留める**
- `config_value()`は`config_value_or_none()`→`ConfigBase::opt_serialize()`を通る。`ConfigOptionString::serialize()`は`escape_string_cstyle()`を掛けるため、**JSONを保持する設定値は`"`が`\"`へエスケープされた文字列として返る**。素の`json.loads()`では読めない
- overrideの値を基本層へ昇格させる案は採らない。プリセット単位の値が全プリセットへ効くようになり、override未設定のプリセットの挙動まで変えてしまう
- プリセットの`plugins`項目もcapability参照を`<plugin_name>;<cloud_uuid>;<capability_name>`で持ち、ローカル導入では`plugin_name`が版込みの`plugin_key`になる。更新するとこの参照が外れるが、**これはホストの`PluginResolver`が扱う**。`refresh_missing_plugins()`が未解決のプラグインとして検知し、モデル読み込み時に「Local plugins required by the current preset are missing:」を通知して`has_missing_plugins()`でスライスをブロックする（`Plater.cpp`）。プラグイン側では検知しない
  - 当初は`execute_capabilities_from_refs()`が`continue`する箇所だけを見て「黙って読み飛ばされる」と判断し、検知と警告を実装した。呼び出し側に`PluginResolver`という層があることを確認しておらず誤りだった。実機で本体の通知が出ることを確認して撤回した
- `plugins`は`save_plugin_collection()`が保存時に再生成する派生値のため、利用者がプロセス設定でプラグインを選び直してプリセットを保存すれば解消する
- 本決定は`orca_plugins/config.json`のレイアウト、監査フックの許可ルート、そして**ホストが`on_load()`の後に既定値を初期投入する順序**へ依存する。この順序が変わると引き継ぎは発火しなくなる。ADR 0001の非互換条件へ追記した

## 結果

- 更新後も利用者の設定が維持される。手作業も、更新前の控えも要らない
- 書き込みは`save_config()`経由に限り、ホストが所有するファイルを直接編集しない。保存に失敗しても既定値へ退避するだけで、既存の設定を壊さない
- OrcaSlicerが`config.json`のレイアウトを変えた場合、引き継ぎは`no_donor`へ退避する。破損ではなく既定値での動作になるが、追従が必要になる
