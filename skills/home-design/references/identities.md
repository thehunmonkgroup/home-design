# Scoped construction identities

Read this reference for layer or boundary edits, generated
member overrides, and input-format conversion. Read [editing](editing.md)
for committing the resulting changeset.

## Named construction substructure

Each wall/slab/roof type layer requires an `id`, unique
within that type. The array still specifies physical layer order. Select the ID
in hosted `layer` fields, cavity regions, framing, cut limits and penetration
`layers` arrays. Keep the ID when changing material, thickness or order. Removing
a selected layer produces an error; assign dependent components deliberately to
another layer before removing it. An explicit footing exposes `layer.legacy.0`.

Every 2D or 3D profile has `boundaryIds`, with one outer-edge ID per outer vertex
and one matching ID loop per hole. An ID identifies the outgoing edge from that
vertex to the next vertex, wrapping at the end. IDs are unique across the whole
profile. Move coordinates and IDs together when reordering a loop. Give each new
edge a new ID and retain a previous ID only on the edge that continues its intent.

```json
{
  "outer": [
    {"point": [0, 0]}, {"point": [4000, 0]},
    {"point": [4000, 3000]}, {"point": [0, 3000]}
  ],
  "boundaryIds": {"outer": ["south", "east", "north", "west"]}
}
```

A wall path has `segmentIds`, one per consecutive point pair. A line or axis-anchor
path has exactly one. Wall framing selects a named `segment`. A slab/footing
`follow` selects an outer `edge`; stairs continue to select a `side`. Roof
`edgeOverhangs` maps every footprint edge ID to its outward distance.

## Generated parts

Inspect `--view resolved --parts` before selecting or overriding a generated part.
Use the returned `key`; do not calculate it from an array position. Each generated
wall or planar framing record also exposes `identityKey`, its generation provenance.

Planar framing requires `originBoundary`, whose starting vertex anchors the layout
frame. Grid indices remain tied to that origin and spacing. Rim and split-board
keys incorporate the named bounding interfaces; blocking incorporates neighboring
members. Wall keys incorporate the selected segment and construction role; top
plates use their controlling roof plane. Parametric roof planes derive identity
from their form and supporting footprint edge, and shared roof edges from adjacent
planes. Explicit roof faces retain their authored IDs.

Dimensional edits can retain an existing part while changing its length. A new
hole can split a joist into different parts. Preview reports removed and added
children; overrides and member-host placements that reference a removed child
fail. Repair them from the candidate's actual generated parts. Ambiguous generation
provenance produces an error instead of selecting an arbitrary fragment.

`memberIds` maps generation identity keys to retained exported member keys.
Parametric roof `faceIds` similarly maps generated plane identities to retained
face IDs. Input-format conversion supplies these maps to preserve external identities.
Keep them during ordinary edits; unused entries preserve identity history. Edit
them only when deliberately assigning identity, never to hide a removed part.

## Explicit migration

Use named selections for authoring. If a source declares the positional input
format, convert it before adding named selections or recipes. Inspect its
`modelVersion`; the [input-format contract](../../../docs/reference/schema-evolution.md#input-format-conversion)
lists accepted values. Loading never rewrites source. An explicit CLI `--schema`
override replaces normal schema selection.

```text
home-design migrate MODEL --to 0.2 --output migration.json
home-design preview MODEL migration.json --output migration-preview.json
home-design transact MODEL migration.json --dry-run
home-design transact MODEL migration.json --build-directory build
```

Migration assigns deterministic `layer.legacy.N`, `segment.legacy.N` and
`boundary.legacy.R.N` names, rebinds selections and retains existing component,
roof-face and generated-member IDs. The changeset includes the original revision
and full changed-object preconditions. Review and apply it once; a source change
requires preparing a fresh migration. Migration preparation does not export or
save a model. The guarded transaction validates and builds the migrated result.

Unsupported input formats and reverse conversions fail explicitly. See the
[input-format contract](../../../docs/reference/schema-evolution.md#input-format-conversion)
for conversion and export guarantees. The target identifier in the command selects
the authoring schema; the design's `revision` advances through the transaction.
