"""DESIGN ONLY. Proposed signatures and invariants, not an implementation.

Caller usage is in rationale.md. Bodies deliberately contain no runtime logic.
Names described as NEW do not exist in the current sibling extensions.
"""

from dataclasses import dataclass
from typing import Callable, Literal, NewType, Protocol, TypeAlias

ViewId = NewType("ViewId", str)  # UUID, independent of label and Project ID.
PropertyName = NewType("PropertyName", str)  # Exact authored attribute token.
PrimPath = NewType("PrimPath", str)
Matrix4: TypeAlias = tuple[tuple[float, float, float, float], ...]
Vec3: TypeAlias = tuple[float, float, float]
IDENTITY_PROJECT_ID = PropertyName(
    "omni:hoops:metadata:tn__IdentityData_qC:tn__ProjectID_m9"
)


@dataclass(frozen=True)
class ExactValue:
    """Boundary factory checks tag/value agreement and finite numbers.

    Uses existing scheme.value_key semantics internally. No case-folding,
    whitespace trimming, coercion, missing-value ID, or alias merging.
    """
    kind: Literal["str", "int", "float", "bool"]
    value: str | int | float | bool


@dataclass(frozen=True)
class ProjectFilter:
    property: PropertyName
    value: ExactValue


@dataclass(frozen=True)
class StageSpace:
    metres_per_unit: float  # Positive finite, read via USD stage metadata.
    up_axis: Literal["Y", "Z"]


@dataclass(frozen=True)
class BoxSnapshot:
    """Domain equivalent of SectionBox plus Inspection display state.

    Matrix, size are stage units. Rigid finite transform; positive extents.
    Persists arbitrary manual orientation and each enabled clipping face.
    Does not retain Section Box's unrelated saved_position_path.
    """
    world_transform: Matrix4
    size: Vec3
    faces: frozenset[Literal["MIN_X", "MAX_X", "MIN_Y", "MAX_Y", "MIN_Z", "MAX_Z"]]
    clipping_enabled: bool
    show_box: bool


@dataclass(frozen=True)
class CameraSnapshot:
    """A sampled camera, never a dependency on a scene camera path.

    Lens values use USD camera units, including aperture/focal-length tenths
    of stage units. Record StageSpace alongside, refuse incompatible changes.
    Sample at the viewport's current time; do not change timeline on opening.
    Additional clip planes are camera projection state, distinct from box planes.
    """
    world_transform: Matrix4
    projection: Literal["perspective", "orthographic"]
    horizontal_aperture: float
    vertical_aperture: float
    horizontal_aperture_offset: float
    vertical_aperture_offset: float
    focal_length: float
    clipping_range: tuple[float, float]
    clipping_planes: tuple[tuple[float, float, float, float], ...]
    focus_distance: float
    f_stop: float
    exposure: float
    center_of_interest_local: Vec3
    aspect_ratio: float
    conform_policy: Literal["fit", "crop", "match_horizontal", "match_vertical"]
    # Adapter validates policies against installed Kit, never invents a mapping.


@dataclass(frozen=True)
class NoHighlight:
    """No project bindings; ordinary Object Colors output stays suspended."""


@dataclass(frozen=True)
class Highlight:
    srgb_hex: str  # Validated #RRGGBB. Adjustable color, no fixed-palette limit.


Appearance: TypeAlias = NoHighlight | Highlight


@dataclass(frozen=True)
class ViewContent:
    filter: ProjectFilter  # Exactly one property and one typed value.
    space: StageSpace
    camera: CameraSnapshot
    box: BoxSnapshot
    highlight: Appearance
    padding_metres: float  # Finite >= 0; initial default 1.0 per side.
    # Schema version is storage knowledge, parsed by records.py, not UI input.
    # Deliberately no persisted member paths or links to other preset records.


@dataclass(frozen=True)
class ViewRecord:
    id: ViewId
    name: str  # Nonempty; case-insensitive uniqueness within this collection.
    content: ViewContent


@dataclass(frozen=True)
class Draft:
    source_id: ViewId | None  # None for a new preview or a deleted source record.
    content: ViewContent


@dataclass(frozen=True)
class Membership:
    """Current snapshot, at sampled viewport time and scene revision.

    Counts refer to discovered editable object roots, not triangle/mesh counts.
    Visible means some loaded drawable geometry survives inherited visibility,
    active viewport purpose filters, and supported viewport exclusion filters.
    Does not mean inside frustum/section box or unoccluded. Exclude our own clip
    result when fitting. Partly hidden objects fit only their visible geometry.
    Roots with no drawable geometry are reported separately from hidden roots.
    """
    matching: tuple[PrimPath, ...]
    visible: tuple[PrimPath, ...]
    hidden: tuple[PrimPath, ...]
    no_loaded_geometry: tuple[PrimPath, ...]
    color_unsupported: tuple[PrimPath, ...]


@dataclass(frozen=True)
class Choice:
    filter: ProjectFilter
    label: str  # Duplicate-looking scalar labels show type to disambiguate.
    matches: int


@dataclass(frozen=True)
class Choices:
    properties: tuple[PropertyName, ...]
    values: tuple[Choice, ...]  # No 100-group cap. UI can virtualize.


@dataclass(frozen=True)
class Applied:
    membership: Membership
    warnings: tuple[str, ...]


@dataclass(frozen=True)
class Refused:
    reason: Literal[
        "no_stage", "no_viewport", "dependency_missing", "context_mismatch",
        "missing_property", "no_matches", "no_visible_geometry",
        "invalid_geometry", "incompatible_stage_space", "unsupported_camera",
        "read_only", "invalid_record", "unsupported_version", "name_conflict",
        "record_missing", "concurrent_edit", "runtime_failure",
    ]
    message: str


@dataclass(frozen=True)
class Superseded:
    """A newer intent, scene change, viewport change, or shutdown won. No write."""


Outcome: TypeAlias = Applied | Refused | Superseded


@dataclass(frozen=True)
class NewView:
    name: str


@dataclass(frozen=True)
class UpdateView:
    id: ViewId


@dataclass(frozen=True)
class Saved:
    id: ViewId
    needs_scene_save: bool
    needs_save_as: bool


@dataclass(frozen=True)
class ViewState:
    records: tuple[ViewRecord, ...]
    draft: Draft | None
    differs_from_record: bool
    membership: Membership | None
    membership_stale: bool
    busy: bool
    status: str


class ProjectViews:
    """NEW public coordinator in project.view/views.py.

    Boundary binds one active viewport and its exact stage/context. Existing
    Object Colors uses default context; refuse mismatches until its NEW scope
    API explicitly supports that context. Never silently target another stage.
    UI subscribes; all deeper services remain private to this owner.
    """

    async def discover(self, *, property: PropertyName = IDENTITY_PROJECT_ID,
                       search: str = "") -> Choices | Refused | Superseded: ...

    async def preview(self, filter: ProjectFilter,
                      padding_metres: float = 1.0) -> Outcome:
        """Discover; fit visible matches with 2*padding/metres_per_unit added
        to local box extents; frame all padded corners with current camera
        orientation/projection and aspect. Enable all clip faces. No matches
        or no visible geometry refuses without changing current inspection.
        Preserve unrelated USD selection throughout.
        """
        raise NotImplementedError

    async def open(self, id: ViewId) -> Outcome:
        """Read/validate whole record; freshly discover/filter; restore saved
        box and camera exactly. Never fit here. Missing selected property,
        zero matches, or all-hidden are warnings: still open saved framing,
        clear prior project assignments, and report the new empty/hidden set.
        Missing property never substitutes Identity Data or another alias.
        """
        raise NotImplementedError

    async def refresh_membership(self) -> Outcome:
        """Update paths/counts/materials only. Camera and box stay unchanged."""
        raise NotImplementedError

    async def refit(self, *, padding_metres: float) -> Outcome:
        """Fresh membership; visible-geometry fit and camera framing. Refuse
        empty/all-hidden without changing existing camera, box, or materials.
        Fit uses stage up-axis: existing Z-only helper needs a Y/Z basis input.
        """
        raise NotImplementedError

    async def set_highlight(self, value: Appearance) -> Outcome: ...
    def save(self, intent: NewView | UpdateView) -> Saved | Refused: ...
    def rename(self, id: ViewId, name: str) -> Saved | Refused: ...
    def delete(self, id: ViewId) -> Saved | Refused: ...
    def subscribe(self, callback: Callable[[ViewState], None]) -> Callable[[], None]: ...
    def close(self) -> None: ...


# NEW upstream contract in section.box. Existing model.SectionBox geometry,
# state.Inspection and state.apply/listeners provide implementation foundations.
# Existing fit_box_to_selection is NOT an explicit-path public fitting API.
class SectionRuntime(Protocol):
    def snapshot(self) -> BoxSnapshot: ...
    def observe(self, callback: Callable[[BoxSnapshot, object], None]) -> Callable[[], None]: ...
    def apply(self, value: BoxSnapshot, *, origin: object) -> None:
        """Apply through sole existing state owner, no nested undo command.
        Public orchestration participates in one outer runtime command.
        origin distinguishes our writes from panel/manipulator edits.
        """
        ...

    async def fit(self, paths: tuple[PrimPath, ...], *, padding_metres: float,
                  cancellation: object) -> BoxSnapshot | Refused:
        """Bind same stage/context, sample time and supported visibility mask.
        Extend existing geometry algorithm; no temporary selection mutation.
        """
        ...


# NEW upstream contract in object.color. scan_steps/value_key/ColorOverrides
# exist today; scope arbitration and detached prepare/commit do not exist.
class ColorInspectionScope(Protocol):
    async def prepare(self, members: tuple[PrimPath, ...], appearance: Appearance,
                      cancellation: object) -> "PreparedAppearance": ...
    def close(self) -> None:
        """Idempotently remove only this scope's layer and reveal the latest
        desired Object Colors scheme. Do not restore a stale scheme snapshot.
        The owner serializes ordinary scheme tasks with inspection activation.
        """
        ...


class PreparedAppearance(Protocol):
    def publish(self) -> tuple[str, ...]:
        """No await. Existing apply_steps must be adapted to construct its
        replacement detached. Verify binding outcomes on publication, retain
        old layer until success, roll back on failure. Partial unsupported
        targets produce warnings and keep original materials on those targets.
        """
        ...
    def discard(self) -> None: ...


class ObjectRecord(Protocol):
    """Existing discovery domain shape, made a stable public API upstream."""
    path: str
    properties: dict[str, str | int | float | bool]


class Scan(Protocol):
    objects: list[ObjectRecord]
    properties: list[str]
    issues: list[str]


class ObjectColorService(Protocol):
    async def discover(self, cancellation: object) -> Scan:
        """Returns existing Scan domain records, not capped Group output."""
        ...
    def begin_inspection(self, *, context_name: str) -> ColorInspectionScope: ...


class ViewCamera:
    """NEW internal camera.py owner, using installed Kit viewport/USD APIs.

    Capture current sampled USD projection, world transform and orbit center.
    Materialize a collision-free camera prim in an owned anonymous session
    sublayer; point bound viewport.camera_path there. All camera commands use
    that context. Normal navigation edits this camera, never the scene camera.
    Save always samples the actual active camera so manual camera switching
    is reflected in the draft. Track switches and navigation as external edits.

    Store aspect and conform policy, not resolution pixels. Preserve framing
    with letterboxing/fit policy where supported. Unsupported round-trip
    policies are explicit refusals, not silent approximations. Camera fitting
    computes bounds in camera space for perspective and orthographic lenses.
    """
    def capture(self) -> CameraSnapshot | Refused: ...
    def apply(self, camera: CameraSnapshot) -> None: ...
    def frame(self, box: BoxSnapshot) -> CameraSnapshot | Refused: ...
    def close(self) -> None:
        """Restore prior viewport camera/path and conform policy only while
        the viewport still references our camera. Respect external switches.
        If original camera disappeared use Kit's supported default camera,
        then delete only our own layer. Shutdown/stage-close is idempotent.
        """
        raise NotImplementedError


"""
Runtime transactions and lifecycle

One monotonic intent revision plus stage generation, bound viewport identity,
external box/camera edit revision, and observed model revision gate publication.
All async discovery/geometry/layer preparation uses those captured values and
cooperative cancellation at each chunk. Check again immediately before commit.
Do not use only task.cancel(): yielded generators must close in finally and
discard unpublished layers. No await between final check and runtime apply.

Read-only scene notices invalidate membership and cancel pending preparation.
Our own temporary camera/material writes are filtered by owned layer/path;
root record edits do not count as membership changes. Visibility, transforms,
properties, resync, time, and purposes invalidate the relevant snapshot. Mark
stale and provide Refresh; Open and Refit always rebuild. Changes during a scan
return Superseded rather than publish a mixture of revisions.

Prepare camera/box/material replacements before touching live state. Commit
through one generation-scoped Kit command. Snapshot and restore the pre-command
camera, box and inspection appearance if any synchronous apply step fails.
Published unsupported-color targets are a partial-success warning, not failure.
Undo/redo restore captured runtime snapshots and membership, checking remaining
paths; they do not rerun an async scan. Scene changes mark membership stale.
Normal camera navigation and Section Box panel commands keep their own undo.
External edits update the draft and can invalidate an in-flight Open/Refit.
Save samples current actual camera and box; no last-known UI cache is authoritative.

Box external edits become draft edits. Project View applies clear the unrelated
saved_position_path; external loading of a Section Box preset becomes the new
draft box. Closing restores pre-inspection box only if Section Box has seen no
external edit after the last Project View write. Otherwise leave deliberate
manual state. Never directly rewrite RTX clip attributes. Section Box handles
restoration through its existing ClipPlaneController. This conditional close
behavior is a proposed product rule, distinct from runtime command Undo.

On active viewport change, close the bound inspection and invalidate its async
work before offering activation on the new viewport; no automatic migration.
Stage close/replacement and extension shutdown release subscriptions, pending
tasks, owned camera layer, and color scope; do not write root data. Dependency
loss ends inspection with a visible error and releases what remains available.
Opening UI alone never activates a saved view. Closing the window is not the
same as Close view; the inspection remains until Close view or lifecycle exit.

Persistence and commands in records.py

Schema v1 uses explicit typed custom attributes on one prim per UUID beneath
marked /__ProjectViews. Refuse an existing unmarked collision. Schema stores
all ViewRecord fields and version. Validate finite/ranged values, dimensions,
known enum variants and exact scalar type once on input/read. Unknown versions
are listed as unsupported and never rewritten. No alias migration or inference.

New/update/rename/delete command owns only the target record path, with root-
layer edit context and UsdLayerUndo reservation. Parent namespace creation is
included without deleting existing siblings. Root opinions override a composed
record; delete uses a root tombstone when weaker records exist. Undo affects no
other extension's custom data. Stage generation guards stale undo commands.
Check writable root and expected record revision before changing it; refuse
external concurrent record edits. This is local command safety, not a multiuser
file merge protocol. Normal Composer save conflict handling still applies.

Save view captures current draft, then authors one complete record atomically.
New returns stable UUID. Update keeps ID/name unless Rename is called. Rename
keeps the exact view content. Delete leaves runtime inspection as an unsaved
draft; undo resurrects the record. Runtime highlight toggles and framing do not
dirty the root until Save view. Report memory commit separately from filesystem
save; errors from later Composer Save are never described as successful sharing.
Do not implicitly update /SectionBox/Presets or objectColorsState.

Minimal verification before claiming implementation complete

1. On real placed instances, create a view using exact Identity Data ID; prove
   a different typed scalar and a conflicting alternate property do not match.
   Discover more than 100 distinct values and select the last one.
2. In centimetre Z-up and Y-up fixtures with hidden descendants, assert visible
   geometry fits with exactly one physical metre per box side. Selection stays
   unchanged. All-hidden preview refuses and leaves prior state intact.
3. Save camera with perspective/orthographic offset lens, manual rotated box
   and disabled faces; scene Save, close stage, reopen, add matching instance,
   Open. Prove camera and box remain equal while membership includes addition.
4. Enable Object Colors first, activate project highlight, No highlight, edit
   pending Object Colors scheme, close. Inspect bound materials: surroundings
   are original during inspection, and close applies the latest desired scheme.
   Check an unsupported target is counted and retains original materials.
5. Exercise undo/redo for runtime Open and root CRUD; prove source camera,
   unrelated root metadata, ordinary presets and stage visibility unchanged.
   Verify read-only preview/write refusal and anonymous Save As persistence.
6. Force delayed scan then switch stage/view and edit camera/box; old operation
   must never publish. Force a commit failure and inspect rollback plus cleanup.

These are behavior checks against USD state and a live viewport, not tests of
method forwarding. Camera conform support and layered material restoration
must be proved in installed Composer before considering the APIs implemented.
"""
