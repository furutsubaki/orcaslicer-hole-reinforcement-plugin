"""OrcaSlicerのスライスパイプラインとの境界。"""

import orca

from .candidate_detection import HoleCandidateDetector
from .config import default_config_dict, parse_json_config
from .config_ui import render_config_ui
from .cylinder_detection import CylinderDetectionCancelled
from .end_classification import HoleEndClassificationCancelled, HoleEndClassifier
from .mesh_extraction import (
    MeshExtractionCancelled,
    VolumeRole,
    extract_transformed_volumes,
)
from .orca_geometry import OrcaPlanarGeometry
from .polygon_detection import PolygonDetectionCancelled
from .reinforcement import (
    LayerHoleContour,
    LayerPlane,
    ReinforcementPlanningCancelled,
    ReinforcementVolumeSlicer,
)
from .solid_reinforcement import SolidReinforcementCancelled, apply_solid_reinforcement
from .version import __version__


class HoleReinforcementCapability(orca.slicing.SlicingPipelineCapabilityBase):
    def __init__(self):
        self._classified_by_object = {}

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

        if getattr(ctx, "object", None) is None:
            return orca.ExecutionResult.skipped()

        config = validation.config
        assert config is not None
        try:
            if ctx.step == orca.slicing.Step.posSlice:
                return self._detect(ctx, config)
            return self._reinforce(ctx, config)
        except (
            MeshExtractionCancelled,
            CylinderDetectionCancelled,
            PolygonDetectionCancelled,
            HoleEndClassificationCancelled,
            ReinforcementPlanningCancelled,
            SolidReinforcementCancelled,
        ):
            return orca.ExecutionResult.success("Hole Reinforcement: cancelled")

    def _detect(self, ctx, config):
        object_id = int(ctx.object.id())
        self._classified_by_object.pop(object_id, None)
        classified = []
        volumes = extract_transformed_volumes(
            ctx.object, cancelled=ctx.cancelled
        )
        for volume in volumes:
            if ctx.cancelled():
                return orca.ExecutionResult.success("Hole Reinforcement: cancelled")
            if volume.role is not VolumeRole.MODEL_PART:
                continue
            candidates = HoleCandidateDetector().detect(
                volume.mesh, config, cancelled=ctx.cancelled
            )
            classified.extend(
                HoleEndClassifier().classify(
                    volume.mesh,
                    candidates,
                    config,
                    cancelled=ctx.cancelled,
                )
            )
        self._classified_by_object[object_id] = tuple(classified)
        accepted = sum(hole.accepted for hole in classified)
        return orca.ExecutionResult.success(
            f"Hole Reinforcement {__version__}: detected {accepted} hole(s)"
        )

    def _reinforce(self, ctx, config):
        if not config.solid_reinforcement:
            return orca.ExecutionResult.skipped("Hole Reinforcement: disabled")
        holes = self._classified_by_object.get(int(ctx.object.id()), ())
        if not any(hole.accepted for hole in holes):
            return orca.ExecutionResult.skipped("Hole Reinforcement: no target holes")

        geometry = OrcaPlanarGeometry()
        host_layers = list(ctx.object.layers())
        layers = []
        for index, layer in enumerate(host_layers):
            if ctx.cancelled():
                return orca.ExecutionResult.success("Hole Reinforcement: cancelled")
            layers.append(_copy_layer_plane(index, layer, holes, geometry, ctx.cancelled))
        planned = ReinforcementVolumeSlicer(geometry).plan(
            holes,
            tuple(layers),
            config,
            cancelled=ctx.cancelled,
        )
        result = apply_solid_reinforcement(
            host_layers,
            planned,
            geometry,
            cancelled=ctx.cancelled,
        )
        return orca.ExecutionResult.success(
            "Hole Reinforcement: solidified "
            f"{result.solid_surfaces} surface(s) in "
            f"{result.changed_collections} collection(s)"
        )


def _copy_layer_plane(index, layer, holes, geometry, cancelled=lambda: False):
    print_z = float(layer.print_z)
    model_regions = geometry.from_host(layer.lslices())
    contours = []
    for region in layer.regions():
        for surface in region.slices.surfaces:
            if cancelled():
                raise ReinforcementPlanningCancelled
            contours.extend(
                geometry.polygon_from_host(hole)
                for hole in surface.expolygon.holes
            )
    matched = _match_hole_contours(holes, contours, print_z)
    return LayerPlane(index, print_z, model_regions, matched)


def _match_hole_contours(holes, contours, print_z):
    available = list(contours)
    matched = []
    for hole_index, hole in enumerate(holes):
        if not hole.accepted:
            continue
        expected = _axis_center_at_z(hole.candidate, print_z)
        if expected is None or not available:
            continue
        contour = min(
            available,
            key=lambda item: _distance_squared(_polygon_centroid(item), expected),
        )
        maximum_distance = _candidate_diameter(hole.candidate)
        if _distance_squared(_polygon_centroid(contour), expected) > maximum_distance**2:
            continue
        matched.append(LayerHoleContour(hole_index, contour))
        available.remove(contour)
    return tuple(matched)


def _axis_center_at_z(candidate, print_z):
    if abs(candidate.axis[2]) <= 1e-9:
        return candidate.center_mm[0], candidate.center_mm[1]
    distance = (print_z - candidate.center_mm[2]) / candidate.axis[2]
    point = tuple(
        candidate.center_mm[index] + candidate.axis[index] * distance
        for index in range(3)
    )
    axial = sum(point[index] * candidate.axis[index] for index in range(3))
    if axial < candidate.axial_start_mm - 1e-7 or axial > candidate.axial_end_mm + 1e-7:
        return None
    return point[0], point[1]


def _candidate_diameter(candidate):
    if hasattr(candidate, "radius_mm"):
        return candidate.radius_mm * 2.0
    return candidate.across_flats_mm


def _polygon_centroid(polygon):
    area_twice = sum(
        first[0] * second[1] - second[0] * first[1]
        for first, second in zip(polygon, polygon[1:] + polygon[:1])
    )
    if abs(area_twice) <= 1e-12:
        return polygon[0]
    return tuple(
        sum(
            (first[axis] + second[axis])
            * (first[0] * second[1] - second[0] * first[1])
            for first, second in zip(polygon, polygon[1:] + polygon[:1])
        )
        / (3.0 * area_twice)
        for axis in range(2)
    )


def _distance_squared(first, second):
    return sum((a - b) ** 2 for a, b in zip(first, second))
