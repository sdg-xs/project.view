"""Versioned, portable templates. Loading always produces an independent scheme."""

from dataclasses import asdict
import json
from pathlib import Path

from .scheme import PALETTE, Scheme

MAX_BYTES = 10_000_000
SCENE_KEY = 'objectColorsState'


def dumps(name: str, scheme: Scheme) -> str:
    payload = {'version': 1, 'name': name, 'scope': 'stage', **asdict(scheme)}
    return json.dumps(payload, indent=2, ensure_ascii=False, allow_nan=False)


def loads(text: str) -> tuple[str, Scheme]:
    if len(text.encode('utf-8')) > MAX_BYTES:
        raise ValueError('Preset exceeds the 10 MB limit.')
    try:
        data = json.loads(text)
    except (TypeError, json.JSONDecodeError) as exc:
        raise ValueError('Preset is not valid JSON.') from exc
    if not isinstance(data, dict) or type(data.get('version')) is not int or data.get('version') != 1 or data.get('scope') != 'stage':
        raise ValueError('Expected a version 1 whole-stage Object Colors preset.')
    if data.get('mode') not in ('Property', 'File', 'Model'):
        raise ValueError('Unknown coloring mode.')
    if not isinstance(data.get('name'), str) or not data['name'].strip():
        raise ValueError('Preset needs a name.')
    if not isinstance(data.get('property_key'), str) or type(data.get('enabled')) is not bool:
        raise ValueError('Invalid property key or enabled state.')
    palettes = data.get('palettes')
    if not isinstance(palettes, dict):
        raise ValueError('Invalid palettes.')
    for criterion, assignments in palettes.items():
        if not isinstance(criterion, str) or not isinstance(assignments, dict):
            raise ValueError('Invalid palette criterion.')
        for key, color in assignments.items():
            if not isinstance(key, str) or (color is not None and color not in PALETTE):
                raise ValueError('Invalid value or palette color.')
    return data['name'], Scheme(data['mode'], data['property_key'], data['enabled'], palettes)


def read(path: str | Path) -> tuple[str, Scheme]:
    path = Path(path)
    if path.stat().st_size > MAX_BYTES:
        raise ValueError('Preset exceeds the 10 MB limit.')
    return loads(path.read_text(encoding='utf-8'))


def export(path: str | Path, name: str, scheme: Scheme) -> None:
    text = dumps(name, scheme)
    loads(text)
    # Templates are immutable through this API, including accidental re-exports.
    with Path(path).open('x', encoding='utf-8') as stream:
        stream.write(text)


def save_scene(stage, scheme: Scheme) -> bool:
    layer = stage.GetRootLayer()
    if not layer.permissionToEdit:
        return False
    data = dict(layer.customLayerData)
    data[SCENE_KEY] = dumps('Scene colors', scheme)
    layer.customLayerData = data
    return True


def load_scene(stage) -> Scheme:
    text = stage.GetRootLayer().customLayerData.get(SCENE_KEY)
    return loads(text)[1] if text else Scheme()
