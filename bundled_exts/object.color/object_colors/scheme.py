"""Typed grouping and deterministic palette assignments, independent of Kit/USD."""

from dataclasses import dataclass, field
import hashlib
import json
import math


PALETTE = (
    '#4E79A7', '#F28E2B', '#E15759', '#76B7B2', '#59A14F', '#EDC948',
    '#B07AA1', '#FF9DA7', '#9C755F', '#BAB0AC', '#1F77B4', '#FF7F0E',
    '#2CA02C', '#D62728', '#9467BD', '#8C564B', '#E377C2', '#7F7F7F',
    '#BCBD22', '#17BECF', '#393B79', '#637939', '#8C6D31', '#843C39',
    '#7B4173', '#6B6ECF', '#B5CF6B', '#E7BA52', '#D6616B', '#CE6DBD',
    '#3182BD', '#6BAED6', '#31A354', '#74C476', '#756BB1', '#9E9AC8',
    '#E6550D', '#FD8D3C', '#969696', '#D9D9D9',
)


@dataclass(frozen=True)
class ObjectRecord:
    path: str
    properties: dict[str, str | int | float | bool]
    file: str = ''
    model: str = ''


@dataclass
class Scheme:
    mode: str = 'Property'
    property_key: str = ''
    enabled: bool = False
    palettes: dict[str, dict[str, str | None]] = field(default_factory=dict)

    @property
    def criterion(self) -> str:
        return self.mode + ':' + (self.property_key if self.mode == 'Property' else '')

    def color(self, key: str) -> str | None:
        palette = self.palettes.setdefault(self.criterion, {})
        if key not in palette:
            if key == 'missing':
                palette[key] = '#969696'
            else:
                digest = hashlib.sha256((self.criterion + '\0' + key).encode()).digest()
                palette[key] = PALETTE[int.from_bytes(digest[:4], 'big') % len(PALETTE)]
        return palette[key]

    def set_color(self, key: str, color: str | None) -> None:
        if color is not None and color not in PALETTE:
            raise ValueError('Choose a color from the fixed palette.')
        self.palettes.setdefault(self.criterion, {})[key] = color


@dataclass(frozen=True)
class Group:
    key: str
    label: str
    objects: tuple[str, ...]
    color: str | None


def value_key(value: object) -> str:
    if value is None or (isinstance(value, float) and not math.isfinite(value)):
        return 'missing'
    if type(value) not in (str, int, float, bool):
        return 'missing'
    return type(value).__name__ + ':' + json.dumps(value, ensure_ascii=False)


def group_objects(objects: list[ObjectRecord], scheme: Scheme) -> list[Group]:
    members: dict[str, list[str]] = {}
    labels: dict[str, str] = {}
    for obj in objects:
        value = (obj.properties.get(scheme.property_key) if scheme.mode == 'Property'
                 else getattr(obj, scheme.mode.lower()) or None)
        key = value_key(value)
        members.setdefault(key, []).append(obj.path)
        labels[key] = 'Unassigned' if key == 'missing' else str(value)
    ordered = sorted(k for k in members if k != 'missing')
    shown = ordered[:100]
    if len(ordered) > 100:
        members['unmapped'] = [p for k in ordered[100:] for p in members[k]]
        labels['unmapped'] = 'Unmapped'
        shown.append('unmapped')
    if 'missing' in members:
        shown.append('missing')
    return [Group(k, labels[k], tuple(members[k]), scheme.color(k)) for k in shown]
