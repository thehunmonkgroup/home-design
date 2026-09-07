# Assembly recipe document contract

A recipe is a separate declarative JSON document validated by
[`assembly-recipe-0.1.schema.json`](../../schema/assembly-recipe-0.1.schema.json).
Its `objects` contain canonical version `0.2` definitions in the six normal
registries. Expansion produces an ordinary changeset; no executable expressions,
new geometry format or adapter-specific construction logic is involved.

## Document fields

| Field | Contract |
| --- | --- |
| `recipeVersion`, `modelVersion` | `0.1` and `0.2`, respectively |
| `id`, `name`, optional `description` | Stable recipe identity and human-readable purpose |
| `assembly` | Local ID of the root assembly in `objects.elements` |
| `objects` | Optional levels/anchors/materials/types/elements/relationships registries; canonical templates use local IDs |
| `parameters` | Named typed inputs with descriptions, defaults/limits and explicit targets |
| `bindings` | External symbolic IDs, each with registry, optional component kind and description |
| `connectionPoints` | Named local element and optional scoped port, with descriptive purpose |
| `overridePaths` | Explicit recipe-local JSON Pointer prefixes permitted for controlled overrides |

Local object IDs are unique across registries and separate from binding names.
Every external typed reference needs a binding declaration in the correct registry.
Expansion validates the complete canonical schema and semantics after binding.
Unknown inputs, overlapping parameter paths, malformed array positions, collisions
and undeclared references introduced by parameters or overrides are rejected.

## Parameter targets and coordinated geometry

Parameter value types are `length`, `angle`, `number`, `integer`, `boolean`,
`string`, `point2` and `point3`. Lengths and points use millimetres; angles use
degrees. Numeric values must be finite. Parameters without defaults are required.

A target is a JSON Pointer into `objects`, such as
`/anchors/anchor.origin/position`. It can also be a scalar affine target:

```json
{"path": "/elements/beam.north/axis/1/offset/0", "scale": 1, "offset": -75}
```

This sets the endpoint coordinate to the input dimension minus 75 millimetres.
`scale` defaults to 1 and `offset` to 0. Affine targets require a numeric input;
they cannot evaluate functions or arbitrary code. Whole-vector targets accept the
corresponding point parameter. Distinct parameters cannot overlap parent/child
paths because application order must not change meaning.

Canonical `PointLocator2` and `PointLocator3` anchor forms in version `0.2` support
an optional `offset` vector in model axes. For example,
`{"anchor":"anchor.origin","offset":[4000,0]}` shares the origin while defining
a separate plan vertex; the three-dimensional form adds XYZ offsets to the
anchor's resolved spatial point. Offsets are translations, not local rotations.
Use these locators, host constraints and explicit affine targets to coordinate
construction. Aggregate membership supplies no geometric transform.

The public [partition](../../recipes/serviced-partition.json) and
[deck](../../recipes/coordinated-deck.json) recipes demonstrate complete documents.
Read the [assembly workflow](../../skills/home-design/references/assemblies.md)
for CLI input, overrides and stock decisions.

## Instance identity and updates

The root assembly's `recipeInstance` records recipe ID/digest, parameters,
bindings, controlled overrides, shared types, named bound connection points and
per-registry local-to-canonical IDs. It stores no redundant template baseline.
Normal IDs combine instance and local names; overlong combinations use a bounded
readable prefix and deterministic digest. The root ID is the requested instance ID.

Default recipe types are private canonical definitions. Explicit `sharedTypes`
map local stock IDs to existing compatible definitions, which are not copied or
edited. Controlled local inputs targeting those shared types are rejected when
they would be discarded. Bindings and external stock have changeset preconditions.

Adaptation needs the exact prior recipe digest. It reconstructs that baseline,
applies new inputs to the selected recipe and performs a three-way dictionary
merge with current canonical objects. Independent local edits remain; overlapping
changes report all conflict paths. Arrays are atomic values. Retained object IDs
remain stable, including after nested duplication. Obsolete definitions used
outside the instance are retained; invalid remaining references reject the update.

Duplication follows nested aggregation, recorded ownership, owned cuts/access
spaces and semantic relationships. Private supporting definitions are copied;
external definitions and containing assemblies remain external. Typed reference
values and dictionary keys are remapped separately from freeform metadata.
Generated member references rebind embedded opening IDs and default roof plane
IDs while preserving authored layer/boundary names and explicit face aliases.
Applicable requirements are copied with remapped local participants.

## Validation and packaging

Preparation checks the authoring contract and produces reviewable operations with
revision/value/absence preconditions. Preview and transaction dry run evaluate
geometry, connection points and coordination. Export preparation is part of the
guarded transaction before source commit.

The installed package bundles authoritative recipes beside schemas, public
examples and progressive skill references. `home-design resources` returns their
locations; `home-design recipes` discovers interfaces without full templates.
`home-design inspect MODEL --object ID --view assembly` provides bound connection
points and paged instance object mappings without requiring recipe files.
