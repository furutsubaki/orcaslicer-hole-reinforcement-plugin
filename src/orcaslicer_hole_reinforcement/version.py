"""プラグインのバージョン。

`__wheel_version__`はwheelメタデータとファイル名に入る値で、メジャーバージョンだけを
持つ。OrcaSlicerはインストール元wheelのstemを`plugin_key`にするため、ここが動くと
別プラグイン扱いになり、プリセットのplugins参照が外れてスライスがブロックされる。
メジャーに固定することで、破壊的変更のとき以外は`plugin_key`が変わらない。
判断の経緯はdocs/adr/0003-fix-wheel-version-for-stable-plugin-key.mdを参照。

`pyproject.toml`が`__wheel_version__`を読むため、この行の形を変えるとビルドが壊れる。
2つの値の整合はtests/test_package_metadata.pyが検証する。
"""

__wheel_version__ = "1"
__version__ = "1.0.0"
