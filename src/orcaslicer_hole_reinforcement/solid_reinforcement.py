"""補強領域で内部Surfaceを分割し、対象部分だけをソリッド化する。"""

from collections.abc import Callable, Sequence
from dataclasses import dataclass

import orca

from .orca_geometry import OrcaPlanarGeometry
from .reinforcement import ReinforcementRegion


class SolidReinforcementCancelled(Exception):
    pass


@dataclass(frozen=True, slots=True)
class SolidReinforcementResult:
    changed_collections: int
    solid_surfaces: int


def apply_solid_reinforcement(
    layers: Sequence[object],
    planned: Sequence[ReinforcementRegion],
    geometry: OrcaPlanarGeometry,
    *,
    cancelled: Callable[[], bool] = lambda: False,
) -> SolidReinforcementResult:
    planned_by_layer = {region.layer_index: region for region in planned}
    changed_collections = 0
    solid_surfaces = 0
    for layer_index, layer in enumerate(layers):
        if cancelled():
            raise SolidReinforcementCancelled
        plan = planned_by_layer.get(layer_index)
        if plan is None:
            continue
        targets = geometry.to_host(plan.regions)
        for layer_region in layer.regions():
            collection = layer_region.fill_surfaces
            rebuilt = []
            changed = False
            for surface in collection.surfaces:
                if cancelled():
                    raise SolidReinforcementCancelled
                if surface.surface_type != orca.host.stInternal:
                    rebuilt.append(_copy_surface(surface, surface.expolygon))
                    continue

                reinforced = [
                    piece
                    for target in targets
                    for piece in surface.expolygon.intersection_ex(target)
                ]
                if not reinforced:
                    rebuilt.append(_copy_surface(surface, surface.expolygon))
                    continue
                remaining = [surface.expolygon]
                for target in targets:
                    remaining = [
                        piece
                        for source in remaining
                        for piece in source.diff_ex(target)
                    ]
                rebuilt.extend(_copy_surface(surface, piece) for piece in remaining)
                rebuilt.extend(
                    _copy_surface(surface, piece, orca.host.stInternalSolid)
                    for piece in reinforced
                )
                solid_surfaces += len(reinforced)
                changed = True

            if changed:
                if cancelled():
                    raise SolidReinforcementCancelled
                collection.set(rebuilt)
                changed_collections += 1
    return SolidReinforcementResult(changed_collections, solid_surfaces)


def _copy_surface(surface, expolygon, surface_type=None):
    copied = orca.host.Surface(
        surface.surface_type if surface_type is None else surface_type,
        expolygon,
    )
    copied.thickness = surface.thickness
    copied.bridge_angle = surface.bridge_angle
    copied.extra_perimeters = surface.extra_perimeters
    return copied
