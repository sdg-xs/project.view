"""Undoable runtime edits and saved-position edits on Kit's shared undo stack."""

from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING

import omni.kit.commands
import omni.kit.undo
from omni.kit.usd_undo import UsdLayerUndo
from pxr import Usd

if TYPE_CHECKING:
    from .model import SectionBox
    from .saved_positions import SavedPositionStore
    from .state import Inspection, SectionBoxState


def execute(command_type, **kwargs):
    success, result = omni.kit.undo.execute(command_type(**kwargs), command_type.__name__, kwargs)
    if not success:
        raise RuntimeError("The section box change could not be completed. See the Kit log.")
    return result


class EditSectionBox(omni.kit.commands.Command):
    def __init__(self, state: SectionBoxState, before: Inspection, after: Inspection, generation: int) -> None:
        self._state = state
        self._before = before
        self._after = after
        self._generation = generation

    def do(self) -> None:
        if self._state.generation == self._generation:
            self._state.apply(self._after)

    def undo(self) -> None:
        if self._state.generation == self._generation:
            self._state.apply(self._before)


class SaveSectionBoxPosition(omni.kit.commands.Command):
    def __init__(self, store: SavedPositionStore, path: str, name: str, box: SectionBox, delete: bool = False) -> None:
        self._store = store
        self._state = store.state
        self._stage = self._state.stage
        self._generation = self._state.generation
        self._path = path
        self._name = name
        self._box = box
        self._delete = delete
        self._previous_selection = self._state.saved_position_path
        self._undo = None

    def do(self) -> str | None:
        if self._state.generation != self._generation:
            return
        self._store.require_writable()
        layer = self._stage.GetRootLayer()
        self._undo = UsdLayerUndo(layer)
        self._undo.reserve(self._path)
        try:
            with Usd.EditContext(self._stage, layer):
                if self._delete:
                    # A root-layer tombstone also hides positions from weaker layers.
                    self._stage.OverridePrim(self._path).SetActive(False)
                else:
                    self._store.write_position(self._stage, self._path, self._name, self._box)
        except Exception:
            self._undo.undo()
            raise
        selected = "" if self._delete else self._path
        self._state.apply(replace(self._state.snapshot, saved_position_path=selected))
        # USD-only edits still need a refresh when the runtime snapshot is unchanged.
        self._state.notify()
        return self._path

    def undo(self) -> None:
        if self._state.generation != self._generation:
            return
        self._store.require_writable()
        self._undo.undo()
        self._state.apply(replace(self._state.snapshot, saved_position_path=self._previous_selection))
        self._state.notify()
