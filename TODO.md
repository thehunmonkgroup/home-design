# Development backlog

Proposed work is listed here separately from supported capabilities.

## Complete shell and concealed services

The proposed scope covers the weather enclosure, explicit structural parts,
interior partitions and fixed accessories, decks, and electrical, plumbing and
mechanical rough-ins. Component completeness means authored geometry,
specifications, durable relationships, quantities and IFC representation; it does
not imply automatic structural sizing, service design or code certification.

### Sequential implementation plan

Each step includes strict schema/reference validation, shared resolved geometry,
IFC4/GLB representation, schedules/inspection where applicable, public or synthetic
regression coverage, and current-state authoring documentation. A checkbox is
complete only after those contracts pass. FreeCAD import/export execution and
verification are excluded from this implementation; IFC4 generation and validation
remain required. The independent native FreeCAD adapter and reverse-edit workflow
below remain separate CAD projects.

1. [x] **Host coordinate frames and placements.** Add reusable face/layer-relative
   coordinates for walls, slabs, roofs, foundations and individual members, with
   mounting offsets and orientation. Extend existing locators first. Prove host
   edits propagate, invalid locations fail, and dependency cycles are rejected.
2. [x] **Solid operations and owned penetrations** (depends on 1). Add deterministic
   solid intersection/subtraction and explicit cut ownership for through-holes,
   selected layers, recesses, notches and bearing seats. Support sloped hosts and
   preserve materials/identity across cuts. Prove net volumes and exported solids.
3. [x] **Physical cavity ownership** (depends on 1–2). Associate explicit parts
   with host layers, clip infill around them, and count each material once. Provide
   envelope/framing/service viewing controls and reject conflicting ownership.
4. [x] **Wall framing layouts** (depends on 1–3). Generate plates, full/short studs,
   headers, king/jack studs, corners, backing and blocking from wall/opening intent.
   Preserve member identities and explicit overrides through dimensional edits.
5. [x] **Floor, roof and deck layouts** (depends on 4). Fit variable-length joists,
   rafters, rim/bridging/blocking, ties and hip/valley members to host boundaries.
   Add authored truss assemblies and member end treatments. Exercise irregular
   decks, sloped/multi-face roofs and supported curved geometry with explicit
   approximation tolerances where curved parts use tessellation.
6. [x] **Hardware, reinforcement and masonry parts** (depends on 1–5). Add hangers,
   straps, hold-downs, post bases/caps, brackets, anchors, scheduled fastener groups,
   bars/mesh/ties, grout and embeds. Verify placement, connection participants,
   actual material quantities and appropriate IFC classifications.
7. [x] **Hosted accessory and interface library** (depends on 1–3, 6). Add ledges,
   stools, shelves, niches, backing, access panels, grilles and fixed equipment;
   membranes, sill pans, boots, flashing laps/returns, seals, cavity barriers and
   ventilation parts. Verify recess/projection, access volumes and explicitly
   declared barrier continuity.
8. [x] **Shared service graph and routing geometry** (depends on 1–3, 7). Add
   systems/circuits, typed ports, mounted equipment, route segments and fittings,
   including branches, transitions and bend radii. Validate port size/type/flow,
   endpoint alignment and disconnected or incompatible networks. Export native
   IFC systems, ports and connections with stable IDs.
9. [x] **Electrical and communications library** (depends on 8). Add receptacles,
   switches, device/junction boxes, panels/protection, lights/detectors, cables,
   conduits and grounding/bonding; typed ratings and circuit schedules. Verify
   connected panel-to-device routes and propagation when a host moves.
10. [x] **Plumbing library** (depends on 8–9). Add supply/waste/vent/gas runs,
    elbows/tees/reducers, valves/manifolds, traps/cleanouts, fixture connections,
    insulation and supports. Check authored falls, ports and system separation.
11. [x] **Mechanical library** (depends on 8–10). Add ducts, transitions/branches,
    dampers, registers/grilles, ventilation equipment, refrigerant/condensate,
    insulation/supports and service-access zones. Verify branched routing and
    coordinated penetrations through sloped and horizontal hosts.
12. [x] **Service interfaces and clash diagnostics** (depends on 2–11). Integrate
    sleeves, protective plates, fire/acoustic/weather seals and hangers with runs.
    Detect unintended service/framing intersections and access conflicts while
    recognizing owned cavities/cuts. Check authored hole/notch limits; do not
    infer engineering approval.
13. [x] **IFC and report completeness audit** (depends on 1–12). Audit every new
    family for native IFC classes/predefined types, standard properties/quantities,
    nesting/systems/ports, canonical identity, usable scene selection and schedules.
    Evaluate analytic swept/profile/Boolean IFC bodies for supported primitives
    while retaining a reliable tessellated representation for complex geometry.
14. [x] **Public complete-shell example and coordinated edits** (depends on 13).
    Add a public example covering a framed opening, interior accessory, roof/floor/
    irregular deck framing, hardware, sealed penetrations and connected electrical,
    plumbing and mechanical branches. Validate and build it; verify host changes,
    physical quantities, meaningful negative diagnostics and deterministic exports.
15. [x] **Final acceptance** (depends on 14). Audit every checkbox in this section
    and the component backlog against implemented behavior. Run Python tests with
    coverage, flake8, basedpyright, web tests/typecheck/lint/build, all public model
    validation and isolated builds. Update supported-state guides and the project
    skill. Leave FreeCAD execution checks excluded, preserve existing staging,
    and do not stage new changes.

### Framing and physical assemblies

- [x] Add wall-, floor-, roof- and deck-relative framing layouts that reuse member
  geometry and adapt to host boundaries, slopes and openings. Include plates,
  headers, opening jamb studs, short studs, corners, blocking, rim boards,
  bridging, roof ties, hips/valleys and authored truss assemblies. Preserve
  identities through edits and support individual member overrides.
- [x] Support variable member lengths and end cuts, including bearing seats and
  notches, for irregular decks and intersecting roofs. Define supported curved
  geometry separately from polygonal approximations.
- [x] Coordinate explicit framing with cavity layers: represent insulation in the
  remaining space, avoid overlapping physical solids and duplicate material
  quantities, and provide useful envelope/framing/service inspection views.
- [x] Add reusable connection hardware with placement, participant references,
  specifications and quantities: hangers, straps, hold-downs, post bases/caps,
  brackets, anchors and fasteners. Allow connection schedules to describe repeated
  fasteners without requiring a separate detailed solid for every screw.
- [x] Define reinforcement and masonry detailing support for shells requiring
  reinforcing bars/mesh, ties, grout and embedded anchors; distinguish aggregate
  material descriptions from individually modeled construction parts.

### Envelope interfaces and interior accessories

- [x] Extend layer/sweep/detail support with hosted membranes and interface parts
  for sill pans, roof boots, flashing returns/laps, air and vapor seals,
  cavity barriers and roof ventilation. Add continuity checks for explicitly
  authored weather and air barriers.
- [x] Add reusable hosted accessories for window stools/ledges, shelves, niches,
  backing, access panels, grilles and fixed equipment. Store host face/layer,
  mounting elevation, recess/projection, orientation and clearance volumes.

### Connected building services

Step 8 uses this internal dependency order:

1. [x] Complete the generic device/port foundation: explicit systems and circuit
   membership, internal port groups, mating compatibility, port-based placement,
   disconnected-network checks and native IFC ports/groups/connections.
2. [x] Build route geometry on those port frames: circular and rectangular
   sections, solid and hollow material, authored paths, tangent bends, section
   orientation, endpoint ports and physical quantities. Preserve geometric
   tolerances and reject invalid bends or self-intersections. Extend owned cuts
   to consume resolved route-shaped bore/clearance volumes so host infill cannot
   occupy a pipe or duct's intended empty passage, including bends inside hosts.
3. [x] Add reusable fitting geometry and port arrangements for elbows, branches,
   size/shape transitions and terminations; retain distinct mates at junctions
   and physical material accounting through cavities and cuts.
4. [x] Integrate routes/fittings with the network validator, IFC, GLB, schedules,
   documentation and coordinated-edit tests, including disconnected and
   incompatible routed branches. Verify native port classification by physical
   route/fitting family, including cable-carrier ports on conduits. Complete the
   step-8 acceptance checks before starting discipline-specific device libraries.

- [x] Add a shared service model with systems, circuits, typed connection ports,
  equipment/devices, route segments and fittings. Validate compatible connections,
  sizes and endpoint placement, and preserve connectivity through design edits.
- [x] Add electrical and communications components: receptacles, switches,
  junction/device boxes, distribution panels, protective devices, lights, detectors,
  cable/conduit runs and grounding/bonding connections. Preserve authored ratings,
  cable specifications, circuit membership and circuit schedules.

Step 9 uses this internal dependency order:

1. [x] Add explicit electrical/communications device roles, typed ratings and
   power/signal/grounding/bonding/containment port functions on the shared physical
   device, route and fitting contracts. Export concrete native device types.
2. [x] Add typed cable/conduit specifications and circuit supply/protection/load
   data, validate references and authored rating compatibility, and produce circuit
   schedules without inferring automatic sizing or code compliance.
3. [x] Exercise mounted panel-to-device branches, protective and grounding parts,
   communications connections and coordinated host edits through IFC/GLB builds,
   negative diagnostics and the complete step-9 acceptance gates.

- [x] Add plumbing components: water supply, waste/vent and applicable gas runs,
  elbows/tees/reducers, valves, manifolds, traps, cleanouts, fixture connections,
  insulation and supports. Reuse drainage fall checks where applicable and add
  system connectivity and fitting geometry.

Step 10 uses this internal dependency order:

1. [x] Add typed pipe/plumbing specifications and authored gravity-fall checks to
   the shared routes. Reuse existing drainage rules where they apply; preserve
   supply/waste/vent/gas system separation and explicit flow direction.
2. [x] Add plumbing device roles and fitting recipes for valves, manifolds,
   fixture connections, traps and cleanouts, including appropriate native IFC
   products and multi-interface equipment without inferred sizing or flow.
3. [x] Add physical pipe/fitting insulation and route-following supports using
   resolved service geometry. Preserve ownership, actual material quantities and
   mounting intent, with contracts reusable by the mechanical library.
4. [x] Validate connected supply/waste/vent/gas examples, gravity and interface
   failures, coordinated host edits and cuts, IFC/GLB exports and schedules.
   Complete the step-10 acceptance gates before starting mechanical components.

Step 10.3 uses this internal dependency order:

1. [x] Add analytic route/fitting station frames and use them for physical support
   hardware. Preserve section orientation, explicit connection participants,
   material quantities and native IFC/GLB identity through coordinated edits.
2. [x] Build physical pipe/fitting insulation from resolved outside envelopes,
   including bends, branches and transitions. Keep insulation stock separate from
   the service body and integrate cavity ownership, owned cuts and native IFC
   covering classifications with actual quantities.
3. [x] Verify combined insulated and supported runs through coordinated edits,
   physical ownership and export checks, using contracts shared with mechanical
   services. Complete the entire step before the plumbing acceptance examples.

- [x] Add mechanical components: ducts, transitions, branches, dampers,
  registers/grilles, ventilation equipment, refrigerant and condensate lines,
  insulation and supports, with service/access clearances.

Step 11 uses this internal dependency order:

1. [x] Add typed duct specifications and authored operating conditions to shared
   routes and fittings. Preserve rigid/flexible stock, pressure/temperature
   limits and explicit airflow inputs without inferring fan sizing or balancing.
2. [x] Add mechanical device roles for dampers, air terminals and ventilation
   equipment, with native IFC classes, explicit air passages and isolated
   refrigerant, condensate, electrical and control interfaces where applicable.
3. [x] Coordinate connected branches with physical insulation/supports and
   equipment access zones. Exercise refrigerant runs, falling condensate lines
   and owned penetrations through horizontal and sloped construction.
4. [x] Complete mechanical acceptance checks for coordinated edits, system
   separation, invalid ratings/interfaces, IFC4/GLB exports, actual quantities
   and schedules before starting the service-interface clash audit.

- [x] Generalize hosted cuts beyond wall/screen openings to recesses and
  penetrations through specified wall layers, floors, roofs, foundations and
  framing. Include sleeves, protective plates, fire/acoustic seals and weather
  seals, with explicit ownership of each cut.
- [x] Add service/framing clash and clearance checks that distinguish intended
  occupancy of a cavity or sleeve from an unintended intersection. Preserve
  authored hole/notch limits and report violations without inferring engineering
  approval.

Step 12 uses this internal dependency order:

1. [x] Complete reusable sleeve, protective-plate and fire/acoustic/weather-seal
   roles with explicit service/host relationships, physical fabrication geometry,
   owned cuts, cavity accounting and native IFC identities.
2. [x] Add service/framing interference and route-clearance diagnostics against
   final physical geometry. Distinguish construction masks from material, avoid
   duplicate assembly/member reports, and honor explicit intended interfaces.
3. [x] Check authored hole/notch dimensions and edge/section limits in the
   affected host frame. Report geometric violations without supplying unstated
   engineering limits or inferring approval.
4. [x] Validate coordinated service-interface edits, intended cavity/sleeve
   occupancy, negative clashes/access conflicts and exported diagnostic context
   before starting the IFC/report completeness audit.

### Delivery sequence and acceptance

Step 14 uses this internal dependency order:

1. [x] Compose a public shell with explicit wall/floor/roof cavities, a framed
   opening and an irregular framed deck; establish shared hosts and reusable stock.
   Harden roof-cavity subtraction where adjacent sloped framing rims meet: retain
   native material volume through mesh reimport and add a minimal general regression
   before accepting the combined shell.
2. [x] Integrate connected electrical, plumbing and mechanical branches, mounted
   accessories, service supports and sealed penetrations with explicit ownership.
3. [x] Validate coordinated host/service edits and meaningful negative diagnostics;
   compare final quantities, native IFC conversion, scene identities and deterministic
   exports in focused public-example regression coverage.
4. [x] Complete the public canonical example, isolated browser build and supported
   authoring guidance before final acceptance.

- [x] Implement host placement, physical cavity ownership and generalized cuts as
  shared foundations; build framing layouts and the service graph on those
  contracts. Deliver electrical, plumbing and mechanical libraries incrementally.
- [x] Extend schema, reference/semantic/topology validation, shared resolution,
  IFC/GLB exports, inspection, schedules, documentation and focused public or
  synthetic regression coverage together for each component family.
- [x] Add a public coordination example with a framed opening, roof/floor/deck
  framing, a mounted electrical device, connected service branches, a sealed
  penetration and an interior accessory. Verify coordinated edits, physical
  quantities, component selection and export identity.

## CAD interoperability

Step 13 uses this internal dependency order:

Native-classification audit checkpoints:

- [x] Map straight, curved and generated structural members to matching native
  role-specific occurrence/type families; preserve canonical stock identity and
  create only used type variants.
- [x] Distinguish custom hardware/fastener quantity sets from IFC4 standard
  templates instead of assigning nonexistent standard quantity-set names.
- [x] Preserve typed framing-assembly function through matching wall/floor/roof
  role variants and classify authored trusses natively.
- [x] Export applicable standard member/segment/reinforcing quantities and final
  net volumes, and standard nominal fastener properties, using real IFC4 templates.
- [x] Complete remaining service property mappings with explicit native units,
  preserving unmatched specifications without inventing dimensions or ratings.

1. [x] Audit native product/type classifications and canonical identity across
   every new physical role, generated member, service system and port. Correct
   mismatches and verify relevant IFC4 standard property/quantity templates.
2. [x] Export applicable standard properties and quantities from existing
   authored or measured data, retaining supplemental specifications without
   inventing ratings, capacities or nominal dimensions.
3. [x] Verify IFC geometry through the installed IFC geometry kernel and compare
   dimensions/material volumes against resolved geometry. Evaluate analytic
   swept/profile/Boolean bodies for supported primitives; retain reliable
   tessellation wherever richer representations lose physical cuts or identity.
4. [x] Verify scene selection and schedules against the same physical identities
   and quantities, document supported representation behavior and complete the
   audit before authoring the public complete-shell example.

- [x] Map services, fittings, terminals, accessories and hardware to appropriate
  IFC4 classes and predefined types. Export service systems and port connections
  as native IFC relationships, with standard properties/quantities where
  applicable, while retaining canonical identity and supplemental specifications.
- [ ] Add repeatable import checks against a declared FreeCAD version and import
  mode. Check solids, dimensions, units, placements, openings, individual framing
  children, materials, properties and system/assembly relationships; supplement
  IFC schema validation with geometry-kernel conversion checks.
- [x] Evaluate swept-solid, profile and Boolean IFC representations where richer
  downstream editing is needed; document which authoring parameters survive
  import separately from geometry and property preservation.
- [ ] Add a native FreeCAD adapter that consumes `ResolvedModel` and creates
  `.FCStd` parametric features while preserving canonical IDs, units and geometry.
- [ ] Define a CAD-to-canonical reconciliation workflow that translates downstream
  edits into reviewable, revision-checked design transactions.

## Geometry authoring

- [ ] Evaluate additional parametric recipes or explicitly identified imported
  geometry for complex and organic components.

## Schema evolution

- [ ] Define versioned schema migrations, including compatibility rules for
  additive fields and breaking changes, with deterministic conversion tests.
