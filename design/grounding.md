# Project View grounding

Status: updated after the user's first-release scope correction. Implementation in progress.

## Accepted behavior

- Editable 3D views restore the section box, one exact Project ID filter, and highlight settings. The user navigates the camera manually. Saving/restoring camera positions is explicitly deferred to a later release.
- Matching assets receive one adjustable highlight color. Surrounding construction retains original materials. A No highlight action restores original materials without clearing the view.
- Views belong to the model and are available to coworkers with the extensions installed.
- First workflow: construction work-package review. This is the stated interpretation of the user's acceptance of recommendations, not a supplied real-world example.
- On opening a saved view, discover current matching assets, including newly added ones, and preserve the saved section box. Refit to project explicitly recalculates the box. Camera navigation is untouched.
- A project can have multiple named views. Views can be renamed.
- Choose one Project ID from searchable discovered values.
- Fit visible matching assets with one metre of padding per side, adjustable before saving. Preserve manual edits on reopening.
- Respect existing visibility. Report hidden matching assets and exclude them from initial fitting.

## Project ID source

Q11 accepted: Identity Data Project ID by default, with a property selector for other models. Save the exact selected property in each view. Do not automatically combine aliases.

## Existing code traces

All source paths are relative to the sibling extensions directory. The grounding investigator queried existing graphify graphs and checked source. No runtime changes were made.

Object Colors: extension startup creates a public controller -> attach(stage) -> scan_steps -> group_objects -> ColorOverrides.apply_steps.

- object.color/object_colors/discovery.py:88 scans final editable Xforms. Scalar custom and omni:hoops:metadata attributes inherit along Xform ancestors, with nearer values winning. Excludes spatial IFC types, lights/cameras, internal prototypes. Includes placed editable instance roots. Does not discover mesh properties, arrays, dictionaries, or instance-proxy descendants.
- object.color/object_colors/scheme.py:63 encodes typed exact values. group_objects caps displayed named groups at 100. Project discovery must not lose IDs through that display cap.
- object.color/object_colors/overrides.py:47 accepts path-to-color mappings in an anonymous session sublayer, without visibility changes. Instance proxies and PointInstancers are unsupported override targets.
- object.color/object_colors/controller.py:60 owns stage lifecycle and generation cancellation. Ordinary scene changes require explicit refresh.
- object.color/object_colors/presets.py:60 stores one current scheme in root custom data objectColorsState. This is not a collection of saved project views.

Section Box: startup creates private state/clipping controller/position store -> window fit callback -> fit_box_to_selection(context) -> state.edit -> active viewport clip planes.

- section.box/section_box/selection.py:23 fits current context selection, traverses geometry and instance proxies, skips invisible geometry, uses world-XY minimum-area rectangle plus Z height, and falls back to conservative bounds for other geometry. Multiple distant objects yield one combined box. It currently assumes Z-up.
- section.box/section_box/window.py:172 fits and enables clipping but does not frame the camera.
- section.box/section_box/state.py:25 provides state operations, but no public accessor to the running extension. Do not create a second competing clipping owner.
- section.box/section_box/clipping.py:42 writes active render-product RTX clip attributes in session state and restores prior opinions on disable/retarget/destruction.
- section.box/section_box/saved_positions.py:49 stores named boxes under /SectionBox/Presets/Box_<uuid> in the root layer. Records contain name, dimensions, transform, and faces, not camera/filter/colors.
- section.box/section_box/commands.py:42 provides undoable root-layer record edits, not file saving.
- State resets inspection on stage changes. Saved boxes require explicit loading.

Useful integration direction to evaluate: reuse property discovery and geometry; expose a small public interface to the existing section runtime and an explicit-path fitting function. Avoid changing UI selection merely to compute a box, duplicate clipping owners, and UI-private callback coupling. Compare this with a structurally distinct architecture before choosing.

## Representative model evidence

Read-only offline inspection through installed Kit USD libraries inspected a representative scene and its referenced IFC layer. Evidence concerns on-disk data, not unsaved runtime edits.

- upAxis is Z; metersPerUnit is effectively 1.
- Identity Data and an alternate metadata family each contain a scalar string Project ID.
- Sampled IDs are authored on placed leaf Xform instance roots that reference prototypes, compatible with current discovery semantics.
- Paired values agreed where compared. This is not a full-model guarantee.
- model.browser/model_browser/logic.py:20 uses the Identity Data property family.

## Constraints still to specify in the design

Define view record versioning, exact property/value matching, named-view CRUD and undo, persistence consistent with scene Save, clipping and color ownership when existing panels are used, no-matches/all-hidden behavior, visibility counting, stale async cancellation, units/up-axis support, read-only and anonymous scenes, missing dependencies, and unsupported coloring targets. Shared-understanding confirmation was the user's "proceed"; the later camera scope correction supersedes Q1's camera portion.
