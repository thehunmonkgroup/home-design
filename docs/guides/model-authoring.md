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

For solar/orientation work, `coordinateSystem.trueNorthDegrees` is the clockwise
angle from canonical +Y toward +X pointing to true north; zero makes +Y north.
`coordinateSystem.georeference` supplies geographic latitude/longitude. Survey
coordinates remain local geometry; the importer does not reproject a map CRS.

## Registries

The root object contains:

| Registry | Contents |
| --- | --- |
| `project` | Project, site, and building identities |
| `levels` | Storeys and reference datums |
| `anchors` | Shared points, axes, planes, and element stations |
| `materials` | Physical identity and optional render appearance |
| `types` | Reusable architectural, structural, hardware, accessory, envelope and service definitions |
| `elements` | Placed components, service systems/circuits and coordination checks |
| `relationships` | Durable semantic connections between elements |

The complete field contract is [home-model-0.1.schema.json](../../schema/home-model-0.1.schema.json). [Single-Story Gable House](../../examples/single-story-gable-house.json) demonstrates core architectural components. [Hillside Deck House](../../examples/hillside-deck-house.json) demonstrates a two-storey shell with site, construction and envelope coordination. Example dimensions and member sizes are illustrative and require project-specific engineering before construction.

Models use `modelVersion: "0.1"`. Optional root `solarStudies` and `drawings` arrays store reproducible analysis/view requests. Use canonical element IDs for integrations; generated mesh counts and node names depend on resolved geometry.

## Complete shell coordination example

[Complete Shell Coordination House](../../examples/complete-shell-coordination-house.json)
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

### Explicit cavities and physical parts

Use `representation: "explicit"` on a wall, slab or roof layer when its framing or
other contents have separate physical geometry. In this mode the layer's `material`
is its infill material, such as insulation. Omitting `material` leaves the remaining
cavity empty. Explicit layers cannot also declare aggregate `components` fractions.

```json
{
  "name": "Insulated stud cavity", "thickness": 140,
  "function": "structure", "representation": "explicit",
  "material": "material.insulation"
}
```

A physical member, framing assembly, hardware item, detailed fastener group,
reinforcement item, masonry part, sweep or panel declares which regions it occupies:

```json
{
  "occupies": {
    "regions": [{"host": "wall.south", "layer": 2}],
    "fit": "contained"
  }
}
```

The default `contained` fit requires the entire part to lie inside the union of its
declared cavity regions. `clip` trims the part to those regions, including roof
slopes and openings. `intersect` keeps the whole authored part while displacing
infill only inside the declared regions; use it deliberately for parts that extend
outside the host. Every declared region must contain some of the part. A clipped
framing array retains the indices and identities of its surviving members.

Regions are identified by host and zero-based layer index. Duplicate or overlapping
regions, absent layers, aggregate layers and overlapping physical ownership fail
validation. Two parts may touch, but cannot own the same cavity volume. Placement
remains explicit: use host locators when a part must move with the cavity.

The engine subtracts the fitted physical parts from the infill, then applies owned
penetrations to the resulting disjoint solids. A service hole crossing both timber
and insulation uses a cut for each affected physical host. Each cut reports only
the material it actually removes. A cavity schedule reconciles original cavity
volume with remaining infill, remaining parts and empty/cut space. Materials are
counted once from actual solids, including when a part occupies multiple regions.
IFC retains native member geometry, cavity ownership connections and composition
properties; it does not rely on an aggregate timber percentage for explicit parts.

Elements may set `discipline` to `envelope`, `framing`, `services`, `site` or
`accessories`. The viewer's **Envelope**, **Framing** and **Services** buttons isolate
those construction groups. Defaults classify members, arrays, footings and stairs
as framing, drainage sweeps as services, and terrain as site geometry. Accessories
appear in the envelope view. These controls change visibility without changing
geometry or material quantities.

### Members, framing and footings

`memberType` defines `material` and a `section`: a centered rectangle (`width`, `depth`), circle (`diameter`), or local polygon profile with optional holes. A `member` supplies a two-point 3D `axis`, `role` and optional axial `roll`. Roles include beam, column, joist, rafter, stud, decking, stringer and brace. Sections remain perpendicular to their axes. Beams and columns export to their native IFC classes.

`framing` repeats the same member along a unit `distribution` vector with `spacing` and `count`. Its optional `omit` array contains zero-based repetition indices. Omitted members preserve the identities of remaining repetitions. IFC contains a framing assembly with individually typed member children. Use `wallFraming` for a host-driven wall layout; use separate arrays for other explicitly authored repetition patterns.

3D locators accept `{"point": [x,y,z]}`, `{"anchor": "anchor.id"}`, or `{"point": [x,y], "elevation": DATUM}`. A sampled datum contains `kind`, `element`, `surface`, `point`, and `offset`; a level datum uses `kind: "level"`, `level` and `offset`.

`footingType` defines `depth` and `material`. A `footing` has a top `datum` and `shape: "pad" | "strip" | "pier"`. Pads and strips use `footprint`; a circular pier can instead use `center` and `diameter`. Use separate footing segments with different datums for stepped foundations, and constrain each masonry wall segment to its corresponding footing. Add `supports` to preserve the load-bearing relationships.

`load` records a target, footprint, total `forceN`, load category and `foundationRequired` (default true). Model spa loads on their actual supported footprint. Validation checks footprint containment where the target has a footprint and follows every declared support branch to a footing/foundation slab. Missing branches and cycles fail. This is connection completeness, not structural load distribution or sizing. Optional `supports.bearingPoint` is checked against participant bounds; `capacityN` records an engineer's input without inferring load allocation.

### Wall framing layouts

A `wallFraming` element generates physical boards inside one explicit wall layer.
Its `wallFramingType` references rectangular member types and authored spacing:

```json
{
  "kind": "wallFramingType", "name": "Wall framing recipe",
  "studType": "type.stud", "plateType": "type.plate",
  "headerType": "type.header", "spacing": 400,
  "bottomPlates": 1, "topPlates": 2,
  "kingStuds": 1, "jackStuds": 1, "endStuds": 3
}
```

For vertical studs, section `width` runs along the wall and `depth` runs across its
cavity. For horizontal members, `width` runs across the cavity and `depth` is the
member's height, normal to the slope for top plates. Define separate reusable
types for studs, plates and headers. Optional `sillType` and `blockingType` default
to `plateType`. Counts default to one except `topPlates`, which defaults to two.
Section depths may be less than the cavity depth, leaving real infill around them.

```json
{
  "kind": "wallFraming", "name": "South wall framing",
  "type": "type.wallFraming", "host": "wall.south", "layer": 2,
  "blocking": {"midHeight": 1500},
  "openingOverrides": {"opening.window": {"headerType": "type.largeHeader"}}
}
```

The selected layer requires `representation: "explicit"`. The framing derives its
storey and cavity ownership from the host; do not also author `occupies`. It follows
the wall path, base, roof-constrained top profile and hosted openings. Top courses
use slope-normal thickness and plumb joints at roof-profile breaks. Stud tops fit
the underside of the plates. Opening packages contain full king studs, bearing
jack studs, headers and window sills; grid studs fill the remaining full-height
and cripple regions. Bottom plates stop at floor-level door openings. Profiled
openings receive a rectangular rough framing envelope around their bounds.

For a polyline wall, provide a separate framing element for each zero-based
`segment`. An opening package must lie within one segment. `startInset` and
`endInset` reserve space at each run's ends; coordinate these explicitly at corners
and intersecting walls. `endStuds` builds end/corner packs. Default grid stations
start at one spacing interval from the segment origin; `gridOffset` changes that
origin. Stations remain fixed when an end inset changes.

`blocking` is a registry of stable row IDs. A numeric value is the row's center
height above the wall base. An object can set `height`, `memberType`, `role`
(`blocking` or `backing`) and `depthOffset`. Positive offsets move toward the wall's
exterior; negative offsets move inward. For example, a 40 mm deep backing board
inside a 140 mm cavity uses `depthOffset: -50` to meet the interior cavity face.
Each row produces individual bay boards between existing framing. Rows that would
produce partial-height or sloping blocking fail validation.

Inspect the resolved `members` records before adding `memberOverrides`. Keys such
as `opening/opening.window/header`, `end/start/0`, and `grid/0/full` identify
semantic parts. Overrides accept `omit`, a station/height `offset`, and a
same-section `memberType` substitution. Opening overrides can change `headerType`,
`sillType`, `kingStuds` and `jackStuds`. Unknown keys, overlapping members,
out-of-cavity parts and insufficient opening-package space fail validation.
Changing the topology can remove grid/cripple keys; stale overrides must be revised.

Generated members retain their own type, construction role, axis, section frame,
elevation cut profile, centerline length, stock bounding length and final net volume.
The `generatedMembers` schedule contains these records. IFC exports native member
children under a typed assembly, with headers as beams and stable IDs derived from
the assembly ID and member key. Penetrations can cut the assembly; surviving child
quantities update after the cut. Lengths describe authored board geometry, with no
waste or engineering allowance.

Mount another part on a generated member using a member host locator with
`element` set to the assembly ID and `part` set to its member key. For example:

```json
{"host": {"kind": "member", "element": "framing.south",
  "part": "opening/opening.window/header", "station": 200,
  "surface": "positiveX"}}
```

The mounting point follows that member through host/opening edits. An omitted or
missing key fails resolution. Member recipes and overrides express authored
construction decisions; they do not calculate header capacities or approve corner
and opening details.

### Floor, deck and roof-face framing layouts

`planarFraming` fits individual joists, rafters or decking members to one explicit
slab layer or roof-face layer. Its reusable `planarFramingType` requires
`memberType` and `spacing`, and optionally supplies `rimType` and `blockingType`.
All referenced member types have rectangular sections: `width` is transverse to
the member and `depth` is normal to the host surface. Depth cannot exceed the
selected layer thickness, and spacing cannot be less than the main member width.

```json
{
  "kind": "planarFraming", "name": "Deck framing",
  "type": "type.deckFraming", "host": "slab.deck", "layer": 0,
  "direction": [1, 0], "blocking": {"midSpan": 3000}
}
```

The host layer requires `representation: "explicit"`; omit its material for an
open deck cavity or provide an infill material for an insulated floor/roof. The
layout derives its storey and cavity ownership from the host, so do not add
`occupies`. A roof layout also requires a `face` ID from the host's inspection
data. Author one layout per roof face when directions or specifications differ.
Adjacent roof faces miter their framing domains at the bisector of their surface
normals. A miter that disconnects a face's layout domain fails validation; split
that roof face into separate planar boundaries.

`direction` is a unit vector in model XY indicating the longitudinal member
direction. On roofs it projects onto the selected surface. The layout origin is
the first boundary vertex offset normally to the layer center. Grid stations are
measured across that plane from the origin, at integer multiples of `spacing`
plus `gridOffset` (default zero); indices can be negative. Roof spacing and
blocking stations are surface distances. The resolved `plane` records the origin
and local axes.

The grid follows polygonal boundaries and splits around holes. `rimType` frames
the exterior perimeter and hole boundaries with individual boards. Perimeter
joints fit in boundary order, and subsequent grid and blocking members stop at
those boards. `blocking` maps stable row IDs to stations along the local
longitudinal axis. Each row generates separate transverse bay boards;
`blockingType` defaults to `memberType`. The default main role is `joist` for a
slab and `rafter` for a roof; an explicit `role` can also identify decking or
purlins.

Inspect generated keys such as `grid/3/0`, `rim/1/2/0` and `blocking/midSpan/0`
before adding `memberOverrides`. Overrides support `omit`, same-section
`memberType` substitutions and `endCuts`. Grid indices survive dimensional edits; changing
boundary topology can change split-piece indices. Stale override keys fail
validation. Generated members support scoped member host locators, owned
penetrations, individual IFC children and the `generatedMembers` schedule just
like wall framing. Quantities measure the fitted solids, including angled ends;
stock lengths retain the bounding length along each member's declared axis.

### Authored member assemblies and end cuts

`memberAssembly` groups named nodes and individually typed straight members. Set
`assemblyType` to `truss`, `roofSystem`, `floorSystem`, `deckSystem`, `bracing` or
`other`. Every member requires a `memberType`, `role`, and `start`/`end` node keys.
Roles identify chords, webs, ties, hips, valleys, ridge members, bridging and other
structural parts; the author supplies the node geometry and connection design.

```json
{
  "kind": "memberAssembly", "name": "Roof tie",
  "assemblyType": "roofSystem",
  "placement": {"origin": {"point": [0, 0, 3000]}},
  "nodes": {"left": {"local": [0, 0, 0]}, "right": {"local": [4000, 0, 0]}},
  "members": {
    "tie": {"start": "left", "end": "right", "memberType": "type.tie", "role": "tie"}
  }
}
```

`placement` moves and rotates local nodes and their member section frames.
Nodes can instead use three-dimensional point, anchor or host locators, whose
coordinates resolve in the model independently of the assembly placement.
Use host locators for roof members and staggered bridging that follow supporting
components. A member with two local nodes follows the assembly's section
orientation; otherwise its section uses the straight-member world frame.
Optional `roll` rotates an individual section about its axis.

Every node must participate in a member, and a truss network must be connected.
Members must have disjoint physical volumes. At an intersecting joint,
`trimAgainst` lists other scoped member keys whose final solids are subtracted
from that member. Trim references must intersect, cannot cycle, and cannot remove
the whole member. Shared node IDs retain connection intent; a node within another
member's span does not implicitly split that member or create a joint to it.
Use explicit trim interfaces or split the spanning member when that connection
is intended. Assemblies can own explicit cavities through `occupies`.

`endCuts` applies to straight `member` and `framing` elements, individual assembly
members, and wall/planar layout member overrides. Each `start` or `end` entry has
a unit `normal` in the member's rolled section frame and an optional signed
`offset` in millimetres. The cut plane passes through that stock-axis endpoint
plus `normal * offset`; it keeps the positive-normal half-space. Start normals
must point along positive local Z and end normals along negative local Z.
For example, `"end": {"normal": [0, 0, -1], "offset": 100}` shortens the stock
by 100 mm. Inclined normals make real bevels. Net quantities use the cut solid;
stock lengths retain the authored endpoints. Use owned `penetration` elements
for local notches, holes and bearing seats.

### Curved structural members

`curvedMember` uses a `memberType`, `role`, `placement`, centerline `radius`, signed
`sweepAngle` and positive `chordTolerance` in millimetres. Its circular arc lies
in the placement's local XY plane, centered on the placement origin. Optional
`startAngle` defaults to zero, measured from local positive X. Positive sweeps
run counterclockwise; negative sweeps run clockwise. Nonzero sweeps up to a full
360-degree ring are supported. `roll` rotates the section around the tangent.
The section must stay clear of the bend center.

The exported solid uses radial cross sections joined by chords. The tolerance
bounds both the outside bend's chord deviation and circular-section approximation;
resolution fails if the requested tolerance exceeds the 10,000-segment limit
for the path or section, or requires more than 2,000,000 intermediate loft
vertices across both subdivisions. Inspection reports `maxDeviationMm`, `segmentCount`,
the sampled `path`, analytic centerline `memberLength`, `polylineLengthMm`,
uncut `analyticVolumeMm3`, and tessellated `netVolumeMm3`. Material quantities
measure the actual tessellated solid. These controls support circular arcs;
arbitrary splines and automatic bent-stock fabrication design are not inferred.

Curved-member host locators accept `kind: "member"` and an analytic arc-length
`station`, with `surface: "axis"` or no surface. Local X points toward the bend
center for a positive sweep and away for a negative sweep, Y starts normal to
the arc plane, and Z follows the tangent; section roll then applies. Offsets and
rotations use that frame. Skin/end-surface locators and direct `endCuts` are not
supported for curves. Use an explicitly placed penetration for a local curved
member cut.

### Fabricated hardware and fastener groups

`hardware` places a reusable `hardwareType` and declares its connection
`participants`. Supported hardware roles include `hanger`, `strap`, `holdDown`,
`postBase`, `postCap`, `bracket`, `anchor`, `anchorPlate`, `embed` and `other`.
The type supplies the actual shape; a role does not choose dimensions or infer
a manufacturer's connection design.

Each fabricated type requires `material` and a named `solids` registry. An
extruded solid has a `section`, positive extrusion `depth` along local Z, and optional
local `placement` with `origin` and intrinsic XYZ `rotation`. Rectangles and
circles use centered sections; profiles support explicit boundaries and holes.
The solids are unioned so overlapping stock counts once. Optional named `cuts`
use the same local-solid controls and subtract in sorted-key order. Every cut must
intersect remaining stock and leave a nonempty result. A type supports up to
256 stock solids and 256 cuts. Type-local placements contain coordinates;
the element's `placement` accepts model point, anchor and host locators.

A stock solid or cutter can instead use `kind: "revolve"`, a `profile` with
`outer` and optional `holes`, and positive `chordTolerance`. Profile coordinates
are `[radius, height]` in millimetres. Radii must be nonnegative; the profile
revolves a full circle about local Z. Its optional local `placement` uses the
same origin/rotation controls. This supports tapered collars, hollow roof boots,
ring seals and turned parts. For example:

```json
{
  "kind": "revolve",
  "profile": {"outer": [[40, 0], [60, 0], [30, 100], [20, 100]]},
  "chordTolerance": 0.05
}
```

The tolerance bounds radial chord deviation at the largest radius. Revolutions
use at most 10,000 circular segments and 2,000,000 profile/segment vertices;
unresolvable tolerances fail validation. Quantities measure the resulting
tessellated solid. Profile holes retain material voids, and negative radial
coordinates are rejected rather than clipped by the geometry kernel.

For example, this reusable type describes a drilled plate in millimetres:

```json
{
  "kind": "hardwareType", "name": "Illustrative anchor plate",
  "role": "anchorPlate", "material": "material.steel",
  "solids": {"plate": {"section": {"kind": "rectangle", "width": 100, "depth": 80}, "depth": 6}},
  "cuts": {"hole": {"section": {"kind": "circle", "diameter": 12}, "depth": 6}}
}
```

A placed hardware element requires `type`, `placement` and at least one
participant. Each participant is an object such as `{"element": "member.post"}`
or `{"element": "framing.wall", "part": "opening/opening.window/header"}`.
Scoped part keys address generated wall, planar or authored assembly members.
Participants must reference surviving physical construction geometry; duplicates,
self references and missing parts fail validation. Participant references record
connection intent separately from mounting coordinates. They do not move the
hardware or certify contact, fastener spacing or connection capacity.

Hardware supports explicit cavity ownership through `occupies` and can be the
host of an owned penetration. Review the final part, infill and void quantities
after clipping or cutting. Type cuts belong to the fabricated shape; element
penetrations describe separately identified installation cuts.

`fastenerType` uses the same fabricated shape contract and requires a role,
`nominalDiameter` and `nominalLength`. Roles cover screws, bolts, anchor bolts,
nails, dowels, rivets, nail plates, staples and shear connectors. Nominal dimensions
are authored specifications; material quantities come from the unit's actual
solid, including any authored head or type cuts. Circular sections use polygonal
geometry, so nominal cylinder volume and the measured mesh volume can differ.

`fastenerGroup` requires `type`, `placement`, `participants`, a positive integer
`quantity`, and `representation`. Choose `scheduled` for a count without individual
positions, or `detailed` for a named `instances` registry of local placements.
The number of detailed instances must equal `quantity`; their solids cannot
overlap each other. Scheduled groups omit `instances` and cannot own physical
cavities because their positions are unspecified. Detailed groups support
explicit cavity ownership. Scheduled quantities support up to 1,000,000 units;
detailed groups support up to 10,000 instances.

```json
{
  "kind": "fastenerGroup", "name": "Hanger screws",
  "type": "type.connectorScrew", "quantity": 12, "representation": "scheduled",
  "placement": {"origin": {"point": [1000, 0, 2400]}},
  "participants": [{"element": "hardware.hanger"}, {"element": "member.joist"}]
}
```

Schedules include `hardware` and `fasteners` sections. Scheduled fastener volume
equals authored count times the fabricated unit volume and contributes to material
totals without rendering placeholder geometry. Detailed fastener volume measures
the actual placed solids, including cavity clipping, and does not add a second
scheduled volume. `quantity` retains the authored count; IFC also reports the
number of surviving modeled instances. Neither mode adds inferred fasteners or
waste allowances.

### Reinforcement, foundation bodies and masonry

Set `footingType.representation` to `explicit` when individually modeled parts
replace concrete inside a foundation. Its body becomes ownership region `layer: 0`;
parts use `occupies.regions: [{"host": "footing.pad", "layer": 0}]`. The original
material remains in the volume left around those parts. Aggregate footings retain
their ordinary monolithic geometry and reject explicit ownership. Top/bottom
host coordinates remain available; explicit foundations also expose layer 0
coordinates. Inspect `cavities` for the final concrete, occupied and void balance.

`reinforcingBarType` requires `material`, `nominalDiameter` and `role`. Roles cover
`main`, `shear`, `tie`, `ring`, `anchoring`, `edge`, `punching`, `stud` and `other`.
Optional `steelGrade`, `surface` (`plain` or `ribbed`) and `minimumBendRadius`
retain authored specifications. Ribbed bars use a circular coordination solid;
individual ribs and their extra material volume are not generated.

`reinforcingBar` requires its `type`, a three-dimensional `path`, `bendRadius`
and `chordTolerance`. Path points can use shared anchors or host coordinates.
Two points define straight stock; at each direction change a tangent circular
bend replaces the sharp corner. The bend radius is measured to the centerline
and must exceed the section radius and satisfy any authored type minimum.
Adjacent bends must fit within their shared span. Reversals and intersecting
bar solids fail validation.

Use `closed: true` for a planar tie or ring path. Supply each corner once; do not
repeat the first point at the end. Open paths can bend through multiple planes.
For example, four rectangular corner points and a bend radius define a closed
tie with rounded corners. Dimensions, cover offsets, hook angles and spacing
remain authored construction decisions.

Inspection reports analytic `centerlineLengthMm`, the original `authoredPath`,
the sampled `path`, `sectionAreaMm2`, nominal circular area, `sectionCount`,
`sectionSides`, `maxDeviationMm` and actual `netVolumeMm3`. The tolerance bounds
both section approximation and the outside bend's chord error. Resolution limits
are 10,000 path sections, 10,000 section sides and 2,000,000 intermediate loft
vertices. Quantities measure the actual polygonal solid. An owned cut changes
net volume while the nominal uncut centerline length remains inspectable.

`reinforcingMeshType` requires `material`, `longitudinalDiameter`,
`transverseDiameter`, `longitudinalSpacing` and `transverseSpacing`; `steelGrade`
is optional. A `reinforcingMesh` specifies `placement`, `length` and `width`.
Local longitudinal wires run along X from zero to `length`, at Y stations from
zero in multiples of longitudinal spacing through `width`. Transverse wires run
along Y, at X stations in multiples of transverse spacing through `length`.
These dimensions describe wire centerlines; allow for wire radii at the edges.
Spacing cannot be smaller than the parallel wire diameter, and the total wire
count cannot exceed 10,000.

`layerSeparation` is the nonnegative distance from the longitudinal centerline
plane to the transverse plane along local Z. It defaults to the sum of wire
radii, where the sets touch. An explicitly smaller separation produces intersecting
wire solids whose union counts shared material once. Weld beads and connection
capacity are not inferred. Inspection retains both wire counts, total nominal
wire length and final net volume. Circular mesh wires use 64-sided sections.

Bars and meshes support explicit cavity ownership and owned penetrations in the
same way as other physical parts. Their steel must be disjoint from other owners
of the same region. The `reinforcement` schedule retains the authored dimensions
and final quantities; the framing view includes their geometry.

`masonryPartType` reuses the fabricated `material`, `solids` and optional `cuts`
contract. Its roles are `unit`, `mortar`, `grout`, `fill` and `other`. A
`masonryPart` requires `type` and `placement` and can own explicit cavity volume.
For a hollow unit, author its shell as stock minus cell cuts, grout as separate
cell-shaped solids, and mortar as its own bed or joint shape. These parts retain
individual materials and identities. Overlap between separately owned units,
grout, mortar or steel fails validation; author compatible shapes or use a host
layer's infill material for the remaining material volume. The `masonry` schedule
reports the placed parts, and owned penetrations can cut them after composition.

### Hosted accessories and envelope interfaces

`accessory` and `envelopePart` place reusable fabricated shapes on a physical
host. Their types require `material`, named `solids`, optional named `cuts`, and
a `role`. Use extrusions, revolved profiles and their local placements to author
the actual geometry; the role does not infer product dimensions or installation
details. Different materials use separate coordinated parts.

Accessory roles are `ledge`, `windowStool`, `shelf`, `niche`, `backing`,
`accessPanel`, `grille`, `fixedEquipment` and `other`. Envelope roles are
`membrane`, `sillPan`, `roofBoot`, `flashing`, `airSeal`, `vaporSeal`, `weatherSeal`,
`fireStop`, `acousticSeal`, `sleeve`, `protectivePlate`, `cavityBarrier`, `ventBaffle`, `ventMesh`, `ridgeVent`,
`soffitVent`, `dripEdge` and `other`. Thin membranes have real authored thickness;
folded pans, flashing returns and ventilation slots use stock/cut recipes.

```json
{
  "kind": "accessory", "name": "Interior ledge", "type": "type.ledge",
  "placement": {"origin": {"host": {
    "kind": "wall", "element": "wall.interior", "surface": "interior",
    "station": 1200, "height": 900
  }}},
  "projection": 10
}
```

`placement.origin` requires a host locator. Optional `placement.rotation`
orients the part in that frame. Signed `projection` translates the origin along
the host frame's local Z before that part rotation; it defaults to zero. Positive
Z normally projects outward from the chosen face. Host offsets/rotations remain
available and are applied before this projection. The part inherits its host's
storey unless `storey` is supplied.

Recessed parts require actual host clearance: declare explicit cavity ownership
through `occupies`, or supply an owned `penetration` for the affected host.
Unresolved positive-volume overlap with the final host fails validation. A niche
can use negative local Z for its lining and an inward-facing penetration owned
by the niche. `mountingRangeMm` records the final part's minimum/maximum extents
along the mounting frame's Z, and `netVolumeMm3` measures its surviving material.
Scoped generated-member mounts retain the individual member's identity.

For an envelope part that protects a service penetration, add an `interface`
with a construction `host` reference and one or more `services` references.
Sleeves and protective plates require this declaration; seals, boots and other
envelope parts can use it when they serve a particular run. Each service reference
names a `serviceRoute`, `serviceFitting`, `serviceDevice` or `serviceInsulation`.
The construction host can be a wall, slab, roof, footing, member, framing assembly,
panel or masonry part; a generated member uses its scoped `part` key.

```json
{
  "kind": "envelopePart", "name": "Service sleeve", "type": "type.sleeve",
  "placement": {"origin": {"host": {
    "kind": "route", "element": "duct.supply", "station": 1200
  }}},
  "interface": {
    "host": {"element": "framing.floor", "part": "joist.3"},
    "services": [{"element": "duct.supply"}]
  }
}
```

Mounting coordinates and interface participants have separate meanings. A route
station positions the sleeve; the interface records which construction and
services it protects. Author the sleeve passage and seal annuli in their reusable
fabrication recipes. Give each host clearance its own owned penetration, and use
`occupies` when the parts displace explicit cavity infill. Final interface stock
must not overlap its construction host or any listed service. Touching surfaces
are permitted. Listing an interface does not create a cut or resize a part.

Interface parts default to the services review discipline. Their schedules and
scene data retain `interfaceHostId` and `interfaceServiceIds`. IFC exports sleeves
as `IfcCovering`/`IfcCoveringType` with `SLEEVING`, protective plates as
`IfcPlate`/`IfcPlateType`, and seals as coverings with their authored roles. Native
realizing-element connections link each service to its construction host through
the interface part. These parts do not add service ports. Fire, acoustic and
weather roles describe installation intent; use authored specifications and local
`barrierCheck` probes for the required evidence rather than inferring performance
from the role or geometry alone.

### Access spaces and barrier continuity

`clearanceZone` defines an authored nonmaterial space for `access`, `maintenance`,
`operation`, `ventilation`, `installation` or `other`. It requires a physical
`owner`, `placement`, `purpose` and local-extrusion `geometry`. Use a component
frame to make the zone follow its owner's placement and orientation:

```json
{
  "kind": "clearanceZone", "name": "Panel service access",
  "owner": "accessory.panel", "purpose": "maintenance",
  "placement": {"origin": {"host": {
    "kind": "component", "element": "accessory.panel"
  }}},
  "geometry": {
    "section": {"kind": "rectangle", "width": 600, "depth": 800},
    "depth": 750, "placement": {"origin": [0, 0, 25]}
  }
}
```

The owner is excluded from obstruction checks. Optional `allow` entries use
`{"element": "id", "part": "optional generated member key"}`; allowing one
member leaves its siblings subject to the check. Final physical solids determine
`status` (`clear` or `blocked`) and each obstruction's intersection volume.
Nonmaterial elements and terrain are excluded. Use separate terrain/grade checks
for earth clearance. A scheduled fastener group without physical instances cannot
serve as the owner.

`barrierCheck` checks an explicitly authored local interface for `air`, `water`,
`vapor`, `fire` or `acoustic` purposes. It uses the same placement/extrusion
controls and requires two to sixteen unique `participants`: either
`{"element": "envelope.part"}` or `{"element": "wall.host", "layer": 2}`.
The latter selects one physical wall/slab/roof/explicit-footing layer. Author a
probe that spans the intended seam or lap and is filled by the participating
materials; probes can use polygon profiles and local rotations for shaped joins.

A continuous result requires every participant to intersect the probe, their
combined material to form one connected region, and uncovered probe volume to
stay within `maximumGapVolumeMm3` (default 0.00001). The allowance must be smaller
than the probe volume. Duplicated physical material inside the probe fails
validation. A generous gap allowance does not waive disconnected or missing
participants. Inspection includes `gapVolumeMm3`, `coverageFraction`,
`connectedRegions`, `missingParticipants` and `status`.

Both checks use `severity: "error"` by default; `"warning"` retains the reported
failure while allowing a build. Results describe only authored geometric spaces
and interfaces. They do not establish whole-building airtightness, water shedding,
fire resistance or acoustic performance. Neither kind can own cavity material.
Their volumes are excluded from material quantities, default drawings and solar
shading. The viewer retains translucent, initially hidden probe geometry for
inspection; IFC retains virtual elements and their participant/owner assignments.

### Service devices, systems and circuits

`serviceDevice` places an authored reusable `serviceDeviceType`. The type combines
fabricated `material`/`solids`/`cuts` with a generic `role` (`equipment`, `terminal`,
`junction`, `control` or `other`) or an electrical/communications role described
below, and a named `ports` registry. Ports are logical
connection interfaces; their definitions do not create holes or connector solids.
Author those shapes in the fabrication recipe when required.

Each port supplies local `position`, outward `direction`, `section`, `medium`,
`flow` and `connectionType`. Circular sections specify `diameter`; rectangular
sections specify `width` and `height`, all in millimetres. An optional `up` vector
sets rectangular orientation; its projection normal to `direction` must be nonzero.
By default local Z supplies up, or local Y for a vertical direction. `flow` is
`source`, `sink` or `bidirectional`, relative to the device. Media are `electrical`,
`communications`, `water`, `waste`, `vent`, `gas`, `air`, `refrigerant`, `condensate`
or `other`. `connectionType` is an authored mating-technology identifier shared
by compatible interfaces.

For example, one entry in a type's `ports` registry is:

```json
{
  "supply": {
    "position": [50, 0, 50], "direction": [1, 0, 0],
    "section": {"kind": "circle", "diameter": 20},
    "medium": "electrical", "flow": "source",
    "connectionType": "illustrativeConnector"
  }
}
```

The device requires `placement` and `type`; optional `storey` places it in the
spatial tree. Host-based placement supports the accessory projection, fit and
cavity-ownership controls and inherits the host's storey. Freestanding placement
accepts points, anchors and port locators; nonzero `projection` requires a host.
The resolved `ports` preserve their full model-space frames and specifications.

Use a `connectsPorts` relationship to mate different components:

```json
{
  "kind": "connectsPorts",
  "a": {"element": "device.source", "port": "supply"},
  "b": {"element": "device.junction", "port": "inlet"}
}
```

Each port has at most one external mate. A branch therefore uses distinct ports
on a junction. A type's optional `portGroups` describes its internal buses or
passages, for example `[["inlet", "branchA", "branchB"]]`. All named ports must
exist and each group uses one medium. Port groups can connect different sizes
inside authored equipment; an external connection cannot silently act as a
reducer or shape transition. Groups do not consume external mates or infer
internal manufactured geometry, hydraulic behavior or electrical capacity.

Mating ports require equal media and connection technology, compatible flow,
opposing outward normals and positions within 0.01 mm. Circular diameters must
match within the same tolerance. Rectangular ports compare their actual corners,
so swapped dimensions work only with the corresponding physical rotation.
Both ports declaring `source`, or both declaring `sink`, fails validation.

Every port belongs to exactly one `serviceSystem`. The system is a nonphysical
element with `name`, `systemType` and explicit `members` (element/port references).
System types are `electrical`, `communications`, `water`, `coldWater`, `hotWater`,
`waste`, `vent`, `gas`, `supplyAir`, `exhaustAir`, `refrigerant`, `condensate` and
`other`; member media must match that purpose. A `serviceCircuit` is another
nonphysical element requiring `name`, parent `system` and `members`. Circuit
ports must belong to that parent and cannot belong to another circuit. Devices
with separate ports can participate in multiple circuits or systems.

Systems and circuits must each form a connected network through their own
members and declared internal groups. Connected loops are permitted. External
mates cannot cross system boundaries; an explicitly grouped internal passage
can connect same-medium interfaces of different systems without merging their
membership. Different media remain separate even inside shared equipment.

Ports default to requiring a connection. Instance `portStates` can explicitly
declare a named port `open` or `capped`; those ports cannot also have an external
mate. A capped state records design intent and does not manufacture cap geometry.
Unknown state keys, absent ports, duplicate mates, incompatible interfaces,
unassigned ports and disconnected groups fail validation. Schedules retain
systems/circuits, component membership, connection IDs and port counts.

Use `{"port": {"element": "device.source", "port": "supply"}}` wherever a 3D
point locator is accepted. As a placement origin it supplies the port's entire
frame; optional placement rotation then adjusts that frame. Source port locators
are retained in `portPlacements` metadata. Port-based geometry follows device
edits and participates in geometry cycle checks. Semantic connection and system
membership alone do not move geometry or create placement dependencies.

These controls provide generic fabricated devices and explicit connectivity.
Device geometry uses the authored fabrication recipe. Generated service routes
and fittings use the separate contracts below; discipline-specific equipment
ratings are not supplied by the generic device contract.

### Electrical and communications devices

Use `serviceDevice` and reusable `serviceDeviceType` fabrication for electrical
equipment. The device role selects its product meaning and native IFC family:

| Roles | Components |
| --- | --- |
| `receptacle`, `switch` | Power outlets and switching devices |
| `deviceBox`, `junctionBox` | Physical enclosures with authored entries or terminals |
| `distributionPanel`, `circuitBreaker`, `fuse`, `surgeProtector` | Distribution and protection |
| `light`, `smokeDetector`, `heatDetector`, `carbonMonoxideDetector` | Lighting and detection |
| `communicationsOutlet`, `communicationsPanel` | Signal outlets and distribution equipment |
| `groundingBar`, `groundingElectrode`, `bondingClamp` | Earthing and bonding parts |

These roles require an `electrical` object with at least one authored rating or
specification. Supported fields are `ratedVoltageV`, `ratedCurrentA`, `ratedPowerW`,
`supply` (`AC` or `DC`), `frequencyHz`, `poles`, `ways`, `breakingCapacityA`,
`residualTripCurrentA`, `protection`, `enclosureRating`, `signalCategory`,
`dataRateMbps` and `shielded`. `protection` lists any authored `overcurrent`,
`residualCurrent`, `arcFault` and `surge` functions. Frequencies require a supply
designation: AC has a positive frequency and DC has zero frequency. Omit unknown
ratings. The engine retains these specifications without selecting product sizes
or certifying their performance.

Every port on these devices requires a `function`: `power`, `neutral`,
`protectiveEarth`, `bonding`, `signal` or `containment`. Signal ports use medium
`communications`; power/neutral/earth/bonding ports use `electrical`. Containment
ports use either medium and represent a physical carrier entry. Grounding parts
require earth/bonding ports, and communications devices require at least one
communications signal port. Distinct ports can describe the power and signal
interfaces of shared equipment.

For example, a reusable receptacle type supplies authored fabrication and local
ports with ratings such as:

```json
{
  "role": "receptacle",
  "electrical": {
    "ratedVoltageV": 120,
    "ratedCurrentA": 20,
    "supply": "AC",
    "frequencyHz": 60,
    "poles": 1
  }
}
```

This fragment is illustrative specification data; complete the type's material,
fabrication and port definitions. Use the shared host placement, cavity ownership,
penetration and access-volume controls for flush boxes, recessed equipment and
panel access. Author internal terminal/bus connections with `portGroups` and
external connections with `connectsPorts`; mounting does not imply connectivity.
Mount separate devices on their actual wall or component hosts and reference
their ports at route endpoints. Wall translations and rotations then carry the
mounts, route endpoints and owned recess cuts together. Retain explicit mounting
projections and orientations when relocating devices within a panel or wall.

Routes and fittings accept the same optional `function` on their reusable types.
Mating functions must match exactly, including when one side omits the function.
Conduits with a function require `containment`; cables cannot use `containment`.
An entry and a conductor remain distinct interfaces even when their dimensions
match. These port functions describe authored connectivity; they do not simulate
electrical behavior or infer neutral-to-earth bonds.

### Circuit schedules

A `serviceCircuit` can add `schedule` with a scoped `panel` port, a string
`number`, and exactly one `electrical` or `communications` specification. The
panel port belongs to that circuit and identifies a matching distribution or
communications panel output. Circuit numbers are unique within a panel, including
when different output ports supply them. Scheduled circuits include both endpoints
of every member route so a route's length is counted once in that schedule.

An electrical schedule requires `nominalVoltageV`, `supply` (`AC`/`DC`) and
`poles`. Optional fields are `frequencyHz`, `designCurrentA`,
`overcurrentProtection` and `loads`. Protection references a breaker/fuse output
port in the circuit. Each load supplies a distinct device `terminal` port and
authored `apparentPowerVA`. For example:

```json
{
  "panel": {"element": "device.panel", "port": "branch1"},
  "number": "1",
  "electrical": {
    "nominalVoltageV": 120,
    "supply": "AC",
    "poles": 1,
    "frequencyHz": 60,
    "designCurrentA": 10,
    "overcurrentProtection": {"element": "device.breaker", "port": "out"},
    "loads": [
      {"terminal": {"element": "device.light", "port": "in"}, "apparentPowerVA": 900}
    ]
  }
}
```

These are illustrative inputs. The referenced interfaces and their routes need
explicit circuit/system membership and physical connections. A declared load
fails validation when the circuit graph contains a path from the panel to that
load which bypasses its declared protective device. This check concerns the
authored terminal loads and network topology; it does not simulate protection.

Supply checks compare nominal voltage with declared voltage ratings and check
authored AC/DC and frequency compatibility. Design current is checked against
panel/protection current ratings and cable `allowableCurrentA`. Pole counts are
checked against panel/protection ratings. Cable `maximumProtectionA`, when
authored, bounds the declared protective device's current rating. The engine
does not apply the total circuit current to every individual load's device rating.

A communications schedule requires `signalCategory` and optionally specifies
`dataRateMbps`. Declared data rates are compared with available device/cable
limits. Category labels are retained as authored; compatibility between differently
named technologies is not inferred.

Resolved circuits and `schedules.json` expose `circuitSchedule` and
`circuitSchedules`, respectively. Rows retain supply/protection references,
specifications, component IDs, total analytic `routeLengthMm`, and individual
`ratingChecks`. `ratingStatus` is `checked` when all listed rating checks have
known compatible inputs, otherwise `partiallyChecked`. Unknown values remain
`notChecked`; they do not become inferred ratings. `connectedLoadVA` sums only
listed loads. Omitted loads produce `null`, while an explicit empty list produces
zero. No demand factors, inferred loads, current-from-power calculations or
automatic conductor sizing enter these schedules.

### Service routes and empty passages

`serviceRoute` sweeps a reusable `serviceRouteType` along a 3D `path` of point,
anchor, host or port locators. Type `family` selects `pipe`, `duct`, `cable` or
`conduit`; `section` gives **outside** dimensions as a circle `diameter` or rectangle
`width`/`height`. Pipes, ducts and conduits require positive `wallThickness` that
leaves a positive bore. Cables have a solid section and omit wall thickness.
Types also supply `material`, `medium`, `connectionType` and optional `flow`:
`forward` or the default `bidirectional`. Pipes carry fluid media, ducts carry
air, and cables/conduits carry electrical or communications services; pipe, duct
and conduit families also accept explicitly classified `other` media.

For example, this reusable type and instance describe an illustrative water pipe
with a tangent bend. Supply the referenced material/storey and add both generated
ports to a water system's `members` before validating the model.

```json
{
  "types": {
    "type.waterPipe": {
      "kind": "serviceRouteType", "name": "Illustrative hollow pipe",
      "family": "pipe", "material": "material.pipe",
      "section": {"kind": "circle", "diameter": 40}, "wallThickness": 2,
      "medium": "water", "connectionType": "illustrativeMatingFace",
      "flow": "forward"
    }
  },
  "elements": {
    "route.water": {
      "kind": "serviceRoute", "name": "Illustrative water run",
      "type": "type.waterPipe", "storey": "level.ground",
      "path": [{"point": [0, 0, 500]}, {"point": [1000, 0, 500]},
               {"point": [1000, 1000, 500]}],
      "bendRadius": 150, "chordTolerance": 0.2, "clearance": 5,
      "portStates": {"start": "open", "end": "open"}
    }
  }
}
```

`bendRadius` is the centerline radius used at each path corner; it defaults to
zero for straight runs. Bends require a radius greater than the section's
bounding radius, including clearance. For rectangles this bound uses the half
diagonal. Adjacent tangent setbacks must fit their connecting span. Reversals,
zero-length spans and intersecting route/clearance solids fail validation.
`chordTolerance` is required and bounds the combined cross-section and bend
approximation in millimetres. Inspection retains analytic centerline length,
tessellated section area, actual material volume and maximum geometric deviation.

Optional `up` is a world-space initial section Y direction, projected
perpendicular to the initial tangent. Otherwise a starting port locator supplies
its own section Y direction; other starts use world Z, or world Y when the initial
tangent is vertical. The section frame follows successive bends without
additional twist. Generated `start` and `end` ports face outward, preserve the
section's actual orientation and share an internal passage. Forward routes have
a sink at `start` and source at `end`. Use explicit `connectsPorts` mates and
system/circuit membership as for devices. Port locators align endpoints; the
authored path must also align tangents and rectangular section orientation.

Routes retain named, nonmaterial construction volumes independently of physical
meshes: `envelope` encloses the full outside section, `bore` describes a hollow
route's empty passage, and `clearance` expands the outside section by the
instance's nonnegative clearance on every side. Clearance defaults to zero and
does not extend beyond the endpoint planes. These masks share the material
route's bend stations and follow its locators. They are inspectable in resolved
`constructionVolumes` and remain outside rendered bodies and material quantities.

For a route inside an explicit cavity, `occupies` displaces infill around the
actual route material. Also add a `penetration` for each affected host using a
named construction volume, for example:

```json
{
  "kind": "penetration", "name": "Pipe passage through insulation",
  "host": "wall.service", "owner": "route.water", "purpose": "service",
  "layers": [2],
  "geometrySource": {"element": "route.water", "volume": "bore"}
}
```

Use `bore` to empty the passage after material ownership, `envelope` for an
outside-sized hole, or `clearance` for an oversized hole. A sourced cut requires
its source element as `owner`, a different host, and omits `placement`, `section`
and `depth`. A solid cable has no bore. Validation rejects unavailable masks,
overlapping cut ownership, empty cuts and host material left in the bore of a
route with declared cavity ownership. Cuts measure only material actually
removed after cavity composition, including where bends occur inside hosts.
General service clash analysis is separate from this cavity passage check.

Duct route and fitting types can add `duct` with required `designation` and
optional `construction` (`rigid` or `flexible`), `jointing`, `lining`,
`leakageClass`, `roughnessMm`, `positivePressureRatingPa`,
`negativePressureRatingPa`, `minimumTemperatureC` and `maximumTemperatureC`.
These stock specifications retain the authored section and wall thickness;
lining descriptions do not add physical material. Temperature limits must be
ordered. Rigid/flexible segment classifications describe the authored stock;
flexible stock still follows the explicit route geometry.

A duct route or fitting can add `ductConditions` with signed `pressurePa`,
`temperatureC` and nonnegative `flowRateM3s`. Both pressure ratings are positive
magnitudes: for example, a `negativePressureRatingPa` of 750 allows an authored
pressure of -500 Pa and rejects -800 Pa. Use a consistent pressure reference for
the conditions and stock limits. Known pressure and temperature limits are
checked; missing limits and airflow performance remain `notChecked` in
`ductRatingChecks`. The engine retains airflow inputs without calculating duct
sizing, pressure loss, leakage or balancing. These records appear in the ordinary
service route/fitting schedules and exported properties.

Pipe route and fitting types can add `pipe` with required `designation` and optional
`nominalSize`, `construction` (`rigid` or `flexible`), `jointing`, `lining`,
`pressureRatingPa`, `minimumTemperatureC`, `maximumTemperatureC`, `roughnessMm`
and `potableWater`. Trade size does not override outside dimensions or wall
thickness. The temperature range must be ordered. Suitability and material
descriptions remain authored specifications.

Use `serviceInsulation` for physical insulation around a pipe or duct route or
fitting. Its reusable `serviceInsulationType` supplies `material` and positive
`thickness` in millimetres. The occurrence names its service `host`, its `type`
and a positive `chordTolerance`; `storey` defaults to the host's storey.

```json
{
  "kind": "serviceInsulation", "name": "Supply pipe insulation",
  "type": "type.pipeInsulation", "host": "pipe.supply", "chordTolerance": 0.1
}
```

The covering follows the service's control path, section dimensions, bends,
branches and transitions. Thickness expands each local outside section; a cap's
closed end also gains that thickness. Mating ends remain open. The physical
covering excludes the original service envelope, so pipe/duct material and its
internal passage are not counted as insulation. Inspection and the
`serviceInsulation` schedule retain the resulting net volume and material.

The covering's effective tessellation tolerance is at most one quarter of its
thickness. Local thickness also reflects the host's existing mesh approximation;
refine both tolerances for thin layers. Validation rejects an expanded envelope
that cannot enclose the host, an invalid enlarged bend, or a solid whose volume
does not survive mesh serialization.

Declare insulation `occupies.regions` separately from the pipe/duct when both
displace an explicit wall or floor cavity. Empty the pipe/duct bore with its owned
penetration as usual. Insulation supports its own owned cuts, including breaks
and access openings. It follows the authored service envelope; cuts into that
service do not automatically cut the covering. Multiple insulation parts on one
service must have disjoint final solids after their cuts. Covering construction
masks expose the enlarged `envelope`/`clearance` and the original service envelope
as the covering's `bore`. These masks are nonmaterial. Insulation appears in the
services view and remains independently selectable from its service host.

A pipe occurrence can add `conditions` with `pressurePa`, `temperatureC` and/or
`flowRateM3s`. Use the same pressure reference for stock and conditions; pressures
are nonnegative pascal values and temperatures are Celsius. Known pressure and
temperature limits are checked, while missing limits remain `notChecked` in
`pipeRatingChecks`. Flow rate is retained in cubic metres per second and remains
unchecked; the engine does not derive hydraulic capacity, sizing or pressure loss.

Use an occurrence `fallCheck` for geometric gravity coordination:

```json
{
  "fallCheck": {"minimumFall": 0.02, "direction": "startToEnd"}
}
```

`minimumFall` is a nonnegative drop/horizontal-run ratio (`0.02` means 2%).
`direction` is required and selects `startToEnd` or `endToStart`. Every authored
path span must meet the minimum in that direction; an overall endpoint drop
cannot hide a rising intermediate leg. The span directions also bound the
tangents of the generated circular bends. Descending vertical spans pass without
an infinite ratio; their resolved `fallRatio` is `null`. A fully vertical route's
`minimumObservedFall` is also `null`. Resolved check data includes each span's
drop, horizontal run, ratio and overall status.

Fall checks do not change port source/sink/bidirectional flow. This separates a
geometric drainage direction from transport intent, including bidirectional vent
interfaces. A moved anchor or device port triggers the check again. Pipe
specifications and conditions are restricted to pipe routes/fittings; fall checks
apply to routes. These values remain in inspection, schedules and IFC properties.

Mechanical `serviceDeviceType` roles use authored fabrication solids/cuts and
oriented ports. Each requires `mechanical` with a `designation`. Optional
specifications are `airflowRateM3s`, `heatingCapacityW`, `coolingCapacityW`,
`heatRecoveryEfficiency` (0–1), `filterClass` and `refrigerant`. These values
describe the selected equipment; they do not generate internal parts or calculate
its performance.

| Role | Minimum interfaces | Optional technology field |
| --- | --- | --- |
| `damper` | Two air | `damperType` |
| `airTerminal` | One air | `terminalType` |
| `fan` | Two air | `fanType` |
| `airHandler` | Two air | — |
| `heatRecoveryVentilator` | Four air | `heatRecoveryType` |
| `airFilter` | Two air | — |
| `coil` | Two air plus technology-specific interfaces | `coilType` |
| `airConditioner`, `dehumidifier` | Two air | — |
| `refrigerantUnit` | Two refrigerant | — |

`terminalType` selects `register`, `grille`, `diffuser` or `louvre`. `damperType`
selects `backdraft`, `balancing`, `control`, `fire`, `smoke`, `fireSmoke`, `gravity`
or `relief`. `fanType` selects `centrifugalForwardCurved`, `centrifugalRadial`,
`centrifugalBackwardCurved`, `centrifugalAirfoil`, `tubeAxial`, `vaneAxial` or
`propellerAxial`. Technology fields apply only to their corresponding roles.

Heat recovery uses exactly two disjoint air `portGroups`, each with at least two
ports, covering every air interface. Independent electrical/control groups are
also allowed. `heatRecoveryType` selects `counterflowPlate`, `crossflowPlate`,
`parallelflowPlate`, `rotaryWheel`, `runaroundCoil` or `heatPipe`.

For coils, `dxCooling` requires two refrigerant ports; `hydronic`, `waterCooling`
and `waterHeating` require two water ports; `gasHeating` requires a gas port;
`electricHeating` requires an electrical port. Air handlers, coils, air
conditioners, dehumidifiers and refrigerant units may also carry water,
refrigerant, condensate or gas interfaces. Other mechanical roles carry air and
electrical/communications interfaces. Power/control ports require an explicit
`function`, and electrical ports require type `electrical` ratings with consistent
AC/DC frequency data. Keep different media in separate groups and assign each
interface to its actual system. Use the ordinary `clearanceZone` contract for
authored equipment access and maintenance volumes.

Use port-based placements for inline dampers, fittings and terminals, with route
ends tied to equipment ports or component-relative locations. Equipment moves
then propagate through the dependent network, including separate insulation and
route-mounted supports. Reserve access space with a zone located from the
equipment frame; an obstructing physical part fails the declared access check.
Use an insulation envelope as a penetration's `geometrySource` when the hole
must fit the complete insulated run. The owned cut follows the route and measures
actual material removed from the floor or sloped roof after host edits.

Refrigerant supply/return lines can form a connected loop between equipment
interfaces. Keep equipment placement dependencies independent of that loop:
locate equipment first, then route between its ports. Give condensate a separate
system and an authored `fallCheck`; its equipment port direction must match the
initial pipe tangent, including an authored slope. The fall check evaluates the
located path and rejects an uphill change in its declared direction.

Plumbing `serviceDeviceType` roles are `valve`, `manifold`, `fixtureConnection`,
`cleanout`, `waterHeater`, `plumbingPump`, `storageTank` and `waterMeter`. Supply
actual local fabrication solids/cuts and ports. A fixture connection describes
the authored connection part; it does not generate a sink, toilet or appliance.
A cleanout's body and accessible closure also require authored fabrication.
Each plumbing role requires `plumbing` with a `designation`; optional fields are
`nominalSize`, `pressureRatingPa`, `minimumTemperatureC`, `maximumTemperatureC`,
`potableWater` and `capacityL`. These describe the complete equipment rating and
authored capacity, without inferring operation or sizing.

A valve can also specify `plumbing.valveType`: `isolating`, `check`, `mixing`,
`pressureReducing`, `pressureRelief`, `regulating`, `gasCock` or `faucet`. The valve
function supplies native IFC classification; it does not simulate valve operation.
Valves, pumps, water heaters and meters require at least two fluid interfaces;
manifolds and mixing valves require at least three. Heaters and water meters
require two water interfaces. Declare internal passages with `portGroups` and
leave independent passages separate. A manifold's branches need distinct ports.

Equipment may carry water, waste, vent, gas or condensate interfaces alongside
electrical or communications interfaces. Electrical/communications ports require
an explicit `function`; electrical ports also require type `electrical` ratings.
AC/DC frequency rules apply to powered plumbing equipment. Assign each interface
to its actual system, such as separate cold water, hot water, gas and electrical
systems on a water heater. Port groups cannot directly connect different media.

A `serviceFittingType.geometry` with `kind: "trap"` uses a circular `section`,
at least four local `path` control points and a positive `bendRadius`. It creates
a hollow rounded return passage for `pipe` family with `waste` or `condensate`
medium. For example, a diameter-40 section with a radius-60 path through
`[[0,0,200],[0,0,0],[200,0,0],[200,0,150],[400,0,150]]` describes a return with
a horizontal outlet. The generated `start`/`end` frames are its actual mates.
Placement must retain a centerline portion below both interfaces in world Z;
turning the return upside down fails validation. This checks the geometric
return, without calculating water-seal depth, siphoning or vent performance.

All ports on one route or generated fitting belong to the same service system.
A pipe cannot acquire cold-water identity at one end and hot-water identity at
the other. Use explicitly authored equipment interfaces where separate systems
meet; generic devices retain scoped, port-level membership.

Cable route types can add a typed `cable` specification. Its required
`designation` identifies authored stock; optional `construction` is `cable`,
`conductor`, `core` or `opticalFiber`. Optional `conductors` list function, count,
`areaMm2`, `materialSpec` and optional `insulationSpec`. Total nominal conductor
area cannot exceed the complete outside section. Individual conductor/core stock
has one scheduled conductor when that list is supplied. Optical fiber uses the
communications medium. Additional fields are `ratedVoltageV`,
`allowableCurrentA`, `maximumProtectionA`, `jacketSpec`, `signalCategory`,
`dataRateMbps` and `shielded`. Current/protection limits are authored inputs for
the installation; the engine does not derive ampacity or derating.

Resolved cable `conductorSchedule` entries retain those inputs and nominal
`stockLengthMm` equal to count times analytic route length. These internal stock
specifications do not create extra conductor or insulation meshes or material
quantities. The route's material and outside geometry represent the complete
physical stock. Model separate conductor routes when separate geometry is needed.

Conduit route types can add `conduit` with required `designation` and optional
`nominalSize`, `flexible` and `maximumFillFraction` (greater than zero and at most
one). Trade size is descriptive; actual outside dimensions and wall thickness
still control the solid. Fill limits are retained as authored specifications;
the stock specification alone does not associate contained cables or calculate
fill. Cable and conduit specifications are restricted to their respective route
families and remain in inspection, schedules and IFC properties.

### Service fittings

Cable-family fitting types can add `electrical` using the device rating fields.
These ratings participate in circuit voltage/supply/frequency checks and export
as native rated properties plus the complete authored specification. Other
fitting families do not accept electrical ratings on their passage geometry.

`serviceFitting` places a reusable `serviceFittingType` through `placement` and
an optional `storey`, nonnegative construction `clearance`, and named `portStates`.
The type supplies `family` (`pipe`, `duct`, `cable`, `conduit`), `material`,
`medium`, `connectionType`, `chordTolerance`, and optional `flow` (`forward` or
the default `bidirectional`). Hollow families require positive `wallThickness`;
solid cable fittings omit it. Sections use the same outside-dimension contract as
routes. Fitting recipes use type-local millimetre coordinates, transformed together
with their generated ports and construction masks by the instance placement.

The type's `geometry.kind` selects one of four recipes:

- `elbow` supplies `section`, exactly three local `path` points, positive
  `bendRadius`, and optional local `up`. A genuine tangent bend is required;
  straight connectors use straight routes. The generated ports are `start` and
  `end`. Radius, setback, self-intersection and approximation rules match routes.
- `branch` supplies a `trunk` path and a named `branches` registry. Each path
  supplies its own `section`, two or more local points, optional `bendRadius` and
  optional `up`. Paths can be straight or contain tangent bends. The trunk's
  endpoints become `start`/`end`; each branch's final endpoint becomes a port with
  that branch's key. Branch roots must fit fully into the trunk's outside section
  and, for hollow stock, its internal passage. External mating faces must remain
  outside other arms and the trunk. Names `start`, `end` and `trunk` are reserved.
  Tees, angled takeoffs, crosses and multiple arms use this same contract.
- `transition` supplies `startSection`, `endSection`, positive `length`, and
  optional local XY `offset` for the end section. It generates concentric or
  eccentric reducers and round/rectangular shape transitions. The faces remain
  parallel to local XY at Z=0 and Z=`length`; their ports are `start` and `end`.
  Sections preserve their X/Y orientation. Wall thickness reduces each endpoint's
  section dimensions; it is not a constant normal thickness on the inclined taper.
- `cap` supplies `section` and positive `depth`. A hollow cap requires depth
  greater than wall thickness and ends its bore one wall thickness before its
  closed end. It has one actual mating port, `start`, on local Z=0 facing negative
  Z. This recipe produces physical closure geometry independently of port states.

For example, this illustrative reusable tee has a 40 mm outside-diameter trunk
and a smaller side branch. Supply its referenced material before using it:

```json
{
  "kind": "serviceFittingType", "name": "Illustrative reducing tee",
  "family": "pipe", "material": "material.pipe", "wallThickness": 2,
  "medium": "water", "connectionType": "illustrativeMatingFace",
  "chordTolerance": 0.1, "flow": "forward",
  "geometry": {
    "kind": "branch",
    "trunk": {
      "section": {"kind": "circle", "diameter": 40},
      "path": [[0, 0, 0], [0, 0, 400]]
    },
    "branches": {
      "side": {
        "section": {"kind": "circle", "diameter": 20},
        "path": [[0, 0, 200], [200, 0, 200]]
      }
    }
  }
}
```

Every generated port carries the actual endpoint section, orientation, medium and
mating technology. A forward fitting has a sink at `start` and sources at its
other ports. All ports of a multiport fitting share an internal passage/group.
Type `portOverrides` can set `connectionType` and/or `flow` for a generated port,
for example `{"end": {"connectionType": "illustrativeCompression"}}` on an
adapter or a sink override on a mixing branch. Overrides cannot move a port or
change its section/medium; unknown port keys fail validation.
Declare external mates and explicit system/circuit membership as for routes and
devices. Distinct arms have distinct external ports; geometry does not create
connections to other components automatically.

To attach a fitting directly with `placement.origin.port`, author its starting
interface at local `[0, 0, 0]` facing negative Z. The upstream port supplies local
positive Z and the section orientation; instance rotation can adjust the pose.
Inspect rectangular mating frames after changes. Component host locators and
fitting port locators propagate subsequent equipment or route placements without
making semantic network connections into geometry dependencies.

Fittings retain `envelope`, optional `bore`, and `clearance` construction volumes.
Clearance expands outside sections without extending endpoint planes. Cavity
ownership displaces only actual fitting material; use owned `geometrySource`
penetrations to clear the internal passage or provide a larger host hole. Branch
unions count shared material and passages once. Inspection and schedules report
actual net material volume, generated ports, recipe geometry and construction
volume quantities. These recipes describe authored geometry and do not infer
product ratings, pressure loss, fabrication tolerances or approved pipe/duct sizes.

### Service interference and installation clearance

Add `coordinationChecks` to a `serviceRoute`, `serviceFitting`, `serviceDevice` or
`serviceInsulation` when it requires geometric interference review. The required
`interference` value is `error` or `warning`. It checks the service's actual final
material against other physical components after cavity composition and owned
cuts. Unchecked services do not produce these diagnostics automatically.

Routes and fittings can also check their authored `clearance` construction volume:

```json
{
  "interference": "error",
  "clearance": {
    "severity": "warning",
    "allow": [{"element": "framing.floor", "part": "joist.3"}]
  }
}
```

This is a `coordinationChecks` value. Its optional `clearance` object requires
`severity` and can list allowed physical components using `element` and optional
generated-member `part`. An allowed assembly includes all its surviving members.
Missing members and nonphysical allowances fail validation. Devices and insulation
support material interference checks; use `clearanceZone` for their authored
maintenance or access spaces.

The clearance probe contains the complete outside route/fitting envelope plus
its authored radial or section margin, including its bore. It does not infer a
regulatory clearance or add material. To reserve space outside an insulated run,
include the cover thickness in the route's clearance margin. Construction masks,
spaces, terrain, probes and service-system containers are not material obstacles.
Touching boundaries have no positive-volume interference.

Clearance checks recognize explicit installation relationships. A route/fitting's
own insulation, interface parts that name it or that insulation, and hardware
whose participants include either receive clearance exceptions. Authored `allow`
references supply any additional exceptions. These exceptions never suppress
material interference. For example, a correctly fabricated sleeve may occupy a
run's clearance space, but a sleeve wall intersecting the pipe still fails its
physical fit checks. An unrelated nearby sleeve receives no exception.

Owned cavities and cuts change the physical solids being checked. A bore cut
empties the passage; a cut using the `clearance` mask also removes host material
from the specified installation space. Cavity infill that remains in a requested
clearance volume is still an obstruction. Use actual cuts, ownership or an
explicit allowance according to the intended installation.

`service.interference` and `service.clearance-obstructed` identify the checked
service, the individual obstructing component/member and measured intersection
volume. For each checked service, a material collision is reported once per obstacle rather than also
as a clearance obstruction. Generated-member assemblies do not duplicate their
children's reports. The resolved `serviceCoordination` field records results and
clearance-exclusion reasons in scene metadata, schedules and IFC properties.
Warnings permit builds with their evidence retained; errors reject validation
and transactional edits. These checks evaluate geometry, not engineering capacity.

### Host-relative construction coordinates

Three-dimensional member endpoints, sweep/enclosure path points and detail
locations accept a `host` locator. It places the point in a coordinate frame on
another element, so rebuilding after a host edit updates the attached geometry.
For example, this point is 450 mm above a wall's base, at station 1000 mm along
its path, and 25 mm out from its interior finish:

```json
{
  "host": {
    "kind": "wall",
    "element": "wall.south",
    "station": 1000,
    "height": 450,
    "surface": "interior",
    "offset": [0, 0, 25]
  }
}
```

The host coordinate modes are:

| Kind | Host | Coordinates and surfaces |
| --- | --- | --- |
| `wall` | Wall | `station` along the path and `height` above the base; `exterior`, `interior`, `layerExterior`, `layerInterior` or `layerCenter` |
| `surface` | Slab, roof or footing | Model X/Y `point`; `top`, `bottom`, `layerTop`, `layerBottom` or `layerCenter` |
| `member` | Individual member | `station` along its axis; `axis` (default), `positiveX`, `negativeX`, `positiveY`, `negativeY`, `start` or `end` |
| `component` | Explicitly placed component | Its resolved local origin and XYZ frame, with optional offsets/rotations |
| `route` | Service route or fitting | Analytic centerline `station` in millimetres; branched fittings require a `branch` key |

Component frames support hardware, fastener groups, masonry parts, reinforcing
meshes, accessories, envelope parts, service devices, circular members, authored member assemblies,
clearance zones and barrier checks. They follow the component's complete pose;
they do not imply a physical surface. Physical accessories still require a
physical mounting host. Other host kinds expose the specific surface controls
listed above.

Route frames point local Z from the path's start toward its end and preserve the
transported cross-section X/Y orientation. Stations include the exact circular
bend lengths and do not depend on `chordTolerance`. For a branched fitting,
select `branch: "trunk"` or a named branch; station zero is that path's own start.
Transitions expose the line between their section centers, including eccentric
offsets; caps expose their depth axis. These are axis locators, not skin mounts.

For a support that follows a run, use a fabricated `hardware` element with
`role: "hanger"` on its type, explicit connection `participants`, and a placement
such as `{"origin":{"host":{"kind":"route","element":"pipe.supply","station":600}}}`.
Add local offsets and rotations to place the authored clamp, strap or bracket
around the axis. Dimensions, fastening geometry and participant intent remain
authored; stationing does not size or space supports. Set the element's
`discipline: "services"` to include it in the services review view. Its physical
stock/cuts, cavity ownership and actual material quantities use the ordinary
hardware contracts. A route edit moves the support; a shortened route that no
longer reaches its station fails validation.

For an insulated run, size the support's passage around the finished covering.
Include the insulation as a connection participant when the support bears on it.
The route, covering and hardware retain separate selectable solids and material
quantities through a host move. Changing insulation thickness does not resize
the authored support geometry.

Layer surfaces require a zero-based `layer` index. Wall layers run exterior to
interior; slab and roof layers run top to bottom. Explicit footings expose their
body as layer 0; aggregate footings have no selectable layers. Member side names
refer to the host's rolled section coordinates. A side
mount uses the section's X or Y extreme at the other coordinate's zero; profiles
without a physical surface at that point reject the placement. Start/end mounts
require station zero/full member length. Framing arrays are not individual member
hosts.

A roof's optional `face` selects a face ID from its resolved `faceIds`. Supply it
when the point lies on a crease or multiple sloped layer surfaces cover its X/Y.
Each roof layer's location follows its actual normal thickness. The X/Y point is
on the selected layer surface, whose footprint can shift with roof slope/depth.

`offset` is a local `[x, y, z]` displacement in millimetres. For wall faces local Y
is up and local Z points out of the selected face; local X completes a right-handed
frame, following the wall path on interior faces and reversing it on exterior
faces. `layerCenter` uses the exterior-facing orientation. For horizontal and roof
surfaces local Z is the outward normal and local X is model east projected into
the plane. Member axis frames retain the section roll and point local Z along the
member; side frames point local Y along the member and local Z out of its side.

Optional `rotation: [x, y, z]` rotates the frame in degrees about its successive
local X, Y and Z axes, after the offset is positioned in the unrotated host frame.
Point locators use the resulting origin; rotating a point alone does not rotate a
member's section. Use member `roll` for section orientation. Frame orientation is
also available to geometry consumers through the shared placement resolver.

The initial mounting point must lie on the actual host surface, outside openings
and footprint holes, or at a valid member-axis station. Layer-center points are
checked against that layer's exterior/top face. Offsets can intentionally project
from or recess into a host; they do not cut it or establish physical clearance.
Host coordinates preserve placement intent in inspection, schedules and IFC
properties. Add an explicit `attaches` or `supports` relationship when the design
also requires durable connection or support intent.

### Penetrations, recesses and member cuts

A `penetration` removes a real solid from one explicit `host`: a wall, slab,
roof, footing, straight or curved member, framing assembly, hardware item,
reinforcement item, masonry part or screen panel. Its section is a centered
rectangle, circle or polygon profile using the same `section` contract as members.
The cutter extrudes `depth` millimetres along its placement's local positive Z.
For example, a 100 mm diameter hole through a 200 mm floor is:

```json
{
  "kind": "penetration", "name": "Floor service sleeve opening",
  "host": "slab.ground", "purpose": "service",
  "placement": {
    "origin": {"host": {
      "kind": "surface", "element": "slab.ground",
      "surface": "top", "point": [500, 500]
    }},
    "rotation": [180, 0, 0]
  },
  "section": {"kind": "circle", "diameter": 100},
  "depth": 200
}
```

`placement.origin` accepts any 3D point locator. A host locator supplies its
oriented frame; a literal/anchor/elevation locator starts with model XYZ axes.
`placement.rotation` applies intrinsic XYZ rotations in degrees. The example
turns the floor's outward normal inward before extruding. A shallower depth
creates a recess. Rectangular/profile cutters and arbitrary placement rotations
also support member notches, bearing seats and angled end treatments.

`purpose` is `service`, `opening`, `recess`, `notch`, `bearingSeat` or `other`.
Optional `layers: [0, 2]` restricts a cut to those zero-based wall/slab/roof layers;
omitting it cuts all intersected host parts. Explicit footings also accept layer 0.
Members, aggregate footings and screens have no layer selection. Optional `owner` references the canonical component responsible
for the cut. Model each penetrated host with its own penetration element.

Cuts retain the host's canonical identity, material identities and mesh roles.
Inspection records the host's penetration IDs and net volume; the penetration
records the actual removed volume. Material schedules count the remaining solids,
and a separate penetration schedule lists cuts without counting voids as material.
IFC includes each cut as an `IfcOpeningElement` and a native void relationship.
Its body contains only the volume removed from the selected layers. Browser and
drawing outputs show the resulting hole; the cutter itself is not a visible solid.

Mounting frames resolve against the host's authored geometry before these cuts,
so a sleeve or other part can share its opening's mounting coordinates. Existing
door/window openings still participate in wall-surface mount validation. Cutting
does not infer rerouting, reinforcement, support hardware or acceptable notch
sizes. These remain explicitly authored construction decisions.

A cut that removes no material, selects an absent layer, removes its entire host,
or overlaps another cut's ownership fails validation. Cuts through disjoint layers
can share a path. Solid operations require closed, consistently wound source
geometry and use double precision in canonical millimetres. Host coordinate frames
and design datums remain independent of the order in which cuts are authored.

Add named `limits` to a penetration to check supplied hole or notch dimensions
and directional material margins. Each limit requires a `host` locator for the
same host as the cut, plus at least one measurement. It can also retain a
`reference` describing the supplied requirement and `severity: "error"` or
`"warning"`; the default severity is error. For example:

```json
{
  "hole": {
    "host": {
      "kind": "member", "element": "member.stud",
      "surface": "axis", "station": 500
    },
    "maximumExtent": {"y": 40, "z": 40},
    "maximumExtentFraction": {"y": 0.2},
    "minimumEdgeDistance": {"positiveY": 30, "negativeY": 30},
    "reference": "Authored project requirement"
  }
}
```

This is a `limits` value for a transverse hole in `member.stud`. Dimensions and
directions use the selected host frame, including its roll, slope, offset and
rotation. For a member-axis frame, X and Y are section axes and Z follows the
member. A scoped generated member uses `part`; a layer surface uses `layer`.
Roof checks require an explicit `face`. A check must select material that the
penetration actually removes. A nearby member or uncut layer cannot supply its
measurement region.

`maximumExtent` gives positive millimetre limits on any local `x`, `y` or `z`
dimension of the actual removed solid. An oversized cutter is clipped to the
affected stock before measurement. `maximumExtentFraction` gives corresponding
positive ratios up to 1: removed extent divided by the selected host material's
extent before penetration cuts, after cavity composition. These are projected
extents in the specified frame, not inferred nominal member sizes or a calculation
of residual structural capacity. Select the relevant member, face or layer when
the whole host would be too broad.

`minimumEdgeDistance` gives positive millimetre margins in any of `positiveX`,
`negativeX`, `positiveY`, `negativeY`, `positiveZ` or `negativeZ`. Each check sweeps
the removed volume continuously by that distance along the specified direction
and verifies that the swept volume stays within host material. The reference
material restores this cut while retaining every other cut, cavity displacement,
hole, bevel and notch. This checks directional material reserves against actual
boundaries, including between adjacent holes; it does not measure a Euclidean
nearest-edge distance or combine multiple directions into a radial clearance.
Do not require a positive margin in a through-hole's open direction.

`limitResults` records the resolved frame, selected host identity, measured cut
and host extents, supplied limits and per-check status. Failed margins include
the volume extending outside reference material. `penetration.limit-violated`
diagnostics point to each failed source limit; error severity rejects a build or
transaction, while warnings retain their evidence in scene data, schedules and
IFC properties. Both local-extrusion and service-derived penetrations use these
checks. Limits are authored inputs, not engineering approval.

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
