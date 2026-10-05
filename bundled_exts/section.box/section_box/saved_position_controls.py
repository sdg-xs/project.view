"""Controls for named section-box snapshots stored in the current scene."""

import omni.ui as ui

from .saved_positions import SavedPositionStore


class SavedPositionControls:
    def __init__(self, store: SavedPositionStore) -> None:
        self._store = store
        self._state = store.state
        self._stage = self._state.stage
        self._positions = []
        self._combo = None
        self._refreshing = False
        with ui.VStack(spacing=4, height=0):
            with ui.HStack(height=26, spacing=4):
                self._name = ui.StringField(tooltip="Name for a new saved position").model
                ui.Button("Save New", width=80, clicked_fn=lambda: self._on_action("save"))
            self._list_frame = ui.Frame(height=0)
            self._status = ui.Label("Save the scene to keep your saved positions.", word_wrap=True, height=0)
        self._refresh()
        self._state.add_listener(self._on_state_changed)

    def destroy(self) -> None:
        self._state.remove_listener(self._on_state_changed)

    def _selected_path(self) -> str:
        if not self._positions:
            return ""
        index = self._combo.model.get_item_value_model().as_int
        return self._positions[index - 1][0] if 1 <= index <= len(self._positions) else ""

    def _refresh(self, selected_path: str = "") -> None:
        self._positions = self._store.list_positions()
        index = next((i + 1 for i, (path, _) in enumerate(self._positions) if path == selected_path), 0)
        self._refreshing = True
        self._list_frame.clear()
        with self._list_frame:
            with ui.VStack(spacing=4, height=0):
                self._combo = ui.ComboBox(
                    index,
                    "Choose a saved position...",
                    *[name for _, name in self._positions],
                    height=26,
                    enabled=bool(self._positions),
                )
                self._combo.model.add_item_changed_fn(self._on_selected)
                with ui.HStack(height=26, spacing=4):
                    self._update_button = ui.Button(
                        "Update", enabled=bool(index), clicked_fn=lambda: self._on_action("update")
                    )
                    self._delete_button = ui.Button(
                        "Delete", enabled=bool(index), clicked_fn=lambda: self._on_action("delete")
                    )
        self._refreshing = False

    def _on_selected(self, model, item) -> None:
        if self._refreshing:
            return
        selected = bool(self._selected_path())
        self._update_button.enabled = selected
        self._delete_button.enabled = selected
        if selected:
            self._on_action("load")

    def _on_action(self, action: str) -> None:
        path = self._selected_path()
        try:
            if action == "save":
                self._store.save_new(self._name.as_string)
                self._name.set_value("")
                self._status.text = "Position saved. Save the scene to keep it."
            elif action == "load":
                self._store.load(path)
                self._status.text = "Saved position loaded."
            elif action == "update":
                self._store.update(path)
                self._status.text = "Saved position updated. Save the scene to keep it."
            elif action == "delete":
                self._store.delete(path)
                self._status.text = "Saved position deleted. Save the scene to keep this change."
        except (ValueError, RuntimeError) as error:
            self._status.text = str(error)

    def _on_state_changed(self, state) -> None:
        if state.stage != self._stage:
            self._stage = state.stage
            self._name.set_value("")
            self._status.text = "Save the scene to keep your saved positions."
        positions = self._store.list_positions()
        if positions != self._positions:
            self._refresh(state.saved_position_path)
        elif self._selected_path() != state.saved_position_path:
            index = next((i + 1 for i, (path, _) in enumerate(positions) if path == state.saved_position_path), 0)
            self._refreshing = True
            self._combo.model.get_item_value_model().set_value(index)
            self._update_button.enabled = bool(index)
            self._delete_button.enabled = bool(index)
            self._refreshing = False
