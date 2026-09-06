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
| `types` | Reusable architectural, framing, footing, stair, enclosure, sweep and detail definitions |
| `elements` | Placed architectural components |
| `relationships` | Durable semantic connections between elements |

The complete field contract is [home-model-0.1.schema.json](../../schema/home-model-0.1.schema.json). [Single-Story Gable House](../../examples/single-story-gable-house.json) demonstrates core architectural components. [Hillside Deck House](../../examples/hillside-deck-house.json) demonstrates a two-storey shell with site, construction and envelope coordination. Example dimensions and member sizes are illustrative and require project-specific engineering before construction.

Models use `modelVersion: "0.1"`. Optional root `solarStudies` and `drawings` arrays store reproducible analysis/view requests. Use canonical element IDs for integrations; generated mesh counts and node names depend on resolved geometry.

For solar/orientation work, `coordinateSystem.trueNorthDegrees` is the clockwise
angle from canonical +Y toward +X pointing to true north; zero makes +Y north.
`coordinateSystem.georeference` supplies geographic latitude/longitude. Survey
coordinates remain local geometry; the importer does not reproject a map CRS.

## Components

### Walls

A wall has a plan `path`, a reusable layered wall `type`, a `locationLine`, a base constraint, and a top constraint. Paths may be lines, polylines, or shared `axis2` anchors.

Use a height top for a free-standing wall. Use a roof `underside` surface constraint when the wall must follow a roof. Gable ridge and explicit roof-face crossings are inserted into derived geometry while preserving the authoritative wall axis.

Orient exterior wall paths so the left normal points outside (clockwise around a simple building). Layers run from that exterior side inward. The orientation also determines window azimuth and door inward/outward operation. Roof-constrained openings are checked against the actual sloping wall profile.

### Slabs, foundations, and decks

A slab uses a footprint with an outer loop and optional holes, a layered slab type, a level or sampled surface datum, and an `up` or `down` extrusion direction. The `role` carries floor, foundation, deck, landing, ceiling, or roof-slab intent into IFC. Split contiguous deck zones into adjacent slabs and group them in a deck assembly; do not overlap a full deck slab with duplicate zone slabs.

An attached deck remains its own slab element. Express the durable connection to the wall with an `attaches` relationship rather than inferring it from touching geometry.

### Roofs

Parametric roofs support `flat`, `shed`, `gable`, and rectangular `hip` forms. They retain footprint, eave datum, pitch, directional intent, and overhang. Explicit `faceSet` roofs support exact planar 3D boundaries for geometry requiring a custom recipe.

Version 0.1 hip recipes require a rectangular footprint. Use explicit planar faces for irregular hips or multi-ridge roofs.

Pitch is in degrees: 8:12 is approximately `33.690067526`; 1:12 is `4.763641691`. Roof layers measure normal thickness. Surface queries measure the actual underside elevation at the queried X/Y, including that normal thickness.

The default `datumReference: "eave"` places the datum at the overhung footprint's low edge. Use `datumReference: "bearing"` to keep roof planes/ridge fixed relative to the bearing footprint when changing overhangs. `datumSurface: "underside"` makes the datum describe the bearing underside; the default is `"top"`. `edgeOverhangs` provides one outward distance per footprint edge in authored order and overrides uniform `overhang`; it requires a convex footprint without holes.

A `datumPoint: [x, y]` fixes the chosen roof surface elevation at that child-roof point. Combine it with a sampled parent-roof `eaveDatum` to keep a shed roof below an eave:

```json
{
  "eaveDatum": {
    "kind": "surface", "element": "roof.main", "surface": "underside",
    "point": [3000, 0], "offset": -100
  },
  "datumPoint": [3000, 0]
}
```

The parent sample point and child datum point may differ. Keep a semantic `attaches` relationship when the connection is architectural intent. Add explicit `clearances` to verify porch headroom; a placement connection alone does not guarantee clearance.

### Openings, doors, and windows

An opening owns host-relative station, vertical, and depth placement. Its geometry may be rectangular or a local 2D profile. A `voids` relationship selects its host wall or screen panel. A door or window references a reusable type and uses `fills` to occupy the opening.

The wall body is derived with the cut already applied. IFC also retains the `IfcOpeningElement`, `IfcRelVoidsElement`, and `IfcRelFillsElement`, so downstream BIM tools receive the semantics as well as the visible result.

Door types accept `frameWidth`, `panelCount`, `glazingFraction` and an optional manufacturer `clearOpeningWidth`. Sliding doors generate separate glazed panels and tracks. Single-swing doors accept `handing: "left" | "right"` and `swingDirection: "inward" | "outward"`, plus `swingAngle` in degrees. The resolved data includes a 90-degree swing envelope, nominal dimensions and clear-opening estimates; a manufacturer's clear width takes precedence over the geometric estimate. Nominal door width is not clear passage width.

For a screen door, set `infillMaterial` to the screen material and `infillFraction`
to the desired framed-panel infill fraction (greater than zero and at most one).
These fields are used together, separately from `glazingFraction`. Screen infill
retains its material and opacity in IFC and the viewer, and contributes no glazed
area. Use the normal opening, `voids`, and `fills` relationships so the screen door
has a real host cutout, operation, swing envelope and opening schedule entry.

### Layers and specifications

Walls, slabs and roofs resolve each layer separately, displaying exterior/interior or top/bottom finishes and exposing material layers in section cuts and IFC. Each layer contributes its thickness exactly once.

Use concurrent `components` for framing and insulation occupying the same cavity:

```json
{
  "name": "Insulated framing cavity", "thickness": 140, "function": "structure",
  "material": "material.timber",
  "components": [
    {"material": "material.timber", "fraction": 0.17},
    {"material": "material.fiberglass", "fraction": 0.83}
  ]
}
```

Fractions must sum to one. `material` selects the representative visual appearance; otherwise the largest fraction supplies it. IFC preserves concurrent composition on the effective layer material. Material-volume schedules divide the cavity volume by these fractions. Do not add the insulation depth as another consecutive layer.

Reusable types and elements accept scalar `specifications` and structured `performance`. Performance fields are `uFactorWm2K`, `rValueM2KW`, `shgc`, `airLeakageACH50`, `nfrcId`, `glazing` and `frame`. Units are explicit SI: convert US U/R ratings before entering them. Element values override individual type fields; unmodified fields inherit. Elements also accept scalar `properties`. These data reach resolved JSON, the viewer, IFC property sets and schedules.

Set `specifications.thermalBoundary` to `true` or `false` to classify energy-model surfaces. An absent value exports as unassigned, not as an assumed conditioned boundary. Canopies and deck surfaces normally belong in the shading model rather than the conditioned enclosure.

### Members, framing and footings

`memberType` defines `material` and a `section`: a centered rectangle (`width`, `depth`), circle (`diameter`), or local polygon profile with optional holes. A `member` supplies a two-point 3D `axis`, `role` and optional axial `roll`. Roles include beam, column, joist, rafter, stud, decking, stringer and brace. Sections remain perpendicular to their axes. Beams and columns export to their native IFC classes.

`framing` repeats the same member along a unit `distribution` vector with `spacing` and `count`. Its optional `omit` array contains zero-based repetition indices. Omitted members preserve the identities of remaining repetitions. IFC contains a framing assembly with individually typed member children. Divide framing into separate groups around openings; automatic engineered header/corner design is not inferred.

3D locators accept `{"point": [x,y,z]}`, `{"anchor": "anchor.id"}`, or `{"point": [x,y], "elevation": DATUM}`. A sampled datum contains `kind`, `element`, `surface`, `point`, and `offset`; a level datum uses `kind: "level"`, `level` and `offset`.

`footingType` defines `depth` and `material`. A `footing` has a top `datum` and `shape: "pad" | "strip" | "pier"`. Pads and strips use `footprint`; a circular pier can instead use `center` and `diameter`. Use separate footing segments with different datums for stepped foundations, and constrain each masonry wall segment to its corresponding footing. Add `supports` to preserve the load-bearing relationships.

`load` records a target, footprint, total `forceN`, load category and `foundationRequired` (default true). Model spa loads on their actual supported footprint. Validation checks footprint containment where the target has a footprint and follows every declared support branch to a footing/foundation slab. Missing branches and cycles fail. This is connection completeness, not structural load distribution or sizing. Optional `supports.bearingPoint` is checked against participant bounds; `capacityN` records an engineer's input without inferring load allocation.

### Stairs, guards and screens

`stairType` specifies `treadDepth`, `treadThickness`, `maxRiser`, optional `minRiser`/`nosing`, material and a `stringerType`. A `stair` defines plan `origin`, unit `direction`, connected `bottom` and `top` datums, and `clearWidth`. Set `riserCount` for a fixed layout, or let the resolver select uniform risers within the maximum. There is one fewer tread than risers; the upper landing is the final walking surface.

Model landings as slabs with the landing role. For turns or intermediate landings, compose flights and landing slabs into a `stairSystem` assembly. Each flight updates when its datums change; check run and landing alignment after elevation changes. Stair clear width measures the usable flight, with side stringers outside that width.

`railingType` specifies height, post spacing/section, rail section, material and optional baluster infill (`balusterSection`, `maxInfillGap`). `railing.role` distinguishes structural guards from graspable handrails. Use a circular `railSection` for a round handrail. These are geometric/specification controls, not jurisdictional certification.

Railings and `panel` screens accept a 3D `path` or `follow`. A follow references a stair side (`left`/`right`) or slab `edgeIndex`, plus optional outward offset. Stair-following rails account for section width so their inside face preserves stair clear width. Access `openings` are non-overlapping `start`/`end` station intervals measured along the 3D path. A `panelType` defines frame dimensions/material and a separate infill material; use its material opacity to represent screening. Screens never become structural guards implicitly.

A panel's optional `top` overrides its type height with a height or surface
constraint. Use `{"kind": "surface", "element": "roof.porch", "surface":
"underside", "offset": 0}` to close a screen up to a roof. Roof-following panels
and panels hosting openings require a two-point horizontal baseline. Their frame
and infill follow the resolved elevation profile; openings are cut through both,
with framing around the cutout. Out-of-profile and overlapping openings fail
validation. Split panels at roof face changes when the top cannot resolve into
linear segments. Full-height access intervals remain distinct from hosted doors.

Orient screen baselines with their left normal pointing outside the enclosure to
give doors consistent inward/outward operation. Keep screen frames clear of
guards and structural posts, close the perimeter at the house, deck and roof, and
check door swings against adjacent furniture or equipment footprints. Screens and
screen doors are not conditioned-envelope surfaces; set `thermalBoundary: false`
in their specifications.

### Terrain, drainage and interface details

`terrain` contains existing/proposed state and survey `points` in local millimetres. Supply indexed `triangles`, or let the resolver triangulate the point set. Duplicate X/Y coordinates, degenerate/overlapping triangles and out-of-coverage height samples fail. Supply explicit triangles for concave survey boundaries; automatic triangulation covers the convex hull.

Sample terrain `top` in footing, landing and stair datums. An element's optional `grade` terrain reference reports exposure/retained height for walls and foundation/slab perimeters, including terrain-triangle crossings. Retain separate existing and proposed surfaces and reference the intended one explicitly. The [survey workflow](ai-design-workflow.md#survey-import) converts external units/origins without writing the model directly.

`sweepType` reuses the section/material contract. A `sweep` follows a 3D path and identifies gutter, downspout, drain, interceptor, flashing, fascia, soffit or trim intent. Flow runs go upstream to downstream. `minFall` is dimensionless fall per horizontal run; reversed/insufficient falls fail. `drainsTo` connects one run's end to the next run's start. An `outlet` records its name, verified `stable` status and optional footing `exclusionRadius` in mm. Unverified stability warns; discharge inside a footing's exclusion distance fails.

Sweep profiles follow rotation-minimizing frames through shared miter joints,
including holes in a hollow profile. Path reversals and miters that consume a short
segment fail. Start the path in a direction that gives the desired local profile
orientation; the first frame uses world Z as its up reference (world Y for a
vertical start). Use separate runs/details for manufactured elbows or transitions.
Sweeps do not infer bend radii, hydraulic capacity or global self-intersections.

`detailType` supplies a category, reusable instructions, optional reference and material. A `detail` associates it with at least two participants and a 3D location. Use it for flashing, waterproofing, air-sealing transitions and engineer-specified connections. These details appear in schedules/IFC without requiring individually modeled fasteners or membranes.

### Clearances and executable requirements

Any element can carry `clearances`, each with a name, lower and upper sampled/level datums, and a minimum vertical distance in mm. For a porch, sample the low underside and finished deck at the same plan location. Add multiple samples where the critical surfaces vary.

Requirements contain human-readable statements. An optional `check` makes a numeric requirement executable, with a dotted resolved-data `property`, `operator: "atMost" | "atLeast" | "equals"`, and numeric `value`. Apply it to explicit element IDs. Missing/non-numeric properties fail at the requirement's declared severity. For example, use `atMost` to check `performance.uFactorWm2K` against a specified maximum. Certification requires a separate professional assessment.

### Spaces

An explicit space stores its footprint. A derived space stores a seed point and uses its `bounds` wall relationships to select one closed wall loop. The viewer hides space volumes by default; use **Show spaces** to inspect them.

### Assemblies

An assembly groups parts through an `aggregates` relationship. It carries intent such as a roof, wall, floor, deck, or stair system while reusing the part geometry.

## Relationships versus constraints

A placement constraint answers “where is it?” A relationship answers “what durable building meaning connects it?” Keep both when both meanings apply.

Examples:

- A wall base can be constrained to `slab.ground` top while `supports` records the assembly/load intent.
- An opening placement belongs to the opening while `voids` records which wall it cuts.
- A deck datum establishes elevation while `attaches` records its ledger connection to an exterior wall.

Every durable connection uses an explicit relationship; geometric contact supplies supporting spatial evidence.

## Drawing views and dimensions

The optional root `drawings` array stores reproducible views for the exported
SVG sheet. Each entry specifies `id`, `name`, `kind: "projection" | "section"`,
`axis: "x" | "y" | "z"`, and a canonical millimetre `position` for the cut/view
plane. Optional `includeKinds` filters the view. Use explicit views to isolate
crowded construction details.

`dimensions` contains canonical 3D `start`/`end` points and an optional `label`.
Dimensions measure their projected distance in the selected view, so put dimension
endpoints in the measurement plane. Rebuild after changing views or dimensions.
See [Drawings and schedules](export-and-sharing.md#drawings-and-schedules) for
default views, exported sheet contents and output limitations.

## Current boundaries

The engine supports architectural/construction coordination, site geometry, drainage routing, geometric solar studies, schedules and dimensioned view/section exports. Structural analysis, reinforcement design, hydraulic simulation, annual energy modeling/certification, jurisdictional code approval, shop/fabrication detailing and native FreeCAD features remain external. Enter consultant-specified values in canonical fields and preserve their references. SVG drawings are coordination drawings, not a completed permit set.
