# Canonical model and durable identity

The [canonical authoring schema](../../schema/home-model-0.2.schema.json) defines
the model's fields and reference structure. Authoring documents declare
`modelVersion: "0.2"` to select that contract. This machine-readable identifier is
separate from the model's `revision`, which advances when a changeset is committed.
It is also independent of package, changeset, manifest and IFC format identifiers.

Layer, wall-segment and followed-edge selections use scoped names. The schema
requires named profile boundaries and pins planar-framing
origins to a boundary. Roof edge overhangs use a complete map of boundary IDs.
Array order continues to define physical geometry and layer stacking, separately
from reference identity. Duplicate or incomplete topology names fail resolution.
Unused reusable types also reject duplicate layer IDs during semantic validation.

The shared `PlanPoint` contract accepts point/anchor locators or literal XY vectors for
stair origins, sampled elevation datum points and surface mounting points. These
fields participate in normal coordinate resolution and dependency discovery.

`BoundaryIdentity` handles scoped name resolution. `RoofIdentity` derives
parametric plane identities from form and supporting boundaries, and shared-edge
identities from adjacent planes. `PartIdentity` records fitted member provenance;
ambiguous provenance fails explicitly. `identityKey` is a generation key, while
the exported `key` can retain an earlier identity through an authored `memberIds`
map. Roof `faceIds` provides the corresponding plane identity map. Alias values
must remain unique among generated objects. Removed generation keys do not bind
to their old array positions. Changeset preview reports surviving, added and
removed generated children, and stale overrides/placements fail validation.

Roof types support explicit `layerJoin` selection
(`independent` or `miter`) and stair-type `stringerTopCut` selection (`square`
or `plumb`). Defaults are independent roof-face layers and square stringer ends.
These are authored geometry choices.

## Input-format conversion

The loader chooses a schema from the document's `modelVersion`; unknown values
fail validation. An explicit CLI `--schema` override replaces bundled selection.
Loading does not rewrite source. Some bundled examples use positional selectors;
convert those inputs before authoring named selections or instantiating recipes.

| Input field | Accepted contract |
| --- | --- |
| `modelVersion: "0.2"` | Named layers, boundaries and segments; shared point locators |
| `modelVersion: "0.1"` | Positional selectors and literal XY values for stair origins, sampled datum points and surface mounting points |

`ModelMigration.prepare` converts positional inputs to the canonical authoring
contract. It names layers and boundaries, rebinds selections, retains generated
member and roof-face identities, and emits revision-guarded changeset operations
with full preconditions. It does not mutate source or bypass transaction checks.
The source identifier is `"0.1"` and the target is `"0.2"`; reverse conversion is rejected.

Conversion preserves physical geometry, materials and canonical IDs for the
public reference models. IFC root GUID regression coverage includes generated
members and cavity relationships. Supplementary metadata and generated file bytes
can change because named identity information is included. Roof-layer joins and
stair end cuts remain explicit authoring choices.

AI authoring instructions and commands are in the progressively loaded
[identity reference](../../skills/home-design/references/identities.md).
