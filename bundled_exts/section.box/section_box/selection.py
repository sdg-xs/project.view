"""Selected USD geometry expressed as a fitted box or a world-space center."""

from __future__ import annotations

import math
import sys
from collections.abc import Iterable
from typing import TYPE_CHECKING

import numpy as np
from numpy.typing import ArrayLike
from pxr import Gf, Usd, UsdGeom

from .footprint import convex_hull, minimum_rectangle
from .model import SectionBox

if TYPE_CHECKING:
    from omni.usd import UsdContext

ProjectedPoints = tuple[list[tuple[float, float]], float, float]
MeshCache = dict[tuple[str, bytes], tuple[ProjectedPoints | None, Gf.Vec3d]]


def fit_box_to_selection(context: UsdContext | None) -> SectionBox | None:
    """Fit visible geometry with horizontal top and bottom faces."""
    if context is None:
        return None
    stage = context.get_stage()
    if stage is None:
        return None
    selection = context.get_selection()
    paths = selection.get_selected_prim_paths() if selection else []
    return fit_box_to_paths(stage, paths)


def fit_box_to_paths(
    stage: Usd.Stage | None, paths: Iterable[str], *, time: Usd.TimeCode = Usd.TimeCode.Default()
) -> SectionBox | None:
    """Fit visible geometry at explicit prim paths without changing selection."""
    if stage is None:
        return None
    roots = []
    for path in sorted(set(paths)):
        prim = stage.GetPrimAtPath(path)
        if prim.IsValid() and not any(prim.GetPath().HasPrefix(root.GetPath()) for root in roots):
            roots.append(prim)
    if not roots:
        return None

    transforms = UsdGeom.XformCache(time)
    purposes = [UsdGeom.Tokens.default_, UsdGeom.Tokens.render, UsdGeom.Tokens.proxy]
    bounds = UsdGeom.BBoxCache(time, purposes)
    sources = [source for root in roots for source in _visible_sources(root, time, purposes)[0]]
    if not sources:
        return None
    anchor = transforms.GetLocalToWorldTransform(sources[0][0]).ExtractTranslation()
    for prim, mesh in sources:
        if not mesh:
            continue
        points = UsdGeom.Mesh(prim).GetPointsAttr().Get(time)
        if points is None or not len(points):
            continue
        first = Gf.Vec3d(points[0])
        if all(math.isfinite(value) for value in first):
            anchor = transforms.GetLocalToWorldTransform(prim).Transform(first)
            break
    hull = []
    low, high = math.inf, -math.inf
    mesh_cache: MeshCache = {}
    for prim, mesh in sources:
        source = None
        if mesh:
            source = _project_mesh(prim, transforms.GetLocalToWorldTransform(prim), anchor, time, mesh_cache)
        if source is None:
            bound = bounds.ComputeWorldBound(prim)
            extent = bound.GetRange()
            if extent.IsEmpty():
                if mesh:
                    return None
                continue
            matrix = Gf.Matrix4d(bound.GetMatrix())
            matrix.SetTranslateOnly(matrix.ExtractTranslation() - anchor)
            source = _project_points([extent.GetCorner(i) for i in range(8)], matrix)
            if source is None:
                return None
        source_hull, source_low, source_high = source
        hull = convex_hull(hull + source_hull)
        low, high = min(low, source_low), max(high, source_high)
    if not hull:
        return None

    rectangle = minimum_rectangle(hull)
    c, s = rectangle.cosine, rectangle.sine
    a = (rectangle.minimum[0] + rectangle.maximum[0]) / 2
    b = (rectangle.minimum[1] + rectangle.maximum[1]) / 2
    height = (low + high) / 2
    axes = Gf.Matrix3d(c, s, 0, -s, c, 0, 0, 0, 1)
    center = anchor + Gf.Vec3d(c * a - s * b, s * a + c * b, height)
    size = Gf.Vec3d(
        rectangle.maximum[0] - rectangle.minimum[0], rectangle.maximum[1] - rectangle.minimum[1], high - low
    )
    padding = max(1e-9, 32 * sys.float_info.epsilon * max(1.0, *(abs(value) for value in center), *size))
    return SectionBox(transform=Gf.Matrix4d(axes, center), size=size + Gf.Vec3d(2 * padding))


def classify_visible_paths(
    stage: Usd.Stage | None, paths: Iterable[str], *, time: Usd.TimeCode = Usd.TimeCode.Default()
) -> tuple[list[str], list[str], list[str]]:
    """Partition asset roots into visible geometry, hidden geometry, and no usable geometry."""
    visible, hidden, no_geometry = [], [], []
    purposes = [UsdGeom.Tokens.default_, UsdGeom.Tokens.render, UsdGeom.Tokens.proxy]
    bounds = UsdGeom.BBoxCache(time, purposes) if stage is not None else None
    for path in sorted(set(paths)):
        prim = stage.GetPrimAtPath(path) if stage is not None else None
        if prim is None or not prim.IsValid():
            no_geometry.append(path)
            continue
        sources, has_hidden_subtree = _visible_sources(prim, time, purposes)
        if any(not bounds.ComputeWorldBound(source).GetRange().IsEmpty() for source, _ in sources):
            visible.append(path)
        elif has_hidden_subtree:
            hidden.append(path)
        else:
            no_geometry.append(path)
    return visible, hidden, no_geometry


def _visible_sources(
    root: Usd.Prim, time: Usd.TimeCode, purposes: list[str]
) -> tuple[list[tuple[Usd.Prim, bool]], bool]:
    sources: list[tuple[Usd.Prim, bool]] = []
    has_hidden_subtree = False
    traversal = iter(Usd.PrimRange(root, Usd.TraverseInstanceProxies()))
    for prim in traversal:
        imageable = UsdGeom.Imageable(prim)
        if imageable and imageable.ComputeVisibility(time) == UsdGeom.Tokens.invisible:
            has_hidden_subtree = True
            traversal.PruneChildren()
            continue
        if prim.IsA(UsdGeom.PointInstancer):
            traversal.PruneChildren()
        if not prim.IsA(UsdGeom.Boundable) or (imageable and imageable.ComputePurpose() not in purposes):
            continue
        sources.append((prim, prim.IsA(UsdGeom.Mesh)))
    return sources, has_hidden_subtree


def _project_mesh(
    prim: Usd.Prim,
    world: Gf.Matrix4d,
    anchor: Gf.Vec3d,
    time: Usd.TimeCode,
    cache: MeshCache,
) -> ProjectedPoints | None:
    prototype = prim.GetPrimInPrototype() if prim.IsInstanceProxy() else prim
    linear = Gf.Matrix4d(world)
    linear.SetTranslateOnly(Gf.Vec3d(0))
    key = (str(prototype.GetPath()), np.asarray(linear)[:3, :3].tobytes())
    if key not in cache:
        points = UsdGeom.Mesh(prim).GetPointsAttr().Get(time)
        origin = Gf.Vec3d(points[0]) if points is not None and len(points) else Gf.Vec3d(0)
        projected = None if points is None else _project_points(points, linear, origin)
        cache[key] = projected, origin
    projected, origin = cache[key]
    if projected is None:
        return None
    hull, low, high = projected
    translation = linear.TransformDir(origin) + (world.ExtractTranslation() - anchor)
    return ([(x + translation[0], y + translation[1]) for x, y in hull], low + translation[2], high + translation[2])


def _project_points(points: ArrayLike, matrix: Gf.Matrix4d, origin: Gf.Vec3d | None = None) -> ProjectedPoints | None:
    """Return a whole source's hull and height, or refuse its nonfinite coordinates."""
    coordinates = np.asarray(points)
    rows = np.asarray(matrix)
    hull = []
    low, high = math.inf, -math.inf
    for start in range(0, len(coordinates), 65536):
        chunk = coordinates[start : start + 65536].astype(np.float64)
        if origin is not None:
            chunk -= np.asarray(origin)
        world = chunk @ rows[:3, :3] + rows[3, :3]
        if not np.isfinite(world).all():
            return None
        low, high = min(low, float(world[:, 2].min())), max(high, float(world[:, 2].max()))
        if len(world) < 512:
            hull = convex_hull(hull + [tuple(point) for point in world[:, :2].tolist()])
            continue
        xy = np.unique(world[:, :2], axis=0)
        directions = ((1, 0), (0, 1), (1, 1), (1, -1))
        extremes = []
        for dx, dy in directions:
            projection = xy[:, 0] * dx + xy[:, 1] * dy
            extremes.extend((tuple(xy[projection.argmin()].tolist()), tuple(xy[projection.argmax()].tolist())))
        interior = convex_hull(extremes)
        if len(interior) >= 3:
            inside = np.ones(len(xy), dtype=bool)
            for i, (x, y) in enumerate(interior):
                xx, yy = interior[(i + 1) % len(interior)]
                cross = (xx - x) * (xy[:, 1] - y) - (yy - y) * (xy[:, 0] - x)
                tolerance = (
                    32 * sys.float_info.epsilon * max(1.0, abs(xx - x), abs(yy - y)) * max(1.0, float(np.abs(xy).max()))
                )
                inside &= cross > tolerance
            xy = xy[~inside]
        hull = convex_hull(hull + [tuple(point) for point in xy.tolist()])
    return hull, low, high


def selection_center(context: UsdContext | None) -> Gf.Vec3d | None:
    """Return the combined world-aligned midpoint, or None for empty selection."""
    if context is None:
        return None
    selection = context.get_selection()
    paths = selection.get_selected_prim_paths() if selection else []
    if not paths:
        return None

    stage = context.get_stage()
    if stage is None:
        return None

    prims = [stage.GetPrimAtPath(path) for path in paths]
    prims = [prim for prim in prims if prim.IsValid()]
    if not prims:
        return None

    bbox_cache = UsdGeom.BBoxCache(
        Usd.TimeCode.Default(),
        [UsdGeom.Tokens.default_, UsdGeom.Tokens.render, UsdGeom.Tokens.proxy],
    )
    total_range = Gf.Range3d()
    for prim in prims:
        bbox = bbox_cache.ComputeWorldBound(prim)
        total_range = Gf.Range3d.GetUnion(total_range, bbox.ComputeAlignedRange())

    if total_range.IsEmpty():
        return None

    return total_range.GetMidpoint()
