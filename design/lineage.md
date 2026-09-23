# Existing extension ownership and design history

## The question

Which existing ownership and lifecycle rules should Project View preserve when it combines saved camera, project filtering, colors, and section boxes?

## The code in question

`section.box/section_box/state.py`, `clipping.py`, and `saved_positions.py` own inspection state, viewport clipping, and named positions. `object.color/object_colors/controller.py`, `overrides.py`, and `discovery.py` own color lifecycle, temporary material layers, and object discovery. Paths in citations below are relative to the shared `exts` directory.

## What we found

- [Direct] The recorded Section Box contract specifies one runtime box, clipping only in the active viewport, and unclipped startup. Saved positions belong to the main scene regardless of the current edit target. See `section.box/DESIGN.md:7`, `:9`, `:10`, and `:18`, introduced with commit `4382ed9` on 2026-09-21.
- [Direct] Clipping uses the session layer and restores prior authored values on disable, viewport switch, and shutdown. The design explicitly excludes the global RTX enable setting. See `section.box/DESIGN.md:78`.
- [Direct] Commands belong to a scene generation so old commands cannot mutate a new scene or clear unrelated undo history. See `section.box/DESIGN.md:41`.
- [Direct] The architecture retained flat capability modules because additional packages would add lifecycle changes without simplifying callers. See `section.box/DESIGN.md:47`.
- [Direct] Object Colors commit `28de065`, dated 2026-09-23, requires preserving source materials and restoring their appearance on Disable. The dedicated anonymous session layer supports that recorded contract. See `object.color/docs/reference.md:29` and `:31`.
- [Direct] Object discovery excludes internal instance sources to avoid recoloring other instances indirectly. See `object.color/docs/reference.md:19`.
- [Direct] Commit `5b25d23` addressed stale palette callbacks that could edit a different criterion or stage. The review records the defect and the generation/criterion checks. See `object.color/docs/review.md:7`.
- [Direct] Commit `2ba87de`, dated 2026-09-23, changes fitting to a minimum-area XY footprint with horizontal top and bottom faces. Its stated scope includes nested transforms, instances, tilted assets, and georeferenced coordinates.

These are repository-recorded contracts. The original design interview and Object Colors handoff were unavailable, so their exact original human wording and scope remain unverified.

## What we can reasonably infer

- [Inferred] Project View should use the existing Section Box owner. A second controller would write and restore the same render-product session attributes, so independent teardown could overwrite another controller's active state. This follows from `section.box/section_box/clipping.py:42` and `:78`; no historical collision incident was found.
- [Inferred] A public entry point to the existing owner and a fit function accepting explicit paths are consistent with the recorded short call paths. The history does not establish why public integration access is absent.
- [Inferred] Project View previews need an explicit color ownership policy. Normal Object Colors edits persist the whole-stage scheme, while independently created material layers can mask one another. See `object.color/object_colors/controller.py:89`, `:162`, `overrides.py:136`, and `docs/reference.md:41`.

## Contradictory records

`section.box/DESIGN.md:11` still describes common-ancestor orientation. The detailed fitting section at line 62 and commit `2ba87de` describe geometry-derived XY orientation. The implementation agrees with the newer fitting description. The earlier sentence is stale and should be corrected when that document is edited.

## What we do not know

The six reviewed commits and local documents contain no rationale for the absence of public cross-extension accessors or an explicit multi-owner arbitration design. Their commit messages contain no PR or ticket references. The baseline commit `f027f00` records existing code rather than its original rationale. No external historical sources or original interview transcripts were available.

## Sources consulted

- Source control history. Reviewed Section Box commits `f027f00`, `4382ed9`, and `2ba87de`, and Object Colors commits `bd055b8`, `5b25d23`, and `28de065`. Inspected relevant messages, patches, current code, local design/spec/reference/review documents, and targeted lifecycle test assertions. No remote queries were made.
- Issue or ticket tracker. Not searched. No matching historical source MCP was available.
- Long-form documents. Consulted local `section.box/DESIGN.md` and Object Colors documents. No matching external historical document MCP was available; active artifact controls do not provide a searchable historical archive.
- Real-time team chat. Not searched. No matching historical source MCP was available.
- Infrastructure observability. Not searched. No matching historical source MCP was available.
- Error or exception tracking. Not searched. No matching historical source MCP was available.
- Product analytics warehouse. Not searched. No matching historical source MCP was available.

## Constraints for Project View

| Category | Constraint | Basis |
| --- | --- | --- |
| Preserve | One Section Box owner, active viewport clipping, session-only runtime overrides, restoration on release, and scene-generation undo protection. | Recorded Section Box contract. |
| Preserve | Explicitly saved records target the root layer. Normal scene saving controls disk persistence. Temporary adjustments do not overwrite saved records. | `section.box/DESIGN.md:16`, `:18`, `:72`, `:76`. |
| Preserve | Temporary colors retain source materials, act on editable instance roots, and clean up on stage replacement or shutdown. | `28de065`; `object.color/docs/spec.md:13`, `:16`; `docs/reference.md:17`, `:29`. |
| Change | Expose access to the existing Section Box service and explicit-path fitting without calling UI callbacks. | Proposed integration design, inferred from existing ownership. |
| Change | Store a separate Project View record containing camera, filter, box, and color choices. Keep existing named box positions readable. | New accepted scope; existing position schema at `section.box/DESIGN.md:72`. |
| Avoid | A second independent clipping controller, direct Project View RTX writes, global clipping toggles, or UI-private callbacks. | Recorded viewport behavior plus inferred shared-attribute conflicts. |
| Avoid | Using normal whole-stage color edits as an incidental preview operation. | They persist the current scheme to root custom data; `object.color/docs/reference.md:41`. |
| Risk | Color precedence and restoration need an explicit policy when both extensions are active. | Inferred from independent session material layers; `object_colors/overrides.py:136`. |
| Risk | Resolve one stage/context identity before applying a combined view. Object Colors uses the default context; Section Box follows the active viewport context. | Current mechanics at `object.color/object_colors/controller.py:51` and `section.box/section_box/state.py:38`. |
| Risk | Use the newer geometry-fit contract when deriving bounds and update the stale common-ancestor sentence. | Contradiction identified above. |

## Confidence summary

The recorded ownership, persistence, restoration, and scene-lifecycle contracts have direct documentary support. Public API recommendations and concurrent-owner hazards are architectural inferences. The exact original interview wording and the historical reason for missing integration APIs remain unknown.
