"""Complete, named project views stored as independent records in the root layer."""

from __future__ import annotations

from dataclasses import dataclass, replace
import json
import math
import os
from typing import Callable
from uuid import uuid4

import omni.kit.commands
import omni.kit.undo
from omni.kit.usd_undo import UsdLayerUndo
from pxr import Sdf, Usd


ROOT = Sdf.Path("/__ProjectViews")
OWNER = "projectView:owner"
DATA = "projectView:data"
SCHEMA = 1
IDENTITY_PROJECT_ID = "omni:hoops:metadata:tn__IdentityData_qC:tn__ProjectID_m9"


@dataclass(frozen=True)
class ProjectId:
    """An exact scalar property value. Type is part of identity."""

    kind: str
    value: str | int | float | bool

    @classmethod
    def from_value(cls, value: object) -> ProjectId:
        if type(value) not in (str, int, float, bool):
            raise ValueError("A Project ID must be a scalar value.")
        if isinstance(value, float) and not math.isfinite(value):
            raise ValueError("A Project ID must be finite.")
        if isinstance(value, str) and not value.strip():
            raise ValueError("A blank Project ID is not selectable.")
        return cls(type(value).__name__, value)

    @classmethod
    def from_data(cls, data: dict) -> ProjectId:
        if not isinstance(data, dict) or set(data) != {"kind", "value"}:
            raise ValueError("Invalid Project ID record.")
        result = cls.from_value(data["value"])
        if result.kind != data["kind"]:
            raise ValueError("Project ID type does not match its value.")
        return result

    def to_data(self) -> dict:
        return {"kind": self.kind, "value": self.value}


@dataclass(frozen=True)
class BoxRecord:
    transform: tuple[float, ...]
    size: tuple[float, float, float]
    faces: tuple[str, ...]
    enabled: bool
    show_box: bool

    @classmethod
    def from_data(cls, data: dict) -> BoxRecord:
        if not isinstance(data, dict) or set(data) != {"transform", "size", "faces", "enabled", "show_box"}:
            raise ValueError("Invalid section box record.")
        transform = data["transform"]
        size = data["size"]
        faces = data["faces"]
        valid_faces = {"MIN_X", "MAX_X", "MIN_Y", "MAX_Y", "MIN_Z", "MAX_Z"}
        if not isinstance(transform, list) or len(transform) != 16 or any(
            type(v) not in (int, float) or not math.isfinite(v) for v in transform
        ):
            raise ValueError("Invalid section box transform.")
        if not isinstance(size, list) or len(size) != 3 or any(
            type(v) not in (int, float) or not math.isfinite(v) or v <= 0 for v in size
        ):
            raise ValueError("Invalid section box size.")
        if not isinstance(faces, list) or len(set(faces)) != len(faces) or any(face not in valid_faces for face in faces):
            raise ValueError("Invalid section box faces.")
        if type(data["enabled"]) is not bool or type(data["show_box"]) is not bool:
            raise ValueError("Invalid section box activation.")
        return cls(tuple(float(v) for v in transform), tuple(float(v) for v in size),
                   tuple(faces), data["enabled"], data["show_box"])

    def to_data(self) -> dict:
        return {"transform": list(self.transform), "size": list(self.size), "faces": list(self.faces),
                "enabled": self.enabled, "show_box": self.show_box}


@dataclass(frozen=True)
class ViewContent:
    property_name: str
    project_id: ProjectId
    box: BoxRecord
    highlight_enabled: bool
    chosen_color: str
    padding_metres: float
    metres_per_unit: float
    up_axis: str

    @classmethod
    def from_data(cls, data: dict) -> ViewContent:
        if not isinstance(data, dict) or set(data) != {
            "property_name", "project_id", "box", "highlight_enabled", "chosen_color",
            "padding_metres", "metres_per_unit", "up_axis",
        }:
            raise ValueError("Invalid project view content.")
        if not isinstance(data["property_name"], str) or not data["property_name"]:
            raise ValueError("The saved Project ID property is missing.")
        chosen = data["chosen_color"]
        if type(data["highlight_enabled"]) is not bool or not (
            isinstance(chosen, str) and len(chosen) == 7 and chosen[0] == "#"
            and all(c in "0123456789ABCDEFabcdef" for c in chosen[1:])
        ):
            raise ValueError("Invalid highlight setting.")
        padding, scale = data["padding_metres"], data["metres_per_unit"]
        if type(padding) not in (int, float) or not math.isfinite(padding) or padding < 0:
            raise ValueError("Invalid view padding.")
        if type(scale) not in (int, float) or not math.isfinite(scale) or scale <= 0:
            raise ValueError("Invalid scene units.")
        if data["up_axis"] != "Z":
            raise ValueError("This Project View version supports Z-up scenes.")
        return cls(data["property_name"], ProjectId.from_data(data["project_id"]),
                   BoxRecord.from_data(data["box"]), data["highlight_enabled"], chosen,
                   float(padding), float(scale), "Z")

    @property
    def highlight_color(self) -> str | None:
        return self.chosen_color if self.highlight_enabled else None

    def to_data(self) -> dict:
        return {"property_name": self.property_name, "project_id": self.project_id.to_data(),
                "box": self.box.to_data(), "highlight_enabled": self.highlight_enabled,
                "chosen_color": self.chosen_color, "padding_metres": self.padding_metres,
                "metres_per_unit": self.metres_per_unit, "up_axis": self.up_axis}


@dataclass(frozen=True)
class ViewRecord:
    id: str
    name: str
    content: ViewContent

    @classmethod
    def from_data(cls, data: dict) -> ViewRecord:
        if not isinstance(data, dict) or set(data) != {"version", "id", "name", "content"}:
            raise ValueError("Invalid project view record.")
        if data["version"] != SCHEMA:
            raise ValueError(f"Unsupported Project View version: {data['version']!r}.")
        if not isinstance(data["id"], str) or not data["id"] or not isinstance(data["name"], str) or not data["name"].strip():
            raise ValueError("Invalid project view name or ID.")
        return cls(data["id"], data["name"], ViewContent.from_data(data["content"]))

    def to_data(self) -> dict:
        return {"version": SCHEMA, "id": self.id, "name": self.name, "content": self.content.to_data()}


class WriteView(omni.kit.commands.Command):
    """One undoable root-layer record edit, guarded against stage replacement."""

    def __init__(self, store: ViewStore, view_id: str, record: ViewRecord | None):
        self.store = store
        self.stage = store.stage
        self.generation = store.generation
        self.path = store._path(view_id)
        self.record = record
        self.undo_layer = None

    def do(self) -> None:
        self.store._require_writable()
        if self.store.current_stage() != self.stage or self.store.current_generation() != self.generation:
            raise ValueError("The scene changed before this view could be saved.")
        self.undo_layer = UsdLayerUndo(self.stage.GetRootLayer())
        self.undo_layer.reserve(str(self.path))
        try:
            with Usd.EditContext(self.stage, self.stage.GetRootLayer()):
                parent = self.stage.GetPrimAtPath(ROOT)
                if not parent:
                    parent = self.stage.DefinePrim(ROOT, "Scope")
                    parent.CreateAttribute(OWNER, Sdf.ValueTypeNames.Bool, custom=True).Set(True)
                elif parent.GetAttribute(OWNER).Get() is not True:
                    raise ValueError("/__ProjectViews belongs to another scene component.")
                if self.record is None:
                    self.stage.OverridePrim(self.path).SetActive(False)
                else:
                    prim = self.stage.DefinePrim(self.path, "Scope")
                    prim.SetActive(True)
                    text = json.dumps(self.record.to_data(), ensure_ascii=False, allow_nan=False, separators=(",", ":"))
                    prim.CreateAttribute(DATA, Sdf.ValueTypeNames.String, custom=True).Set(text)
                    prim.SetDisplayName(self.record.name)
        except Exception:
            self.undo_layer.undo()
            raise

    def undo(self) -> None:
        if self.store.current_stage() == self.stage and self.store.current_generation() == self.generation and self.undo_layer:
            self.undo_layer.undo()


class ViewStore:
    def __init__(self, stage: Usd.Stage, generation: int,
                 current_generation: Callable[[], int] | None = None,
                 current_stage: Callable[[], Usd.Stage | None] | None = None):
        self.stage = stage
        self.generation = generation
        self.current_generation = current_generation or (lambda: self.generation)
        self.current_stage = current_stage or (lambda: self.stage)
        self.unsupported: tuple[tuple[str, str], ...] = ()

    @staticmethod
    def _path(view_id: str) -> Sdf.Path:
        if not view_id or any(c not in "0123456789abcdef" for c in view_id):
            raise ValueError("Invalid saved view ID.")
        return ROOT.AppendChild(f"View_{view_id}")

    def _require_writable(self) -> None:
        layer = self.stage.GetRootLayer()
        path = layer.realPath
        local_read_only = bool(path and os.path.isfile(path) and not os.access(path, os.W_OK))
        if not layer.permissionToEdit or (not layer.anonymous and not layer.permissionToSave) or local_read_only:
            raise ValueError("The scene is read-only. Save a writable copy before changing views.")

    def list(self) -> tuple[ViewRecord, ...]:
        parent = self.stage.GetPrimAtPath(ROOT)
        if not parent:
            return ()
        if parent.GetAttribute(OWNER).Get() is not True:
            raise ValueError("/__ProjectViews belongs to another scene component.")
        records = []
        unsupported = []
        for prim in parent.GetChildren():
            attr = prim.GetAttribute(DATA)
            if attr and attr.Get():
                try:
                    record = ViewRecord.from_data(json.loads(attr.Get()))
                    if self._path(record.id) != prim.GetPath():
                        raise ValueError("A saved view ID does not match its scene path.")
                    records.append(record)
                except (TypeError, ValueError) as exc:
                    unsupported.append((str(prim.GetPath()), str(exc)))
        self.unsupported = tuple(unsupported)
        return tuple(sorted(records, key=lambda item: (item.name.casefold(), item.id)))

    def get(self, view_id: str) -> ViewRecord:
        path = self._path(view_id)
        prim = self.stage.GetPrimAtPath(path)
        attr = prim.GetAttribute(DATA) if prim and prim.IsActive() else None
        if not attr or not attr.Get():
            raise ValueError("That saved view no longer exists in this scene.")
        record = ViewRecord.from_data(json.loads(attr.Get()))
        if record.id != view_id:
            raise ValueError("The saved view ID is inconsistent.")
        return record

    def _unique_name(self, name: str, except_id: str | None = None) -> str:
        name = name.strip()
        if not name:
            raise ValueError("Enter a name for the view.")
        if any(record.id != except_id and record.name.casefold() == name.casefold() for record in self.list()):
            raise ValueError("Another view already uses that name.")
        return name

    def _write(self, view_id: str, record: ViewRecord | None) -> None:
        self._require_writable()
        success, _ = omni.kit.undo.execute(WriteView(self, view_id, record), "WriteView", {})
        if not success:
            raise RuntimeError("Could not change the saved view. See the Kit log.")

    def new(self, name: str, content: ViewContent) -> ViewRecord:
        name = self._unique_name(name)
        record = ViewRecord(uuid4().hex, name, content)
        self._write(record.id, record)
        return record

    def update(self, view_id: str, content: ViewContent) -> ViewRecord:
        prior = self.get(view_id)
        record = replace(prior, content=content)
        self._write(view_id, record)
        return record

    def rename(self, view_id: str, name: str) -> ViewRecord:
        prior = self.get(view_id)
        record = replace(prior, name=self._unique_name(name, except_id=view_id))
        self._write(view_id, record)
        return record

    def delete(self, view_id: str) -> None:
        self.get(view_id)
        self._write(view_id, None)
