# Public examples and worked edits

Choose the smallest public model that demonstrates the requested integration. Keep custom copies and their outputs outside repository regression fixtures.

## Select a starting model

- [Assemblies](../../../examples/assemblies.json): nine separate construction
  packages with complete authored layers, framing, connections and service
  interfaces. Use the [catalog reference](catalog.md) to select a recipe and
  discover its parameters, connection points and component coverage.

- [Single-Story Gable House](../../../examples/single-story-gable-house.json):
  architectural walls, slab, roof, openings and shared datums.
- [Hillside Deck House](../../../examples/hillside-deck-house.json): site, stepped
  foundations, deck, stair/guard/screen and drainage coordination.
- [Complete Shell Coordination House](../../../examples/complete-shell-coordination-house.json):
  explicit framing, connected services, hosted equipment and owned cuts.
- [Integrated Authoring House](../../../examples/integrated-authoring-house.json):
  named layers and boundaries, two windows sharing stock, the complete
  service partition, and instantiated partition/deck recipes. Use this model for
  combined editing tasks. When starting from a model with positional selectors,
  [convert its input format](identities.md#explicit-migration) before using named selectors or recipes.

## Complete changeset examples

[Move the catalog entrance](../../../examples/change-sets/move-catalog-entrance.json)
applies to revision 7 of [Assemblies](../../../examples/assemblies.json). It moves
the landing, stair, rails, screens, door, supports and connections 350 mm east and
225 mm north, preserving neighboring packages and updating recipe provenance.

Unless a preceding edit is listed, these files apply to revision 1 of their named public model. For an existing
custom design, inspect its actual IDs, type values and revision first; adapt the
intent and preconditions instead of applying a reference change unchanged.

| Source model | Changeset | Verify |
| --- | --- | --- |
| Single-Story Gable House | [Move a window](../../../examples/change-sets/move-window.json) | Opening follows its new station; sill, dimensions, fill and host cut remain coherent |
| Single-Story Gable House | [Narrow one window](../../../examples/change-sets/narrow-one-window.json) | New type assigned only to the selected window; original type and opening preserved |
| Complete Shell Coordination House | [Rotate a serviced partition](../../../examples/change-sets/rotate-service-partition.json) | Framing, electrical/water branches, ledge and owned interfaces follow; independent air branch and quantities preserved |
| Integrated Authoring House | [Rotate a serviced partition](../../../examples/change-sets/rotate-service-partition.json) | The coordinated edit preserves named selectors |
| Integrated Authoring House | [Local shared window](../../../examples/change-sets/local-shared-window.json) | North window becomes 1400 mm wide; east window retains the original shared type and geometry |
| Integrated Authoring House | [Insert a named layer](../../../examples/change-sets/insert-named-layer.json) | Add 6 mm gypsum lining to the recipe partition; its named cavity, framing and box retain their references |
| Integrated Authoring House, after inserting the layer (revision 2) | [Reorder named layers](../../../examples/change-sets/reorder-named-layers.json) | Exchange the two gypsum lining leaves; physical order changes while the cavity remains selected by ID |
| Integrated Authoring House | [Duplicate the deck](../../../examples/change-sets/duplicate-deck.json) | Independent copy at `[25000, -5000]`, width 4800 mm; original stock, geometry and provenance preserved |
| Integrated Authoring House, after duplicating the deck (revision 2) | [Adapt the copied deck](../../../examples/change-sets/adapt-copied-deck.json) | Copy length becomes 4800 mm and height 2400 mm; its posts, beams and slab stay coordinated |

Copy the chosen source to a separate design workspace before applying an example.
Use `home-design transact MODEL CHANGE --dry-run`, then apply with explicit
`--build-directory` and `--web-assets` destinations outside the source directory.
The transaction writes the next revision to that copy. Apply sequential examples
in the stated order; independent examples start from a fresh revision 1 copy.
See [editing](editing.md) for the complete command protocol.

The narrow-window example uses the small one-window model. The local-shared-window
example verifies the same operation with two stock users. Always inspect type users
before deciding whether a stock edit should affect one occurrence or all of them.

The two recipe packages in Integrated Authoring House sit outside the main building
for separate review. They demonstrate composition and editing, rather than an
approved building arrangement. See [assemblies](assemblies.md) to prepare new
parameterized changesets instead of editing their expanded object lists by hand.

- [Complete shell coordination example](#complete-shell-coordination-example)

## Complete shell coordination example

[Complete Shell Coordination House](../../../examples/complete-shell-coordination-house.json)
combines explicit insulated wall, floor and roof cavities, framed openings, an
irregular deck, bearing plates, piers/posts and pad footings. Its service partition
contains a recessed box and carries two scheduled electrical circuits, earthing
parts and an interior ledge. A connected cold-water branch crosses that partition
through an owned sleeve opening with seal rings and a protective plate. An
independently placed mechanical branch includes a damper, two terminals,
insulation, a support and an equipment-access volume.

Use `electrical.anchor.wall.start` and `electrical.anchor.wall.end` to move or
rotate the service partition through a guarded transaction. Its framing, mounted
circuits, water branches, ledge, recess and penetration interfaces follow their
host references. `mechanical.anchor.mechanical` controls the separate air branch.
The opening limit on `interface.cut.partition` and the coordination checks on
`plumbing.pipe.supply` provide explicit examples of dimensional and interference
diagnostics. Inspect the generated member, cavity, circuit and service schedules
after edits, and use the framing/services views to see concealed components.

Dimensions, ratings, spans and seal geometry are illustrative authoring inputs.
The example demonstrates coordination and physical quantities without supplying
structural sizing, hydraulic/airflow calculations or approved seal assemblies.
