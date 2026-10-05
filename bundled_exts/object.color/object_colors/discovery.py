"""Discover final editable Xforms and their inherited object properties."""

from dataclasses import dataclass, field
import math
from pxr import Usd, UsdGeom, UsdLux

from .scheme import ObjectRecord

HOOPS = 'omni:hoops:metadata:'
SPATIAL_TYPES = {'IFCPROJECT', 'IFCSITE', 'IFCBUILDING', 'IFCBUILDINGSTOREY'}


@dataclass
class Scan:
    objects: list[ObjectRecord] = field(default_factory=list)
    properties: list[str] = field(default_factory=list)
    issues: list[str] = field(default_factory=list)

    def unavailable_reason(self, mode: str) -> str:
        if mode == 'Property':
            return '' if self.properties else 'No authored scalar object properties were found.'
        return '' if any(getattr(o, mode.lower()) for o in self.objects) else (
            'No source layer provenance is available.' if mode == 'File' else
            'No model asset metadata or objectColors:model mapping is available.')


def _properties(prim):
    values = {}
    for attr in prim.GetAuthoredAttributes():
        key = attr.GetName()
        if not (attr.IsCustom() or key.startswith(HOOPS)) or key.startswith('objectColors:'):
            continue
        if attr.GetTypeName().isArray:
            continue
        value = attr.Get()
        if type(value) in (str, bool, int, float) and not (isinstance(value, float) and not math.isfinite(value)):
            values[key] = value
    return values


def _provenance(prim):
    file = ''
    for spec in prim.GetPrimStack():
        if not spec.layer.anonymous and (spec.typeName or spec.referenceList.GetAppliedItems()):
            file = spec.layer.realPath or spec.layer.identifier
            break
    model = ''
    current = prim
    while current and not current.IsPseudoRoot():
        attr = current.GetAttribute('objectColors:model')
        if attr and attr.Get():
            model = str(attr.Get())
            break
        api = Usd.ModelAPI(current)
        if api.GetAssetName():
            model = api.GetAssetName()
            break
        if api.GetAssetIdentifier().path:
            model = api.GetAssetIdentifier().path
            break
        current = current.GetParent()
    return file, model


def scan_stage(stage) -> Scan:
    steps = scan_steps(stage)
    while True:
        try:
            next(steps)
        except StopIteration as done:
            return done.value


def _contains_scene_setup(prim, prototype_setup):
    if prim.HasAPI(UsdLux.LightAPI) or prim.IsA(UsdGeom.Camera):
        return True
    root = prim.GetPrototype() if prim.IsInstance() else prim
    path = str(root.GetPath())
    if path in prototype_setup:
        return prototype_setup[path]
    found = any(p.HasAPI(UsdLux.LightAPI) or p.IsA(UsdGeom.Camera)
                for p in Usd.PrimRange(root, Usd.TraverseInstanceProxies()))
    if prim.IsInstance():
        prototype_setup[path] = found
    return found


def scan_steps(stage):
    result = Scan()
    source_roots = set()
    for prim in stage.Traverse():
        if prim.IsInstance():
            refs = prim.GetMetadata('references')
            for ref in refs.GetAppliedItems() if refs else []:
                source = stage.GetPrimAtPath(ref.primPath) if ref.primPath else None
                if not ref.assetPath and source and not source.IsAbstract():
                    source_roots.add(ref.primPath)
    for path in source_roots:
        result.issues.append(f'{path}: instance source geometry is excluded; color the placed instances instead')
    properties: dict[str, dict[str, str | int | float | bool]] = {}
    leaves: dict[str, Usd.Prim] = {}
    for index, prim in enumerate(stage.Traverse()):
        if index % 128 == 0:
            yield index
        if any(prim.GetPath().HasPrefix(p) for p in source_roots):
            continue
        if not prim.IsA(UsdGeom.Xform):
            continue
        path = str(prim.GetPath())
        parent = prim.GetParent()
        while parent and not parent.IsPseudoRoot() and not parent.IsA(UsdGeom.Xform):
            parent = parent.GetParent()
        parent_path = str(parent.GetPath())
        leaves.pop(parent_path, None)
        authored = _properties(prim)
        properties[path] = properties.get(parent_path, {}) | authored
        if str(authored.get(HOOPS + 'TYPE', '')) not in SPATIAL_TYPES:
            leaves[path] = prim
    prototype_setup: dict[str, bool] = {}
    for index, (path, prim) in enumerate(leaves.items()):
        if index % 128 == 0:
            yield index
        if any(source.HasPrefix(prim.GetPath()) for source in source_roots):
            continue
        if _contains_scene_setup(prim, prototype_setup):
            continue
        file, model = _provenance(prim)
        result.objects.append(ObjectRecord(path, properties[path], file, model))
    result.properties = sorted({k for obj in result.objects for k in obj.properties})
    return result


def property_label(key: str) -> str:
    if key.startswith(HOOPS):
        return '[HOOPS] ' + key.removeprefix(HOOPS).replace(':', ' / ')
    return key.replace(':', ' / ')
