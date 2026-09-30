# Project View

Status: implemented and verified in Kit 110.2 and the Composer Window menu. User decisions Q1-Q11 are recorded in [grounding](design/grounding.md).

## Problem

Construction reviewers need several named inspection views for a work package identified by Project ID. Each view restores a section area and Asset Status display settings while finding the project's current assets. Status colors distinguish groups within the project. The user navigates the camera manually; camera saving belongs to a later release. Existing Object Colors and Section Box provide discovery, temporary colors, geometry fitting, and clipping, but neither stores this combined view. Their existing source-material, session-layer, and explicit-save contracts remain intact.

## Usage

1. Open Project View. Use the Project ID property dropdown, initially Identity Data / Project ID, to choose the model's ID field.
2. Search for a Project ID and click it to preview. The selected ID button gets a highlighted background. Restore the project's saved section default, or fit all visible matching assets with one metre of padding per side. Apply all status colors in Color mode. Use the previous Asset Status property if available, otherwise the first discovered field. The camera stays where the user positioned it.
3. Use the Asset Status dropdown to choose a discovered field. Original and Color controls sit between the dropdown and the status rows. Original restores original materials. Color applies every status group's color within the project. Assets outside the project retain their original materials. Rows show current status values and counts.
4. Click a status row to select it without changing the display mode or other groups' colors. Click its color circle to choose from the Object Colors 40-color palette. In Color mode, the group repaints immediately. In Original mode, the palette choice is stored until Color is enabled. These actions never move the box or camera.
5. Navigate manually and adjust the section box in Section Box. Save section sets the project's default box. Reset section removes that default and fits the current visible project assets with one metre of padding per side. Save New creates a separate named view; Update, Rename, and Delete operate on that view. Rename changes only its label.
6. Use Composer Save to write view records to the model file. Coworkers with the extensions open that model and choose a saved view.
7. Opening a view restores its saved box, project property and value, status property, display mode, selected row, and status colors. Membership and status values are freshly discovered; the saved box does not move. Clicking a Project ID also rescans its assets, then restores its saved section default or fits a new preview. Camera navigation stays unchanged.

```python
from object_colors.scheme import value_key

project_property = views.property_name
choices = await views.discover(project_property, search="01514")
await views.preview(project_property, choices[0].project_id, padding_metres=1.0)
# With an Asset Status property selected and an "Installed" value discovered:
installed = value_key("Installed")
await views.select_status(installed)
await views.set_status_color(installed, "#59A14F")
views.save_section()
saved = views.save_new("Level 2 installation")

await views.open(saved.id)
await views.set_status_coloring(False)
await views.reset_section()
views.update()

views.rename(saved.id, "Level 2 north installation")
await views.exit()
```

The panel consumes a single state subscription. It does not sequence color and clipping changes. [The type sketch](design/project_view_sketch.py) records the earlier coordinator design, before Asset Status replaced the single highlight choice.

## Project section defaults

Save section stores the current section position, size, and rotation for the exact Project ID property and typed value. A different property or value has its own default. Clicking an ID restores its default when present. Otherwise, it fits the current visible project assets with one metre of padding on each side.

Reset section removes that project's default and immediately fits its visible assets with one metre of padding per side. Future clicks use a fresh fit. Save section and Reset section sit side by side on the row above a full-width Exit view button. They preserve the camera, display mode, and palette choices.

Project section defaults persist in the scene through Composer Save or Save As. They are independent of named views' section snapshots and color settings. Saving or resetting a project default does not rewrite a named view. The internal `refit()` and `refresh()` APIs remain available without panel buttons.

Acceptance criteria:

- Save a moved, resized, and rotated section, switch projects, then return. Its complete saved position, size, and rotation return.
- The default matches both the exact property and the typed Project ID. Other properties and IDs retain their own defaults or automatic fits.
- Save the scene and reopen it. The project default returns on the next ID click.
- Reset removes the default and fits all visible project assets with one metre of padding per side. After saving and reopening, future ID clicks fit the current assets again.
- Save and Reset preserve the camera, Original or Color mode, palette choices, and existing named-view records.

## Asset Status decisions

The Asset Status controls replace the single Highlight color field. Property discovery examines only elements matching the selected project's exact property and typed ID. Candidate fields have normalized names that identify Asset Status. The dropdown does not assume a future fixed property name. Decisions about fixed Project ID and Asset Status parameters remain deferred.

Color mode applies all status groups at once. Typed status equality determines group membership, so a text value and a numeric value with the same display text remain distinct. Clicking a status selects its row only. Selection never disables other groups or enables colors in Original mode. Clicking a Project ID starts in Color mode with the previous status property when available, otherwise the first discovered field.

Status values and counts come from current project assets. Per-status palette choices belong to the view. Named Open rediscovers current data using the saved settings. The internal `refresh()` operation updates membership, status values, counts, and colors while retaining the current box, property, display mode, selected row, and palette choices. Original restores source material appearance while retaining each status transparency percentage, property, and palette choice. Color reapplies all group colors. Switching modes clears the selected row.

## Behavior proposed for the final review

These complete the accepted workflow; they are proposed defaults, not additional accepted interview answers.

- Exit View restores the section box and color display from before entering project inspection. Section Box edits made during inspection are draft changes, captured by Save section for the project default or Save New and Update for a named view. Switching between project views does not replace the original return point. Camera navigation is independent of Project View.
- Object Colors visibly yields color control while a project view is active. Its existing scheme is preserved. Deliberate edits to that scheme can be stored by Object Colors, but its panel marks the display as suspended until Exit View. On exit its latest intended scheme returns. Original mode does not release this suspension.
- Saved views do not activate automatically when a model opens. Closing the Project View panel merely hides its controls; Exit View ends inspection.
- Save New, Update, Rename, and Delete create undoable scene-record commands. Section Box gestures retain their own undo behavior. Project View activation, status or color changes, internal `refit()`, and Exit do not create a combined undo item; undoing a Section Box edit restores only the box. Temporary edits never silently update a saved view.
- Opening a saved view whose assets are now absent or hidden still restores its saved box and reports the missing/hidden counts. Preview without a saved default requires visible geometry. The internal `refit()` operation refreshes membership, counts, and colors but keeps the box if nothing can be fitted.
- Changes to an open model mark membership stale. Clicking a Project ID, Open, Reset section, and the internal `refit()` and `refresh()` operations rescan. The extension does not continuously rescan or refit the entire model.
- Shared means records travel with the saved USD scene. This is not concurrent editing or automatic synchronization between coworkers.

## Shape and ownership

Use Candidate A's coordinator shape, subject to cross-review. `ProjectViews` owns a draft, saved-view operations, and one inspection session. It combines small public capabilities from the existing owners. It neither clicks their UI nor writes competing rendering overrides.

| Module | Responsibility |
| --- | --- |
| `project_view/views.py` | Exact project and status matching, scoped status discovery, inspection draft, async intent/stage checks, combined runtime actions and exit |
| `project_view/records.py` | Named view and project section records, validation/versioning, per-record root-layer commands |
| `project_view/window.py` | Property dropdowns, ID search and automatic preview, status rows and palette, named views, controls, status |
| `project_view/extension.py` | Dependency wiring and lifecycle |
| Existing `object_colors` | Discovery and sole effective color override owner |
| Existing `section_box` | Explicit-path geometry fitting and sole clipping/state owner |

Transparency sliders sit between each status row and color circle. They display whole percentages and apply on release, avoiding panel reconstruction during a drag. Object Colors owns the opacity overrides. Color materials are keyed by both color and percentage. Original mode references copies of USD Preview Surface or OmniPBR material networks, retaining textures and separate mesh/subset materials. Affected native instances are temporarily made editable when needed; removing the session layer restores instancing. Unsupported shader networks produce notices.

The public operations hide discovery, cancellation, preparation, publication, and rollback. The window never coordinates those stages. Storage details stay in records.py. Keep short call paths rather than a separate adapter layer for each existing method.

The upstream extensions provide these integration contracts:

- Section Box exposes access to its running state and explicit-path fitting. Project View applies its transient box through Section Box's state owner, without creating a box-only undo entry for a combined view change. Manual Section Box controls retain their existing undo behavior. The selection command uses the same fitting function. Preserve its geometry-derived XY rotation and existing controls.
- Object Colors exposes discovery records without the legend's 100-group cap, plus a transient inspection scope. The scope serializes its existing scheme work with project highlighting. It constructs replacement layers before publishing, keeps one effective owned color layer, and restores the latest desired scheme on release. Entering or leaving this scope does not persist an enabled/disabled scheme change.
- Both extension services validate the exact same stage/context before changes. The first version targets their existing default-context Composer workflow and Z-up section controls. Refuse unsupported contexts or axes before applying any effect; do not silently operate on a different scene. Physical padding uses the scene's metres-per-unit value, including centimetre scenes.

This retains established ownership while adding useful integration operations. It avoids a new shared-runtime extension and wholesale migration of the two working panels.

## Saved record and runtime state

Each saved record has an immutable UUID, a unique case-insensitive name within the model, and complete view content. Schema 4 stores the exact project property and typed value; the status property, selected row's typed value, per-status palette choices, integer transparency percentages from 0 to 100, and `color_enabled` display mode; box world transform, size, active faces, activation and overlay state; and padding in metres. Store stage units and up-axis alongside spatial values so later metadata changes cannot silently reinterpret them. Record member paths are intentionally absent: the project filter defines membership, and status values define color groups.

Schemas 1, 2, and 3 remain readable and default to 0% transparency. Schema 1 records preserve their legacy whole-project color on Open. Selecting an Asset Status property transitions them to the current display modes. Schema 2 records enable Color when they contain a selected status or an enabled legacy highlight, and use Original otherwise. An enabled schema 2 view now colors all status groups. Schema 3 records preserve the explicit display mode. Schema 4 also preserves per-status transparency in both display modes.

Identity Data is the initial property choice in the dropdown. A view never silently substitutes an alternate Project ID property or merges fields. ID search affects displayed choices, not equality. Missing/blank values are not Project IDs. Discovery counts placed object roots, including editable instance roots, rather than counting their meshes or shared prototypes.

No supported schema has camera fields. Preview, status and color changes, Open, Save section, Reset section, Save New, Update, and Exit never navigate or replace the active camera. A later camera feature requires a new versioned record design.

Named records live beneath a marked, collision-checked `/__ProjectViews` root-layer scope, one prim per UUID. Existing Section Box positions and `objectColorsState` remain separate. New/Update/Rename/Delete target only the relevant record through Kit layer undo; deletion prevents a weaker-layer record from reappearing. Unknown record versions are left untouched and shown as unsupported. Anonymous stages require Save As for sharing. Read-only scenes permit inspection but refuse record changes.

Live section and material changes remain session state. Root records change only on explicit record operations; Composer Save is the disk-persistence boundary. Saved box values are independent from the transient membership snapshot and unsaved draft.

## Visibility, failures, and lifecycle

Visibility means loaded drawable geometry that remains visible through inherited USD visibility and supported viewport display filters, not whether an object happens to be inside the current camera or section. Fit must not use its own clipping result as input. Partly hidden objects contribute only visible geometry. Count fully hidden matches separately from objects lacking usable loaded geometry. Never unhide assets or change selection to compute a fit.

Unsupported instance boundaries or stronger material bindings are reported with affected paths/counts; they do not masquerade as successful coloring. Missing stage, wrong context, invalid record, or incompatible stage-space metadata refuses the operation before changing the view.

Prepare scan, geometry, and material work before publishing. One intent revision plus stage generation and bound viewport identity prevents an old operation from publishing after a newer command, scene switch, or shutdown. External box edits invalidate a pending apply. On publication failure, restore the previous complete runtime snapshot. Close generators and discard unpublished layers on cancellation.

Saved-record and Section Box commands are generation-scoped. Old undo entries cannot modify a newly opened scene. Viewport changes end the bound inspection rather than moving it silently. Shutdown removes only owned session data and subscriptions, preserving authored scene data and unrelated undo history.

## Synthesis decision

Candidate A scored 23/25 and Candidate B 17/25 in the independent cross-judge before the camera deferral. Re-screening the reduced design still favors A because it retains established ownership without a shared-runtime migration. B's useful whole-Open clipping refusal, dependency error, and material counts were grafted. The full decision and corrections are in [synthesis.md](design/synthesis.md).

Parent revisions: distinguish saved records from unsaved drafts; retain status palette choices in Original mode; use deterministic Exit restoration; keep the first version within the existing Z-up/default-context integration; remove all camera work from this release.

## Tradeoffs and alternatives

- Accept small changes to both existing extensions in exchange for one clipping owner and one effective color owner.
- Accept rescans on user actions in exchange for avoiding expensive continuous scans and unexpected view movement.
- Accept ordinary Composer Save in exchange for consistent scene persistence and no implicit saving of unrelated model edits.
- Reject a new shared runtime for now because it requires migrating established ownership and deployment before this feature can work.
- Reject an independent renderer because competing material and clip writers make restoration unreliable.
- Reject linking a saved view to separate color/box presets because a view must remain complete when those unrelated presets are renamed or deleted.

## Verification and remaining technical risks

The isolated Kit 110.2 checks cover extension startup, the property dropdown, automatic preview from ID buttons, rapid ID selection, material precedence, clipping, exact Project IDs, a searchable 105th ID, centimetre padding, hidden and absent matches, root-layer records, scene Save/reopen, camera and selection preservation, and cleanup. The results are in [kit-results.json](verification/kit-results.json), with the fixture in [verify_kit.py](tests/verify_kit.py). The checks also cover a forced color-scope close failure and shutdown during inspection.

The Composer panel appears in the Window menu and discovers IDs in a representative scene. Rapid ID clicks are verified through the actual panel controls. Race tests for stage switches and a full visual color/section review remain.

## Implementation reconciliation

The implementation uses the existing Section Box and Object Colors owners, with small public integration APIs in each. Project View applies transient section snapshots directly through Section Box state. Saved-record actions use Kit undo; composite runtime transitions have no undo entry. The first release has no camera fields or camera actions.
