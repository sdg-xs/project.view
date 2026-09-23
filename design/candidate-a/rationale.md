# Candidate A: Project View coordinates the existing owners

## Problem

A named project view must reopen its saved camera, section box, exact property/value filter, and highlight, while discovering current membership. Section Box already owns active-viewport clipping, runtime undo, and box manipulation. Object Colors already owns discovery and material overrides. Project View should coordinate these owners through new public contracts, not create a competing clip controller or repurpose the persisted Object Colors scheme. Identity Data is the accepted default property; each view saves the selected exact scalar attribute. The Q11 update from the parent supersedes the pending note in grounding.md.

## Usage (caller's view)

```python
# Project View window: selecting a discovered value starts an editable preview.
choices = await views.discover(property=IDENTITY_PROJECT_ID, search="01514")
await views.preview(choices.values[0].filter, padding_metres=1.0)
# The user orbits normally and adjusts the existing Section Box panel.
saved = views.save(NewView("Tower 3 / level 1"))
# The root layer is now dirty. Normal Composer Save writes the model to disk.

# Coworker: opening discovers today's objects but preserves saved framing.
await views.open(saved.id)
await views.set_highlight(NoHighlight())  # Original model materials, box retained.
await views.refit(padding_metres=1.5)  # Explicitly changes camera and box.
views.save(UpdateView(saved.id))

# Saved-view list: stable identity is independent of the display name.
views.rename(saved.id, "Tower 3 / coordination")
views.delete(saved.id)  # Undo restores the record; the current draft remains.
views.close()  # Ends inspection and restores the prior viewport where still owned.
```

The window subscribes to one `ViewState`. It renders available IDs, draft differences, operation progress, and explicit refusal or warning outcomes. It does not coordinate separate camera, box, and material operations.

## Shape

`ProjectViews` owns the draft and one stage/viewport session. A complete `ViewRecord` stores one exact filter, framing, highlight choice, and fit padding. Paths are transient results of discovery, never the saved definition. An uncapped index maps typed exact values to editable object paths. String `"7"`, integer `7`, and boolean values remain distinct. Display search only filters that index; it cannot change equality or merge attributes. This follows foundational-thinking and boundary-discipline.

Four implementation modules suffice: `views.py` owns the session, matching index, async work, and runtime transactions; `records.py` owns records, schema validation, and root-layer CRUD commands; `camera.py` owns temporary cameras and viewport restoration; `window.py` renders state and issues intent. Existing Section Box owns geometry and clipping; existing Object Colors owns discovery and all color-layer activation. There is no integration-adapter package or sequence of one-method wrappers. The public methods hide matching, cancellation, rollback, and undo, per minimize-reader-load.

New public contracts are required. Section Box must expose its running runtime, observe/snapshot/apply operations, and explicit-path fit with time, up-axis, and physical padding. Object Colors must expose uncapped typed discovery and an exclusive, transient inspection scope. The scope suspends ordinary scheme output without changing `objectColorsState`. Only one color override layer is effective, avoiding the existing collection-name collisions. No highlight removes project bindings while keeping ordinary scheme output suspended, so surrounding and matching assets show original materials. Object Colors edits during inspection change that panel's desired scheme and its usual undo/persistence, but the panel clearly says its display is suspended. Closing inspection applies the latest desired scheme, including deliberate intervening edits. This proposed interaction needs behavior review.

The camera adapter samples the actual USD camera and saves a complete projection snapshot, world transform, center of interest, and aspect policy. It restores through a unique session camera rather than changing the source camera. Box panel edits and viewport navigation update the draft; saved records change only through Save view. Opening or refitting publishes a single undoable runtime transaction after async preparation. Cancelled or failed preparation leaves the previous preview intact. The sketch specifies commit gates, rollback, and cleanup.

Each UUID record is a root-layer prim beneath a marked, collision-checked `/__ProjectViews` scope. Versioned properties contain the complete record; unsupported versions remain untouched. New/update/rename/delete are per-record Kit commands with layer undo, scoped to the current stage generation. View saving never calls filesystem Save. Anonymous editable stages accept records and show “Save As required”; read-only roots permit previews but refuse record writes. Ordinary scene Save is the sharing boundary. Saved views list on reopening; none auto-activates. These choices preserve the existing explicit-save model.

## Synthesis decision

Candidate A is submitted for comparison. No cross-candidate synthesis has occurred in this package.

## Tradeoffs accepted

- We accept two small upstream public-API changes in exchange for one clipping owner and one material-layer owner.
- We accept suspended Object Colors display during inspection in exchange for a literal original-materials guarantee and preservation of later panel edits.
- We accept an explicit Refresh membership action after ordinary model edits in exchange for avoiding continuous expensive scans. Each Open and Refit refreshes automatically.
- We accept stage-space compatibility checks on saved views in exchange for avoiding silent reinterpretation after units or up-axis metadata changes. Metre and centimetre stages, and Y/Z-up fitting, are supported at creation; incompatible later metadata changes refuse Open until resolved.

## Alternatives considered

An independent Project View renderer using its own `ColorOverrides` instance and clip controller looks self-contained but makes callers arbitrate competing session opinions. Existing collection names can collide, and existing Section Box edits become disconnected from the saved draft. It hides less than its attractive one-call entry point suggests.

A single new universal inspection service would absorb camera, clipping, color, discovery, and both existing panels. It could offer an equally deep caller interface, but would replace established ownership and require migrating two extensions before delivering one view. The selected design puts coordination in Project View while leaving domain operations with their owners.

Reusing saved Section Box positions and Object Colors presets as linked records spreads one view across three independently editable identities. Delete, rename, and partial save require repair policy. A complete Project View record avoids that policy and does not add another saved box preset implicitly.

## Implementation reconciliation

No implementation exists. All service signatures in the sketch are proposals unless explicitly marked available. No other extension was edited.

## Open questions and risks

- Is visibly suspending Object Colors display while allowing edits to its desired scheme the preferred interaction during Project View inspection?
- Should closing inspection restore the prior box only if it has not been deliberately edited in Section Box since the last Project View apply, as proposed?
- Does the installed viewport API expose a stable aspect/conform policy for round-tripping differently sized viewports? If not, should activation refuse an unsupported policy rather than approximate framing?

## Next implementation step

After synthesis and the required shared-understanding checkpoint, prove the two service contracts with one live create/open/no-highlight/close cycle before building record CRUD or the full window.
