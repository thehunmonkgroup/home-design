# Layers, ownership and cuts

Read [identity and composition](composition.md) for shared authoring rules. Use this reference whenever placement, material ownership or host cuts change. For a service passage, also read [routes](routes.md); for sleeves/seals, read [envelope interfaces](envelope.md).

- [Layers and specifications](#layers-and-specifications)
- [Explicit cavities and physical parts](#explicit-cavities-and-physical-parts)
- [Host-relative construction coordinates](#host-relative-construction-coordinates)
- [Penetrations, recesses and member cuts](#penetrations-recesses-and-member-cuts)

## Layers and specifications

Walls, slabs and roofs resolve each layer separately, displaying exterior/interior or top/bottom finishes and exposing material layers in section cuts and IFC. Each layer contributes its thickness exactly once.

Use concurrent `components` for framing and insulation occupying the same cavity:

```json
{
  "id": "cavity", "name": "Insulated framing cavity", "thickness": 140, "function": "structure",
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


## Explicit cavities and physical parts

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
    "regions": [{"host": "wall.south", "layer": "cavity"}],
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

Regions are identified by host and layer ID. Duplicate or overlapping
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


## Host-relative construction coordinates

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

Surface host `point` fields accept a literal XY vector or a
point/anchor locator. Use the same assembly origin as the slab, footing or roof
footprint when a mounting point should translate with that assembly.

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

Layer surfaces require a named `layer` ID. Wall layers run exterior to
interior; slab and roof layers run top to bottom. Explicit footings expose their
body as `layer.legacy.0`; aggregate footings have no selectable layers. Read
[scoped identities](identities.md) before inserting or reordering layers. Member side names
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


## Penetrations, recesses and member cuts

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
Optional `layers: ["finish", "cavity"]` restricts a cut to those named wall/slab/roof layers;
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
