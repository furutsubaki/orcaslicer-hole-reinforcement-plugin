"""OrcaSlicerに依存しない設定スキーマと検証。"""

from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
import json
import math
from typing import TypeAlias


CURRENT_SCHEMA_VERSION = 2
SUPPORTED_SHAPES = ("circle", "hexagon", "octagon", "regular_polygon")
SUPPORTED_END_KINDS = ("through", "blind")


@dataclass(frozen=True, slots=True)
class HoleReinforcementConfig:
    schema_version: int = CURRENT_SCHEMA_VERSION
    min_hole_diameter_mm: float = 0.5
    max_hole_diameter_mm: float = 10.0
    reinforcement_width_mm: float = 2.0
    min_hole_depth_mm: float = 1.0
    enabled_shapes: tuple[str, ...] = SUPPORTED_SHAPES
    enabled_end_kinds: tuple[str, ...] = SUPPORTED_END_KINDS
    circle_radial_tolerance_mm: float = 0.1
    polygon_edge_length_tolerance_percent: float = 5.0
    polygon_angle_tolerance_deg: float = 2.0
    min_polygon_sides: int = 3
    max_polygon_sides: int = 64
    axis_tolerance_deg: float = 2.0
    solid_reinforcement: bool = True
    diagnostics_enabled: bool = True

    def to_dict(self) -> dict[str, object]:
        result = asdict(self)
        result["enabled_shapes"] = list(self.enabled_shapes)
        result["enabled_end_kinds"] = list(self.enabled_end_kinds)
        return result


PluginConfig: TypeAlias = HoleReinforcementConfig


@dataclass(frozen=True, slots=True)
class ValidationIssue:
    key: str
    code: str
    message: str


@dataclass(frozen=True, slots=True)
class ConfigValidation:
    config: HoleReinforcementConfig | None
    issues: tuple[ValidationIssue, ...] = ()

    @property
    def is_valid(self) -> bool:
        return self.config is not None and not self.issues

    def summary(self) -> str:
        return "; ".join(f"{issue.key}: {issue.message}" for issue in self.issues)


@dataclass(frozen=True, slots=True)
class _NumericRule:
    minimum: float
    maximum: float


_NUMERIC_RULES = {
    "min_hole_diameter_mm": _NumericRule(0.1, 100.0),
    "max_hole_diameter_mm": _NumericRule(0.1, 100.0),
    "reinforcement_width_mm": _NumericRule(0.1, 20.0),
    "min_hole_depth_mm": _NumericRule(0.1, 1000.0),
    "circle_radial_tolerance_mm": _NumericRule(0.0, 1.0),
    "polygon_edge_length_tolerance_percent": _NumericRule(0.0, 25.0),
    "polygon_angle_tolerance_deg": _NumericRule(0.0, 15.0),
    "axis_tolerance_deg": _NumericRule(0.0, 15.0),
}

_INTEGER_RULES = {
    "min_polygon_sides": (3, 64),
    "max_polygon_sides": (3, 64),
}

_BOOLEAN_KEYS = ("solid_reinforcement", "diagnostics_enabled")
_KNOWN_KEYS = frozenset(HoleReinforcementConfig.__dataclass_fields__)


def default_config() -> HoleReinforcementConfig:
    return HoleReinforcementConfig()


def default_config_dict() -> dict[str, object]:
    return default_config().to_dict()


def parse_json_config(raw: object) -> ConfigValidation:
    if not isinstance(raw, str):
        return _invalid("$", "type", "configuration must be a JSON string")

    try:
        supplied = json.loads(raw)
    except (TypeError, ValueError):
        return _invalid("$", "json", "configuration is not valid JSON")

    return parse_config(supplied)


def parse_config(supplied: object) -> ConfigValidation:
    if not isinstance(supplied, Mapping):
        return _invalid("$", "type", "configuration must be an object")

    defaults = default_config_dict()
    issues: list[ValidationIssue] = []

    for key in sorted(set(supplied) - _KNOWN_KEYS, key=str):
        issues.append(ValidationIssue(str(key), "unknown", "unknown setting"))

    values = dict(defaults)

    schema_version = supplied.get("schema_version", CURRENT_SCHEMA_VERSION)
    if type(schema_version) is not int:
        issues.append(ValidationIssue("schema_version", "type", "must be an integer"))
    elif schema_version not in (1, CURRENT_SCHEMA_VERSION):
        issues.append(
            ValidationIssue(
                "schema_version",
                "unsupported_version",
                f"unsupported schema version {schema_version}",
            )
        )
    else:
        values["schema_version"] = CURRENT_SCHEMA_VERSION

    for key, rule in _NUMERIC_RULES.items():
        value = supplied.get(key, defaults[key])
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            issues.append(ValidationIssue(key, "type", "must be a number"))
            continue
        number = float(value)
        if not math.isfinite(number):
            issues.append(ValidationIssue(key, "finite", "must be finite"))
            continue
        if number < rule.minimum or number > rule.maximum:
            issues.append(
                ValidationIssue(
                    key,
                    "range",
                    f"must be between {rule.minimum:g} and {rule.maximum:g}",
                )
            )
            continue
        values[key] = number

    for key, (minimum, maximum) in _INTEGER_RULES.items():
        value = supplied.get(key, defaults[key])
        if type(value) is not int:
            issues.append(ValidationIssue(key, "type", "must be an integer"))
            continue
        if value < minimum or value > maximum:
            issues.append(
                ValidationIssue(
                    key, "range", f"must be between {minimum} and {maximum}"
                )
            )
            continue
        values[key] = value

    for key in _BOOLEAN_KEYS:
        value = supplied.get(key, defaults[key])
        if type(value) is not bool:
            issues.append(ValidationIssue(key, "type", "must be a boolean"))
            continue
        values[key] = value

    values["enabled_shapes"] = _parse_choice_list(
        "enabled_shapes",
        supplied.get("enabled_shapes", defaults["enabled_shapes"]),
        SUPPORTED_SHAPES,
        issues,
    )
    values["enabled_end_kinds"] = _parse_choice_list(
        "enabled_end_kinds",
        supplied.get("enabled_end_kinds", defaults["enabled_end_kinds"]),
        SUPPORTED_END_KINDS,
        issues,
    )

    minimum_diameter = values.get("min_hole_diameter_mm")
    maximum_diameter = values.get("max_hole_diameter_mm")
    if (
        isinstance(minimum_diameter, float)
        and isinstance(maximum_diameter, float)
        and minimum_diameter > maximum_diameter
    ):
        issues.append(
            ValidationIssue(
                "min_hole_diameter_mm",
                "relation",
                "must not exceed max_hole_diameter_mm",
            )
        )

    if values["min_polygon_sides"] > values["max_polygon_sides"]:
        issues.append(
            ValidationIssue(
                "min_polygon_sides",
                "relation",
                "must not exceed max_polygon_sides",
            )
        )

    if issues:
        return ConfigValidation(None, tuple(issues))

    return ConfigValidation(HoleReinforcementConfig(**values))


def _parse_choice_list(
    key: str,
    value: object,
    supported: Sequence[str],
    issues: list[ValidationIssue],
) -> tuple[str, ...]:
    if not isinstance(value, (list, tuple)) or isinstance(value, (str, bytes)):
        issues.append(ValidationIssue(key, "type", "must be an array"))
        return ()
    if not value:
        issues.append(ValidationIssue(key, "empty", "must not be empty"))
        return ()
    if any(not isinstance(item, str) for item in value):
        issues.append(ValidationIssue(key, "item_type", "all items must be strings"))
        return ()
    if len(set(value)) != len(value):
        issues.append(ValidationIssue(key, "duplicate", "must not contain duplicates"))
        return ()

    unknown = sorted(set(value) - set(supported))
    if unknown:
        issues.append(
            ValidationIssue(key, "choice", f"unsupported value: {', '.join(unknown)}")
        )
        return ()

    return tuple(item for item in supported if item in value)


def _invalid(key: str, code: str, message: str) -> ConfigValidation:
    return ConfigValidation(None, (ValidationIssue(key, code, message),))
