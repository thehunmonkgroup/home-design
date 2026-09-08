# Inspecting model context

Read this reference when the task requires these commands. Return to
[editing](editing.md) for guarded transactions.

## Inspect only the needed context

Source inspection is the default and works even when schema or geometry validation
fails. It returns authored parameters and references without generating meshes.
Use `--view resolved` when you need final dimensions, ports, cavity quantities or
other derived measurements. Only add `--meshes` when actual vertices/faces are
needed. Resolved inspection requires a valid model.
Generated member arrays are omitted from default resolved data and replaced by
a `generatedParts` count and discovery hint. Use `--parts --limit 20` or `--part KEY`
for their detailed records. Complete resolved JSON remains available in build outputs.

When querying saved JSON, distinguish these document shapes:

| Output | Component lookup | Measurements |
| --- | --- | --- |
| `inspect --object ID --view resolved` | One selected object at the root | `.data` (no `.resolved` wrapper) |
| `resolved-model.json` | `.elements[]`, selected by `.id` | Selected record's `.data`; meshes are large |
| `render-manifest.json` | `.elements[ID]` mapping | Viewer properties and scene-node identities |

For example, `jq '.elements[] | select(.id == "wall.north") | .data'
resolved-model.json` selects one component's measurements. Use paths returned by
build/transaction receipts and the published catalog; asset directories include a
model key and content version, so guessing their layout is unnecessary.

In `schedules.json`, component-family rows (including `drainage` and
`penetrations`) use `id` and put measurements in `dimensionsAndSpecifications`.
Specialized `cavities` rows use `elementId`; `generatedMembers` use `assemblyId`
plus `key`; material totals use `materialId`. `circuitSchedules` use `id` with
their schedule fields directly. Inspect one row's keys before projecting a new
report family, and retain its explicit `Mm3`/`M3` units when comparing volumes.
Repeated `framing` groups expose individual children through `inspect --parts`
and aggregate quantities in `schedules.framing`; their children are not rows in
`schedules.generatedMembers`, which covers the other framing assembly families.

Start with `--limit 20` and focused fields or roles; do not request depth 64 or
1000 records simply to discover participants. Save a larger report and select
its relevant IDs/paths when a complete audit is needed. `--query` searches names,
IDs and tags, rather than semantic concepts such as “recipe”. List assemblies or
use `--view assembly` to discover recipe provenance.

Use `--view assembly` for a recipe instance's named parameters, bound connection
points and paged canonical object mapping. See [assemblies](assemblies.md) for
discovery, controlled overrides and coordinated updates.

```bash
home-design inspect MODEL --kind wall --query north
home-design inspect MODEL --registry types --query window
home-design inspect MODEL --object ID --field /placement --field /type
home-design inspect MODEL --object ID --references --relationships
home-design inspect MODEL --object ID --dependents --depth 4
home-design inspect MODEL --object ID --dependencies --role placement
home-design inspect MODEL --object ID --type-users
home-design inspect MODEL --object ID --view resolved
home-design inspect MODEL --object FRAMING_ID --parts --limit 20
home-design inspect MODEL --object FRAMING_ID --part 'opening/OPENING_ID/header'
```

`--object` accepts IDs from any registry; `--element` is an alias. Use
`--registry` to disambiguate duplicate IDs while repairing an invalid source.
`--field` paths are JSON Pointers relative to the selected authored object.

Reference records distinguish placement, type, material, containment, ownership,
connection, semantic relationship and requirement roles. Each records its source
JSON path, target existence and any scoped member/port/layer/face selection.
Incoming references show the components that use the selected object; outgoing
references show what that object uses. `--type-users` follows type references
through reusable stock/recipes to occurrences. `--dependents` and `--dependencies`
traverse the authored reference graph; semantic records alone do not imply
geometry movement. Inspect related openings/fills and other semantic participants
as well when planning an edit.

A traversal returns one discovery path per object. Its `reference` describes
that path's final edge, not every reason the object depends on the selection.
An ownership/connection edge with `geometryDependency: false` does not establish
that the component stays still: inspect its direct placement references and use
preview to verify actual propagation. Use `--role placement` for a focused
placement traversal, then inspect other roles required by the task.

Pages default to 100 records. When `nextOffset` is non-null, repeat the query with
that `--offset`; `--limit` accepts 1–1000. Traversals default to depth 2; increase
`--depth` when `depthLimited` is true, up to 64. Do not treat a truncated page or
depth-limited query as the entire dependency graph. Scoped member output shares
IFC child identities and records; arrays retain omitted-index gaps.
