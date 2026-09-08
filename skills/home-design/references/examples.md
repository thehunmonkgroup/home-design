# Public examples and worked edits

Choose the public model that demonstrates the requested integration. Copy it to a
separate design workspace before editing. Keep custom copies and outputs outside
repository regression fixtures.

## Select a starting model

| Model | Purpose |
| --- | --- |
| [Assemblies](../../../examples/assemblies.json) | Nine inspectable construction packages: exterior wall, roof, deck, floor, wet wall, ventilation, foundation, entrance and truss. Use the [catalog](catalog.md) for recipe interfaces and parameters. |
| [Hillside Deck House](../../../examples/hillside-deck-house.json) | Terrain, multiple storeys, foundations, deck, stair/guard/screen, drainage and solar coordination. Its two view windows share stock. |
| [Master Suite Gable House](../../../examples/master-suite-gable-house.json) | A detailed framed and layered house with bedroom, ensuite, electrical circuits and water/waste/vent plumbing. Its [twelve-view tour](../../../docs/guides/master-suite-gable-house.md) exposes interiors and concealed construction. |

These models complement each other; none demonstrates every engine option.
Master Suite's services are electrical and plumbing; Assemblies supplies the
ventilation example. Assemblies has open service interfaces for connection into
larger designs, rather than a complete house-wide network.

Use `home-design inspect` to discover source IDs and `home-design views MODEL`
to discover prepared visual reviews. For a small new design, select or instantiate
the relevant assembly instead of copying unrelated house construction. When a
source uses positional selectors, [convert its input format](identities.md#explicit-migration)
before using named selectors or recipes.

## Complete changeset examples

Each independent example starts from an unchanged copy of the indicated source.
The revision is a design revision, not an engine version. Sequential edits use the
preceding result. For custom models, inspect their actual revision, IDs and values;
adapt intent and guards instead of applying these files unchanged.

| Source and starting revision | Changeset | Verify |
| --- | --- | --- |
| Master Suite, 9 | [Move a window](../../../examples/change-sets/move-window.json) | North opening moves from station 7200 to 6700 mm; window, host cut and opening framing follow; sill and other windows stay fixed |
| Master Suite, 9 | [Narrow one window](../../../examples/change-sets/narrow-one-window.json) | North window receives its own 1400 mm stock; original type and rough opening remain unchanged |
| Hillside, 5 | [Local shared window](../../../examples/change-sets/local-shared-window.json) | Upper view window becomes 800 mm wide; lower view window retains the shared 900 mm stock and geometry |
| Assemblies, 8 | [Rotate a serviced partition](../../../examples/change-sets/rotate-service-partition.json) | Wet wall turns 90 degrees about its start; framing, water branches, ledge, sleeve and seals follow; ventilation and quantities remain unchanged |
| Assemblies, 8 | [Rotate an electrical wall](../../../examples/change-sets/rotate-electrical-wall.json) | Exterior wall turns 90 degrees; opening framing, boxes, recesses, receptacle and cable follow; neighboring packages remain unchanged |
| Assemblies, 8 | [Insert a named layer](../../../examples/change-sets/insert-named-layer.json) | Add 6 mm back gypsum; extend the sleeve, cut and rear seal through the thicker wall while preserving the named cavity and framing references |
| Assemblies, after insertion, 9 | [Reorder named layers](../../../examples/change-sets/reorder-named-layers.json) | Exchange the two back lining leaves; cavity selection remains `layer.legacy.1` despite its changed array position |
| Assemblies, 8 | [Duplicate the deck](../../../examples/change-sets/duplicate-deck.json) | Independent complete deck at `[21000, 0]`, width 4800 mm; original geometry, stock and provenance remain unchanged |
| Assemblies, after duplication, 9 | [Adapt the copied deck](../../../examples/change-sets/adapt-copied-deck.json) | Copy length becomes 4800 mm and height 2400 mm; boards, framing, guards, posts, beams, connectors and pads remain coordinated |
| Assemblies, 8 | [Move the catalog entrance](../../../examples/change-sets/move-catalog-entrance.json) | Landing, stair, rails, screens, door and supports move 350 mm east and 225 mm north; recipe origin and neighboring packages stay coherent |

Use `home-design preview MODEL CHANGE`, then
`home-design transact MODEL CHANGE --dry-run`. Complete the transaction with an
explicit `--build-directory` and optional `--web-assets` destination outside the
public source directory. A dry run does not test exporters. See [editing](editing.md)
for source guarding, publication and recovery. Preserve the Master Suite companion
`views/master-suite-gable-house/` directory when copying its named tour.

## Prepare equivalent edits

Use [local type preparation](changesets.md) for occurrence stock and
[assembly preparation](assemblies.md) for duplication and adaptation. The deck
examples use `complete-deck`, instance `assembly.complete-deck`, and new instance
`assembly.deck.copy`. Prepare against the current source to obtain current value
and absence preconditions; do not hand-edit the expanded package object list.

The two rotation examples change the host wall's end offset from `[4000, 0]` to
`[0, 4000]`, retaining its start anchor. They are intentional local geometry edits:
aggregate membership alone does not rotate an assembly. The recipes expose origin
but no rotation parameter; future recipe adaptations preserve independent local
edits and reject overlapping changes. Use the recipe's origin parameter for a
whole-package translation, as the entrance example demonstrates.

The wet wall's `interface.cut.partition` contains authored opening limits, and its
`plumbing.pipe.supply` requests interference diagnostics (both prefixed
`assembly.interior-wet-wall.`). Inspect these objects when investigating dimensional
or collision failures. Compare schedules, generated identities, owned cut volumes
and unrelated objects after edits; use wall-content and framing/services views to
inspect concealed results. Dimensions and ratings remain illustrative authoring
inputs, not structural or service-sizing calculations.
