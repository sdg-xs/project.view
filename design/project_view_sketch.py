"""First-release Project View contract. Design sketch; methods show caller intent.

Saved views have a Project ID filter, section box, and color. Camera navigation
is wholly outside this version. No path list or layer state is persisted.
"""

from dataclasses import dataclass
from typing import Callable, Literal, NewType


ViewId = NewType("ViewId", str)
PropertyName = NewType("PropertyName", str)
PrimPath = NewType("PrimPath", str)
Color = NewType("Color", str)


@dataclass(frozen=True)
class TextId:
    value: str


@dataclass(frozen=True)
class IntegerId:
    value: int


@dataclass(frozen=True)
class RealId:
    value: float


@dataclass(frozen=True)
class BooleanId:
    value: bool


ProjectId = TextId | IntegerId | RealId | BooleanId


@dataclass(frozen=True)
class ProjectFilter:
    property: PropertyName
    value: ProjectId


@dataclass(frozen=True)
class BoxState:
    world_transform: tuple[float, ...]  # Validated 4x4 matrix, 16 entries.
    dimensions: tuple[float, float, float]  # Stage units.
    active_faces: frozenset[Literal["MIN_X", "MAX_X", "MIN_Y", "MAX_Y", "MIN_Z", "MAX_Z"]]
    enabled: bool
    show_box: bool


@dataclass(frozen=True)
class Appearance:
    enabled: bool  # False shows source materials.
    chosen_color: Color  # Retained so highlight can be turned back on.


@dataclass(frozen=True)
class ViewContent:
    filter: ProjectFilter
    box: BoxState
    appearance: Appearance
    padding_metres: float
    metres_per_unit: float
    up_axis: Literal["Z"]


@dataclass(frozen=True)
class ViewRecord:
    id: ViewId
    name: str
    content: ViewContent


@dataclass(frozen=True)
class Membership:
    matching: tuple[PrimPath, ...]
    visible: tuple[PrimPath, ...]
    hidden: tuple[PrimPath, ...]
    no_geometry: tuple[PrimPath, ...]
    colored: int
    unsupported_color: tuple[PrimPath, ...]


@dataclass(frozen=True)
class ViewState:
    records: tuple[ViewRecord, ...]
    draft: ViewContent | None
    source_id: ViewId | None
    membership: Membership | None
    membership_stale: bool
    busy: bool
    status: str


class ProjectViews:
    """One caller interface hides all matching, effect, and save coordination."""

    async def choices(self, property: PropertyName, search: str = "") -> tuple[ProjectFilter, ...]: ...

    async def preview(self, filter: ProjectFilter, padding_metres: float = 1.0) -> Membership:
        """Fit visible current matches and highlight them; never touch camera or selection.

        Refuse before changing the view if no visible geometry can be fitted.
        One physical metre on each side is the initial padding.
        """
        raise NotImplementedError

    async def open(self, id: ViewId) -> Membership:
        """Rescan current members, restore saved box/appearance, leave camera alone.

        An absent or all-hidden project still opens with its saved box and counts.
        If the active viewport cannot clip an enabled box, refuse the whole open.
        """
        raise NotImplementedError

    async def refresh(self) -> Membership:
        """Rescan paths and colors. Keep the box and camera in place."""
        raise NotImplementedError

    async def refit(self, padding_metres: float) -> Membership:
        """Refresh paths/colors; refit box only when visible geometry exists.

        Zero visible matches produce a warning, not stale colors or moved box.
        """
        raise NotImplementedError

    async def highlight(self, color: Color | None) -> Membership:
        """None restores original model materials while retaining inspection."""
        raise NotImplementedError

    def save_new(self, name: str) -> ViewRecord: ...
    def update(self, id: ViewId) -> ViewRecord: ...
    def rename(self, id: ViewId, name: str) -> ViewRecord: ...
    def delete(self, id: ViewId) -> None: ...
    async def exit(self) -> None: ...
    def subscribe(self, callback: Callable[[ViewState], None]) -> Callable[[], None]: ...


# Ownership contracts, implemented by existing extensions:
# Section Box: get_runtime_state() exposes its sole live state;
# fit_box_to_paths(stage, paths) and classify_visible_paths(stage, paths)
# do not mutate selection or create another clip controller.
# Object Colors: get_controller() exposes its sole material writer;
# begin_inspection(stage) returns an exclusive lease with async apply(mapping)
# and close(). Scheme edits during inspection remain desired state only.
# Both require the exact stage/context and refuse stale generations.

# Storage contract:
# One versioned complete record per UUID under marked /__ProjectViews in the
# root layer. Save New/Update/Rename/Delete affect only one record and use Kit
# undo. Composer Save (or Save As for anonymous stages) writes the scene file.
# Opening and changing a live view do not author persistent material/clip data.
