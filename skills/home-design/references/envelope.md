# Hosted accessories and envelope coordination

Read [identity and composition](composition.md) for shared authoring rules. Read [layers and cuts](layers-cuts.md) for mounting and recesses. Service sleeves and seals also require [service interfaces](services.md) and [route masks](routes.md).

- [Hosted accessories and envelope interfaces](#hosted-accessories-and-envelope-interfaces)
- [Access spaces and barrier continuity](#access-spaces-and-barrier-continuity)

## Hosted accessories and envelope interfaces

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


## Access spaces and barrier continuity

Failed access diagnostics include the obstructing component IDs and intersected
volumes in `details.obstructions`. Barrier failures include gap volume, coverage,
connected regions and missing participants. Use those measurements to locate the
construction needing correction before editing the probe or its allowances.

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
`{"element": "envelope.part"}` or `{"element": "wall.host", "layer": "cavity"}`.
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
