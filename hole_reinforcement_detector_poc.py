# /// script
# requires-python = ">=3.12"
#
# [tool.orcaslicer.plugin]
# name = "Hole Reinforcement Detector PoC"
# description = "Detects small vertical circular holes without modifying slice geometry."
# author = "furutsubaki"
# version = "0.04"
# type = "slicing-pipeline"
# ///
"""垂直円穴の検出条件とレイヤー間連結を検証する、形状変更前のPoC。"""

import json
import math
from datetime import datetime
from pathlib import Path

import orca


_DEFAULTS = {
    "max_hole_diameter_mm": 10.0,
    "reinforcement_width_mm": 2.0,
    "min_continuous_layers": 3,
    "circularity_tolerance": 0.10,
    "solid_reinforcement": 0.0,
    "extra_perimeters": 0,
}

_DIAGNOSTIC_LOG = Path(__file__).with_name("diagnostic.log")


def _write_diagnostic(message, reset=False):
    mode = "w" if reset else "a"
    timestamp = datetime.now().astimezone().isoformat(timespec="milliseconds")
    with _DIAGNOSTIC_LOG.open(mode, encoding="utf-8") as stream:
        stream.write(f"{timestamp} {message}\n")


def _config(plugin):
    try:
        supplied = json.loads(plugin.get_config())
    except (AttributeError, TypeError, ValueError):
        supplied = {}

    result = dict(_DEFAULTS)
    for key in result:
        if key in supplied:
            result[key] = supplied[key]
    return result


def _ring_metrics(ring, scaled_mm):
    points = [(float(point.x), float(point.y)) for point in ring.points]
    if len(points) < 3:
        return None

    twice_signed_area = 0.0
    centroid_x_numerator = 0.0
    centroid_y_numerator = 0.0
    perimeter = 0.0
    xs = []
    ys = []
    for index, (x1, y1) in enumerate(points):
        x2, y2 = points[(index + 1) % len(points)]
        cross = x1 * y2 - x2 * y1
        twice_signed_area += cross
        centroid_x_numerator += (x1 + x2) * cross
        centroid_y_numerator += (y1 + y2) * cross
        perimeter += math.hypot(x2 - x1, y2 - y1)
        xs.append(x1)
        ys.append(y1)

    if abs(twice_signed_area) < 1.0 or perimeter <= 0.0:
        return None

    area = abs(twice_signed_area) / 2.0
    centroid_divisor = 3.0 * twice_signed_area
    center_x = centroid_x_numerator / centroid_divisor
    center_y = centroid_y_numerator / centroid_divisor
    equivalent_diameter = 2.0 * math.sqrt(area / math.pi) / scaled_mm
    bounding_diameter = max(max(xs) - min(xs), max(ys) - min(ys)) / scaled_mm
    circularity = 4.0 * math.pi * area / (perimeter * perimeter)
    return {
        "center_x_mm": center_x / scaled_mm,
        "center_y_mm": center_y / scaled_mm,
        "diameter_mm": equivalent_diameter,
        "bounding_diameter_mm": bounding_diameter,
        "circularity": circularity,
        "points_scaled": [(int(x), int(y)) for x, y in points],
    }


def _candidates_for_layer(layer, layer_index, scaled_mm, config):
    candidates = []
    minimum_circularity = 1.0 - float(config["circularity_tolerance"])
    maximum_diameter = float(config["max_hole_diameter_mm"])
    for region in layer.regions():
        for surface in region.slices.surfaces:
            for hole in surface.expolygon.holes:
                metrics = _ring_metrics(hole, scaled_mm)
                if metrics is None:
                    continue
                if metrics["diameter_mm"] <= maximum_diameter and metrics["circularity"] >= minimum_circularity:
                    metrics["layer_index"] = layer_index
                    metrics["print_z_mm"] = float(layer.print_z)
                    candidates.append(metrics)
    return candidates


def _same_hole(previous, current):
    diameter_tolerance = max(0.20, previous["diameter_mm"] * 0.05)
    center_tolerance = max(0.20, previous["diameter_mm"] * 0.05)
    center_distance = math.hypot(
        previous["center_x_mm"] - current["center_x_mm"],
        previous["center_y_mm"] - current["center_y_mm"],
    )
    return (
        abs(previous["diameter_mm"] - current["diameter_mm"]) <= diameter_tolerance
        and center_distance <= center_tolerance
    )


def _continuous_tracks(layer_candidates):
    completed = []
    active = []
    for candidates in layer_candidates:
        unused = list(candidates)
        next_active = []
        for track in active:
            match = next((candidate for candidate in unused if _same_hole(track[-1], candidate)), None)
            if match is None:
                completed.append(track)
                continue
            track.append(match)
            unused.remove(match)
            next_active.append(track)
        next_active.extend([[candidate] for candidate in unused])
        active = next_active
    return completed + active


def _targets_by_layer(tracks):
    targets = {}
    for track in tracks:
        for candidate in track:
            targets.setdefault(candidate["layer_index"], []).append(candidate)
    return targets


def _copy_surface(surface, expolygon, surface_type=None):
    copied = orca.host.Surface(surface_type or surface.surface_type, expolygon)
    copied.thickness = surface.thickness
    copied.bridge_angle = surface.bridge_angle
    copied.extra_perimeters = surface.extra_perimeters
    return copied


def _expanded_targets(targets, width_scaled):
    expanded = []
    for target in targets:
        polygon = orca.host.Polygon()
        for x, y in target["points_scaled"]:
            polygon.append(orca.host.Point(x, y))
        expanded.extend(orca.host.ExPolygon(polygon).offset(width_scaled))
    return expanded


class HoleReinforcementDetector(orca.slicing.SlicingPipelineCapabilityBase):
    def get_name(self):
        return "Hole Reinforcement Detector PoC"

    def get_default_config(self):
        return _DEFAULTS

    def execute(self, ctx):
        if ctx.object is None:
            return orca.ExecutionResult.success()

        if ctx.step == orca.slicing.Step.posPrepareInfill:
            return self._reinforce_fill_surfaces(ctx)
        if ctx.step != orca.slicing.Step.posSlice:
            return orca.ExecutionResult.success()

        _write_diagnostic("execute(posSlice): start", reset=True)
        try:
            config = _config(self)
            _write_diagnostic(f"config={json.dumps(config, sort_keys=True)}")
            scaled_mm = 1.0 / orca.slicing.unscale(1)
            layer_candidates = []
            for layer_index, layer in enumerate(ctx.object.layers()):
                if ctx.cancelled():
                    _write_diagnostic("execute(posSlice): cancelled")
                    return orca.ExecutionResult.success("Hole detector: cancelled")
                layer_candidates.append(_candidates_for_layer(layer, layer_index, scaled_mm, config))

            candidate_count = sum(len(candidates) for candidates in layer_candidates)
            _write_diagnostic(f"layers={len(layer_candidates)}, candidates={candidate_count}")
            for layer_index, candidates in enumerate(layer_candidates):
                for candidate in candidates:
                    _write_diagnostic(
                        f"candidate: layer={layer_index}, center=({candidate['center_x_mm']:.3f},"
                        f"{candidate['center_y_mm']:.3f}), equivalent_diameter={candidate['diameter_mm']:.3f}mm, "
                        f"bounding_diameter={candidate['bounding_diameter_mm']:.3f}mm, "
                        f"circularity={candidate['circularity']:.4f}"
                    )
            minimum_layers = max(1, int(config["min_continuous_layers"]))
            detected = [track for track in _continuous_tracks(layer_candidates) if len(track) >= minimum_layers]
            if not hasattr(self, "_targets"):
                self._targets = {}
            self._targets[ctx.object.id()] = _targets_by_layer(detected)
            details = []
            for index, track in enumerate(detected, start=1):
                average_diameter = sum(item["diameter_mm"] for item in track) / len(track)
                detail = (
                    f"#{index}: diameter={average_diameter:.2f}mm, "
                    f"layers={track[0]['layer_index']}-{track[-1]['layer_index']}, "
                    f"z={track[0]['print_z_mm']:.2f}-{track[-1]['print_z_mm']:.2f}mm"
                )
                details.append(detail)
                _write_diagnostic(detail)

            summary = f"Hole detector: {len(detected)} hole(s) detected"
            if details:
                summary += "; " + "; ".join(details)
            _write_diagnostic(summary)
            return orca.ExecutionResult.success(summary)
        except Exception as error:
            _write_diagnostic(f"execute(posSlice): error: {type(error).__name__}: {error}")
            raise

    def _reinforce_fill_surfaces(self, ctx):
        config = _config(self)
        if not bool(float(config["solid_reinforcement"])):
            _write_diagnostic("execute(posPrepareInfill): solid reinforcement disabled")
            return orca.ExecutionResult.success("Hole reinforcement: disabled")

        targets = getattr(self, "_targets", {}).get(ctx.object.id(), {})
        if not targets:
            _write_diagnostic("execute(posPrepareInfill): no tracked holes")
            return orca.ExecutionResult.success("Hole reinforcement: no tracked holes")

        scaled_mm = 1.0 / orca.slicing.unscale(1)
        width_scaled = int(round(float(config["reinforcement_width_mm"]) * scaled_mm))
        if width_scaled <= 0:
            _write_diagnostic("execute(posPrepareInfill): reinforcement width is zero")
            return orca.ExecutionResult.success("Hole reinforcement: zero width")

        reinforced_regions = 0
        reinforced_rings = 0
        for layer_index, layer in enumerate(ctx.object.layers()):
            layer_targets = targets.get(layer_index, [])
            if not layer_targets:
                continue
            expanded_targets = _expanded_targets(layer_targets, width_scaled)
            for region in layer.regions():
                rebuilt = []
                changed = False
                for surface in region.fill_surfaces.surfaces:
                    if not surface.is_internal() or surface.is_solid():
                        rebuilt.append(_copy_surface(surface, surface.expolygon))
                        continue

                    rings = [
                        ring
                        for expanded_geometry in expanded_targets
                        for ring in surface.expolygon.intersection_ex(expanded_geometry)
                    ]
                    if not rings:
                        rebuilt.append(_copy_surface(surface, surface.expolygon))
                        continue

                    remaining = [surface.expolygon]
                    for expanded_geometry in expanded_targets:
                        next_remaining = []
                        for geometry in remaining:
                            next_remaining.extend(geometry.diff_ex(expanded_geometry))
                        remaining = next_remaining

                    rebuilt.extend(_copy_surface(surface, geometry) for geometry in remaining)
                    rebuilt.extend(
                        _copy_surface(surface, geometry, orca.host.stInternalSolid)
                        for geometry in rings
                    )
                    changed = True
                    reinforced_rings += len(rings)

                if changed:
                    region.fill_surfaces.set(rebuilt)
                    reinforced_regions += 1

        message = (
            f"Hole reinforcement: solidified {reinforced_rings} ring surface(s) "
            f"in {reinforced_regions} region(s)"
        )
        _write_diagnostic(f"execute(posPrepareInfill): {message}")
        return orca.ExecutionResult.success(message)


@orca.plugin
class HoleReinforcementDetectorPackage(orca.base):
    def register_capabilities(self):
        orca.register_capability(HoleReinforcementDetector)
