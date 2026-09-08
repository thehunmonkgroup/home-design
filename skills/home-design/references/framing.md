# Framing and structural assemblies

Read [identity and composition](composition.md) for shared authoring rules. Read [layers and cuts](layers-cuts.md) for selected layers, cavities, host coordinates and scoped cuts. Read [hardware](hardware.md) for physical connectors.

- [Members, framing and footings](#members-framing-and-footings)
- [Wall framing layouts](#wall-framing-layouts)
- [Floor, deck and roof-face framing layouts](#floor-deck-and-roof-face-framing-layouts)
- [Authored member assemblies and end cuts](#authored-member-assemblies-and-end-cuts)
- [Curved structural members](#curved-structural-members)

## Members, framing and footings

`memberType` defines `material` and a `section`: a centered rectangle (`width`, `depth`), circle (`diameter`), or local polygon profile with optional holes. A `member` supplies a two-point 3D `axis`, `role` and optional axial `roll`. Roles include beam, column, joist, rafter, stud, decking, stringer and brace. Sections remain perpendicular to their axes. Beams and columns export to their native IFC classes.

`framing` repeats the same member along a unit `distribution` vector with `spacing` and `count`. Its optional `omit` array contains zero-based repetition indices. Omitted members preserve the identities of remaining repetitions. IFC contains a framing assembly with individually typed member children. Use `wallFraming` for a host-driven wall layout; use separate arrays for other explicitly authored repetition patterns.

3D locators accept `{"point": [x,y,z]}`, `{"anchor": "anchor.id"}`, or `{"point": [x,y], "elevation": DATUM}`. A sampled datum contains `kind`, `element`, `surface`, `point`, and `offset`; a level datum uses `kind: "level"`, `level` and `offset`.

`footingType` defines `depth` and `material`. A `footing` has a top `datum` and `shape: "pad" | "strip" | "pier"`. Pads and strips use `footprint`; a circular pier can instead use `center` and `diameter`. Use separate footing segments with different datums for stepped foundations, and constrain each masonry wall segment to its corresponding footing. Add `supports` to preserve the load-bearing relationships.

`load` records a target, footprint, total `forceN`, load category and `foundationRequired` (default true). Model spa loads on their actual supported footprint. Validation checks footprint containment where the target has a footprint and follows every declared support branch to a footing/foundation slab. Missing branches and cycles fail. This is connection completeness, not structural load distribution or sizing. Optional `supports.bearingPoint` is checked against participant bounds; `capacityN` records an engineer's input without inferring load allocation.


## Wall framing layouts

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
  "type": "type.wallFraming", "host": "wall.south", "layer": "cavity",
  "segment": "south.run",
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

For a polyline wall, provide a separate framing element for each named
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
as `segment/south.run/opening/opening.window/header`, `segment/south.run/end/start/0`,
and `segment/south.run/grid/0/full` identify
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
  "part": "segment/south.run/opening/opening.window/header", "station": 200,
  "surface": "positiveX"}}
```

The mounting point follows that member through host/opening edits. An omitted or
missing key fails resolution. Member recipes and overrides express authored
construction decisions; they do not calculate header capacities or approve corner
and opening details.


## Floor, deck and roof-face framing layouts

`planarFraming` fits individual joists, rafters or decking members to one explicit
slab layer or roof-face layer. Its reusable `planarFramingType` requires
`memberType` and `spacing`, and optionally supplies `rimType` and `blockingType`.
All referenced member types have rectangular sections: `width` is transverse to
the member and `depth` is normal to the host surface. Depth cannot exceed the
selected layer thickness, and spacing cannot be less than the main member width.

```json
{
  "kind": "planarFraming", "name": "Deck framing",
  "type": "type.deckFraming", "host": "slab.deck", "layer": "cavity",
  "originBoundary": "south",
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
the starting vertex of `originBoundary`, offset normally to the layer center. Grid stations are
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

Inspect generated keys before adding `memberOverrides`. Keys derive
from named bounding interfaces; models can retain keys such as
`grid/3/0` through explicit identity maps. See [scoped identities](identities.md).
Overrides support `omit`, same-section `memberType` substitutions and `endCuts`.
Grid indices survive dimensional edits; new holes can replace a board with
distinct split pieces. Stale override keys fail
validation. Generated members support scoped member host locators, owned
penetrations, individual IFC children and the `generatedMembers` schedule just
like wall framing. Quantities measure the fitted solids, including angled ends;
stock lengths retain the bounding length along each member's declared axis.


## Authored member assemblies and end cuts

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


## Curved structural members

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
