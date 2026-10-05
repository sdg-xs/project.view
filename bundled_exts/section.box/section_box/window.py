"""Section Box control panel — an ``omni.ui.Window`` for interactive configuration.

Provides sliders for size, checkboxes for faces,
fit-to-selection, rotation, and saved positions.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Optional

import omni.ui as ui

from .model import Face
from .saved_position_controls import SavedPositionControls
from .selection import fit_box_to_selection, selection_center

if TYPE_CHECKING:
    from .saved_positions import SavedPositionStore
    from .state import SectionBoxState

WINDOW_TITLE = "Section Box"

# Axis labels used in the UI.
_AXIS_LABELS = ("X", "Y", "Z")

# Face pairs grouped by axis for layout.
_FACE_PAIRS: tuple[tuple[Face, Face], ...] = (
    (Face.MIN_X, Face.MAX_X),
    (Face.MIN_Y, Face.MAX_Y),
    (Face.MIN_Z, Face.MAX_Z),
)


class SectionBoxWindow:
    """Standalone ``omni.ui.Window`` with section-box controls."""

    def __init__(self, state: SectionBoxState, store: SavedPositionStore) -> None:
        self._state = state
        self._store = store
        self._position_controls = None
        self._window: Optional[ui.Window] = None
        self._size_sliders: list[ui.FloatSlider] = []
        self._face_checkboxes: dict[Face, ui.CheckBox] = {}
        self._enabled_checkbox: Optional[ui.CheckBox] = None
        self._show_checkbox: Optional[ui.CheckBox] = None
        self._rotation_slider: Optional[ui.FloatSlider] = None
        self._syncing = False

        self._build_window()
        self._state.add_listener(self._on_state_changed)

    def destroy(self) -> None:
        self._state.remove_listener(self._on_state_changed)
        if self._position_controls:
            self._position_controls.destroy()
            self._position_controls = None
        if self._window:
            self._window.destroy()
            self._window = None
        self._size_sliders.clear()
        self._face_checkboxes.clear()

    @property
    def visible(self) -> bool:
        return self._window.visible if self._window else False

    @visible.setter
    def visible(self, value: bool) -> None:
        if self._window:
            self._window.visible = value

    # --- window construction -------------------------------------------------

    def _build_window(self) -> None:
        self._window = ui.Window(WINDOW_TITLE, width=320, height=480)
        with self._window.frame:
            with ui.ScrollingFrame():
                with ui.VStack(spacing=6, height=0):
                    self._build_enable_section()
                    ui.Spacer(height=4)
                    self._build_size_section()
                    ui.Spacer(height=4)
                    self._build_faces_section()
                    ui.Spacer(height=4)
                    self._build_actions_section()
                    ui.Spacer(height=4)
                    self._build_rotation_section()
                    ui.Spacer(height=4)
                    self._build_saved_positions_section()

    def _build_enable_section(self) -> None:
        with ui.HStack(height=24, spacing=8):
            ui.Label("Section Box Active", width=0)
            model = ui.SimpleBoolModel(self._state.enabled)
            self._enabled_checkbox = ui.CheckBox(model=model, width=24)
            model.add_value_changed_fn(lambda m: self._state.edit(enabled=m.as_bool) if not self._syncing else None)
        with ui.HStack(height=24, spacing=8):
            ui.Label("Show Box", width=0)
            model = ui.SimpleBoolModel(self._state.show_box)
            self._show_checkbox = ui.CheckBox(model=model, width=24)
            model.add_value_changed_fn(lambda m: self._state.edit(show_box=m.as_bool) if not self._syncing else None)

    def _build_size_section(self) -> None:
        with ui.CollapsableFrame("Size", collapsed=False):
            with ui.VStack(spacing=4):
                self._size_sliders = []
                for axis in range(3):
                    with ui.HStack(height=24, spacing=8):
                        ui.Label(f"  {_AXIS_LABELS[axis]}", width=40)
                        model = ui.SimpleFloatModel(self._state.box.size[axis])
                        slider = ui.FloatSlider(model=model, min=0.1, max=10000.0)
                        model.add_begin_edit_fn(lambda m: self._state.begin_edit())
                        model.add_end_edit_fn(lambda m: self._state.end_edit())
                        model.add_value_changed_fn(
                            lambda m, _a=axis: (
                                self._state.set_size_component(_a, m.as_float) if not self._syncing else None
                            )
                        )
                        self._size_sliders.append(slider)

    def _build_faces_section(self) -> None:
        with ui.CollapsableFrame("Active Faces", collapsed=False):
            with ui.VStack(spacing=4):
                for face_min, face_max in _FACE_PAIRS:
                    with ui.HStack(height=24, spacing=8):
                        for face in (face_min, face_max):
                            checked = face in self._state.box.faces
                            model = ui.SimpleBoolModel(checked)
                            cb = ui.CheckBox(model=model, width=24)
                            ui.Label(face.name, width=60)
                            model.add_value_changed_fn(
                                lambda m, _f=face: self._state.set_face(_f, m.as_bool) if not self._syncing else None
                            )
                            self._face_checkboxes[face] = cb

    def _build_actions_section(self) -> None:
        with ui.CollapsableFrame("Actions", collapsed=False):
            with ui.VStack(spacing=4):
                with ui.HStack(height=28, spacing=8):
                    ui.Button(
                        "Center on Selection",
                        clicked_fn=self._on_center_on_selection,
                        tooltip="Move the box to the selection's center, keeping its size and rotation.",
                    )

                with ui.HStack(height=28, spacing=8):
                    ui.Button(
                        "Fit to Selection",
                        clicked_fn=self._on_fit_to_selection,
                        tooltip="Fit selected geometry with top and bottom faces parallel to the scene's XY plane.",
                    )
                    ui.Button("Reset", clicked_fn=self._on_reset)

    def _build_rotation_section(self) -> None:
        with ui.CollapsableFrame("Rotation", collapsed=False):
            with ui.HStack(height=24, spacing=8):
                ui.Label("Degrees :", width=60)
                model = ui.SimpleFloatModel(self._state.box.z_rotation_degrees)
                self._rotation_slider = ui.FloatSlider(
                    model=model, min=-180.0, max=180.0, tooltip="Set the box's angle around world Z."
                )
                model.add_begin_edit_fn(lambda m: self._state.begin_edit())
                model.add_end_edit_fn(lambda m: self._state.end_edit())
                model.add_value_changed_fn(lambda m: self._on_rotate(m.as_float) if not self._syncing else None)

    def _build_saved_positions_section(self) -> None:
        with ui.CollapsableFrame("Saved Positions", collapsed=False):
            self._position_controls = SavedPositionControls(self._store)

    # --- action callbacks ----------------------------------------------------

    def _on_fit_to_selection(self) -> None:
        self._state.sync_stage()
        box = fit_box_to_selection(self._state.active_context())
        if box is not None:
            self._state.edit(box=box, enabled=True)

    def _on_center_on_selection(self) -> None:
        self._state.sync_stage()
        center = selection_center(self._state.active_context())
        if center is not None:
            box = self._state.box
            self._state.edit(box=box.translated(center - box.transform.ExtractTranslation()))

    def _on_reset(self) -> None:
        self._state.reset()

    def _on_rotate(self, degrees: float) -> None:
        self._state.edit(box=self._state.box.with_z_rotation(degrees))

    # --- state synchronisation -----------------------------------------------

    def _on_state_changed(self, state: SectionBoxState) -> None:
        """Keep the UI widgets in sync when the model changes externally."""
        if not self._window or self._syncing:
            return
        self._syncing = True
        try:
            self._sync_widgets(state)
        finally:
            self._syncing = False

    def _sync_widgets(self, state: SectionBoxState) -> None:
        if self._enabled_checkbox and self._enabled_checkbox.model:
            self._enabled_checkbox.model.set_value(state.enabled)

        for axis, slider in enumerate(self._size_sliders):
            if slider.model:
                slider.model.set_value(state.box.size[axis])

        for face, cb in self._face_checkboxes.items():
            if cb.model:
                cb.model.set_value(face in state.box.faces)

        if self._show_checkbox and self._show_checkbox.model:
            self._show_checkbox.model.set_value(state.show_box)

        if self._rotation_slider and self._rotation_slider.model:
            self._rotation_slider.model.set_value(state.box.z_rotation_degrees)
