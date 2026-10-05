"""Section Box toggle on Kit's main toolbar."""

from pathlib import Path

import omni.kit.widget.toolbar as toolbar_module
import omni.ui as ui


class _SectionBoxTool(toolbar_module.WidgetGroup):
    def __init__(self, model):
        super().__init__()
        self._model = model

    def get_style(self):
        data = Path(__file__).resolve().parent.parent / "data"
        return {
            "Button.Image::section_box_toggle": {"image_url": str(data / "icon.svg")},
            "Button.Image::section_box_toggle:checked": {"image_url": str(data / "icon_active.svg")},
        }

    def create(self, default_size):
        return {
            "section_box_toggle": ui.ToolButton(
                name="section_box_toggle",
                model=self._model,
                tooltip="Toggle Section Box",
                width=default_size,
                height=default_size,
            )
        }


class ToolbarButton:
    def __init__(self, state, window):
        self._state = state
        self._window = window
        self._syncing = False
        self._model = ui.SimpleBoolModel(state.enabled)
        self._subscription = self._model.subscribe_value_changed_fn(self._on_toggled)
        self._group = _SectionBoxTool(self._model)
        self._toolbar = toolbar_module.get_instance()
        if self._toolbar:
            self._toolbar.add_widget(self._group, priority=900)
        self._state.add_listener(self._on_state_changed)

    def destroy(self):
        self._state.remove_listener(self._on_state_changed)
        self._subscription = None
        if self._toolbar:
            self._toolbar.remove_widget(self._group)
        self._group.clean()
        self._group = None
        self._toolbar = None
        self._window = None

    def _on_toggled(self, model):
        if not self._syncing:
            self._state.edit(enabled=model.as_bool)
            self._window.visible = model.as_bool

    def _on_state_changed(self, state):
        self._syncing = True
        try:
            self._model.set_value(state.enabled)
        finally:
            self._syncing = False
