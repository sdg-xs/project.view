"""Candidate B design sketch. Signatures and pseudocode only; no runtime code.

Caller usage:

    session = inspection_runtime.bind(active_viewport)
    sources = await session.project.sources()
    await session.project.start(ProjectFilter(sources.default_property, chosen_id), 1.0)
    session.project.save_new("Level 2 work package")
    await session.project.open(view_id)  # recalculate members, restore saved framing
    session.project.no_highlight()      # original materials despite parked scheme
    await session.project.refit()       # explicit new camera and box fit

    runtime = inspection_runtime.for_context(active_viewport.usd_context_name)
    runtime.colors.set_scheme(scene_scheme)  # Object Colors uses the same material writer

    session.section.edit(box=dragged_box)    # Section Box uses the same clip writer

Module ownership proposed by this sketch:

    inspection_runtime/catalog.py    ObjectRecord scan and exact-value index
    inspection_runtime/geometry.py   SectionBox model and explicit-path fit
    inspection_runtime/session.py    registry, live state, ownership and generations
    inspection_runtime/effects.py    one color sublayer and one clip-plane sink
    inspection_runtime/camera.py     temporary viewport camera and round trip
    project_view/store.py            versioned, undoable root-layer view records
    project_view/window.py           selectors, named views, status, user actions

This file deliberately has no implementation. Existing feature stores stay in
object_colors/presets.py and section_box/saved_positions.py.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING, NewType, Protocol

if TYPE_CHECKING:
    from inspection_runtime.scheme import Scheme  # moved from object_colors/scheme.py


ViewId = NewType("ViewId", str)
PrimPath = NewType("PrimPath", str)
PropertyName = NewType("PropertyName", str)

IDENTITY_PROJECT_ID = PropertyName(
    "omni:hoops:metadata:tn__IdentityData_qC:tn__ProjectID_m9"
)


@dataclass(frozen=True)
class ProjectFilter:
    property_name: PropertyName  # exact USD attribute, selected per view
    project_id: str               # exact string value, no alias/coercion


@dataclass(frozen=True)
class SourceChoices:
    default_property: PropertyName
    properties: tuple[PropertyName, ...]
    values_by_property: dict[PropertyName, tuple[str, ...]]  # full index, no 100-group cap


@dataclass(frozen=True)
class Membership:
    matched: tuple[PrimPath, ...]
    visible: tuple[PrimPath, ...]
    hidden: tuple[PrimPath, ...]
    unfit: tuple[PrimPath, ...]


@dataclass(frozen=True)
class CameraState:
    world_transform: tuple[float, ...]  # validated 4x4 row-major matrix
    projection: str                     # validated perspective or orthographic
    focal_length: float
    horizontal_aperture: float
    vertical_aperture: float
    clipping_range: tuple[float, float]


@dataclass(frozen=True)
class BoxState:
    transform: tuple[float, ...]  # validated 4x4 world transform
    size: tuple[float, float, float]
    faces: frozenset[str]
    enabled: bool


class HighlightMode(Enum):
    COLOR = "color"
    ORIGINAL = "original"


@dataclass(frozen=True)
class Highlight:
    mode: HighlightMode
    color: str | None  # invariant: valid #RRGGBB iff COLOR; None iff ORIGINAL


@dataclass(frozen=True)
class ViewRecord:
    version: int
    view_id: ViewId
    name: str
    filter: ProjectFilter
    camera: CameraState
    box: BoxState
    highlight: Highlight
    padding_m: float


@dataclass(frozen=True)
class ViewStatus:
    view_id: ViewId | None
    membership: Membership
    colored_count: int
    color_issues: tuple[str, ...]
    dirty: bool
    message: str


class Catalog(Protocol):
    async def refresh(self) -> SourceChoices:
        """Scan this exact context/stage; cancel stale generations."""
        raise NotImplementedError

    def match(self, selection: ProjectFilter) -> Membership:
        """Exact indexed membership, then current effective visibility and geometry."""
        raise NotImplementedError


class ColorCapability(Protocol):
    def set_scheme(self, scheme: Scheme) -> None:
        """Object Colors user intent takes the single material writer.

        TODO: park source scheme on project entry without persisting a disabled
        scheme; a later explicit edit supersedes the parked value.
        """
        raise NotImplementedError


class SectionCapability(Protocol):
    async def fit_selection(self) -> BoxState | None:
        """Use active context selection and shared explicit-path fitter."""
        raise NotImplementedError

    def begin_edit(self) -> None:
        raise NotImplementedError

    def edit(self, *, box: BoxState | None = None, enabled: bool | None = None) -> None:
        """Update shared live box; one clip owner; mark project draft dirty."""
        raise NotImplementedError

    def end_edit(self) -> None:
        """Commit a drag as one generation-scoped Kit undo command."""
        raise NotImplementedError


class ProjectCapability(Protocol):
    async def sources(self) -> SourceChoices:
        raise NotImplementedError

    async def start(self, selection: ProjectFilter, padding_m: float = 1.0) -> ViewStatus:
        """Fit visible matches; keep camera and box if none can be fit."""
        raise NotImplementedError

    async def open(self, view_id: ViewId) -> ViewStatus:
        """Rescan members, then restore saved camera/box without automatic refit."""
        raise NotImplementedError

    async def refresh_membership(self) -> ViewStatus:
        """Recalculate paths and colors, preserving current camera/box."""
        raise NotImplementedError

    async def refit(self) -> ViewStatus:
        """Fit visible current matches with stored padding; leave frame if none."""
        raise NotImplementedError

    async def set_filter(self, selection: ProjectFilter) -> ViewStatus:
        """Change one draft's exact property/value and refresh; do not refit."""
        raise NotImplementedError

    def set_padding(self, metres: float) -> None:
        """Change subsequent fits; do not move current box or camera."""
        raise NotImplementedError

    def set_highlight(self, color: str) -> None:
        """Apply to matches via the runtime's sole material writer."""
        raise NotImplementedError

    def no_highlight(self) -> None:
        """Mute sole material layer so original materials show, view stays active."""
        raise NotImplementedError

    def save_new(self, name: str) -> ViewId:
        """Capture live camera/box and write an undoable root-layer record."""
        raise NotImplementedError

    def update(self, view_id: ViewId) -> None:
        """Replace one record from live values; never save the scene file."""
        raise NotImplementedError

    def rename(self, view_id: ViewId, name: str) -> None:
        raise NotImplementedError

    def delete(self, view_id: ViewId) -> None:
        raise NotImplementedError

    def close(self) -> None:
        """Release project leases; restore prior scheme/box/camera if still owned."""
        raise NotImplementedError


class ViewportSession(Protocol):
    section: SectionCapability  # backed by the runtime's one stage-local box
    project: ProjectCapability


class InspectionRuntime(Protocol):
    catalog: Catalog
    colors: ColorCapability

    def bind(self, viewport: object) -> ViewportSession:
        """Require viewport context and stage identity to match this runtime."""
        raise NotImplementedError

    def close(self) -> None:
        """Cancel tasks, release owned layers and leases, invalidate commands."""
        raise NotImplementedError


class InspectionRegistry(Protocol):
    def for_context(self, context_name: str) -> InspectionRuntime:
        """One runtime per context/stage; stage change swaps generation."""
        raise NotImplementedError

    def bind(self, viewport: object) -> ViewportSession:
        """Bind the viewport's actual context, never the default by assumption."""
        raise NotImplementedError


# Store and adapter signatures stay private to their owner modules.
class ViewStore(Protocol):
    def list(self) -> tuple[ViewRecord, ...]:
        raise NotImplementedError

    def read(self, view_id: ViewId) -> ViewRecord:
        """Parse and validate schema/version at the USD boundary."""
        raise NotImplementedError

    def write(self, record: ViewRecord) -> None:
        """Root-layer UsdLayerUndo command; scene Save remains the user's action."""
        raise NotImplementedError

    def delete(self, view_id: ViewId) -> None:
        """Root-layer inactive opinion, undoable and generation scoped."""
        raise NotImplementedError


class CameraAdapter(Protocol):
    def capture(self) -> CameraState:
        """Read current viewport pose/projection/lens, including manual changes."""
        raise NotImplementedError

    def apply(self, camera: CameraState) -> None:
        """Create/activate an owned temporary session camera; never edit source."""
        raise NotImplementedError

    def release(self) -> None:
        """Restore prior camera only if the owned camera is still active."""
        raise NotImplementedError


# Transaction pseudocode for session.py:
# 1. Capture stage/context/viewport identities, generation, and intent revision.
# 2. Scan/build assignments without mutating live effects; yield Kit frames.
# 3. Recheck identities and revision. If stale, discard all prepared work.
# 4. Atomically replace the one owned color sublayer and clip/camera state.
# 5. Verify effective bindings; publish counts and per-path failures.
# 6. On close/retarget, remove owned layers and restore only still-owned opinions.
