# Reusable assemblies

Read [composition](composition.md) before combining assemblies and
[editing](editing.md) before saving an existing model. Use this reference for
instantiation, duplication and parameter changes. Read the component domain
references only when changing stock, ports, framing or other construction details.

## Discover an assembly interface

```bash
home-design recipes
home-design recipes serviced-partition
home-design recipes coordinated-deck --objects --limit 20
home-design recipes coordinated-deck --object stock.joist
home-design recipes coordinated-deck --parameter height
```

The catalog lists installed recipes. A recipe ID, filename stem or explicit JSON
path selects one. The default detail response contains parameters, external
bindings, named connection points, allowed overrides and object counts. Parameter
target paths are returned only by `--parameter NAME`. Inspect
individual local objects when needed; avoid loading the entire template first.

Recipes expand into ordinary canonical objects. The assembly records the exact
recipe digest, selected inputs and local-to-canonical ID mapping. Rendering uses
those canonical objects; the recipe file is needed for reproducible adaptation,
not for building an existing instance.

Public recipes include:

The [construction catalog](catalog.md) provides complete exterior wall, insulated
roof, floor/deck, wet wall, ventilation, foundation, entrance and truss packages.
The two smaller recipes below provide focused starting points.

- `serviced-partition`: insulated wall, framed rough opening, flush electrical
  rough-in box, owned recess and open containment interface. It exposes origin,
  wall width/height, opening width and box height. Add connected service routes or
  receptacles through the [electrical](electrical.md) and [services](services.md)
  interfaces when requested.
- `coordinated-deck`: rectangular deck surface, fitted joists/rims, two beams,
  four posts and four concrete pads. Origin, width, length and height coordinate
  the package. Its connection points expose the deck surface and north beam for
  additional stairs, guards, hardware or building connections.

Recipe stock dimensions are illustrative. Geometric coordination does not resize
members for structural capacity or add products outside the declared package.

## Instantiate

Recipes require `modelVersion: "0.2"`. If the destination declares another input
format, prepare and transact the [format conversion](identities.md#explicit-migration) first.

Inspect the destination storey, then bind it explicitly. Supply parameter values
as JSON; lengths remain millimetres. Quote shell arguments containing arrays,
spaces or JSON strings.

```bash
home-design prepare home.json instantiate --object assembly.office \
  --recipe serviced-partition --bind binding.storey=level.ground \
  --param 'origin=[16000,0]' --param width=4800 \
  --output add-office.json
home-design preview home.json add-office.json
home-design transact home.json add-office.json --dry-run
home-design transact home.json add-office.json
```

All creation operations have absence preconditions; external participants have
value preconditions. Existing IDs are never overwritten. Preparation validates
the authoring contract; dry run checks resolved geometry and coordination;
successful transaction also prepares and publishes exports.

Inspect the resulting instance compactly:

```bash
home-design inspect home.json --object assembly.office --view assembly --limit 20
```

`connectionPoints` contains actual canonical element IDs and optional port names.
`objects` pages the local-to-canonical mapping. Follow `nextOffset` when needed.
Inspect the selected endpoint with `--view resolved` before connecting services.
A named connection point identifies an interface; add actual placement constraints
and semantic connections separately. Exposed ports must exist in the resolved
model, and normal service connection checks still apply.

## Adapt without losing local edits

```bash
home-design prepare home.json adapt --object assembly.office \
  --param width=5200 --output widen-office.json
```

The CLI finds an installed recipe using the instance's recorded ID. Supply
`--recipe path/to/recipe.json` for a workspace recipe. Preview and transact the
prepared changeset as above. Changes update the recorded inputs and affected
canonical objects together, preserving stable instance IDs.

Adaptation reconstructs the previous output from its exact recipe and inputs,
then compares it with the current model and proposed output. Independent local
edits, such as a renamed component, remain. If both the local edit and requested
update change the same field differently, `recipe.update-conflict` lists the
conflicting paths. Arrays are treated as complete values so an insertion cannot
silently retarget another item. Inspect the reported source and decide how to
combine the intended changes; do not bypass preconditions or overwrite local edits.

A changed recipe requires both the new recipe and the exact previous document:

```bash
home-design prepare home.json adapt --object assembly.office \
  --recipe recipes/partition-new.json --previous-recipe recipes/partition-old.json \
  --output update-office.json
```

Keep previous recipe versions available. A digest mismatch prevents guessing a
baseline. Canonical models still validate and build without those recipe files.
Distributed prior templates are retained under `recipes/history/`, outside the
active recipe list. For example, the
[screened-entrance baseline](../../../recipes/history/screened-entrance-8ffd963f.json)
matches digest `8ffd963f58abedc9999719250aa7dcd4a08f3eb145d191c65cc74e0195da7952`.
Pass that exact file with `--previous-recipe` when updating an instance with that
digest to the current entrance recipe. `home-design resources` locates the same
history directory in an installed package.

## Controlled overrides and stock

The recipe's `overridePaths` advertises local template fields that may be changed.
Use recipe-local IDs in these paths, before instance prefixes are added:

```bash
home-design prepare home.json adapt --object assembly.office \
  --override '/elements/assembly.root/name="Office partition"' \
  --output label-office.json
```

Recorded overrides persist through parameter updates. Remove one explicitly with
`--clear-override /elements/assembly.root/name` during adaptation. Overrides may
not introduce undeclared external references. Use declared bindings or a separate
ordinary changeset for additional external construction.

Types are instance-local by default. `--share-type LOCAL=EXISTING` explicitly uses
an existing compatible type when instantiating or adapting. Local type parameters
or overrides that would be discarded by a shared choice are rejected. During
adaptation, `--local-type LOCAL` restores a private recipe type before applying
its overrides. Sharing a type does not silently edit that external definition.
Retired definitions remain if another occurrence uses them.

An ordinary occurrence-only type edit outside the recipe remains an intentional
local edit. When changing the recipe's stock at the same time, review any reported
overlap and inspect all type users. See [changesets](changesets.md).

## Duplicate and recombine

```bash
home-design prepare home.json duplicate --object assembly.office \
  --new-object assembly.study --recipe serviced-partition \
  --param 'origin=[24000,0]' --param width=4000 --output copy-office.json
```

Duplication changes only the new package. It retains local edits, nested groups,
owned cuts/access spaces, semantic connections and applicable authored
requirements. Canonical references and opening-derived member keys are remapped;
external references remain external. The new instance remains adaptable.

Any canonical assembly can be duplicated without a recipe. Omit `--recipe` and
parameter options in that case. Explicit aggregate membership defines its parts;
private supporting anchors/stock are copied and externally used definitions remain
shared. A generic duplicate starts at the same location. Inspect and coordinate
its shared anchors and hosts before moving it. Duplicating a group does not invent
a transform or copy a containing external assembly.

To combine packages, add an `assembly` and an `aggregates` relationship naming the
child assemblies. Coordinate actual positions using shared anchors/host locators
and connect compatible ports explicitly. Nested recipe provenance is preserved
when the parent is duplicated. Review connections to external equipment and
supports: retaining an endpoint does not establish a second physical connection.

For defining new reusable packages, read the
[recipe document contract](../../../docs/reference/assembly-recipes.md).
