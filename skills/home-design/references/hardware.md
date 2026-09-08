# Hardware, reinforcement and masonry

Read [identity and composition](composition.md) for shared authoring rules. Read [layers and cuts](layers-cuts.md) for host coordinates and displaced material. For route-mounted hangers, also read [routes](routes.md).

- [Fabricated hardware and fastener groups](#fabricated-hardware-and-fastener-groups)
- [Reinforcement, foundation bodies and masonry](#reinforcement-foundation-bodies-and-masonry)

## Fabricated hardware and fastener groups

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

Detailed instances remain bodies of one canonical group, rather than separate IFC
products. Named instances survive in GLB mesh roles such as `fastener:left.back`;
indexed scene-node names can change when instances are inserted. Use the group ID
and named role when comparing individual fasteners across edits.

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


## Reinforcement, foundation bodies and masonry

Set `footingType.representation` to `explicit` when individually modeled parts
replace concrete inside a foundation. Its body becomes ownership region `layer: 0`;
parts use `occupies.regions: [{"host": "footing.pad", "layer": "layer.legacy.0"}]`. The original
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
