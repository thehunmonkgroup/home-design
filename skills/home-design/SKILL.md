---
name: home-design
description: Safely create, inspect, and modify IFC-aligned home designs from natural-language requests. Use for architectural design changes, component or relationship edits, model validation, Three.js preview rebuilds, and IFC exports in this repository. Use the repository development workflow for engine implementation.
---

# Home Design

Use the canonical home JSON as the editable source of every design decision. Apply requested changes through validated transactions against that source, then regenerate `build/`, `web/public/model/`, resolved meshes, GLB nodes, and IFC entities as disposable outputs.

## Task scope and verification

- For custom designs, use the validation, transaction, build, inspection, and diagnostic workflows below. Leave repository tests, fixtures, and snapshots unchanged, including when the custom design starts as a copy of an example.
- Maintain design-specific repository regression tests only for public reference JSON models in `examples/`. Keep private design data and its generated outputs outside the test suite.
- Engine development is a separate scope: if a design requires an engine fix or new capability, explain the limitation and obtain authorization before changing code or tests. For authorized development, use public examples or minimal synthetic fixtures to test general behavior, following `docs/architecture.md`.

## Existing design

1. Run `home-design validate MODEL --json`.
2. Run `home-design inspect MODEL`; then inspect each affected element with `--element ID --relationships`.
3. Trace integrations before proposing changes: shared anchors, reusable types, hosts/openings/fills, joins, supports/load paths, attachments, surface datums, stair/edge followers, grade, drainage, interface details, space boundaries, and assemblies.
4. Accept metric or US customary dimensions and translate every length to millimetres before authoring JSON. Use the deterministic conversion workflow below for US customary values. Keep angles in degrees and preserve stable IDs when renaming, moving, or resizing objects.
5. Write one focused change set that conforms to `schema/change-set-0.1.schema.json`. Set `baseRevision` to the inspected revision and add preconditions for every important value the request assumes.
6. Prefer `moveAnchor` for coordinated geometry, `moveOpening` for hosted placement, `putObject` for complete registry objects, and `set` for narrow parameters. Inspect incoming relationships before deletion and express each coordinated removal as an explicit transaction operation.
7. Dry-run through the guarded workflow:

   ```bash
   python skills/home-design/scripts/design_transaction.py MODEL CHANGE --dry-run
   ```

8. After the dry run passes, apply the transaction and rebuild both adapter outputs:

   ```bash
   python skills/home-design/scripts/design_transaction.py MODEL CHANGE
   ```

9. Reinspect changed and integrated elements. Review applicable clearance/load/drainage diagnostics, layer sections, schedules and solar studies. Report the new revision, material design effects, validation result, and viewer/IFC/report paths. A dry run validates geometry but does not execute exporters; verify the completed build separately.

If the request is materially ambiguous, ask one focused question before writing. Treat every validation failure as an active design constraint: explain the specific invariant, revise the transaction, and run validation again.

## Measurement conversion

Interpret dimensions in the measurement system used by the requester. Store canonical lengths in millimetres and present a familiar US customary equivalent alongside metric results when it helps review.

Use the conversion script for each US customary length that affects authored geometry:

```bash
python skills/home-design/scripts/convert_length.py "8 ft 6 1/2 in" --to mm
python skills/home-design/scripts/convert_length.py "2603.5 mm" --to ft-in
```

The JSON result's `millimetres` field supplies the canonical value. Preserve that value through the transaction; apply dimensional rounding when the requester specifies a tolerance or precision. Derive areas and volumes from converted canonical lengths. Ask one focused question when a source dimension lacks a unit or has multiple plausible interpretations.

## New design

Create a schema-valid canonical JSON object using `examples/single-story-gable-house.json` (Single-Story Gable House) as a core reference or `examples/hillside-deck-house.json` (Hillside Deck House) for construction/site features. Example member sizes and dimensions are illustrative, not engineered inputs. Choose semantic, stable IDs before adding cross-references. Add reusable materials and types before elements, add explicit relationships after their participants, then run:

```bash
home-design validate MODEL --json
home-design build MODEL --output build --web-assets web/public/model
```

Completion requires both commands to succeed. IFC4 is the CAD output, including for import into FreeCAD.

Use `examples/complete-shell-coordination-house.json` (Complete Shell Coordination
House) for explicit wall/floor/roof/deck framing, service branches and sealed
penetrations. Its service-partition anchors coordinate mounted electrical/water
components, an interior ledge and owned cuts. Its mechanical anchor controls the
separate insulated air branch. Inspect cavity, generated-member, circuit and
service schedules alongside the framing/services views after edits.

## Model collections

`validate` and `build` accept multiple paths or quoted glob patterns, such as
`home-design build 'examples/*.json' --web-assets web/public/model`. JSON reports
use a `models` array for any input count. Keep patterns limited to canonical model
files, excluding change sets and generated JSON.

Build artifacts are under `<output>/<filename-stem>/`, where `--output` defaults
to `build` and the stem is the source filename without `.json`. Rebuilding replaces
that generated model directory. The last input with a matching stem wins. Browser
publication defaults to `--web-assets-mode merge`, retaining other homes. The
guarded transaction script also merges its rebuilt model into the collection.
Use `--web-assets-mode replace` when the selected sources define the intended
complete publication set; it removes other managed models and superseded browser
versions. Check the collection before sharing because merge retains previously
published private homes. Use the returned artifact paths and the viewer's model
selector to review the intended home; the viewer initially opens the first by
project name. Read `docs/guides/export-and-sharing.md` for collection workflows.

For a shareable static website, use `home-design website-export MODEL... --output
build/website`. This builds an isolated collection containing exactly the selected
homes and packages the viewer without changing local preview assets. Node/npm
and installed `web/` dependencies are required. The output directory is disposable
and replaced on subsequent exports. Exporting is local; upload only when the user
requests deployment to the intended audience. Read
`docs/guides/website-deployment.md` for preview and hosting options.

## Modeling rules

- Keep X east, Y north, Z up; keep local geometry near the building origin.
- Distinguish placement constraints from semantic relationships even when both connect the same components.
- Use host locators for construction points that must follow a wall face/layer,
  roof plane, slab/footing surface or individual member. Inspect layer indices and
  roof face IDs before editing. Local offsets position geometry without creating
  cuts or support relationships; retain explicit connection intent separately.
- Model doors and windows through an opening plus `voids` and `fills`; derive wall or screen-panel cuts from those relationships.
- Use `penetration` elements for owned service holes, recesses, notches and bearing
  seats. Inspect each host and selected layer before cutting; review the actual
  removed and remaining volumes after the transaction. Cutters extrude along local
  positive Z, so outward host frames normally need a 180-degree local rotation to
  cut inward. Author one cut per host and avoid overlapping cut ownership.
- Add named penetration `limits` for supplied hole/notch dimensions, extent
  fractions and directional material margins. Use a locator on the cut's own host,
  selecting the affected member, layer or roof face. Review actual removed extents
  and margin results after host edits; neighboring cuts remain material boundaries.
  Directional margins test a continuous sweep, not a radial nearest-edge distance.
  Preserve the requirement reference and severity without inventing engineering
  limits or treating a passing geometric check as approval.
- Use roof surface constraints for walls intended to follow roofs.
- Use bearing-referenced roofs when overhang edits must preserve plate/ridge geometry. Roof layer thickness is normal to the slope; sample actual undersides and add explicit porch/entry clearance checks.
- Compose decks and stair landings with slabs, flights with stairs, repeated framing with member arrays, and stepped foundations with coordinated footing/wall segments. Screens and structural guards are separate components; preserve clear stair widths with following handrails.
- For enclosed porches, use roof-constrained screen tops on horizontal two-point baselines. Check closure at the roof, deck and house, and separation from guards/posts. Host screen doors in panels with explicit screen infill materials and review their swing envelopes against adjacent equipment.
- Record explicit loads and support paths for ridge/spa/deck systems. Bearing-point and connectivity checks do not calculate capacity or certify structure.
- Preserve existing/proposed terrain separately. Use `home-design import-survey` to prepare a revision-checked change; review coordinate units/origin before the guarded transaction. Never extrapolate unknown grade.
- For aggregate cavities, use one physical layer with concurrent material fractions,
  not stacked insulation and framing depths. Preserve energy inputs in unit-explicit
  performance fields and record consultant requirements/references.
- For individually modeled cavity parts, use an explicit layer with its infill
  material and part `occupies.regions`; remove aggregate material fractions from
  that layer. Use host locators for coordinated placement. Review fit mode,
  ownership conflicts and the final infill/part/void balance after cuts, then
  inspect the framing or services view.
- Use `wallFraming` with authored rectangular member types for host-driven plates,
  stud packs, opening framing, blocking and backing. Inspect generated member keys
  before overriding or mounting to them; use scoped member host `part` references.
  Coordinate segment indices and end insets at wall bends/corners. Review actual
  member and cavity quantities after cuts; framing recipes do not size structure.
- Use `planarFraming` for boundary-fitted floor/deck framing or a selected roof
  face. Inspect its layer, face ID and resolved plane before setting directions,
  grid offsets and blocking stations. Keep roof measurements in the surface
  plane; review adjacent-face miters, hole rims and generated member quantities.
- Use profile sweeps for drainage/trim and details for reusable interface instructions. Check drainage fall, connected endpoints and outlet/footing exclusions.
- Use `memberAssembly` for authored truss chords/webs, ties and bracing networks.
  Inspect scoped node/member keys, declare intersecting joints with `trimAgainst`,
  and retain host locators for coordinated endpoints. Review final child solids
  and connections after cuts. Use `endCuts` for planar stock end treatments and
  owned penetrations for local bearing seats or notches.
- Use `curvedMember` for circular structural arcs with explicit `chordTolerance`.
  Review the resolved error bound, analytic lengths and tessellated material
  quantities. Curved mounts use analytic axis stations; skin mounts are unsupported.
- Use `hardware` with reusable local stock/cut recipes for construction connectors.
  Specify connection participants separately from mounting coordinates, including
  scoped generated member keys where needed. Inspect the surviving participants
  and actual hardware volume after cuts. Use `fastenerGroup` with authored counts
  and either scheduled representation or named detailed placements; scheduled
  groups contribute type-based material quantities without individual meshes.
- Place service hangers with a `route` host locator and an analytic `station`.
  Select `branch` for a fitting trunk or named branch. Review the transported
  section axes before applying offsets/rotations, retain explicit hardware
  participants, and use the services discipline for service supports. Stations
  follow route edits and reject locations beyond a shortened path; support
  dimensions, spacing and fastening remain authored inputs.
- Use explicit footing representation and body layer 0 when reinforcement or
  grout displaces foundation concrete. Author bar/tie paths with bend radii and
  approximation tolerances, and mesh dimensions with explicit wire spacing and
  layer separation. Review nominal stock lengths alongside actual net volumes.
  Place masonry units, grout and mortar as disjoint `masonryPart` solids or use
  host infill for remaining material; review the final cavity balance after cuts.
- Use an `attaches` relationship for interfaces such as a deck connection so the canonical graph carries durable connection intent.
- Use `serviceDevice` for generic fabricated equipment with authored local ports.
  Specify each port's medium, mating technology, section, outward direction and
  source/sink/bidirectional flow. Declare internal buses/passages with type
  `portGroups`; branches require distinct external ports. Use `connectsPorts`
  relationships and explicit port membership in `serviceSystem` and optional
  `serviceCircuit` elements. Review connectedness, system separation and exact
  mating alignment. Unconnected ends need authored open/capped `portStates`;
  these states do not create termination solids.
- Use port locators when geometry must follow a device interface. Inspect the
  resolved port frame and retained `portPlacements` before changing orientations.
  Semantic connections do not position equipment; geometry references must stay
  acyclic even when the service network itself forms a loop.
- Use explicit electrical device roles on `serviceDeviceType` for receptacles,
  boxes, switches, panels/protection, lighting/detection, communications and
  grounding/bonding parts. Supply typed `electrical` ratings and purposeful ports.
  Match `function` on device, route and fitting interfaces; distinguish carrier
  entries from conductors. Inspect native IFC types, retained ratings and actual
  mounting/cavity geometry. Author bonds and buses explicitly with port groups.
- Use typed cable/conduit specifications on route types for stock designations,
  nominal conductor schedules and authored current/data/fill limits. Keep actual
  outside dimensions independent of trade sizes; nominal stock schedules do not
  create extra material. Add a circuit `schedule` with its actual panel output,
  unique panel number and electrical or communications specification. Include
  complete route endpoint membership. Inspect unknown rating checks, declared
  loads and any path bypassing the authored protective device after edits.
- Use `serviceRoute` for pipe, duct, cable and conduit paths with authored outside
  dimensions, wall thickness where hollow, bend radius and chord tolerance.
  Inspect transported `start`/`end` port frames, especially for rectangular routes.
  Coordinate both ports through explicit service systems and external mates.
  For cavity routes, displace physical stock with `occupies` and empty the bore
  with an owned `penetration.geometrySource` referencing the route's `bore`,
  `envelope` or `clearance` construction volume. Review actual removed volume and
  final infill balance; construction masks are nonmaterial and do not render.
- Use typed pipe specifications and occurrence `conditions` for authored stock,
  pressure and temperature limits. Add `fallCheck` with an explicit direction and
  minimum drop/run ratio for gravity coordination. Inspect each span after moving
  endpoints; a net drop does not permit a rising intermediate leg. Keep all ports
  on a route/fitting within one system and use equipment interfaces between
  systems. Retain unknown ratings and flow inputs without inferring hydraulics.
- Use plumbing device roles for valves, manifolds, fixture connections, cleanouts,
  heaters, pumps, tanks and meters. Supply typed `plumbing` specifications and
  actual fabricated bodies/ports. Keep separate system interfaces explicit on
  equipment, including powered interfaces with electrical ratings/functions.
  Use a pipe `trap` fitting for a rounded return passage; inspect its lowered
  centerline after placement. The return check does not calculate a water seal.
- Use `serviceInsulation` with a pipe/duct route or fitting `host`, a reusable
  material/thickness type and `chordTolerance`. Review its separate stock volume,
  fitting branches and covered cap ends. Declare cavity ownership and insulation
  cuts explicitly, retaining the pipe's own bore cut. Refine host and covering
  tolerances for thin layers; final insulation parts on one host cannot overlap.
  Size route-mounted supports around the finished cover and include it among
  connection participants when appropriate; thickness edits do not resize hardware.
- Add `duct` stock specifications and `ductConditions` to duct routes/fittings
  when pressure, temperature or airflow inputs are known. Pressure conditions are
  signed; positive/negative pressure ratings are positive magnitudes. Review
  `ductRatingChecks` and preserve unchecked airflow performance. Nominal lining
  and leakage specifications do not create material or inferred calculations.
- Use mechanical device roles with a typed `mechanical` designation, actual
  fabrication geometry and explicit air/fluid interfaces. Heat-recovery units
  require two disjoint air passage groups; specified coil technologies require
  matching energy interfaces. Keep refrigerant, condensate, power and signal
  systems separate. Add electrical ratings/functions to powered equipment and
  author service-access volumes with `clearanceZone`.
- Use `serviceFitting` for reusable elbows, branched passages, size/shape transitions
  and physical caps. Inspect generated `start`/`end` and named branch ports before
  connecting routes. Branch roots must fit their trunk's passage; keep external
  mating faces exposed. For port-based placement, author the type's starting face
  at the local origin facing negative Z. Apply the same cavity ownership and
  construction-volume cuts as routes. Review native IFC fitting and port families,
  material volume and explicit system membership after coordinated edits.
- Use `accessory` and `envelopePart` for physical hosted ledges, niches, access
  panels, membranes, flashing and seals. Supply actual reusable fabrication
  geometry: extrusions, full revolutions of nonnegative radius/height profiles,
  and local stock/cut placements. Review projection and final mounting extents.
  Recessed parts require explicit cavity ownership or owned host penetrations.
- Use envelope `sleeve` and `protectivePlate` roles with an explicit `interface`
  construction host and service references. Add the same declaration to service
  fire, acoustic and weather seals. Keep route-relative mounting separate from
  these participants; author each passage, stock dimension and host cut. Review
  surviving scoped host identity, disjoint material and cavity contributions after
  edits. Interface declarations do not create holes, resize parts or establish
  rated performance; use authored specifications and barrier probes as needed.
- Use component host frames for access spaces and cuts that follow a placed
  part's complete pose. `clearanceZone` checks final physical obstructions,
  excluding its owner and explicit allowed parts. `barrierCheck` probes an
  authored interface between envelope pieces or selected host layers; inspect
  missing participants, connected regions and actual uncovered volume. Treat
  these as local geometric checks, with authored error/warning severity. Their
  nonmaterial volumes remain outside material schedules, drawings and shading.
- Add service `coordinationChecks` with authored interference severity for
  physical clash review after cuts and cavity composition. Routes/fittings also
  support clearance checks against their outside envelope plus authored margin.
  Inspect individual obstacle IDs and measured volumes, then resolve real stock
  overlaps. Clearance allowances and explicit cover/interface/support connections
  apply only to installation space; they do not suppress material collisions.
  Review retained exclusion reasons, use scoped member references when needed,
  and keep equipment maintenance spaces in `clearanceZone`.
- Represent spaces explicitly by default. Derive a space from boundary walls when they form one unambiguous closed loop around its seed.
- State analysis limits explicitly: coordination geometry and authored requirements do not replace structural engineering, hydraulic analysis, annual energy/certification modeling, code review or permit/fabrication drawings. Preserve professional inputs without claiming independent verification.

Read `docs/guides/model-authoring.md` when field semantics are needed, `docs/guides/ai-design-workflow.md` for coordinated transactions/survey/solar workflows, and `docs/guides/export-and-sharing.md` for IFC, drawings, schedules and energy handoffs. For authorized engine changes, follow `docs/architecture.md`: extend schema, reference/validation, shared resolution, adapters, focused tests and user guides together. Never edit generated outputs as implementation fixes or stage Git changes.
