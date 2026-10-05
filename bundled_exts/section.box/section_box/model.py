"""Pure section-box geometry. No omni, no carb, no I/O, so it is testable from plain CPython."""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass, field, replace
from enum import Enum

from pxr import Gf


class Face(Enum):
    MIN_X = (0, -1.0)
    MAX_X = (0, 1.0)
    MIN_Y = (1, -1.0)
    MAX_Y = (1, 1.0)
    MIN_Z = (2, -1.0)
    MAX_Z = (2, 1.0)

    @property
    def axis(self) -> int:
        return self.value[0]

    @property
    def sign(self) -> float:
        return self.value[1]

    @property
    def opposite(self) -> Face:
        return Face((self.axis, -self.sign))


AXIS_VECTORS: tuple[Gf.Vec3d, Gf.Vec3d, Gf.Vec3d] = (
    Gf.Vec3d(1.0, 0.0, 0.0),
    Gf.Vec3d(0.0, 1.0, 0.0),
    Gf.Vec3d(0.0, 0.0, 1.0),
)

# Lives beside corners() because the pairs are meaningless without that corner bit ordering.
EDGE_INDICES: tuple[tuple[int, int], ...] = tuple((i, i | bit) for i in range(8) for bit in (1, 2, 4) if not i & bit)

_VALID_AXES = (0, 1, 2)


def _require_axis(axis: int) -> None:
    if axis not in _VALID_AXES:
        raise ValueError(f"axis must be 0, 1 or 2, got {axis!r}")


@dataclass(frozen=True)
class SectionBox:
    transform: Gf.Matrix4d = field(default_factory=lambda: Gf.Matrix4d(1.0))
    size: Gf.Vec3d = field(default_factory=lambda: Gf.Vec3d(100.0, 100.0, 100.0))
    faces: frozenset[Face] = frozenset(Face)

    def active_planes(self) -> list[tuple[float, float, float, float]]:
        planes: list[tuple[float, float, float, float]] = []
        for face in Face:
            if face not in self.faces:
                continue
            local_normal = AXIS_VECTORS[face.axis] * face.sign
            normal = self.transform.TransformDir(local_normal)
            # The transform may carry scale, which TransformDir passes straight through.
            length = normal.GetLength()
            if length == 0.0:
                continue
            normal = normal / length
            local_point = local_normal * (self.size[face.axis] / 2.0)
            point = self.transform.Transform(local_point)
            offset = Gf.Dot(point, normal)
            planes.append((float(normal[0]), float(normal[1]), float(normal[2]), float(-offset)))
        return planes

    def corners(self) -> list[Gf.Vec3d]:
        half = self.size * 0.5
        return [
            self.transform.Transform(
                Gf.Vec3d(
                    half[0] if i & 1 else -half[0],
                    half[1] if i & 2 else -half[1],
                    half[2] if i & 4 else -half[2],
                )
            )
            for i in range(8)
        ]

    def with_face(self, face: Face, active: bool) -> SectionBox:
        faces = self.faces | {face} if active else self.faces - {face}
        return replace(self, faces=frozenset(faces))

    @property
    def z_rotation_degrees(self) -> float:
        """World-XY heading of the box's X axis, in signed degrees."""
        axis = self.transform.TransformDir(AXIS_VECTORS[0])
        return math.degrees(math.atan2(axis[1], axis[0]))

    def with_z_rotation(self, degrees: float) -> SectionBox:
        """Set an absolute world-Z angle while keeping the box centered and upright."""
        transform = Gf.Matrix4d().SetRotate(Gf.Rotation(AXIS_VECTORS[2], degrees))
        transform.SetTranslateOnly(self.transform.ExtractTranslation())
        return replace(self, transform=transform)

    def rotated(self, axis: int, degrees: float) -> SectionBox:
        _require_axis(axis)
        rotation = Gf.Matrix3d().SetRotate(Gf.Rotation(AXIS_VECTORS[axis], degrees))
        # Pre-multiplying applies the turn in the box's own frame, before its existing orientation.
        linear = rotation * self.transform.ExtractRotationMatrix()
        transform = Gf.Matrix4d(linear, self.transform.ExtractTranslation())
        return replace(self, transform=transform)

    def translated(self, offset: Gf.Vec3d) -> SectionBox:
        """Return a copy shifted by *offset* in world space."""
        new_transform = Gf.Matrix4d(self.transform)
        new_transform.SetTranslateOnly(self.transform.ExtractTranslation() + offset)
        return replace(self, transform=new_transform)

    def resized(self, face: Face, delta: float) -> SectionBox:
        """Grow or shrink the box by *delta* local units on *face*'s axis.

        Positive *delta* always pushes the face outward (away from the centre),
        negative pulls it inward.  The opposite face stays fixed, so the centre
        shifts by half the delta along the face's direction.
        """
        axis = face.axis
        new_extent = max(0.0, self.size[axis] + delta)
        components = [self.size[0], self.size[1], self.size[2]]
        components[axis] = new_extent
        new_size = Gf.Vec3d(*components)

        # Shift the centre so the opposite face doesn't move.
        shift = self.transform.TransformDir(AXIS_VECTORS[axis] * face.sign * ((new_extent - self.size[axis]) / 2.0))
        new_transform = Gf.Matrix4d(self.transform)
        new_transform.SetTranslateOnly(self.transform.ExtractTranslation() + shift)
        return replace(self, transform=new_transform, size=new_size)

    def inverted(self) -> SectionBox:
        return replace(self, faces=frozenset(face.opposite for face in self.faces))

    @classmethod
    def for_bounds(cls, minimum: Sequence[float], maximum: Sequence[float]) -> SectionBox:
        size = Gf.Vec3d(*(max(0.0, maximum[i] - minimum[i]) for i in range(3)))
        centre = Gf.Vec3d(*((minimum[i] + maximum[i]) / 2.0 for i in range(3)))
        return cls(transform=Gf.Matrix4d(1.0).SetTranslate(centre), size=size)
