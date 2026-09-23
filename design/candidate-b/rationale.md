# Candidate B: shared inspection runtime

## Problem

Project View must reopen a named view with a fixed camera and box while discovering the current assets for one exact Project ID. Object Colors and Section Box already have useful discovery, material, geometry, and clipping code, but their live controllers write independently. Two material layers can compete through direct bindings and `objectColors_<hex>` collection order; two clip controllers would compete on the active render product. This candidate moves live inspection ownership into one shared runtime used by all three panels. It preserves Object Colors' root `objectColorsState`, Section Box's `/SectionBox/Presets`, and their user workflows.

## Usage (caller's view)

Project View binds the active viewport and its USD context. The first scan offers exact scalar property names and untruncated values. The initial property is `omni:hoops:metadata:tn__IdentityData_qC:tn__ProjectID_m9`; the user can choose another exact property. A new draft fits visible matches with 1 m padding on each side. Saving captures the current camera and box after any manual edits. Opening an existing view rescans membership but applies its saved camera and box. Refit is an explicit action.

```python
# project_view/window.py
session = inspection_runtime.bind(active_viewport)
sources = await session.project.sources()
await session.project.start(ProjectFilter(sources.default_property, chosen_id), padding_m=1.0)
session.project.set_highlight("#E15759")  # or session.project.no_highlight()
view_id = session.project.save_new("Level 2 work package")
status = await session.project.open(view_id)
session.project.update(view_id)             # capture current camera, box, filter, color, padding
await session.project.refit()               # only explicit refit changes saved framing in memory
session.project.rename(view_id, "Level 2 north")
session.project.delete(view_id)
```

```python
# object_colors/controller.py: its scheme persistence and undo remain here.
runtime = inspection_runtime.for_context(active_viewport.usd_context_name)
catalog = await runtime.catalog.refresh()
runtime.colors.set_scheme(scene_scheme)    # one runtime owns the effective binding layer
```

```python
# section_box/window.py and manipulator: unchanged gestures, shared live box.
session = inspection_runtime.bind(active_viewport)
fitted = await session.section.fit_selection()
if fitted:
    session.section.edit(box=fitted, enabled=True)  # one runtime owns clip planes
session.section.begin_edit()
session.section.edit(box=dragged_box)
session.section.end_edit()                   # one Kit undo item for the drag
```

## Shape

`inspection_runtime` is a new dependency of all three extensions. Its registry keys state by USD context and exact stage identity. It owns one live box for that stage and binds clipping and camera effects only to the active viewport. The stage catalog holds editable placed Xform records and an index from `(exact property name, typed exact value)` to paths. The Project ID selector reads the full index, never Object Colors' 100-group display. String Project IDs compare exactly; absent, non-string, and aliased properties do not match. Source labels can be friendly, but the saved key is the actual USD attribute name.

The runtime has one material writer per stage. It reuses the existing `ColorOverrides` mechanism after moving it into the shared module. Color state is one of source scheme, project highlight, or original materials. Opening a project view parks the effective Object Colors scheme without changing its root-layer persistence. `No highlight` selects original materials even if that scheme was enabled. Exiting restores the parked scheme unless a deliberate Object Colors edit has since claimed color ownership; such an edit ends the project color session. The runtime replaces only its own anonymous session layer, verifies the composed binding, and reports unsupported instance proxies, PointInstancers, missing geometry, and stronger bindings as partial results. Surroundings keep their source materials. It never writes visibility.

The runtime is the sole clipping writer and owns a live `SectionBox` snapshot shared with Section Box's controls and manipulator. It preserves the existing active-render-product, session-layer, prior-opinion restoration policy. Section Box edits while a project view is active change the live box and mark that view draft dirty; `Update` captures it. Closing the view restores the pre-view box unless a later explicit Section Box command claimed the box. Existing named box positions remain separate records. A fit function takes explicit object paths, traverses visible geometry and instance proxies, handles Y-up or Z-up, and adds `padding_m / metersPerUnit` stage units to each side. The same padded world bounds drive an aspect-aware camera fit. Invalid units or unsupported axes refuse a fit. Hidden matching objects count separately and contribute no fit geometry. A matched object with no usable geometry is reported as unfit, not hidden.

The camera adapter captures a semantic pose, projection, and lens state from the viewport. Opening a view creates a temporary camera in its own session sublayer and activates it, so a source camera prim is never edited. Manual navigation changes that temporary camera. `Update` reads it back; camera values, not its temporary path, go in the view record. Closing restores the prior camera path and free-camera state if the session still owns the active camera. External camera selection supersedes that restoration. An isolated Kit test must prove capture, apply, manual orbit, save, reopen, and close for both free and authored source cameras before this adapter is accepted.

`project_view/store.py` owns versioned `/ProjectViews/Views/View_<uuid>` root-layer records. Each record has an immutable ID, unique case-insensitive name, exact property and value, camera values, box transform/size/faces/enabled, highlight mode/color, and padding in metres. Reads validate every field and refuse unknown versions without modifying them. New, update, rename, and delete use Kit commands with `UsdLayerUndo`, reserve only the affected record, and explicitly target the root layer. A normal user scene Save persists dirty records. Anonymous roots permit drafting but require Save As for sharing; read-only roots permit opening and temporary edits but refuse record changes with a clear message. Deletion writes a root-layer inactive opinion so weaker copies cannot reappear.

Stage or viewport changes cancel pending scans and effects, release owned session layers, restore prior clip and camera state where the old target remains valid, and bump a generation. Async work checks the generation, stage, context, viewport, and user-intent revision immediately before committing a new layer or applying a camera/box. A newer user command wins. Open, Refit, highlight changes, and box gestures are generation-scoped Kit undo commands for complete runtime snapshots; record edits use separate root-layer undo commands. Opening a view with no matches still restores its saved camera and box and reports zero matches. If every match is hidden, it reports the hidden count and leaves those saved values intact. Initial fit or explicit Refit with no visible usable geometry declines to move either camera or box. Manual framing is then available for saving. The active view's membership refresh changes highlighting and counts but never the saved framing. If the viewport cannot clip, opening a view with an enabled box refuses to apply it rather than reporting a partly restored view. Missing runtime dependencies prevent Project View startup with a visible error.

This interface is deeper than a coordinator because callers do not sequence scanning, material muting, clipping, camera leases, and undo. The migration is substantial despite the earlier Section Box decision to keep flat capability modules. That decision remains sound for Section Box alone; shared effect ownership across three panels is a new constraint. This candidate is justified only if the three extensions ship together and their live effect ownership actually moves. Keeping the old controllers as active writers would negate the main invariant. The module split follows ownership rather than load/transform/save phases: `catalog.py` knows object membership, `geometry.py` knows fitting, `session.py` knows live state and conflict policy, `effects.py` knows USD/RTX session opinions, and `camera.py` knows viewport camera conversion. Feature-specific scene stores stay with their extensions.

Validation should use a representative scene for exact Identity Data and alternate-property discovery, plus isolated Kit fixtures for no matches, hidden and unfit objects, Y-up and non-metre units, camera round trip, material restoration, competing panel edits, and stage/viewport switches during async work. Reopen a scene after a normal Save to prove the root-layer record survives while temporary bindings and camera prims do not; run undo/redo across record changes and live view edits.

## Synthesis decision

Pending the orchestrator's comparison with the other candidate.

## Tradeoffs accepted

- We accept a coordinated migration of two mature extensions in exchange for one enforceable color and clip owner.
- We accept a shared runtime dependency in exchange for no stage/context mismatch between panels.
- We accept an ephemeral viewport camera and Kit-specific adapter in exchange for leaving authored cameras untouched.
- We accept explicit refresh or reopen for newly added members in exchange for avoiding continuous whole-stage scans; refresh never refits.

## Alternatives considered

An orchestrator above the two current controllers has a smaller migration, but it exposes mute/order/restore rules to the Project View caller and cannot guarantee that a panel or scheduled task will not write another competing layer. A Project View-only copy of discovery, coloring, and clipping hides integration work at first but creates two independent clip writers and two definitions of a match. A global saved inspection prim with material bindings and camera prims would make viewport effects persistent and change source presentation for coworkers before they open a view.

## Implementation reconciliation

Design only. No implementation deviations have been accepted.

## Open questions and risks

- Can Kit 110.2's viewport camera APIs round-trip free and authored cameras through an ephemeral session camera without a frame jump or source-prim edit?
- Will a coordinated upgrade of Object Colors and Section Box be acceptable for the rollout? If they must remain independently deployable, this candidate loses much of its reason to exist.
- Does the scene contain time-sampled Project ID or geometry values that require matching and fitting at the viewport's current time rather than the default time?

## Next implementation step

Prove the camera adapter and single-owner material/clip handoff in an isolated Kit fixture, then migrate the existing panels to the shared runtime one capability at a time.
