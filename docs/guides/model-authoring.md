# Model authoring guide

The canonical file is a normalized, ID-keyed JSON graph that stores design intent. Render objects and the IFC EXPRESS graph are derived representations.

## Coordinate and identity rules

- Lengths are millimetres; angles are degrees.
- The local system is right-handed and Z-up: X east, Y north, Z up.
- Registry keys are stable IDs. A component keeps its ID when it moves or receives a new name.
- References and identity use stable IDs; array position supplies ordering only.
- Georeferencing, when present, is separate from local building coordinates.

Three.js receives `(x / 1000, z / 1000, -y / 1000)`. IFC remains millimetre-based. Each adapter performs this conversion explicitly.

Requests may express dimensions in metric or US customary units. Convert source dimensions to canonical millimetres with `skills/home-design/scripts/convert_length.py`, then author the resulting metric value. For review, the same script can present a metric value as feet and fractional inches.

## Registries

The root object contains:

| Registry | Contents |
| --- | --- |
| `project` | Project, site, and building identities |
| `levels` | Storeys and reference datums |
| `anchors` | Shared points, axes, planes, and element stations |
| `materials` | Physical identity and optional render appearance |
| `types` | Reusable wall, slab, roof, door, window, and space definitions |
| `elements` | Placed architectural components |
| `relationships` | Durable semantic connections between elements |

The complete field contract is [home-model-0.1.schema.json](../../schema/home-model-0.1.schema.json). Start new work from [reference-home-0.1.json](../../examples/reference-home-0.1.json), which intentionally exercises every version 0.1 element and relationship kind.

## Components

### Walls

A wall has a plan `path`, a reusable layered wall `type`, a `locationLine`, a base constraint, and a top constraint. Paths may be lines, polylines, or shared `axis2` anchors.

Use a height top for a free-standing wall. Use a roof `underside` surface constraint when the wall must follow a roof. Gable ridge and explicit roof-face crossings are inserted into derived geometry while preserving the authoritative wall axis.

### Slabs, foundations, and decks

A slab uses a footprint with an outer loop and optional holes, a layered slab type, a level datum, and an `up` or `down` extrusion direction. The `role` carries floor, foundation, deck, landing, ceiling, or roof-slab intent into IFC.

An attached deck remains its own slab element. Express the durable connection to the wall with an `attaches` relationship rather than inferring it from touching geometry.

### Roofs

Parametric roofs support `flat`, `shed`, `gable`, and rectangular `hip` forms. They retain footprint, eave datum, pitch, directional intent, and overhang. Explicit `faceSet` roofs support exact planar 3D boundaries for geometry requiring a custom recipe.

Version 0.1 hip recipes require a rectangular footprint. Use explicit planar faces for irregular hips or multi-ridge roofs.

### Openings, doors, and windows

An opening owns host-relative station, vertical, and depth placement. Its geometry may be rectangular or a local 2D profile. A `voids` relationship selects its host wall. A door or window references a reusable type and uses `fills` to occupy the opening.

The wall body is derived with the cut already applied. IFC also retains the `IfcOpeningElement`, `IfcRelVoidsElement`, and `IfcRelFillsElement`, so downstream BIM tools receive the semantics as well as the visible result.

### Spaces

An explicit space stores its footprint. A derived space stores a seed point and uses its `bounds` wall relationships to select one closed wall loop. The viewer hides space volumes initially; use **Show spaces** to inspect them.

### Assemblies

An assembly groups parts through an `aggregates` relationship. It carries intent such as a roof, wall, floor, deck, or stair system while reusing the part geometry.

## Relationships versus constraints

A placement constraint answers “where is it?” A relationship answers “what durable building meaning connects it?” Keep both when both meanings apply.

Examples:

- A wall base can be constrained to `slab.ground` top while `supports` records the assembly/load intent.
- An opening placement belongs to the opening while `voids` records which wall it cuts.
- A deck datum establishes elevation while `attaches` records its ledger connection to an exterior wall.

Every durable connection uses an explicit relationship; geometric contact supplies supporting spatial evidence.

## Current boundaries

Version 0.1 covers the architectural core. Structural analysis, MEP routing, parametric stairs, terrain, energy simulation, code compliance, fabrication details, construction sheets, and native FreeCAD features belong to future versions. Extend the schema and resolver together, and place all authoritative data in validated canonical fields.
