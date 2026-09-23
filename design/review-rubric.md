# Candidate review rubric

Score each criterion from 0 to 5. A candidate with unresolved ownership or data-loss defects cannot be selected without revision, regardless of total.

1. Accepted workflow: complete trace from discovered exact Project ID through visible fitting, one-metre padding, adjustable color/off, named save/load/update/rename, current membership with fixed framing, shared scene persistence.
2. Runtime ownership and reversibility: one clip owner and effective color owner, original surroundings, no source camera/material edits, deliberate manual edits, exit/restoration, partial failure and stale tasks.
3. Interface depth: small cohesive operations hide meaningful complexity; callers do not coordinate low-level steps, copied state, opaque internal ordering, or private UI callbacks.
4. Persistence and lifecycle: stable record identity, schema validation/versioning, precise undo, stage/context/generation boundaries, normal disk Save, readonly behavior, missing data and unsupported cases.
5. Migration and proof: justified changes to existing extensions, bounded scope, independent verification of actual rendering/camera/material restoration/save roundtrip, source-backed APIs and explicitly unverified assumptions.

Screen against architect design-red-flags.md: shallow modules, leaked storage/framework types, temporal decomposition, pass-through methods. Compare whole structures, not prose polish or file count alone.
