"""Temporary material appearances, including copies of original shader networks."""

from dataclasses import dataclass
from hashlib import sha256
import re

from pxr import Gf, Sdf, Usd, UsdShade


@dataclass(frozen=True)
class Appearance:
    color: str | None
    transparency: int = 0

    def __post_init__(self):
        if self.color is not None and (not isinstance(self.color, str) or not re.fullmatch(r'#[0-9A-Fa-f]{6}', self.color)):
            raise ValueError('Inspection colors must be #RRGGBB values.')
        if type(self.transparency) is not int or not 0 <= self.transparency <= 100:
            raise ValueError('Transparency must be an integer from 0 to 100.')

    @property
    def opacity(self):
        return 1.0 - self.transparency / 100.0

    @property
    def color_key(self):
        assert self.color is not None
        return self.color.removeprefix('#').upper() + (f'_T{self.transparency}' if self.transparency else '')


def source_stage(stage, owned_layer):
    """Read original bindings without muting or changing the displayed stage."""
    session = Sdf.Layer.CreateAnonymous('original-materials.usda')
    session.TransferContent(stage.GetSessionLayer())
    session.subLayerPaths = [path for path in session.subLayerPaths
                             if owned_layer is None or path != owned_layer.identifier]
    source = Usd.Stage.Open(stage.GetRootLayer(), session, stage.GetPathResolverContext(), Usd.Stage.LoadNone)
    source.SetLoadRules(stage.GetLoadRules())
    for path in stage.GetMutedLayers():
        if owned_layer is None or path != owned_layer.identifier:
            source.MuteLayer(path)
    return source


class OriginalMaterials:
    def __init__(self, source, layer, material_root):
        self.source = source
        session = Sdf.Layer.CreateAnonymous('transparency-work.usda')
        session.subLayerPaths = [layer.identifier, source.GetSessionLayer().identifier]
        self.work = Usd.Stage.Open(source.GetRootLayer(), session, source.GetPathResolverContext(), Usd.Stage.LoadNone)
        self.work.SetLoadRules(source.GetLoadRules())
        for path in source.GetMutedLayers():
            self.work.MuteLayer(path)
        self.work.SetEditTarget(layer)
        self.material_root = material_root
        self.materials = {}

    def material(self, original, appearance):
        source_path = str(original.GetPath()) if original else ''
        key = source_path, appearance.transparency
        if key in self.materials:
            return self.materials[key]
        name = 'O' + sha256(source_path.encode()).hexdigest()[:16] + f'_T{appearance.transparency}'
        path = self.material_root + '/' + name
        mat = UsdShade.Material.Define(self.work, path)
        if original:
            mat.GetPrim().GetReferences().AddInternalReference(source_path)
            surfaces = [mat.ComputeSurfaceSource(context)[0] for context in ('', 'mdl')]
            shaders = {str(shader.GetPath()): shader for shader in surfaces if shader}
            if not shaders:
                raise ValueError(f'{source_path}: no supported surface shader')
            for shader in shaders.values():
                if not shader.GetPath().HasPrefix(mat.GetPath()):
                    raise ValueError(f'{source_path}: surface shader is outside its material')
                shader_id = shader.GetIdAttr().Get() or shader.GetSourceAssetSubIdentifier('mdl')
                if shader_id == 'UsdPreviewSurface':
                    self._input(shader, 'opacity', Sdf.ValueTypeNames.Float, appearance.opacity)
                    self._input(shader, 'opacityThreshold', Sdf.ValueTypeNames.Float, 0.0)
                elif shader_id == 'OmniPBR':
                    self._input(shader, 'enable_opacity', Sdf.ValueTypeNames.Bool, True)
                    self._input(shader, 'enable_opacity_texture', Sdf.ValueTypeNames.Bool, False)
                    self._input(shader, 'opacity_constant', Sdf.ValueTypeNames.Float, appearance.opacity)
                    self._input(shader, 'opacity_threshold', Sdf.ValueTypeNames.Float, 0.0)
                else:
                    raise ValueError(f'{source_path}: transparency is unsupported for {shader_id}')
        else:
            shader = UsdShade.Shader.Define(self.work, path + '/Surface')
            shader.CreateIdAttr('UsdPreviewSurface')
            reader = UsdShade.Shader.Define(self.work, path + '/DisplayColor')
            reader.CreateIdAttr('UsdPrimvarReader_float3')
            reader.CreateInput('varname', Sdf.ValueTypeNames.Token).Set('displayColor')
            reader.CreateInput('fallback', Sdf.ValueTypeNames.Float3).Set(Gf.Vec3f(.18))
            shader.CreateInput('diffuseColor', Sdf.ValueTypeNames.Color3f).ConnectToSource(reader.ConnectableAPI(), 'result')
            shader.CreateInput('opacity', Sdf.ValueTypeNames.Float).Set(appearance.opacity)
            shader.CreateInput('opacityThreshold', Sdf.ValueTypeNames.Float).Set(0.0)
            mat.CreateSurfaceOutput().ConnectToSource(shader.ConnectableAPI(), 'surface')
        self.materials[key] = str(mat.GetPath())
        return self.materials[key]

    @staticmethod
    def _input(shader, name, value_type, value):
        input_value = shader.CreateInput(name, value_type)
        input_value.DisconnectSource()
        input_value.Set(value)
