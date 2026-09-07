# Plumbing and gravity services

Read [identity and composition](composition.md) for shared authoring rules. Read [service interfaces](services.md) for ports and network membership. Read [layers and cuts](layers-cuts.md) for cavity ownership and passages. Read [routes](routes.md) for paths, fittings, insulation and their geometry.

- [Pipe stock and operating conditions](#pipe-stock-and-operating-conditions)
- [Plumbing equipment and traps](#plumbing-equipment-and-traps)

## Pipe stock and operating conditions

Pipe route and fitting types can add `pipe` with required `designation` and optional
`nominalSize`, `construction` (`rigid` or `flexible`), `jointing`, `lining`,
`pressureRatingPa`, `minimumTemperatureC`, `maximumTemperatureC`, `roughnessMm`
and `potableWater`. Trade size does not override outside dimensions or wall
thickness. The temperature range must be ordered. Suitability and material
descriptions remain authored specifications.

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


## Plumbing equipment and traps

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
