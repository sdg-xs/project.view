"""Stage-local visualization layer; source geometry and materials are never edited."""

from dataclasses import dataclass, field

from pxr import Gf, Sdf, Usd, UsdGeom, UsdShade, UsdUtils

from .appearance import Appearance, OriginalMaterials, source_stage


PURPOSES = ('', 'full', 'preview')


@dataclass
class ApplyReport:
    colored: int = 0
    issues: list[str] = field(default_factory=list)
    colored_paths: list[str] = field(default_factory=list)
    unsupported_paths: list[str] = field(default_factory=list)

    @property
    def unsupported(self) -> int:
        return len(self.unsupported_paths)


def _linear(hex_color):
    values = [int(hex_color[i:i + 2], 16) / 255 for i in (1, 3, 5)]
    return Gf.Vec3f(*(v / 12.92 if v <= .04045 else ((v + .055) / 1.055) ** 2.4 for v in values))


def _binding(layer, prim_path, name, targets, strength):
    prim = Sdf.CreatePrimInLayer(layer, prim_path)
    schemas = prim.GetInfo('apiSchemas').prependedItems if prim.HasInfo('apiSchemas') else []
    if 'MaterialBindingAPI' not in schemas:
        prim.SetInfo('apiSchemas', Sdf.TokenListOp.Create(prependedItems=schemas + ['MaterialBindingAPI']))
    relationship = prim.relationships.get(name) or Sdf.RelationshipSpec(prim, name, custom=False)
    relationship.targetPathList.explicitItems = [Sdf.Path(path) for path in targets]
    relationship.SetInfo('bindMaterialAs', strength)


def _collection_binding(layer, root, material, purpose, original, paths):
    suffix = ':' + purpose if purpose else ''
    for path in paths:
        _binding(layer, path, 'material:binding' + suffix, [material],
                 UsdShade.Tokens.weakerThanDescendants if original else UsdShade.Tokens.strongerThanDescendants)
    if root is None:
        return
    key = material.rsplit('/', 1)[1]
    name = 'objectColors_' + (key if original else key[1:]) + ('_' + purpose if original else '')
    prim = Sdf.CreatePrimInLayer(layer, root)
    schemas = prim.GetInfo('apiSchemas').prependedItems if prim.HasInfo('apiSchemas') else []
    schema = 'CollectionAPI:' + name
    if schema not in schemas:
        prim.SetInfo('apiSchemas', Sdf.TokenListOp.Create(prependedItems=schemas + [schema]))
    expansion = prim.attributes.get(f'collection:{name}:expansionRule') or Sdf.AttributeSpec(
        prim, f'collection:{name}:expansionRule', Sdf.ValueTypeNames.Token, Sdf.VariabilityUniform, False)
    expansion.default = Usd.Tokens.explicitOnly if original else Usd.Tokens.expandPrims
    includes = prim.relationships.get(f'collection:{name}:includes') or Sdf.RelationshipSpec(
        prim, f'collection:{name}:includes', custom=False)
    includes.targetPathList.explicitItems = [Sdf.Path(path) for path in paths]
    _binding(layer, root, f'material:binding:collection{suffix}:{name}',
             [f'{root}.collection:{name}', material], UsdShade.Tokens.strongerThanDescendants)


def _visibility_roots(prim):
    """Find imageable roots whose invisibility covers the asset's geometry."""
    roots: list[Sdf.Path] = []
    for part in Usd.PrimRange(prim):
        path = part.GetPath()
        if UsdGeom.Imageable(part) and not any(path.HasPrefix(root) for root in roots):
            roots.append(path)
    return roots


class ColorOverrides:
    def __init__(self, stage):
        self.stage = stage
        self.layer = None
        self.enabled = True
        self.closed = False
        self.material_root = '/__ObjectColors'
        while stage.GetPrimAtPath(self.material_root):
            self.material_root += '_'

    def set_enabled(self, enabled: bool):
        self.enabled = enabled
        if self.layer:
            if enabled:
                self.stage.UnmuteLayer(self.layer.identifier)
            else:
                self.stage.MuteLayer(self.layer.identifier)

    def apply(self, assignments: dict[str, str | Appearance]) -> ApplyReport:
        steps = self.apply_steps(assignments)
        while True:
            try:
                next(steps)
            except StopIteration as done:
                return done.value

    def apply_steps(self, assignments: dict[str, str | Appearance]):
        if self.closed:
            raise RuntimeError('Color overrides are closed.')
        appearances = {path: value if isinstance(value, Appearance) else Appearance(value)
                       for path, value in assignments.items()}
        report = ApplyReport()
        prior = self.layer
        prior_paths = list(self.stage.GetSessionLayer().subLayerPaths)
        new_layer = None
        completed = False
        try:
            new_layer = Sdf.Layer.CreateAnonymous('object-colors.usda')
            originals = (OriginalMaterials(source_stage(self.stage, prior), new_layer, self.material_root)
                         if any(a.color is None and a.transparency < 100 for a in appearances.values()) else None)
            work = originals.work if originals else Usd.Stage.Open(new_layer)
            batches: dict[tuple[str | None, str, str, bool], list[str]] = {}
            checks = []
            expected = {}
            original_targets = {}
            original_instances: dict[str, list[str]] = {}
            hidden_targets = {}
            for index, (path, appearance) in enumerate(appearances.items()):
                if index % 64 == 0:
                    yield .4 * index / len(assignments)
                prim = self.stage.GetPrimAtPath(path)
                if not prim or prim.IsInstanceProxy() or prim.IsA(UsdGeom.PointInstancer):
                    report.issues.append(f'{path}: cannot override this instance boundary')
                    report.unsupported_paths.append(path)
                    continue
                if not any(p.IsA(UsdGeom.Gprim) for p in Usd.PrimRange(prim, Usd.TraverseInstanceProxies())):
                    report.issues.append(f'{path}: no loaded renderable geometry')
                    report.unsupported_paths.append(path)
                    continue
                if appearance.transparency == 100:
                    hidden_targets[path] = _visibility_roots(prim)
                    work.OverridePrim(prim.GetPath()).SetInstanceable(False)
                    checks.append(path)
                    continue
                root = '/' + path.strip('/').split('/')[0]
                if appearance.color is None:
                    assert originals is not None
                    source = originals.source.GetPrimAtPath(path)
                    targets = [p for p in Usd.PrimRange(source, Usd.TraverseInstanceProxies())
                               if p.IsA(UsdGeom.Gprim) or p.IsA(UsdGeom.Subset)]
                    bindings = []
                    binding_roots = {}
                    try:
                        for target in targets:
                            for purpose in PURPOSES:
                                material, relationship = UsdShade.MaterialBindingAPI(target).ComputeBoundMaterial(purpose)
                                mat_path = originals.material(material, appearance)
                                bindings.append((str(target.GetPath()), mat_path, purpose))
                                binding_root = None
                                if relationship:
                                    owner = relationship.GetPrim()
                                    strength = UsdShade.MaterialBindingAPI.GetMaterialBindingStrength(relationship)
                                    if ((owner != target and strength == UsdShade.Tokens.strongerThanDescendants)
                                            or (owner == target and ':collection:' in relationship.GetName())):
                                        binding_root = str(owner.GetPath())
                                binding_roots[str(target.GetPath()), purpose] = binding_root
                    except ValueError as exc:
                        report.issues.append(f'{path}: {exc}')
                        report.unsupported_paths.append(path)
                        continue
                    # Editable copies let each mesh and face subset retain its own material.
                    original_instances[path] = []
                    for part in Usd.PrimRange(source, Usd.TraverseInstanceProxies()):
                        if part.IsInstance():
                            work.OverridePrim(part.GetPath()).SetInstanceable(False)
                            original_instances[path].append(str(part.GetPath()))
                    original_targets[path] = bindings
                    for target_path, mat_path, purpose in bindings:
                        binding_root = binding_roots[target_path, purpose]
                        batches.setdefault((binding_root, mat_path, purpose, True), []).append(target_path)
                    checks.append(path)
                    continue
                checks.append(path)
                mat_path = self.material_root + '/C' + appearance.color_key
                expected[path] = mat_path
                for purpose in PURPOSES:
                    batches.setdefault((root, mat_path, purpose, False), []).append(path)
                mat = UsdShade.Material.Get(work, mat_path)
                if not mat:
                    mat = UsdShade.Material.Define(work, mat_path)
                    shader = UsdShade.Shader.Define(work, mat_path + '/Surface')
                    shader.CreateIdAttr('UsdPreviewSurface')
                    shader.CreateInput('diffuseColor', Sdf.ValueTypeNames.Color3f).Set(_linear(appearance.color))
                    shader.CreateInput('opacity', Sdf.ValueTypeNames.Float).Set(appearance.opacity)
                    shader.CreateInput('opacityThreshold', Sdf.ValueTypeNames.Float).Set(0.0)
                    shader.CreateInput('roughness', Sdf.ValueTypeNames.Float).Set(.65)
                    mat.CreateSurfaceOutput().ConnectToSource(shader.ConnectableAPI(), 'surface')
            authored = 0
            total_bindings = sum(len(paths) for paths in batches.values())
            # Author bindings into a detached layer. Hundreds of collections on the
            # composed source stage would otherwise recompose every material copy.
            binding_layer = Sdf.Layer.CreateAnonymous('appearance-bindings.usda')
            for targets in hidden_targets.values():
                for path in targets:
                    prim_spec = Sdf.CreatePrimInLayer(binding_layer, path)
                    visibility = Sdf.AttributeSpec(
                        prim_spec, 'visibility', Sdf.ValueTypeNames.Token, Sdf.VariabilityVarying, False)
                    visibility.default = UsdGeom.Tokens.invisible
            for (collection_root, mat_path, purpose, original), paths in batches.items():
                yield .4 + .4 * authored / max(1, total_bindings)
                _collection_binding(binding_layer, collection_root, mat_path, purpose, original, paths)
                authored += len(paths)
            # Prepend our collections to source collection ordering at each root.
            for root in {k[0] for k in batches if k[0] is not None}:
                prim = binding_layer.GetPrimAtPath(root)
                ours = sorted(name for name in binding_layer.GetPrimAtPath(root).properties.keys()
                              if name.startswith('material:binding:'))
                previous = prior.GetPrimAtPath(root) if prior else None
                prior_order = [name for name in self.stage.GetPrimAtPath(root).GetPropertyOrder()
                               if previous is None or name not in previous.properties]
                prim.propertyOrder = ours + [n for n in prior_order if n not in ours]
            with Sdf.ChangeBlock():
                UsdUtils.StitchLayers(new_layer, binding_layer)
            self._replace(new_layer)
            # Reject rather than silently accept a stronger session opinion or unsupported binding.
            rejected = set()
            for owner, targets in hidden_targets.items():
                if any(UsdGeom.Imageable(self.stage.GetPrimAtPath(str(target))).ComputeVisibility()
                       != UsdGeom.Tokens.invisible for target in targets):
                    rejected.add(owner)
            for index in range(0, len(checks), 128):
                yield .8 + .2 * index / len(checks)
                paths = [path for path in checks[index:index + 128] if path in expected]
                prims = [self.stage.GetPrimAtPath(path) for path in paths]
                for purpose in PURPOSES:
                    materials, _ = UsdShade.MaterialBindingAPI.ComputeBoundMaterials(prims, purpose)
                    for path, mat in zip(paths, materials):
                        if not mat or str(mat.GetPath()) != expected[path]:
                            rejected.add(path)
            if original_targets:
                for purpose in PURPOSES:
                    targets = [(owner, target, expected) for owner, bindings in original_targets.items()
                               for target, expected, material_purpose in bindings if material_purpose == purpose]
                    prims = [self.stage.GetPrimAtPath(target) for _, target, _ in targets]
                    materials, _ = UsdShade.MaterialBindingAPI.ComputeBoundMaterials(prims, purpose)
                    for (owner, _, mat_path), mat in zip(targets, materials):
                        if not mat or str(mat.GetPath()) != mat_path:
                            rejected.add(owner)
            for path in checks:
                if path in rejected:
                    report.issues.append(f'{path}: existing binding prevented coloring')
                    report.unsupported_paths.append(path)
                else:
                    report.colored += 1
                    report.colored_paths.append(path)
            if rejected:
                with Sdf.ChangeBlock():
                    rejected_targets = set(rejected)
                    for path in rejected:
                        rejected_targets.update(target for target, _, _ in original_targets.get(path, ()))
                        for instance in original_instances.get(path, ()):
                            work.GetPrimAtPath(instance).ClearInstanceable()
                    for (collection_root, mat_path, purpose, original), paths in batches.items():
                        if collection_root is None:
                            continue
                        key = mat_path.rsplit('/', 1)[1]
                        name = 'objectColors_' + (key if original else key[1:]) + ('_' + purpose if original else '')
                        collection = Usd.CollectionAPI(work.GetPrimAtPath(collection_root), name)
                        collection.GetIncludesRel().SetTargets([p for p in paths if p not in rejected_targets])
                    for path in rejected_targets:
                        prim = work.GetPrimAtPath(path)
                        if prim:
                            prim.ClearInstanceable()
                            prim.RemoveProperty('visibility')
                            for purpose in PURPOSES:
                                prim.RemoveProperty('material:binding' + (':' + purpose if purpose else ''))
            completed = True
            return report
        finally:
            if not self.closed:
                if not completed and new_layer is not None and self.layer is new_layer:
                    assert new_layer is not None
                    session = self.stage.GetSessionLayer()
                    paths = [p for p in session.subLayerPaths if p != new_layer.identifier
                             and (prior is None or p != prior.identifier)]
                    if prior is not None:
                        index = prior_paths.index(prior.identifier)
                        paths.insert(min(index, len(paths)), prior.identifier)
                    session.subLayerPaths = paths
                    self.layer = prior
                self.set_enabled(self.enabled)

    def _replace(self, layer):
        session = self.stage.GetSessionLayer()
        prior = self.layer
        paths = [p for p in session.subLayerPaths if not prior or p != prior.identifier]
        session.subLayerPaths = [layer.identifier] + paths
        self.layer = layer
        if prior:
            self.stage.UnmuteLayer(prior.identifier)

    def close(self):
        self.closed = True
        if self.layer:
            session = self.stage.GetSessionLayer()
            session.subLayerPaths = [p for p in session.subLayerPaths if p != self.layer.identifier]
            self.stage.UnmuteLayer(self.layer.identifier)
            self.layer = None
