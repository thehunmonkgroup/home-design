# Schema versions and durable identity

The default authoring schema is [home-model-0.2](../../schema/home-model-0.2.schema.json).
The loader also supports [home-model-0.1](../../schema/home-model-0.1.schema.json)
and selects the schema from `modelVersion`. Unknown versions fail validation.
An explicit schema override controls validation instead of bundled selection.
Loading is read-only; version conversion is an explicit changeset operation.

Version 0.2 replaces positional layer, wall-segment and followed-edge selections
with scoped names, requires named profile boundaries and pins planar-framing
origins to a boundary. Roof edge overhangs use a complete map of boundary IDs.
Array order continues to define physical geometry and layer stacking, separately
from reference identity. Duplicate or incomplete topology names fail resolution.
Unused reusable types also reject duplicate layer IDs during semantic validation.

`BoundaryIdentity` handles scoped name resolution. `RoofIdentity` derives
parametric plane identities from form and supporting boundaries, and shared-edge
identities from adjacent planes. `PartIdentity` records fitted member provenance;
ambiguous provenance fails explicitly. `identityKey` is a generation key, while
the exported `key` can retain an earlier identity through an authored `memberIds`
map. Roof `faceIds` provides the corresponding plane identity map. Alias values
must remain unique among generated objects. Removed generation keys do not bind
to their old array positions. Changeset preview reports surviving, added and
removed generated children, and stale overrides/placements fail validation.

`ModelMigration.prepare` supports the deterministic `0.1` → `0.2` transition.
It names layers and boundaries, replaces selections, retains generated-member
and roof-face identities, and emits standard changeset operations with full
preconditions. It does not mutate source or bypass ordinary transaction checks.
The migration preserves physical geometry, materials and canonical IDs for the
public reference models. IFC root GUID regression coverage includes generated
members and cavity relationships; the material layer description also exposes
the new layer ID. Generated file bytes and supplementary resolved metadata can
change because schema identity information is added.

Schema versions describe authoring contracts independently of the package,
changeset, manifest and IFC versions. Breaking authoring changes require another
explicit schema version and conversion policy. Proposed changes belong in
`TODO.md`; legacy readers must not silently accept new positional semantics.

AI authoring instructions and commands are in the progressively loaded
[identity reference](../../skills/home-design/references/identities.md).
