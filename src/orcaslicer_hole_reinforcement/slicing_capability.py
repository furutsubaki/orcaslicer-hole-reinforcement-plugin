"""OrcaSlicerのスライスパイプラインとの境界。"""

import orca

from .config import default_config_dict, parse_json_config
from .config_ui import render_config_ui
from .version import __version__


class HoleReinforcementCapability(orca.slicing.SlicingPipelineCapabilityBase):
    def get_name(self):
        return "Hole Reinforcement"

    def get_default_config(self):
        return default_config_dict()

    def has_config_ui(self):
        return True

    def get_config_ui(self):
        try:
            language = orca.host.app_language()
        except (AttributeError, RuntimeError):
            language = ""
        return render_config_ui(language)

    def execute(self, ctx):
        if ctx.step not in (
            orca.slicing.Step.posSlice,
            orca.slicing.Step.posPrepareInfill,
        ):
            return orca.ExecutionResult.skipped()

        validation = parse_json_config(self.get_config())
        if not validation.is_valid:
            return orca.ExecutionResult.failure(
                orca.PluginResult.FatalError,
                f"Hole Reinforcement: invalid configuration: {validation.summary()}",
            )

        return orca.ExecutionResult.skipped(
            f"Hole Reinforcement {__version__}: production processing is not implemented yet"
        )
