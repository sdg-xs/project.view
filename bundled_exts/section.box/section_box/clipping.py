"""Apply all enabled box faces to the active viewport's RTX render product."""

from __future__ import annotations

from typing import TYPE_CHECKING

import omni.kit.app
import omni.kit.viewport.utility as vp_util
from pxr import Usd

if TYPE_CHECKING:
    from .state import SectionBoxState

_ENABLED_ATTR = "omni:rtx:scene:sectionPlane:enabled"
_PLANE_ATTR = "omni:rtx:scene:sectionPlane:plane"


class ClipPlaneController:
    def __init__(self, state: SectionBoxState) -> None:
        self._state = state
        self._target = None
        self._previous_plane = None
        self._previous_enabled = None
        self._dirty = True
        self._state.add_listener(self._on_state_changed)
        self._update_sub = (
            omni.kit.app.get_app()
            .get_update_event_stream()
            .create_subscription_to_pop(self._on_update, name="section.box.clipping")
        )
        self._on_update(None)

    def destroy(self) -> None:
        self._update_sub = None
        self._state.remove_listener(self._on_state_changed)
        self._clear_planes()

    def _on_state_changed(self, state: SectionBoxState) -> None:
        self._dirty = True
        self._on_update(None)

    def _on_update(self, event) -> None:
        self._state.sync_stage()
        if not self._state.enabled or not self._state.box.faces:
            self._clear_planes()
            return

        viewport = vp_util.get_active_viewport(usd_context_name=None)
        stage = viewport.stage if viewport else None
        target = (stage, viewport.render_product_path) if stage else None
        if target != self._target:
            self._clear_planes()
            self._dirty = True
        if target is None or not self._dirty:
            return

        stage, path = target
        prim = stage.GetPrimAtPath(path)
        attr = prim.GetAttribute(_PLANE_ATTR) if prim else None
        if not attr:
            return  # The render product may arrive after the stage opens.

        if self._target is None:
            spec = stage.GetSessionLayer().GetAttributeAtPath(attr.GetPath())
            self._previous_plane = spec.default if spec and spec.HasInfo("default") else None
            enabled_spec = stage.GetSessionLayer().GetAttributeAtPath(prim.GetAttribute(_ENABLED_ATTR).GetPath())
            self._previous_enabled = enabled_spec.default if enabled_spec and enabled_spec.HasInfo("default") else None
            self._target = target

        # The model uses outward normals. RTX keeps the positive half-space,
        # so negate all four coefficients to retain the interior of the box.
        planes = [-value for plane in self._state.box.active_planes() for value in plane]
        with Usd.EditContext(stage, stage.GetSessionLayer()):
            attr.Set(planes if planes else [0.0, 0.0, 0.0, 0.0])
            prim.GetAttribute(_ENABLED_ATTR).Set(bool(planes))
        self._dirty = False

    def _clear_planes(self) -> None:
        if self._target is None:
            return
        stage, path = self._target
        prim = stage.GetPrimAtPath(path)
        attr = prim.GetAttribute(_PLANE_ATTR) if prim else None
        if attr:
            with Usd.EditContext(stage, stage.GetSessionLayer()):
                if self._previous_plane is None:
                    attr.Clear()
                else:
                    attr.Set(self._previous_plane)
                enabled_attr = prim.GetAttribute(_ENABLED_ATTR)
                if self._previous_enabled is None:
                    enabled_attr.Clear()
                else:
                    enabled_attr.Set(self._previous_enabled)
        self._target = None
        self._previous_plane = None
        self._dirty = True
