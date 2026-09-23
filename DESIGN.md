# Project View

Status: implemented and verified in Kit 110.2 and the Composer Window menu. User decisions Q1-Q11 are recorded in [grounding](design/grounding.md).

## Problem

Construction reviewers need several named inspection views for a work package identified by Project ID. Each view restores a section area and color choice while finding the project's current assets. The user navigates the camera manually; camera saving belongs to a later release. Existing Object Colors and Section Box provide discovery, temporary colors, geometry fitting, and clipping, but neither stores this combined view. Their existing source-material, session-layer, and explicit-save contracts remain intact.

## Usage

1. Open Project View. Select a property, initially Identity Data / Project ID, then search and select one of its Project IDs.
2. Choose Preview. Fit visible matching assets with one metre of padding per side. Highlight matching assets; surrounding construction retains its original materials. The camera stays where the user positioned it.
3. Navigate manually, then adjust the section box, padding for subsequent fits, and highlight color. No highlight restores original materials while retaining the view and its project filter.
4. Save New with a name. Create several views for the same project, then use Update, Rename, or Delete on an existing view. Rename changes only the label.
5. Use Composer Save to write view records to the model file. Coworkers with the extensions open that model and choose a saved view.
6. Opening a view restores its saved box, property/value, and highlight choice. Membership is freshly discovered; the saved box does not move. Refresh updates membership and colors; Refit explicitly updates the box. Camera navigation stays unchanged.

```python
project_property = views.property_name
choices = await views.discover(project_property, search="01514")
await views.preview(project_property, choices[0].project_id, padding_metres=1.0)
saved = views.save_new("Level 2 installation")

await views.open(saved.id)
await views.set_highlight(None)
await views.refit(padding_metres=1.5)
views.update()

views.rename(saved.id, "Level 2 north installation")
await views.exit()
```

The panel consumes a single state subscription. It does not sequence color and clipping changes. [The type sketch](design/project_view_sketch.py) derives its operations from this usage.

## Behavior proposed for the final review

These complete the accepted workflow; they are proposed defaults, not additional accepted interview answers.

- Exit View restores the section box and color display from before entering project inspection. Section Box edits made during inspection are draft changes, captured only by Save New or Update. Switching between project views does not replace the original return point. Camera navigation is independent of Project View.
- Object Colors visibly yields color control while a project view is active. Its existing scheme is preserved. Deliberate edits to that scheme can be stored by Object Colors, but its panel marks the display as suspended until Exit View. On exit its latest intended scheme returns. No highlight does not release this suspension.
- Saved views do not activate automatically when a model opens. Closing the Project View panel merely hides its controls; Exit View ends inspection.
- Save New, Update, Rename, and Delete create undoable scene-record commands. Section Box gestures retain their own undo behavior. Project View activation, highlight changes, Refit, and Exit do not create a combined undo item; undoing a Section Box edit restores only the box. Temporary edits never silently update a saved view.
- Opening a saved view whose assets are now absent or hidden still restores its saved box and reports the missing/hidden counts. Initial Preview refuses with no visible fit; Refit refreshes membership, counts and colors but keeps the box if nothing can be fitted.
- Changes to an open model mark membership stale; Refresh, Open, and Refit rescan. The extension does not continuously rescan or refit the entire model.
- Shared means records travel with the saved USD scene. This is not concurrent editing or automatic synchronization between coworkers.

## Shape and ownership

Use Candidate A's coordinator shape, subject to cross-review. `ProjectViews` owns a draft, saved-view operations, and one inspection session. It combines small public capabilities from the existing owners. It neither clicks their UI nor writes competing rendering overrides.

| Module | Responsibility |
| --- | --- |
| `project_view/views.py` | Exact project matching, inspection draft, async intent/stage checks, combined runtime actions and exit |
| `project_view/records.py` | View records, validation/versioning, per-record root-layer commands |
| `project_view/window.py` | Property/ID search, named views, controls, status |
| `project_view/extension.py` | Dependency wiring and lifecycle |
| Existing `object_colors` | Discovery and sole effective color override owner |
| Existing `section_box` | Explicit-path geometry fitting and sole clipping/state owner |

The public operations hide discovery, cancellation, preparation, publication, and rollback. The window never coordinates those stages. Storage details stay in records.py. Keep short call paths rather than a separate adapter layer for each existing method.

The upstream extensions provide these integration contracts:

- Section Box exposes access to its running state and explicit-path fitting. Project View applies its transient box through Section Box's state owner, without creating a box-only undo entry for a combined view change. Manual Section Box controls retain their existing undo behavior. The selection command uses the same fitting function. Preserve its geometry-derived XY rotation and existing controls.
- Object Colors exposes discovery records without the legend's 100-group cap, plus a transient inspection scope. The scope serializes its existing scheme work with project highlighting. It constructs replacement layers before publishing, keeps one effective owned color layer, and restores the latest desired scheme on release. Entering or leaving this scope does not persist an enabled/disabled scheme change.
- Both extension services validate the exact same stage/context before changes. The first version targets their existing default-context Composer workflow and Z-up section controls. Refuse unsupported contexts or axes before applying any effect; do not silently operate on a different scene. Physical padding uses the scene's metres-per-unit value, including centimetre scenes.

This retains established ownership while adding useful integration operations. It avoids a new shared-runtime extension and wholesale migration of the two working panels.

## Saved record and runtime state

Each saved record has an immutable UUID, a unique case-insensitive name within the model, and complete view content. Content includes the exact property name and typed exact value; box world transform, size, active faces, activation and overlay state; highlight on/off and retained chosen color; and padding in metres. Store stage units and up-axis alongside spatial values so later metadata changes cannot silently reinterpret them. Record member paths are intentionally absent: the filter defines membership.

Identity Data is the initial property choice. A view never silently substitutes an alternate Project ID property or merges fields. Search affects displayed choices, not equality. Missing/blank values are not Project IDs. Discovery counts placed object roots, including editable instance roots, rather than counting their meshes or shared prototypes.

The first schema has no camera fields. Preview, Open, Refit, Save New, Update, and Exit never navigate or replace the active camera. A later camera feature requires a new versioned record design.

Named records live beneath a marked, collision-checked `/__ProjectViews` root-layer scope, one prim per UUID. Existing Section Box positions and `objectColorsState` remain separate. New/Update/Rename/Delete target only the relevant record through Kit layer undo; deletion prevents a weaker-layer record from reappearing. Unknown record versions are left untouched and shown as unsupported. Anonymous stages require Save As for sharing. Read-only scenes permit inspection but refuse record changes.

Live section and material changes remain session state. Root records change only on explicit record operations; Composer Save is the disk-persistence boundary. Saved box values are independent from the transient membership snapshot and unsaved draft.

## Visibility, failures, and lifecycle

Visibility means loaded drawable geometry that remains visible through inherited USD visibility and supported viewport display filters, not whether an object happens to be inside the current camera or section. Fit must not use its own clipping result as input. Partly hidden objects contribute only visible geometry. Count fully hidden matches separately from objects lacking usable loaded geometry. Never unhide assets or change selection to compute a fit.

Unsupported instance boundaries or stronger material bindings are reported with affected paths/counts; they do not masquerade as successful coloring. Missing stage, wrong context, invalid record, or incompatible stage-space metadata refuses the operation before changing the view.

Prepare scan, geometry, and material work before publishing. One intent revision plus stage generation and bound viewport identity prevents an old operation from publishing after a newer command, scene switch, or shutdown. External box edits invalidate a pending apply. On publication failure, restore the previous complete runtime snapshot. Close generators and discard unpublished layers on cancellation.

Saved-record and Section Box commands are generation-scoped. Old undo entries cannot modify a newly opened scene. Viewport changes end the bound inspection rather than moving it silently. Shutdown removes only owned session data and subscriptions, preserving authored scene data and unrelated undo history.

## Synthesis decision

Candidate A scored 23/25 and Candidate B 17/25 in the independent cross-judge before the camera deferral. Re-screening the reduced design still favors A because it retains established ownership without a shared-runtime migration. B's useful whole-Open clipping refusal, dependency error, and material counts were grafted. The full decision and corrections are in [synthesis.md](design/synthesis.md).

Parent revisions: distinguish saved records from unsaved drafts; retain the chosen color while highlight is off; use deterministic Exit restoration; keep the first version within the existing Z-up/default-context integration; remove all camera work from this release.

## Tradeoffs and alternatives

- Accept small changes to both existing extensions in exchange for one clipping owner and one effective color owner.
- Accept explicit Refresh in exchange for avoiding expensive continuous scans and unexpected view movement.
- Accept ordinary Composer Save in exchange for consistent scene persistence and no implicit saving of unrelated model edits.
- Reject a new shared runtime for now because it requires migrating established ownership and deployment before this feature can work.
- Reject an independent renderer because competing material and clip writers make restoration unreliable.
- Reject linking a saved view to separate color/box presets because a view must remain complete when those unrelated presets are renamed or deleted.

## Verification and remaining technical risks

The isolated Kit 110.2 scene passes 16 checks for extension startup, material precedence, clipping, exact Project IDs, a searchable 105th ID, centimetre padding, hidden and absent matches, root-layer records, scene Save/reopen, camera and selection preservation, and cleanup. The results are in [kit-results.json](verification/kit-results.json), with the fixture in [verify_kit.py](tests/verify_kit.py). The checks also cover a forced color-scope close failure and shutdown during inspection.

The Composer panel appears in the Window menu and discovers IDs in a representative scene. Race tests for rapid view or stage switches and a full visual color/section review remain.

## Implementation reconciliation

The implementation uses the existing Section Box and Object Colors owners, with small public integration APIs in each. Project View applies transient section snapshots directly through Section Box state. Saved-record actions use Kit undo; composite runtime transitions have no undo entry. The first release has no camera fields or camera actions.
