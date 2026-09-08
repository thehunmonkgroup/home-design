# Routes, fittings and insulation

Read [identity and composition](composition.md) for shared authoring rules. Read [service interfaces](services.md) for ports and network membership. Read [layers and cuts](layers-cuts.md) for cavity ownership and passages.

- [Service routes and empty passages](#service-routes-and-empty-passages)
- [Service insulation](#service-insulation)
- [Service fittings](#service-fittings)

## Service routes and empty passages

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
  "layers": ["cavity"],
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

When a run passes through a stud, plate or other cavity occupant, omit `occupies`
on that run and use an `envelope` penetration on each intersected wall/floor/roof
and framing host. Cavity ownership is checked before penetrations: declaring the
run and uncut timber as occupants would claim the same volume and fail. The
explicit cuts remove both infill and timber from the passage while the service
retains its own material quantity. Enable `coordinationChecks` to verify the
resulting physical clearances. Add cuts only to hosts actually intersected by
the run; empty cuts fail validation.


## Service insulation

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

## Service fittings

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
