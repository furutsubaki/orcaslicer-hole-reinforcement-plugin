"""OrcaSlicer穴補強プラグインの正式版パッケージ。"""

from .version import __version__

try:
    import orca as _orca
except ModuleNotFoundError as error:
    if error.name != "orca":
        raise
else:
    from . import plugin as _plugin

__all__ = ["__version__"]

