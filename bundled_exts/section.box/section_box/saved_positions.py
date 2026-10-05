"""Explicit named positions stored in the scene's root layer."""

from __future__ import annotations

import math
import os
from typing import TYPE_CHECKING
from uuid import uuid4

from pxr import Gf, Sdf, Usd

from .commands import SaveSectionBoxPosition, execute
from .model import Face, SectionBox

if TYPE_CHECKING:
    from .state import SectionBoxState


class SavedPositionStore:
    def __init__(self, state: SectionBoxState) -> None:
        self.state = state

    def _positions_path(self) -> Sdf.Path:
        return Sdf.Path(self.state.stage_prim_path).AppendChild("Presets")

    def list_positions(self) -> list[tuple[str, str]]:
        stage = self.state.stage
        parent = stage.GetPrimAtPath(self._positions_path()) if stage else None
        if not parent:
            return []
        positions = []
        for prim in parent.GetChildren():
            attr = prim.GetAttribute("sectionBox:name")
            name = attr.Get() if attr else None
            if name:
                positions.append((str(prim.GetPath()), name))
        return sorted(positions, key=lambda item: (item[1].casefold(), item[0]))

    def require_writable(self) -> None:
        self.state.sync_stage()
        stage = self.state.stage
        if not stage:
            raise ValueError("Open a scene before saving a position.")
        layer = stage.GetRootLayer()
        local_read_only = layer.realPath and os.path.isfile(layer.realPath) and not os.access(layer.realPath, os.W_OK)
        if not layer.permissionToEdit or (not layer.anonymous and not layer.permissionToSave) or local_read_only:
            raise ValueError("This scene is read-only. Save a writable scene copy to change saved positions.")

    def save_new(self, name: str) -> str:
        self.require_writable()
        name = name.strip()
        if not name:
            raise ValueError("Enter a name for the saved position.")
        if any(label.casefold() == name.casefold() for _, label in self.list_positions()):
            raise ValueError("That name already exists. Use Update or choose another name.")
        path = str(self._positions_path().AppendChild(f"Box_{uuid4().hex}"))
        return execute(SaveSectionBoxPosition, store=self, path=path, name=name, box=self.state.box)

    def load(self, path: str) -> None:
        self.state.sync_stage()
        prim = self._get_position(path)
        values = [prim.GetAttribute(f"sectionBox:{key}").Get() for key in ("size", "transform", "faces")]
        if any(value is None for value in values):
            raise ValueError("This saved position is incomplete.")
        size, transform, names = values
        if any(not math.isfinite(v) or v < 0 for v in size) or any(
            not math.isfinite(transform[r, c]) for r in range(4) for c in range(4)
        ):
            raise ValueError("This saved position contains invalid dimensions or coordinates.")
        if any(name not in Face.__members__ for name in names):
            raise ValueError("This saved position contains unknown faces.")
        box = SectionBox(
            size=Gf.Vec3d(size), transform=Gf.Matrix4d(transform), faces=frozenset(Face[name] for name in names)
        )
        self.state.edit(box=box, enabled=True, saved_position_path=path)

    def update(self, path: str) -> None:
        self.require_writable()
        prim = self._get_position(path)
        execute(
            SaveSectionBoxPosition,
            store=self,
            path=path,
            name=prim.GetAttribute("sectionBox:name").Get(),
            box=self.state.box,
        )

    def delete(self, path: str) -> None:
        self.require_writable()
        self._get_position(path)
        execute(SaveSectionBoxPosition, store=self, path=path, name="", box=self.state.box, delete=True)

    def _get_position(self, path: str) -> Usd.Prim:
        stage = self.state.stage
        if not stage or not path or Sdf.Path(path).GetParentPath() != self._positions_path():
            raise ValueError("Select a saved position in the current scene.")
        prim = stage.GetPrimAtPath(path)
        if not prim or not prim.IsActive() or not prim.GetAttribute("sectionBox:name"):
            raise ValueError("The saved position no longer exists.")
        return prim

    @staticmethod
    def write_position(stage: Usd.Stage, path: str, name: str, box: SectionBox) -> None:
        prim = stage.DefinePrim(path, "Scope")
        prim.SetActive(True)
        for key, value_type, value in (
            ("name", Sdf.ValueTypeNames.String, name),
            ("size", Sdf.ValueTypeNames.Double3, box.size),
            ("transform", Sdf.ValueTypeNames.Matrix4d, box.transform),
            ("faces", Sdf.ValueTypeNames.StringArray, [face.name for face in Face if face in box.faces]),
        ):
            prim.CreateAttribute(f"sectionBox:{key}", value_type, custom=True).Set(value)
        prim.SetDisplayName(name)
