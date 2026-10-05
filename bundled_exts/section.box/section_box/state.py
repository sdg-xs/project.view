"""Runtime inspection state, scoped to the active viewport's USD stage."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, replace

import carb.settings
import omni.kit.viewport.utility as vp_util
import omni.usd
from pxr import Gf

from .commands import EditSectionBox, execute
from .model import Face, SectionBox


@dataclass(frozen=True)
class Inspection:
    box: SectionBox
    enabled: bool = False
    show_box: bool = True
    saved_position_path: str = ""


class SectionBoxState:
    def __init__(self) -> None:
        self._settings = carb.settings.get_settings()
        self._listeners: list[Callable] = []
        self._value = Inspection(self.default_box())
        self._edit_start = None
        self.generation = 0
        self.stage = None
        self._context = None
        self._stage_event_sub = None
        self.sync_stage()

    @staticmethod
    def active_context():
        viewport = vp_util.get_active_viewport(usd_context_name=None)
        return omni.usd.get_context(viewport.usd_context_name if viewport else "")

    def sync_stage(self) -> None:
        context = self.active_context()
        if context != self._context:
            self._context = context
            self._stage_event_sub = (
                context.get_stage_event_stream().create_subscription_to_pop(self._on_stage_event) if context else None
            )
        stage = context.get_stage() if context else None
        if stage != self.stage:
            self.stage = stage
            self.generation += 1
            self._edit_start = None
            self._value = Inspection(self.default_box())
            self.notify()

    def _on_stage_event(self, event) -> None:
        if event.type in (int(omni.usd.StageEventType.OPENED), int(omni.usd.StageEventType.CLOSED)):
            self.sync_stage()

    def destroy(self) -> None:
        self.generation += 1
        self._stage_event_sub = None
        self._edit_start = None
        self._listeners.clear()

    @property
    def snapshot(self) -> Inspection:
        return self._value

    def apply(self, value: Inspection) -> None:
        if value != self._value:
            self._value = value
            self.notify()

    def edit(self, **changes) -> None:
        self.sync_stage()
        value = replace(self._value, **changes)
        if value == self._value:
            return
        if self._edit_start is not None:
            self.apply(value)
        else:
            execute(EditSectionBox, state=self, before=self._value, after=value, generation=self.generation)

    def begin_edit(self) -> None:
        self.sync_stage()
        self._edit_start = self._value

    def end_edit(self) -> None:
        before, self._edit_start = self._edit_start, None
        if before is not None and before != self._value:
            execute(EditSectionBox, state=self, before=before, after=self._value, generation=self.generation)

    @property
    def box(self) -> SectionBox:
        return self._value.box

    @box.setter
    def box(self, value: SectionBox) -> None:
        self.apply(replace(self._value, box=value))

    @property
    def enabled(self) -> bool:
        return self._value.enabled

    @enabled.setter
    def enabled(self, value: bool) -> None:
        self.apply(replace(self._value, enabled=value))

    @property
    def show_box(self) -> bool:
        return self._value.show_box

    @property
    def saved_position_path(self) -> str:
        return self._value.saved_position_path

    @property
    def stage_prim_path(self) -> str:
        return str(self._settings.get("/persistent/exts/section.box/stagePrimPath") or "/SectionBox")

    def add_listener(self, callback: Callable) -> None:
        if callback not in self._listeners:
            self._listeners.append(callback)

    def remove_listener(self, callback: Callable) -> None:
        if callback in self._listeners:
            self._listeners.remove(callback)

    def toggle_face(self, face: Face) -> None:
        self.set_face(face, face not in self.box.faces)

    def set_face(self, face: Face, active: bool) -> None:
        self.edit(box=self.box.with_face(face, active))

    def set_size_component(self, axis: int, value: float) -> None:
        components = list(self.box.size)
        components[axis] = max(0.0, value)
        self.edit(box=replace(self.box, size=Gf.Vec3d(*components)))

    def reset(self) -> None:
        self.edit(box=self.default_box(), saved_position_path="")

    def default_box(self) -> SectionBox:
        size = self._settings.get("/persistent/exts/section.box/defaultSize") or [100.0] * 3
        names = self._settings.get("/persistent/exts/section.box/defaultFaces")
        faces = (
            frozenset(Face[name] for name in names if name in Face.__members__)
            if names is not None
            else frozenset(Face)
        )
        return SectionBox(size=Gf.Vec3d(*size), faces=faces)

    def notify(self) -> None:
        for listener in list(self._listeners):
            try:
                listener(self)
            except Exception:
                import traceback

                traceback.print_exc()
