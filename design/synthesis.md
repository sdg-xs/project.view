# Project View design synthesis

Candidate A is the base. Candidate B was reviewed but its shared runtime requires migrating the two existing extensions before this feature can work. Both candidates were read in full, screened for shallow modules, leaked state, temporal decomposition, and pass-through methods, and scored against [the rubric](review-rubric.md).

| Criterion (0-5) | Candidate A | Candidate B |
| --- | ---: | ---: |
| Accepted workflow | 5 | 4 |
| Runtime ownership and reversibility | 4 | 3 |
| Interface depth | 4 | 3 |
| Persistence and lifecycle | 5 | 4 |
| Migration and proof | 5 | 3 |
| Total | 23 | 17 |

Cross-judge and parent agree on Candidate A. Keep the existing Section Box state and clip owner, Object Colors' sole effective material owner, and a Project View coordinator with a complete named record. A's public entry point hides matching, rendering handoff, record operations, and lifecycle. B's registry/runtime/session/capability chain adds reader load and rollout coupling. B's filter and camera types also conflict with its own promised exact matching and full camera restoration.

Grafted from B: an enabled box on a viewport unable to clip refuses the entire Open, a missing dependency is visible at startup, material binding reports colored/unsupported counts, and a free/authored-camera acceptance test is a gate before completing the camera adapter. Do not graft its shared runtime or color-session takeover.

Required corrections to A, accepted by the parent review on 2026-09-23:

- Refit always commits fresh membership and matching highlight. If nothing visible can fit, keep the existing camera and box, report counts and a framing warning. Never keep stale assignments.
- Object Colors can retain edits to its desired scheme while Project View temporarily owns the visible color layer; its panel shows that display is suspended. No highlight shows original materials. Exit reveals the latest scheme. Bind the inspection to exact stage/context.
- Make the temporary-camera proof cover free and authored cameras, projection and offsets, orbit center, manual navigation, source-camera immutability, and closure.
- Keep internal cancellation/operation-origin tokens private and typed, with explicit apply failures and rollback. Do not spread `object`-typed control tokens through the public interface.

No feature implementation existed at synthesis. The user's "proceed" after the behavior review is accepted as the shared-understanding confirmation required by grilling. The design follows the explicit accepted behavior in grounding.md and the final proposed defaults in DESIGN.md.

## Scope correction and re-screen

The user then chose to leave camera saving for a later release and navigate manually in this release. This supersedes the camera part of Q1 and the earlier camera sketches. The revised caller flow and signatures are in [project_view_sketch.py](project_view_sketch.py). Candidate A without its camera adapter has three Project View capability modules and two small upstream services. Candidate B without its camera component still requires a new shared runtime and coordinated migration of both working extensions. The structural choice remains A; the camera-specific score advantage, graft, and risk are removed from the first-release comparison. There is no camera field in schema v1 and no camera operation in the panel or coordinator. First-release verification must assert that Preview, Open, Refit, Save, and Exit leave the viewport camera unchanged.
