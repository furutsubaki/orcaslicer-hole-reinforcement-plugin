"""OrcaSlicerへのパッケージ登録。"""

import orca

from .slicing_capability import HoleReinforcementCapability


@orca.plugin
class HoleReinforcementPackage(orca.base):
    def register_capabilities(self):
        orca.register_capability(HoleReinforcementCapability)

