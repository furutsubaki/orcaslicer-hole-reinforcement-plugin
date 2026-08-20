"""OrcaSlicerなしでPoCの純粋な形状計算と連結処理を確認する。"""

import importlib.util
import math
import sys
import types
from pathlib import Path


class _Base:
    pass


orca = types.ModuleType("orca")
orca.base = _Base
orca.plugin = lambda cls: cls
orca.register_capability = lambda cls: None
orca.slicing = types.SimpleNamespace(SlicingPipelineCapabilityBase=_Base)
sys.modules["orca"] = orca

plugin_path = Path(__file__).resolve().parents[1] / "hole_reinforcement_detector_poc.py"
spec = importlib.util.spec_from_file_location("hole_detector_poc", plugin_path)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class Point:
    def __init__(self, x, y):
        self.x = x
        self.y = y


class Ring:
    def __init__(self, diameter_mm, segments=96, scale=1_000_000):
        radius = diameter_mm * scale / 2.0
        self.points = [
            Point(round(radius * math.cos(2.0 * math.pi * index / segments)),
                  round(radius * math.sin(2.0 * math.pi * index / segments)))
            for index in range(segments)
        ]


metrics = module._ring_metrics(Ring(10.0), 1_000_000)
assert abs(metrics["diameter_mm"] - 10.0) < 0.01
assert abs(metrics["bounding_diameter_mm"] - 10.0) < 0.001
assert metrics["circularity"] > 0.99

layers = []
for layer_index in range(5):
    layers.append([
        {"center_x_mm": 0.0, "center_y_mm": 0.0, "diameter_mm": 4.0, "layer_index": layer_index},
        {"center_x_mm": 20.0, "center_y_mm": 0.0, "diameter_mm": 9.0, "layer_index": layer_index},
    ])
tracks = module._continuous_tracks(layers)
assert sorted(len(track) for track in tracks) == [5, 5]
print("detector harness: ok")
