# IFC representation contract

The IFC contains the same geometry as the browser preview, represented as tessellated bodies. It also includes wall axes, IFC element/type classes, materials, containment, openings/fills, wall path connections, space boundaries, general connections, and aggregation.

Construction exports include native beams, columns, members, footings, stair flights,
railings and terrain. Framing groups expand into individually identified members.
Screens and miscellaneous profile/detail components preserve canonical kind/role
even where IFC uses a proxy. Terrain is an open surface; physical component layers
are separate closed bodies with material-specific styles.

Physical `Body` representations use closed IFC4 polygonal face sets. They retain
the final resolved cuts, hollow passages, curved-member approximation and separate
material bodies. Lengths, profiles, source placements and specifications remain
properties alongside native classes, types and relationships; these properties
do not create an editable extrusion or Boolean feature history in a CAD importer.
The IFC geometry-kernel regression checks compare converted material volumes and
world-space extents with the resolved model, including trimmed and rotated stock.
Before writing a cable face set with coincident vertices, the adapter
regularizes its surface folds and verifies each connected shell's volume.
This preserves closed cable bodies through native import at compound bends;
independent shells retain their topology. Canonical model geometry and quantities
remain the reference for the export comparison.

Native `IfcDoor` and `IfcWindow` `OverallWidth`/`OverallHeight` retain their hosted
rough-opening dimensions in project millimetres. Nominal stock, rough-opening
clearance and estimated clear passage remain separate resolved properties. This
follows the opening-size definitions in the IFC4
[door](https://standards.buildingsmart.org/IFC/RELEASE/IFC4/FINAL/HTML/schema/ifcsharedbldgelements/lexical/ifcdoor.htm)
and [window](https://standards.buildingsmart.org/IFC/RELEASE/IFC4/FINAL/HTML/schema/ifcsharedbldgelements/lexical/ifcwindow.htm)
contracts; a swung leaf's world bounding box is not used as its opening size.

Host-relative construction points retain their source coordinates in
`Pset_HomeDesignData.hostPlacements`. Penetrations export as `IfcOpeningElement`
objects with native void relationships to their explicit hosts. Their bodies
contain only the actual removed volume, including any selected-layer restriction.
Authored penetration limits retain their host frames, measured extents and
directional material-margin results in `Pset_HomeDesignData.limitResults`, the
penetration schedule and scene metadata. Warning-level violations remain in
`diagnostics.json`; error-level violations prevent the build. These checks do not
add physical products or assert engineering approval.
Recess, notch and bearing-seat purposes use the IFC recess classification. The
host's exported body already contains the cut, and material schedules measure its
remaining solids. Cut volumes are nonphysical and are excluded from browser
geometry, material quantities, drawings and shading geometry.

Explicit cavity layers export their remaining infill geometry separately from the
physical parts occupying them. Native element connections identify cavity owners;
host `cavities` and part `cavityContributions` properties preserve the layer and
volume balance. The `cavities` schedule reports infill, occupied and void volumes
after cuts. An explicit layer without an infill material has no rendered infill.

Wall framing exports a typed `IfcElementAssembly` with separately typed member
children; headers use `IfcBeam` with `LINTEL`. Joists use `IfcBeam` with `JOIST`;
studs and plates use `IfcMember` with `STUD` and `PLATE`. Child identities derive from the canonical
assembly ID and semantic member key. Each child retains its construction role,
section frame, axis, cut profile, lengths and final net volume. The
`generatedMembers` schedule exposes the same records after cavity composition
and penetration cuts. The browser groups their meshes under the framing element.

Planar layouts and authored member assemblies use the same individually typed
child contract. Authored shared-node joints export `IfcRelConnectsElements` with
`IfcConnectionPointGeometry`; declared trimming interfaces export element
connections. Connections to members wholly removed by cuts are omitted.
Circular structural members use the same native role classification as straight
stock: curved beams use `IfcBeam`, while rafters and braces use `IfcMember`.
Their properties retain radius, sweep, tessellation tolerance and analytic/mesh quantities.

Structural occurrences reuse matching role-specific IFC stock types, retaining
the canonical stock ID in `Pset_HomeDesignType.canonicalTypeId`. Native types carry
the effective predefined role; user-defined roles retain the authored label.
Only variants used by exported members are created. Canonical product IDs and
source-derived member identities remain independent of the native class.
Typed wall and planar framing also use matching assembly-role variants, retaining
`wallSystem`, `floorSystem` or `roofSystem` through type assignment. Authored trusses
use the native `TRUSS` assembly classification.

Fabricated hardware exports as typed `IfcDiscreteAccessory`; fastener groups use
`IfcMechanicalFastener` and `IfcMechanicalFastenerType`. Native predefined types
identify shoes, brackets, anchor plates and specific fastener families. Other
hardware roles retain their authored name as a user-defined type. Multi-participant
connections use `IfcRelConnectsWithRealizingElements`, naming the hardware or
fastener group that joins the participants. Scoped participants reference their
individual generated IFC members.
Custom `Qto_HomeDesignHardware` and `Qto_HomeDesignFastener` sets retain modeled
net volumes and authored fastener counts without claiming an IFC4 standard
quantity template for those fields.

Route-mounted hangers use the same native accessory and realizing-connection
contracts. Their `hostPlacements` retain the analytic station and selected fitting
branch, while the exported body follows the resolved tangent frame. These
supports contribute their own physical material once and do not duplicate route
stock. Explicit service review discipline is retained in the manifest.

IFC project units are millimetres for lengths, square metres for native areas and
cubic metres for native volumes. Geometry, placements, diameters and length
quantities retain millimetres; native section areas and volume quantities convert
from canonical mm²/mm³ to the declared units. Unit-explicit JSON properties such
as `netVolumeMm3` retain their canonical values.
Standard service measures use pascals for pressure, kelvin for absolute
temperature and cubic metres per second for volumetric flow. The flow unit uses
metres and seconds independently of the millimetre geometry unit.

Applicable IFC4 standard quantity sets complement the custom construction and
service data. Members retain nominal uncut `Length` and authored
`CrossSectionArea`, while `NetVolume` measures the final stock after cuts. Walls,
slabs, footings and plates also receive standard net volumes. Pipe and duct
segments receive centerline length, gross cross-section area including their
passage, and net cross-section area of stock; cable and carrier segments receive
length and material cross-section area. Reinforcing bars receive count and nominal
centerline length. Analytic section areas remain independent of tessellation.
Only quantities defined by the applicable IFC4 template are emitted. Unavailable
weights, capacities and other quantities are not inferred, and custom net-volume
sets remain available for families whose standard templates do not define volume.

Hardware has native net-volume quantities. Fastener groups also have authored
`Count` and surviving `ModeledCount` quantities. Scheduled groups have no body;
their volume derives from count times the fabricated unit shape and appears once
in IFC quantities and material schedules. Detailed groups have a body for each
placed instance and use the final mesh volumes. The manifest retains either group
for inspection; only detailed groups add fastener meshes to the browser scene.
`Pset_MechanicalFastenerCommon` also retains the authored nominal diameter and
length using native length measures in millimetres.

Reinforcing bars and ties export `IfcReinforcingBar` with native diameter,
nominal section area, analytic uncut bar length, steel grade and surface
specification. Ties use the native `LIGATURE` predefined type. Reinforcement meshes
use `IfcReinforcingMesh` with native wire diameters, spacing and nominal centerline
extents. Both retain reusable native types. Masonry units, grout and mortar use
typed `IfcBuildingElementPart` entities with their authored role. Native quantity
sets report final net volume and applicable nominal bar length or wire count.
Explicit foundation ownership connections retain body layer 0 and the reconciled
concrete/steel/grout volumes in the same cavity schedules as walls and slabs.

Hosted accessories export typed `IfcBuildingElementPart` objects; envelope
interfaces use typed `IfcCovering`, with native `MEMBRANE` classification for
membranes and `SLEEVING` for sleeves. Protective plates use typed `IfcPlate`;
seals and other shapes retain authored user-defined roles. Their final solids
have native net-volume quantities, and `IfcRelConnectsElements` identifies the
mounting host, including an individual generated member when selected. Source
mounting frames, projection, surviving extents and specifications remain in
properties. These generic accessory roles describe authored built-in parts;
they do not supply connected electrical or mechanical equipment semantics.

Parts with a service `interface` also export native
`IfcRelConnectsWithRealizingElements`: each listed service connects to the
construction host through the sleeve, plate or seal. Scoped hosts identify the
individual surviving member. These connections preserve installation intent
without adding service ports or asserting fire, acoustic or weather performance.

Clearance zones and barrier probes export translucent `IfcVirtualElement`
geometry without physical material quantities. `IfcRelAssignsToProduct` associates
each zone with its owner and each probe with its participant products. Layer
selections and geometric check results remain in `Pset_HomeDesignData`. These
virtual shapes are retained for coordination and do not count as construction
material or shade the model.

Generic service devices export typed `IfcDistributionElement` products. Each
port exports as `IfcDistributionPort` nested under its device with native flow,
port/system classification and an oriented model-space placement. Port property
sets retain canonical scoped IDs, mating dimensions/technology, termination
state and membership. `connectsPorts` produces a native `IfcRelConnectsPorts`
with the canonical relationship ID; source/sink order follows the authored flow.
Internal device groups remain in properties and do not create additional
external port connections.

Service systems use `IfcDistributionSystem`; circuits use
`IfcDistributionCircuit`. Native group assignments retain device membership and
parent-system/circuit grouping. A port is assigned to its circuit when present,
otherwise to its system. The parent system still groups its devices and circuits.
Neither system nor circuit is a physical spatial product or material volume.
Scheduled circuits retain checked rows in `Pset_HomeDesignCircuitSchedule` and
receive a native `IfcRelAssignsToProduct` association with their source panel.
The schedule's scoped panel/protection/load references remain available alongside
the ordinary nested ports and system/circuit assignments.
Freestanding devices have native net-volume quantities; mounted devices share
the mounting/quantity contract used by hosted accessories.

Electrical device roles export concrete IFC outlets, switching devices, junction
boxes, distribution boards, protective devices, light fixtures, sensors,
communications appliances and cable fittings, each with a matching native type.
An unspecified product technology retains `USERDEFINED` and its authored role;
for example, a generic fuse does not imply a fuse-disconnector assembly. Earthing
terminations use cable fitting `EXIT` and grounding bars use `JUNCTION`.
Rated voltage, rated current and pole count use `Pset_ElectricalDeviceCommon` with
native measure types and declared volt/ampere units. All authored ratings remain
in `Pset_HomeDesignElectrical` and the resolved device data. Containment entry
ports use `CABLECARRIER`, including on devices; conductive and signal interfaces
use `CABLE`.

Service routes export as typed `IfcPipeSegment`, `IfcDuctSegment`,
`IfcCableSegment` or `IfcCableCarrierSegment` products according to their family.
Native type classifications distinguish rigid/flexible pipe/duct segments, cables and
conduits. Routes retain the same nested ports, systems and connection contracts
as devices, with native analytic centerline-length and net material-volume
quantities. Tessellated bodies contain only the physical route material, including
the actual hollow passage. Construction envelope/bore/clearance masks remain in
resolved JSON and do not create extra IFC or GLB products. A penetration derived
from a mask exports its actually removed host volume as a native opening.

Authored service coordination checks preserve their measured conflicts and
clearance-exclusion reasons in `Pset_HomeDesignData.serviceCoordination`, scene
metadata and the component's schedule row. Warning-level conflicts also appear
in `diagnostics.json`; error-level conflicts prevent the build. These results
identify the actual obstacle or scoped member without creating diagnostic solids,
additional IFC products or material quantities.

Typed cable/conduit stock specifications export in `Pset_HomeDesignCable` and
`Pset_HomeDesignConduit`. Cable construction distinguishes native `CABLESEGMENT`,
`CONDUCTORSEGMENT` and `CORESEGMENT`; optical fiber retains `USERDEFINED` with
role `opticalFiber`. Nominal internal conductor schedules remain specifications,
without duplicate physical products or material quantities.
Duct stock retains `Pset_HomeDesignDuct` on reusable types and occurrences;
signed operating pressure, temperature and airflow inputs use
`Pset_HomeDesignDuctConditions`. Stock construction selects `RIGIDSEGMENT` or
`FLEXIBLESEGMENT` for duct segments. Fittings retain their bend/junction/transition
classification. These inputs add no material or inferred airflow performance.

Pipe stock retains `Pset_HomeDesignPipe`, with operating inputs in
`Pset_HomeDesignPipeConditions` and directional geometric checks in
`Pset_HomeDesignFallCheck`. Rigid and flexible stock use native `RIGIDSEGMENT`
and `FLEXIBLESEGMENT` classifications. Unknown rating checks remain in resolved
product data; exported flow specifications do not imply hydraulic calculations.

Applicable standard service common sets retain the canonical type reference.
Pipe segments export actual outer and inner diameters; trade-size labels do not
become nominal numeric dimensions. Pipe and duct segments and fittings export authored
allowable pressure and temperature ranges as native bounded properties. Suction
ratings become negative gauge-pressure bounds, and Celsius limits convert to
kelvin. Missing bounds stay absent. Operating conditions remain separate from
stock limits and jurisdictional classifications.

Boilers and tanks export authored storage capacities in cubic metres. Fans and
dampers export authored nominal airflow in cubic metres per second. Unsupported
or differently defined standard fields remain absent: the exporter preserves
the supplemental specifications without inferring agency ratings, nominal duct
dimensions or sensible/latent capacity splits.

Mechanical devices retain `Pset_HomeDesignMechanical` and native typed products:
`IfcDamper`, `IfcAirTerminal`, `IfcFan`, `IfcAirToAirHeatRecovery`, `IfcFilter`,
`IfcCoil` and `IfcUnitaryEquipment`. Declared technology selects the corresponding
IFC predefined type; unspecified technology retains `USERDEFINED` with the role.
Air handlers, air conditioners, dehumidifiers and refrigerant units use the
appropriate unitary-equipment classification. Equipment with several service
media retains separate native distribution ports, system membership and authored
internal passage groups. Its physical quantities come from the fabricated body.

Plumbing devices retain `Pset_HomeDesignPlumbing` on products and reusable types.
Valves use `IfcValve` with an authored function when supplied. Manifolds, fixture
connections and cleanouts use `IfcPipeFitting` with junction, connector and
user-defined classifications respectively. Water heaters use `IfcBoiler/WATER`,
pumps use `IfcPump`, storage tanks use `IfcTank/STORAGE`, and water meters use
`IfcFlowMeter/WATERMETER`. Powered equipment also retains its electrical ratings.
Each interface keeps its own native port/system classification. Trap passages
use `IfcPipeFitting/USERDEFINED` with role `trap`, physical hollow geometry and
generated ports; no calculated hydraulic seal is implied.

Physical service insulation exports as independently typed `IfcCovering` with
native `INSULATION` classification. A native element connection identifies the
service host. Its final net-volume quantity uses the same material solid as the
GLB and schedules, including cavity clipping and owned insulation cuts. The
covering creates no extra distribution ports or system flow paths. Construction
envelopes remain nonmaterial masks; an owned cut using one exports the actual
removed host material as an opening.

Generated fittings export as `IfcPipeFitting`, `IfcDuctFitting`, `IfcCableFitting`
or `IfcCableCarrierFitting`, with concrete reusable types and family-specific
bend, junction, transition or closure classifications. Unsupported native enum
labels use `USERDEFINED` with the authored recipe role. Native cable-carrier
ports distinguish conduit interfaces from cable interfaces. Fittings have nested
oriented ports, native system/connection relationships and net-volume quantities.
Physical caps contain closed-end material and only their actual mating port;
their native classification is `USERDEFINED` with role `cap`. Cable-carrier
`CROSS` fittings have two branches starting at the same trunk point. Staggered
takeoffs retain `USERDEFINED` with role `branch`.

Reusable layered types receive `IfcMaterialLayerSet`. Concurrent framing/insulation
constituents are preserved as JSON in `Pset_HomeDesignComposition`, sharing one
physical layer thickness. `Pset_HomeDesignData` retains resolved product performance,
operation geometry, specifications and applicable requirements. Material definitions
and project-wide requirements/connections are retained in
`Pset_HomeDesignMaterial` and `Pset_HomeDesignProject`. Structured values are JSON text
so downstream tools can recover fields without guessing their units. Importer UI
support for displaying layer sets and JSON properties varies; inspect the IFC data
when a CAD application's property panel omits them.

Apply design changes to the canonical JSON and rebuild the IFC. Edits made in
FreeCAD are independent of the canonical model.
