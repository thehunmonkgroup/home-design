# Mechanical services

Read [identity and composition](composition.md) for shared authoring rules. Read [service interfaces](services.md) for ports and network membership. Read [layers and cuts](layers-cuts.md) for cavity ownership and passages. Read [routes](routes.md) for paths, fittings, insulation and their geometry.

- [Duct stock and conditions](#duct-stock-and-conditions)
- [Equipment and separate interfaces](#equipment-and-separate-interfaces)

## Duct stock and conditions

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


## Equipment and separate interfaces

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
