# Service interfaces and networks

Read [identity and composition](composition.md) for shared authoring rules. Read this before editing a connected service network. Continue to [routes](routes.md) and the relevant [electrical](electrical.md), [plumbing](plumbing.md) or [mechanical](mechanical.md) reference.

- [Service devices, systems and circuits](#service-devices-systems-and-circuits)
- [Service interference and installation clearance](#service-interference-and-installation-clearance)

## Service devices, systems and circuits

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


## Service interference and installation clearance

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
