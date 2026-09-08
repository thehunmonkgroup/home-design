# Electrical and communications

Use [identity and composition](composition.md) for shared authoring rules.
Load [service interfaces](services.md) when changing ports/system membership,
[routes](routes.md) for cable/conduit geometry, and the relevant sections of
[layers and cuts](layers-cuts.md) or [framing](framing.md) when changing a recess
or its surrounding construction.

For an additional outlet on an existing branch, start with the focused
[branch extension workflow](electrical-edits.md). It identifies the coordinated
objects and routes to field details only when needed.

- [Electrical and communications devices](#electrical-and-communications-devices)
- [Circuit schedules](#circuit-schedules)
- [Cable and conduit stock](#cable-and-conduit-stock)

## Electrical and communications devices

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


## Circuit schedules

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


## Cable and conduit stock

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
