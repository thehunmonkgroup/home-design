# Architecture and developer guide

## Language boundary

Python owns the operations where building semantics, topology, geometry, and desktop CAD ecosystems overlap. TypeScript owns the browser-only Three.js inspection client. JSON is the language-neutral contract. This keeps the project to two implementation languages and prevents Three.js scene details from leaking into authoring data.

```text
English request
      ↓
transactional change JSON
      ↓
canonical IFC-aligned model JSON
      ↓ validate / index / resolve
adapter-neutral resolved model
      ├── IFC4 + BIM relationships
      ├── GLB + render manifest ──→ Three.js viewer
      └── schedules / envelope + solar / SVG drawings
```

Export adapters consume `ResolvedModel` and share canonical identity and geometry.
FreeCAD interoperability uses IFC4 import. `ResolvedElement.construction_volumes`
retains named nonmaterial masks separately from physical `meshes` and lightweight
`data`. Resolved JSON serializes them as `constructionVolumes`; adapters do not
render or count them as material. Sourced penetrations consume these pre-cut
volumes through normal geometry dependencies, then intersect them with the final
host materials after cavity ownership. Route passage checks run after those cuts.

## Python components

| Module | Responsibility |
| --- | --- |
| `loader.py` | JSON loading and Draft 2020-12 schema diagnostics |
| `graph.py` | ID registries, typed references, relationship lookup, dependency cycles |
| `inspection.py` | Bounded source queries, typed incoming/outgoing edges, transitive dependents/type users and optional resolved member inspection |
| `validation/semantic.py` | Cardinality, compatibility, and domain invariants |
| `validation/topology.py` | Profiles, joins, opening fit/overlap, explicit roof planarity |
| `locators.py` | Shared point, axis, station, level, path, and profile resolution |
| `frames.py`, `placement.py` | Independent orthonormal transforms, host face/layer/route frames, local adjustments and mounting-point validation |
| `solids.py`, `penetrations.py` | Double-precision Boolean solids, explicit cut ownership, layer selection and net host geometry |
| `solid_surfaces.py` | Candidate planar boundary regularization that cancels coincident opposite faces, preserves holes and shares conforming edges within each connected shell |
| `cavities.py`, `review.py` | Disjoint physical cavity composition, final volume reconciliation and construction review disciplines |
| `wall_framing.py`, `member_assemblies.py` | Wall/opening-driven board layouts, stable generated member keys, scoped mounting and final child quantities |
| `planar_framing.py` | Boundary-fitted slab/roof-face member layouts, perimeter and hole rims, blocking, and adjacent-face miters |
| `assembly_geometry.py`, `member_geometry.py` | Named structural node networks, scoped trimming dependencies, rolled stock frames and physical end treatments |
| `curved_members.py` | Circular-arc structural solids with bounded path/section tessellation and analytic curve metadata |
| `fabrication.py`, `hardware.py` | Reusable local stock/cut recipes, placed accessories, fastener count/instance semantics and final scoped participants |
| `round_paths.py`, `reinforcement.py`, `masonry.py` | Tangent-radius circular paths and analytic station frames, reinforcing bar/mesh quantities and explicit masonry material parts |
| `mounted_parts.py` | Physical hosted accessories/envelope parts, post-cut mounting fit, access obstructions and local barrier probes |
| `service_interfaces.py` | Explicit construction/service participants for sleeves, protective plates and seals, scoped host identity and final stock overlap checks |
| `service_coordination.py` | Authored post-cut service/material and construction-clearance intersections, scoped obstacle identity, explicit installation exceptions and diagnostic evidence |
| `cut_limits.py` | Host-frame cut extents, authored extent fractions, exact polyhedral directional material reserves and retained limit diagnostics |
| `service_ports.py`, `services.py` | Oriented service interfaces, generic fabricated devices, explicit systems/circuits and port-level connectivity validation |
| `electrical.py`, `adapters/ifc_electrical.py` | Electrical/communications device roles, typed ratings, interface-purpose validation and native device classifications/rated measures |
| `circuit_schedules.py` | Scoped panel/protection/load references, explicit rating checks, protection-path checks and power/communications schedule rows |
| `service_routes.py` | Solid/hollow circular and rectangular routes, transported endpoint frames and named construction-volume masks |
| `service_insulation.py` | Expanded service envelopes, separately owned insulation material, serialized-volume checks and duplicate-covering rejection |
| `drainage.py`, `plumbing.py`, `adapters/ifc_plumbing.py` | Shared directional fall rules, pipe stock/operating limits, plumbing device interfaces and native equipment classifications/properties |
| `mechanical.py`, `adapters/ifc_mechanical.py` | Duct stock, signed operating limits, equipment interface requirements, isolated heat-recovery passages and native classifications/properties |
| `fitting_geometry.py`, `service_fittings.py` | Type-local elbows, branched passages, eccentric shape transitions and caps with generated mating interfaces and shared construction masks |
| `geometry.py` | Polygon, wall-profile, box, and roof-plane geometry primitives |
| `resolver.py` | Element and relationship integration into absolute shared geometry |
| `space_geometry.py` | Derived wall-axis and full-wall-thickness interior room footprints, including holes and area-basis semantics |
| `components.py`, `construction.py` | Typed construction resolution, oriented members, shared-miter sweeps, repeated framing, stairs, guards and screens |
| `roof_controls.py`, `layers.py`, `doors.py`, `screens.py` | Bearing/overhang roof controls, physical material layers, framed doors and profiled screen enclosures |
| `roof_joints.py`, `sweep_volumes.py` | Shared roof-layer/framing bisectors and nonmaterial drainage sweep envelopes/bores for owned junction cuts |
| `terrain.py`, `survey.py` | Triangulated grade surfaces, bounded elevation queries and revision-checked survey import changes |
| `coordination.py` | Bearing bounds, load paths, drainage connections/outlets, grade exposure and numeric requirements |
| `requirements.py` | Shared numeric requirement evaluation and failure diagnostics |
| `solar.py`, `reports.py` | Geographic solar vectors, sampled geometric shading, schedules and envelope exports |
| `changes.py` | Revision/precondition enforcement, operation dispatch, atomic commit |
| `change_preparation.py`, `change_preview.py` | Explicit coordinated operation generation and authored/resolved before/after review with retained validation evidence |
| `schema_diagnostics.py` | Kind/op discriminator-aware field diagnostics from the authoritative schema |
| `capabilities.py` | Component/type pairing, resolver registration, host/cavity contracts, generated children, native IFC defaults and viewer labels |
| `processing.py` | Declared construction-stage prerequisites and shared cavity/network state |
| `recipes.py`, `assembly_instantiation.py`, `assembly_updates.py`, `assembly_duplication.py` | Declarative package inputs, deterministic expansion, three-way updates and nested reference-safe copying |
| `assembly_scope.py`, `reference_remapping.py`, `scoped_remapping.py`, `recipe_interfaces.py` | Ownership scope, typed canonical/scoped identity remapping and resolved connection-point validation |
| `part_contracts.py`, `port_contracts.py`, `quantities.py` | Typed generated stock, service interfaces and dimensioned measurements at shared boundaries |
| `adapters/ifc.py` | IFC4 types, bodies, axes, containment, materials, and relationships |
| `view_navigation.py`, `view_properties.py` | Explicit relationship navigation, generated-member review metadata and dimensioned human-readable properties |
| `adapters/ifc_units.py` | Explicit millimetre, square/cubic-metre, volt/ampere, pascal, kelvin and cubic-metre-per-second project units, with native area/volume conversions |
| `adapters/ifc_standard_services.py` | IFC4 common-set dimensions, storage/flow measures and optional signed pressure/absolute-temperature bounds from matching authored specifications |
| `adapters/ifc_structural.py` | Shared native member classifications and role labels for straight/curved occurrences and matching reusable type variants |
| `adapters/ifc_quantities.py` | IFC4-template-filtered nominal stock/route sections and lengths, reinforcing counts, and final material net volumes in declared units |
| `adapters/ifc_properties.py` | Lossless specification/property data, material layer sets, concurrent cavity constituents and item styles |
| `adapters/ifc_hardware.py` | Native accessory/fastener classifications, realizing-element connections and count/net-volume quantities |
| `adapters/ifc_reinforcement.py` | Native reinforcement dimensions, steel specifications and final construction-part quantities |
| `adapters/ifc_mounted_parts.py` | Native mounted parts/coverings, physical host connections, net quantities and virtual coordination assignments |
| `adapters/ifc_services.py` | Native distribution groups, nested oriented ports and stable external mating relationships |
| `adapters/drawings.py` | Orthographic SVG projections, mesh-plane sections with holes and explicit dimensions |
| `adapters/gltf.py` | Three.js coordinate conversion, materials, GLB, node manifest |
| `visual_render.py`, `render_sections.py` | Validated source snapshots, packaged capture runtime, image provenance and temporary material-filled section surfaces |
| `batch.py` | Ordered input expansion, deduplication and per-model validation reports |
| `build.py` | Evaluated source snapshots, adapter staging, per-model directory replacement and publication rollback |
| `source_state.py`, `transactions.py` | Exact-byte source guards, cooperative writer locks, prepared commits and journal-based publication recovery |
| `publication.py` | Immutable browser assets, managed cleanup and atomic catalog publication |
| `cli.py` | Validation, inspection, preparation, previews, transactions/recovery, builds, resources, unit conversion, survey and solar workflows |

All geometry stays in canonical millimetres through `ResolvedModel`. The glTF adapter alone converts to Three.js metres/Y-up. IFC declares millimetre project units and consumes resolved vertices without an implicit scale.

The IFC body contract consumes final resolved meshes. It preserves their physical
cuts, cavity composition, material partitions and declared curve approximation
as polygonal face sets. Native swept profiles and Boolean solids can represent
individual primitives, but the adapter does not reconstruct construction history
from final meshes or replace processed parts with their uncut stock. Native
classification, axes, relationships and properties carry the available source
semantics alongside these bodies. Geometry-kernel regression checks compare IFC
world extents and material volume, then reconcile scene ownership and schedule
quantities; GLB comparisons account for its float32 vertex precision. GLB meshes
use local vertices centered on their bounds and a translating node transform to
retain world placement without sacrificing thin-part precision to the building's
coordinate offset.

## Batch builds and browser catalog

The build CLI defaults its artifact root to `build` under the working directory.
Without an explicit `--web-assets` or `--no-web-assets`, it searches the working
directory and ancestors for a viewer in that directory or its `web` child. A
candidate has `index.html` and a `package.json` named `home-design-viewer`; the
first match supplies `public/model`. Malformed or unrelated package metadata is
skipped. Discovery does not use model-source paths or installed package resources.
No match means artifact-only output. `BuildService` and guarded transactions retain
their explicit publication destinations; discovery belongs to the build CLI.

`BuildService.build_many` validates all inputs and stages all adapter outputs before
replacing any generated model directory. Inputs are processed in order, with the
last source for a filename stem supplying that output. `build` delegates a single
source to the same workflow. Artifact paths in `BuildResult` include the model
subdirectory. Each input is captured once and `ModelValidator.evaluate` retains
the resolved model. `PreparedBuild` binds validation evidence to a canonical source
fingerprint and the exact captured bytes. Adapters consume that retained result;
metadata hashes those bytes. Source guards reject changes before publication.

`DesignTransaction` prepares candidate validation and all adapters before committing
the source under a cooperative destination lock. Its atomic journal records
`committing`, `committed` and `published` phases. Publication errors preserve the
saved source and roll back generated model directories. `recover` verifies the
candidate byte hash and rebuilds the saved revision without applying the changeset.
This also recovers an interrupted journal phase when the committed bytes match.
Journals remain under the build root and are excluded from browser assets.

Build directory replacement preserves backups until browser publication succeeds
and restores them on a caught publication error. This is not a filesystem-wide
crash transaction. Per-root exclusive publication locks reject competing writers
with retry guidance. An interrupted process may leave its lock directory; remove
that lock only after confirming its writer is no longer running.

The viewer root contains `index.json` with format
`home-design-model-catalog-0.1` and a `models` array. Entries contain `key`, `name`,
`sourceRevision`, `version` and `baseUrl`. The key is the source filename stem;
the name is `project.name`. No source filesystem paths enter the catalog.
`baseUrl` is the URL-encoded key followed by an asset-version directory and a
trailing slash, relative to `/model/`.

The version is a SHA-256 fingerprint of the browser artifact filenames and bytes.
Complete immutable asset directories are installed before atomic replacement of
the catalog. Merge retains other catalog entries and earlier asset versions;
replace removes excluded models and superseded versions after the catalog commits.
Cleanup targets generated artifact filenames within managed version directories,
preserving unrelated files. The catalog is revalidated on page load; versioned
URLs keep manifests, geometry and reports tied to one completed build.

## Installed authoring resources

`build_support.ResourceBuild` copies the authoritative repository schemas, public
examples, assembly recipes, documentation and progressive skill into wheel resources, preserving
relative links. Source distributions contain the same inputs. Editable installs
read checkout resources directly. `home-design resources` returns their installed
locations; model workflows and unit conversion work outside a checkout. Website
export additionally requires a viewer source tree and Node dependencies, selected
with `--web-project` when that tree is elsewhere.

## Construction resolution and coordination

The [shared resolved contracts](reference/resolved-contracts.md) define placement
frames, physical stock, layers, ports and quantities used across module boundaries,
and the explicit construction-stage prerequisites.

The authoring schema uses `modelVersion: "0.2"`, independently of the design's
`revision`. [Canonical model and durable identity](reference/schema-evolution.md)
defines named subcomponents and explicit conversion of positional inputs.
The [recipe contract](reference/assembly-recipes.md) defines explicit parameters,
bindings, compact provenance and three-way instance updates. Expanded assemblies
remain ordinary canonical objects consumed by the existing resolver and adapters.
`ModelResolver.resolve_component` caches dependency-resolved elements and rejects
recursive placement. Surface datums can connect slabs, footings, member endpoints,
stairs and roofs to other geometry, including terrain. Relationships alone do not
move geometry. Sampled clearance checks run after resolution; support/load,
drainage and explicit requirement checks consume the same resolved model.

`RequirementEvaluator` supplies `requirementResults` in resolved JSON and the
render manifest. Each result has the authored requirement `id`, aggregate `status`
(`satisfied`, `violated`, or `notChecked`), and per-target `checks` containing
`elementId`, `property`, `operator`, `actual`, `expected`, and `status`. A requirement
with a check and targets is satisfied only when all targets pass; a missing or
nonnumeric property fails the check. Notes and checks without targets are not
automatically checked. Coordination diagnostics consume these same results and
apply the authored severity to failures. Authored requirements remain unchanged.

Penetration limits resolve their host frames before cutting. `Penetrations.apply`
retains the post-cavity host registry and evaluates limits after every owned cut
has been applied. Each check intersects the actual removed solid with its scoped
member/face/layer. Extent fractions use that scope's pre-penetration material
extent; margin containment uses final material with only the current removed
volume restored. Other cuts therefore remain boundaries independently of cut ID
ordering. A directional margin sweeps each boundary triangle into a convex prism
and unions the prisms with the original solid. It preserves concavity and holes
instead of taking the convex hull of the entire cut. The native containment
difference supplies failed margin volume without exporting diagnostic solids.
Lengths use a 1e-6 mm comparison tolerance, fractions 1e-9, and margin containment
the shared 1e-6 mm³ solid-volume tolerance. The validator reports authored-severity
`penetration.limit-violated` diagnostics; all frames and results remain in
`limitResults` for adapter and report consumption.

Roof thickness is measured normal to its planes. A vertical underside query
subtracts `thickness / cos(pitch)`, matching the exported solids. Bearing datums
keep ridge/plate geometry fixed while edge overhangs vary. Hip faces use clipped
bearing planes; explicit roof faces retain their own plane normals. Layer meshes
keep stable layer roles for styles and net quantities. Cavity constituents share
one thickness and divide volume by fractions, not serial layers.

Sweeps use rotation-minimizing frames and shared miter planes; individual segments
are closed solids with coincident joint caps. Reversed paths and locally inverted
miters fail resolution. General global self-intersection detection is not inferred.
Terrain is an open triangulated surface excluded from material-volume quantities.

Profiled screens use a horizontal baseline and height or surface-constrained top.
Their elevation profiles are partitioned into frame and infill regions after
hosted opening subtraction. Doors on panels share the wall-door placement and
IFC void/fill pipeline. Explicit door infill materials retain material identity
without being counted as glazing.

IFC framing arrays expand into native members under a canonical assembly. Their
generated IDs are deterministic derivatives of source IDs and member indices.
All bodies use polygonal face sets; styles are per mesh. Ordered material layer
sets live on reusable types. Nested specifications and requirements use JSON-text
properties, including project-level requirements and connection data. IFC is
a coordinated tessellated model, not a native fabrication or analysis model.

Polygon, wall-profile and planar-face triangulation uses constrained Delaunay
triangles so concave boundaries and hole edges remain in the mesh. This requires
Shapely 2.1 or newer and GEOS 3.10 or newer. Fitted framing validates closed solids,
stock widths and disjoint member volumes before cavity composition. Planar layouts
offset boundaries along surface normals and partition adjoining roof domains at
normal bisectors; shared member-assembly contracts retain individual identities,
mounting frames and final quantities through subsequent cuts.

Authored member assemblies resolve scoped trim dependencies before checking
positive-volume overlaps. Local-node members transform both geometry and section
frames with the assembly placement; globally located nodes use world member
frames. IFC node and trim connections reference surviving children after solid
operations. End treatments clip stock with inward-oriented planes in its retained
section frame. Circular members loft radial sections, union adjacent closed
segments, and allocate their explicit error budget to section and path deviation.
Analytic mounting uses the retained arc intent independently of tessellation.

Fabricated types union single-material local extrusions or full radial-profile
revolutions before applying named type cuts. Revolutions reject negative radii
and bound circular tessellation by the authored chord tolerance, 10,000 segments
and 2,000,000 intermediate vertices. Hardware and detailed fasteners enter the physical cavity pipeline;
scheduled fasteners retain a computed type-volume contribution without meshes.
Reports add that contribution once, separately from mesh quantities. Hardware
participants resolve after cavity composition, penetrations and final member
refresh, so scoped references must identify surviving children. These semantic
participant references do not create geometry dependencies or infer physical
contact. IFC connects each participant pair through the authored realizing
hardware and exports single-participant hardware as an element attachment.

Explicit footings expose a synthetic body layer 0 with the original material as
infill. Its mesh role participates in the same cavity/penetration accounting as
layered hosts; aggregate footing output retains its original representation.
Rounded circular paths replace corners with analytic tangent arcs, transport
shared section frames and union their lofts. Closed paths require planarity;
nonadjacent volume overlap fails resolution. Orthogonal reinforcement meshes
union wire intersections before allocation. Masonry parts use fabricated stock
and cuts and participate as disjoint cavity owners. Nominal bar lengths and wire
counts describe the uncut authored stock; final quantities use surviving solids.

Mounted accessories/envelope parts resolve host frames and signed projection
before cavity composition and cuts. Their post-cut refresh rejects positive
material overlap with the surviving physical host and records mounting extents
and net volume. Access checks then intersect nonmaterial probes with final
physical solids, expanding generated members for scoped exceptions. Barrier
checks intersect declared materials with a local probe and require all
participants, one connected region and an authored maximum uncovered volume.
Their diagnostic severity is an explicit authoring input.

Service-interface declarations on envelope parts retain construction and service
participants separately from mounting dependencies. Post-cut validation resolves
scoped construction members, requires surviving physical participants and rejects
material overlap with either side of the interface. The original declaration and
resolved participant IDs remain in scene, IFC property and schedule data. IFC
class selection uses the same role mapping for types and occurrences: sleeving
is a covering, protective plates are plates, and seals retain user-defined
covering roles. `IfcRelConnectsWithRealizingElements` connects each service to the
construction host through the physical interface part without creating ports or
implicit geometry dependencies.

Optional service `coordinationChecks` run after interface and hardware participant
refresh. They expand generated-member containers once and intersect final service
stock with physical candidates using native solid unions for measured diagnostic
volumes. Material collisions take precedence over clearance obstructions for the
same checked service/candidate pair. Clearance-only exclusions resolve authored
component references and explicit insulation, interface and hardware connections;
they never suppress material checks. Results and exclusion reasons remain in
`serviceCoordination`, and the validator emits authored-severity diagnostics with
the source check path and actual obstacle ID. Checks add no product or material
meshes. Device/accessory maintenance spaces continue to use clearance probes.

Coordination meshes have role `coordination`. Material reports, orthographic
drawings and solar occlusion exclude their element kinds; GLB retains translucent
geometry with default visibility disabled. IFC uses virtual elements with native
product assignments, while physical mounted parts receive native mounting
connections and net-volume quantities. Component host frames expose existing
resolved placements without implying a face; their references participate in
the same geometry dependency-cycle checks as other placement locators.

Service devices resolve local port frames alongside their physical geometry.
Electrical roles reuse the same service-device schema, fabrication, cavity,
mounting and network pipeline. Typed ratings stay on reusable definitions and
resolved devices. Port functions are checked against media and matched at external
connections; generated route/fitting ports inherit their type's function. Carrier
stock requires containment intent when a function is authored. Generic devices
and routes can retain unclassified interfaces, but those cannot mate with a
classified interface. Native electrical device types carry supported standard
rated measures and supplemental unit-explicit rating data.

Plumbing roles share the fabricated device pipeline and preserve typed equipment
specifications. Their minimum fluid-interface and media checks run before
placement; powered equipment also uses electrical frequency validation. Separate
equipment ports can belong to different systems, while internal port groups
retain the common-media invariant. Pipe fittings reuse route stock rating checks.
Trap recipes use the rounded path solver and verify the placed centerline has a
return below both interfaces; this is a geometric check, not hydraulic seal
analysis. Discipline dispatch selects native IFC device classes independently
from the generic device geometry and mounting implementation.

Routes retain their world-space `pathControls` and initial `sectionUp`; fitting
paths retain these in type-local coordinates. Host route stationing reuses the
analytic rounded path and parallel transport, then applies a fitting's placement.
Branches require an explicit scoped path selection. Coordinate transforms live
in `frames.py`, below both the path solver and host resolution; `placement.py`
also exports those frame names for existing consumers. Station evaluation uses
analytic lengths independently of the tessellated `path` retained for inspection.

Service insulation expands the source's outside sections and subtracts its exact
resolved envelope. Cap coverings also extend the closed end. A temporary cutter
extends open interface caps by one millimetre to avoid coincident Boolean faces;
this candidate is used only when it removes the same volume as the exact envelope.
The exported construction masks retain the original envelope. The shared solid
output boundary checks triangle and reimported volumes against the native result.
It first discards face ancestry and simplifies at the kernel's tolerance, then
retries the native triangulation if necessary. Native splits
compute retained and removed cut material together; an equivalent subtraction
provides a fallback when the removed intersection cannot serialize stably.
The fallback must preserve the native result's volume before serialization.
When native triangle serialization remains unstable, a final candidate rebuilds
planar boundaries within each connected shell. It cancels overlapping faces with
opposite orientations, retains holes and splits edges at shared boundary points.
Planar grouping uses 1e-6 mm tolerance and 1e-7 mm projected coordinates; original
vertices remain preferred. Boundary loops collapsed below three distinct vertices
at that tolerance are omitted before triangulation. The candidate passes only when both triangle integration
and native reimport preserve the original material volume under the same 1e-6 mm³
absolute / 1e-9 relative tolerance. Independent shells are not welded together.
Unstable or materially changed candidates fail resolution. Insulation
uses explicit cavity ownership and ordinary owned cuts, then rejects overlapping
final covering solids on the same service. Native IFC coverings share the mounted
part connection/quantity adapter without adding distribution ports.

Port locators consume those frames through the same component cache as host
locators. Dependency indexing examines actual path fields below the registry
identity; component names do not classify a reference as geometric. Anchor
references remain positional. External service mates and system membership do
not produce geometry edges, so a semantic network may contain loops.

After cavity/cut/mounting resolution, `ServiceNetworks` copies port records,
checks external mates, adds authored internal group edges, verifies induced
system/circuit connectivity and annotates membership. External ports accept at
most one mate; internal groups do not consume that mate. The IFC adapter nests
ports in their owning product and assigns each to the narrowest authored circuit
or system. Parent systems group devices and circuits. Shared equipment keeps
port-level system separation, with internal groups retained as explicit data.
Routes and generated fittings require a single system across all their ports;
system interfaces remain explicit equipment intent. Directional pipe fall checks
use authored tangent directions, so a net endpoint drop cannot mask a local rise.
The minimum-grade downward cone is convex and also contains the minor-arc bend
tangents between valid spans. Vertical drops avoid infinite report values.
Profile sweeps use the shared fall validator while retaining their existing finite
`segmentFalls` report convention. Pipe operating checks compare only supplied
limits and preserve missing inputs as `notChecked`.
`CircuitSchedules` consumes this validated adjacency graph and annotated registry.
Schedule references remain semantic, so they do not place geometry or introduce
geometry dependencies. Scheduled routes require complete endpoint membership.
Removing a declared protective device's ports from the induced circuit graph
must disconnect each declared load from its panel; otherwise the protection path
fails. Rating checks retain absent inputs as `notChecked` and reject incompatible
known values. Circuit rows sum each included route once and retain explicitly
listed apparent-power loads without derived demand or current calculations.

Typed cable stock retains nominal conductor counts/areas and centerline-based
lengths separately from the route's actual material. Individual conductor/core
classifications require one scheduled conductor. Conduit trade data describes
the existing hollow solid. These specifications flow through resolved data,
reports and native stock property sets without adding meshes or material volume.

Host frames resolve against authored component geometry and retain roof plane
boundaries independently of mesh tessellation. `CavityComposition.apply` fits owned
parts and subtracts their geometry from explicit cavity infill. `Penetrations.apply`
then cuts those disjoint physical hosts, and `CavityComposition.refresh` reconciles
final infill, part and void volumes against the original cavity regions.
`MemberAssemblies.refresh` updates generated member records so child quantities
and counts agree with the surviving physical meshes. These
operations work on a copy of the resolved registry after placement resolution,
preserving the base
geometry cache, so repeated resolution is idempotent and cuts do not create
placement cycles through their own hosts. Manifold's double-precision mesh API
performs Boolean operations; output vertices and cyclically normalized triangle
indices are sorted for deterministic serialization. Boolean output at or below
1e-6 cubic millimetres is treated as numerical contact residue; touching bounding
boxes do not invoke an intersection. Source roles/materials remain
on host solids. Removed volumes have the nonphysical `void` role and export only
as IFC opening bodies, with layer-restricted native void relationships. Generated
relationships use `<penetration-id>/voids` identities.

Explicit cavity ownership exports as native element connections with identities
`<part-id>/cavity/<host-id>/<layer-id>` (converted layer IDs retain their
original numeric GUID seed). Host/part property sets retain the selected
regions and actual volume contributions. Aggregate material fractions remain an
independent layer representation and cannot coexist with explicit ownership.

Solar studies use NOAA approximate solar-position equations and direct ray tests
against opaque model meshes. They are deterministic geometric snapshots, not an
annual energy simulation. The client only presents stored results and transforms
sun vectors/clipping planes to the GLB coordinate system; it does not re-solve them.

## TypeScript components

`web/app/lib/model.ts` is the runtime and static render-manifest contract. `HomeViewer.tsx` loads GLB and manifest together, indexes loader-safe node names back to stable canonical IDs, and owns only presentation state. It does not calculate building geometry.

`web/app/lib/catalog.ts` validates catalog entries, sorts display names and loads
selected-model assets. `HomeViewer` owns catalog selection and mounts a model review
keyed by model key and asset version. Each review owns its scene and presentation
state, so canonical IDs reused across models cannot leak selection or visibility.
Unmount aborts asset requests and disposes scene geometry, materials, textures,
shadows, controls and the renderer. Geometry finishing asynchronous parsing after
cancellation is also disposed. Reports resolve relative to the active asset version.

The viewer is a static React/Vite application. `web/index.html` loads
`web/app/main.tsx`; the build emits HTML, CSS, JavaScript and imported assets into
`web/dist/`. Relative asset and catalog URLs support hosting at a domain root or
under a subdirectory with a trailing slash. There is no server-side application
runtime or database.

`WebsiteExporter` implements `home-design website-export`. It expands the same
model selection as `build`, builds into temporary directories, and publishes a
fresh catalog with only those sources. It sets `HOME_DESIGN_PUBLIC_DIR` for the
Vite subprocess to that isolated asset tree, excluding `web/public/` contents.
Viewer logs go to stderr; stdout contains the resulting directory and model
catalog entries as JSON. Only static viewer output and browser model artifacts
reach the destination; temporary CAD and diagnostic outputs are discarded.

Website exports add deterministic gzip copies of `model.glb` and
`render-manifest.json`, preserving their original counterparts. Each exported
catalog entry has an optional `compressedAssets` map from those two original
filenames to positive compressed byte lengths. The loader appends `.gz`, streams
both downloads with aggregate progress, and decompresses them with
`DecompressionStream` before validation and GLB parsing. This works on plain static
servers without `Content-Encoding` configuration. HTTP-decoded responses are
also accepted. Catalogs without this metadata and browsers without decompression
use the original assets. Encoded HTTP responses with unavailable transfer sizes
show indeterminate progress; model preparation is a separate phase. Cancellation
stops both downloads and suppresses stale progress updates.

The destination must be empty or contain the `website-export.json` marker with
format `home-design-website-0.1`. It must be separate from viewer and selected
model sources. A successful export replaces the complete directory; build failure
leaves the previous export unchanged. Directory installation restores the prior
export on a caught rename failure. Exports do not modify local preview assets or
deploy externally. `--web-project` selects a viewer checkout when it is not adjacent
to the installed Python source. Node/npm and installed viewer dependencies are
required; the exporter does not install packages.

The active viewer assets under `web/public/model/` are also ignored because they may represent a private home. The TypeScript integration test reads a committed reference manifest from `web/tests/fixtures/` instead.

Viewer visibility is capability-based: `canToggleVisibility` checks whether a
manifest element exports scene nodes. Per-component controls, hidden-state updates,
and bulk visibility controls use this capability, independent of component kind.
New kinds with exported nodes participate automatically; records without nodes
remain inspectable without visibility state. No component-kind visibility list
or additional manifest flag is required.

`DesignRequirements` presents exported evaluation results independently of
violation severity, with no client-side validation. Missing results have an
explicit unavailable status. `ViewOrientation` uses the camera's horizontal
orientation to display canonical +Y north after the Z-up/Y-up transform; it does
not infer georeferenced true north. Navigation help is available on hover, focus,
and tap without changing the camera.

## Determinism and identity

- Resolved JSON, GLB, manifest, diagnostics, metadata, schedules, envelope and SVG drawings are byte-stable for an unchanged source.
- Every canonical IFC root and generated IFC root uses a UUIDv5-derived compressed GlobalId.
- IFC `Tag` and `Pset_HomeDesignIdentity.CanonicalId` preserve source IDs.
- GLB nodes use loader-safe, hash-suffixed generated names; the manifest maps them back to canonical IDs.
- Build metadata records the exact source SHA-256 and revision.

IFC header timestamps may vary between builds, so conformance tests compare the complete IFC root GUID set and semantics rather than raw STEP bytes.

## Adding a component

1. Add authoring intent to the JSON Schema and a minimal public/synthetic fixture.
2. Register a `ComponentCapability` in `capabilities.py`: kind/label, expected reusable
   type and native IFC defaults, resolver route, discipline, host frame modes,
   direct host targets, cavity eligibility and generated-member capabilities.
   Shared stock types use a consistent IFC type class. `home-design capabilities`
   audits schema coverage in both directions; `--kind KIND` returns one contract.
3. Add typed extraction for new reference shapes and semantic compatibility rules.
   The graph consumes registered type/host pairings and shared reference roles.
   Placement drives geometry; ownership, connection and requirements remain distinct.
4. Add topology checks and implement the domain resolver using shared geometry.
   Bind a new resolver route in `ModelResolver` when needed. Unknown kinds and
   missing bindings fail explicitly; nonphysical groups use dedicated handlers.
5. Add specialized native IFC classification/properties when the default class is
   insufficient. Keep adapter bodies based on final shared resolved meshes.
6. Supply manifest defaults and labels through the registry. The viewer accepts
   registered families without a second kind list; built-in labels/order remain
   fallbacks for manifests without display metadata. Domain-specific controls may need UI support.
7. Add focused parameter tests and integration tests for reference propagation,
   host/cavity behavior, IFC/GLB identity and final quantities. Registration audits
   verify schema and IFC class coverage; they do not establish geometric correctness.
8. Update the project skill's relevant technical references and task routing.
   Update user guides for user-visible capabilities and controls; keep component
   field semantics in the authoritative skill references. The native export
   contract is in `docs/reference/ifc-contract.md`.

## Test strategy

The [representative AI editing evaluations](reference/ai-editing-evaluations.md)
record fresh-context authoring trials, component/workflow coverage and the fixes
they verify. These assess discovery and coordinated editing separately from
automated regression coverage and downstream CAD import.

Design-specific regression coverage belongs only to public reference JSON models
in `examples/`. These tests preserve the reference models' intended geometry and
component relationships. Maintain them alongside changes to those reference models.

Custom design authoring uses model validation, guarded transactions, completed
builds, inspection, and diagnostic review, leaving repository tests, fixtures, and
snapshots unchanged. This also applies to custom designs copied from an example.
Keep private design files, their generated outputs, and project-specific
requirements outside the repository test suite; tests remain independent of the
active custom model and viewer assets.

General software tests cover reusable behavior and may use public examples or
minimal synthetic fixtures; they are not restricted to complete example homes.
`tests/fixtures/basic-shell.json` and its guarded `move-window.json` provide a small
synthetic input for general geometry, CLI and transaction tests. They are test
resources, excluded from the public model catalog and installed authoring examples.
Public worked-edit regressions use Assemblies for package/layer/service edits,
Hillside for shared-window stock, and Master Suite for framed window edits.
Engine feature development and defect fixes require separate authorization from
custom design authoring. When a custom design exposes an engine limitation,
explain the limitation and obtain authorization before changing code or tests.
For authorized development, reproduce the general behavior with public or
synthetic inputs and add focused regression coverage.

Component tests target decisions with expensive failure modes: schema rejection, missing or mistyped references, dependency cycles, anchor propagation, watertight profiles with holes, all roof recipes, explicit roof constraints, derived spaces, opening cuts, fill clearance, join connectivity, transaction conflicts, and atomic commit.

Construction regression tests additionally compare queried roof undersides with
actual solids, preserve ridge geometry under asymmetric overhangs, propagate grade
changes through footings/posts/stairs/handrails, reject incomplete load paths and
invalid drainage falls, preserve profile holes through sweep bends, avoid cavity
thickness/quantity double counting, retain section openings, and exercise solar
orientation/occlusion. End-to-end tests validate IFC4 and retain specifications,
material layers, reports, survey transactions and web asset copies together.

Integration tests exercise the supported workflow and cross-adapter contracts: canonical JSON through CLI, resolver, IFC4 validation, stable GUIDs, GLB scene nodes, render manifest, and web asset publication. TypeScript tests cover manifest compatibility, display grouping, scene-object selection, measurement formatting, and the generated Python-to-viewer manifest.

The [viewer contract](reference/viewer-contract.md) describes navigation links,
generated-member node ownership, parent/child visibility and explicit display units.

Electrical integration coverage includes distinct circuits on a shared mounted
panel, branch protection, communications, grounding/bonding conductors and an
owned flush-box recess. Transactional wall rotations/translations preserve port
alignment, circuit membership, material quantities and schedule identity through
IFC/GLB builds. Removing a required recess cut fails physical mounting validation.

Run every gate before merging:

```bash
pytest --cov --cov-report=term-missing
flake8 src tests
basedpyright .

cd web
npm test
npm run typecheck
npm run lint
npm run build
```
