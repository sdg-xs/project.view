"""Notify Scene UI when the section box's runtime state changes."""

from __future__ import annotations

from typing import TYPE_CHECKING

import omni.ui.scene as sc

if TYPE_CHECKING:
    from .state import SectionBoxState


class SectionBoxManipulatorModel(sc.AbstractManipulatorModel):
    """Scene UI adapter for a manipulator that reads runtime state directly."""

    def __init__(self, state: SectionBoxState) -> None:
        super().__init__()
        self._state = state
        self._state.add_listener(self._on_state_changed)

    def destroy(self) -> None:
        self._state.remove_listener(self._on_state_changed)

    @property
    def state(self) -> SectionBoxState:
        return self._state

    def _on_state_changed(self, state: SectionBoxState) -> None:
        self._item_changed(None)
