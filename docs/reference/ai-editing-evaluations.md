# Representative AI editing evaluations

These evaluations measure whether an AI can discover the supported authoring
workflow and carry out coordinated changes. Component presence in an example,
automated engine tests and successful AI editing are separate forms of evidence.
Coverage is representative: it does not establish every combination of geometry,
equipment variant or downstream CAD application's behavior.

## Evaluation protocol

Each evaluator receives a construction request, repository access and a separate
temporary workspace, without the implementation conversation. It starts with
`AGENTS.md` and the home-design skill, follows task-specific references, and uses
public examples, schemas and the package CLI. Implementation and test code are
excluded from evaluator discovery. The coordinating developer diagnoses and fixes
reported defects; fresh evaluators check blocked authoring workflows after repairs,
and focused rechecks verify improved diagnostic payloads.

Acceptance requires a guarded changeset, preview, dry run, completed transaction
and IFC/GLB exports. Measurements must establish the requested change, coordinated
dependents, stable identities and preservation of unrelated objects. Expected
rejections must preserve the saved source. Export receipts alone are insufficient.
Evaluators record commands, references loaded, failed assumptions, diagnostics,
recovery attempts and context burden. Browser review and actual FreeCAD import
are recorded separately from engine exports.

The tables below retain the completed editing punch list and its evidence.
Proposed development and downstream CAD work remain in [TODO.md](../../TODO.md).

## Verified baseline

The baseline independent trial records concern a coordinated authoring fixture.
Their saved measurements below describe those trial inputs, not the current public
models. The maintained [worked edits](../../skills/home-design/references/examples.md)
and `tests/integration/test_authoring_examples.py` exercise the same teaching topics
on Assemblies, Hillside and Master Suite. Automated migration checks do not imply
new independent AI trials.

| Editing task | Verified outcome |
| --- | --- |
| Translate the serviced wall | Thirty affected components and eleven generated members follow; quantities and eighteen independent mechanical components remain unchanged. A fresh retry moves the wall north without command repairs. |
| Resize one occurrence of shared window stock | The north window becomes 1350 mm wide; the east window, rough opening and sill remain unchanged. |
| Insert and reorder named layers | A 9 mm lining is added, then lining order changes; twenty framing identities and cavity, box and cut references survive. |
| Duplicate and adapt a deck | A separate 5200 × 4600 mm deck at elevation 2300 mm retains coordinated framing, beams, posts and pads; original objects remain unchanged. A fresh retry verifies compact inspection/preparation output. |
| Reject an oversized fill and repair the edit | An 1800 mm window fails with `fill.exceeds-opening` without altering source bytes; a corrected local 1380 mm window exports successfully. |

These trials expose and verify fixes for external-workspace environment discovery,
anchor-operation syntax, placement dependency traversal and excessive saved-report
output. They do not constitute independent editing coverage for all components
merely carried along by a wall or deck translation.

## Representative coverage

| Exercise | Component families and integration decisions |
| --- | --- |
| Roof pitch | `roof`, `planarFraming`, `sweep`, `envelopePart`, `penetration`; ridge joins, layers and drainage interfaces |
| Electrical addition | `serviceDevice`, `serviceRoute`, `serviceSystem`, `serviceCircuit`, `wallFraming`, `penetration`; ports, recesses, circuits and schedules |
| Foundation and membrane | `footing`, `reinforcingBar`, `reinforcingMesh`, `masonryPart`, `barrierCheck`, `envelopePart`; cover, continuity and material quantities |
| Plumbing connection | `accessory`, `serviceFitting`, `serviceRoute`, `serviceDevice`, `serviceSystem`; open boundaries, fall, sleeves, seals and host cuts |
| Mechanical change | `serviceInsulation`, `serviceFitting`, `serviceRoute`, `serviceDevice`, `hardware`, `clearanceZone`; oriented sections, supports and access |
| Framing detail | `wallFraming`, `planarFraming`, `memberAssembly`, `curvedMember`, `member`, `hardware`, `fastenerGroup`; stable generated keys, trims and connections |
| Detailed fasteners | `fastenerGroup`, `hardware`, `member`; named physical instances, overlap rejection and exported quantities rather than scheduled counts alone |
| Hillside grade | `terrain`, `framing`, `member`, `footing`, `stair`, `load`, `detail`, `sweep`; sampled datums, load/support paths and drainage |
| Entrance change | `slab`, `stair`, `railing`, `panel`, `door`; coordinated rise, clear openings and interfaces |
| Room and opening edits | `space`, `wall`, `opening`, `window`, `door`; boundaries, rehosting, references and removal |
| Package composition | `assembly`; instantiation, nesting, connection points, independent local changes and adaptation conflicts |
| Site and delivery | Survey conversion, georeference, solar studies, drawings, reports and selected model publication |
| Guarding and recovery | Stale revisions/value guards, publication failure, recovery journal and installed resources |

All 38 registered component families have a designated exercise. A family receives
editing coverage only after its behavior is changed or explicitly verified in the
corresponding trial; presence in an exported model does not qualify by itself.

## Extended trial results

| Exercise | Result and independent evidence |
| --- | --- |
| Roof pitch | Pass on a fresh retry after the serialization repair. Revision 7→8 changes pitch to 30° and rise to 1010.363 mm. Layer depths, the mitered ridge, all 22 member identities, cavity balance, fixed eaves/drainage and four owned junction cuts are verified. All 245 unrelated resolved objects and IFC identities are preserved. The retry needs no modeling/export repairs. |
| Electrical addition | Pass after two diagnosed fit corrections. Revision 1→2 adds a recessed outlet, widened local box, tee and cable runs while retaining existing loads. All fourteen circuit ports are reachable, seven mates have zero gap and opposing normals, and removing the breaker disconnects both outlets. Circuit 2 cable length is 1212.123889804 mm; both original 900 VA load declarations remain unchanged. All 121 unrelated existing resolved elements and the framing schedule remain equal. |
| Electrical guide retry | Pass with the first complete candidate, discovered through public skill links. A second catalog outlet, tee and three cable segments retain a fourteen-port protected circuit, seven exact mates and the original 900 VA load. Independent lengths sum to 2525.123889804 mm; 78 physical intersection checks find no collisions and the manufactured entry clears the cable by 0.993442 mm. All 198 unrelated resolved objects and 382 original IFC element identities remain stable. The new tee's unspecified ratings correctly leave the circuit partially checked. The same trial verifies the full inward door sweep and native opening dimensions. |
| Foundation and membrane | Pass. Guarded revision 7→8 adds 100 mm footing depth below its fixed top: concrete increases 0.132 m³. Lower bars move with the bottom, preserving 92 mm cover; upper mesh retains 138 mm top cover. All 45 masonry parts, wall, drain and unrelated resolved objects remain equal. A physically stepped 20 mm membrane lap reports zero gap and one connected region without relaxing the probe. |
| Mechanical branch | Pass. Revision 1→2 extends a terminal branch from 300 to 700 mm and changes local insulation from 10 to 20 mm. Eight oriented mates, a connected seventeen-port system, support fit, coverage and clear access are verified; only three resolved objects change and 100 remain equal. A deliberate obstruction is rejected with exact source preservation; a retry confirms the diagnostic names the blocker and 22944 mm³ intrusion. |
| Plumbing connection | Pass. Revision 7→8 connects supply and waste extensions and moves the passage's sleeve, seals, plate and cut exactly 50 mm. Both new mates have zero gap/opposing normals; 237 unrelated resolved elements remain equal. An uphill candidate is rejected without source changes. The existing horizontal waste port retains a 200 mm mating tangent followed by two 3% descending spans; the nonascending check does not claim positive fall on that original horizontal interface. |
| Framing details | Pass through four transactions. A stud moves 50 mm while retaining its scoped/IFC identity and seventeen other members. A truss apex rises 100 mm with trim/gusset coordination and all 64 scheduled screws retained. A curved member is added, then its radius changes from 1000 to 1200 mm; analytic lengths and tessellated quantities are independently checked. |
| Detailed fasteners | Pass with 28 checks through two guarded exports. Four scheduled screws become named physical instances, then increase to six. Their 8468.680924 mm³ total agrees across resolved/IFC/GLB geometry, and the detailed scheduled contribution is zero. Count mismatch and coincident instances reject while preserving all 22 source/export hashes. All 260 unrelated resolved objects remain equal. Manual geometry checks establish plate/post contact; group IFC identity and named GLB roles remain stable, while indexed scene-node names can shift. |
| Hillside grade | Pass with 21 measured checks. Proposed terrain rises 100 mm while finished surfaces remain fixed; sixteen footings rise and fifteen posts shorten. Explicit sixteen-riser authoring preserves the stair's 4200 mm run and landing alignment. Five support branches still connect the shifted 31000 N load to footings. Drain fall remains 0.025 against 0.01 minimum, with 2389.31 mm footing clearance against the retained 1000 mm exclusion. Installation-note and load-footprint edits also export. |
| Entrance construction | Pass with 64 measured checks. Landing rises 175 mm, flight becomes seven 175 mm risers with 1680 mm run, and supports/cap stations/guards/screens follow. A locally widened door retains a 920 mm clear estimate and its corrected inward sweep stays on the landing. All original IDs/relationships and 216 unrelated resolved elements remain equal. This trial identifies the catalog orientation and native IFC dimension improvements below. |
| Rooms, rehosting and removal | Pass with 58 checks through six exported revisions, with the axis-area limitation identified separately. Rehosting transfers a 0.353276 m³ opening cut from north to east wall; coordinated deletion restores it. IFC kernel geometry, GLB triangles, per-layer volumes, fill nodes, joins and stable GUIDs are checked. Incomplete removal rejects with three incoming-reference paths. |
| Package composition | Pass with 23 checks through eleven guarded exports. A partition and supported deck share placement, form a nested assembly and translate seventeen physical components together while retaining the base/top interface. Local edits survive parameter adaptation; an overlapping height change rejects with its exact conflict path and preserves source/IFC/GLB. Deliberate conflict resolution and shared/private stock changes work. All thirteen original resolved records remain equal after rebuilding the baseline with the same engine. |
| Interior room boundary | Pass on a fresh trial with 242 checks through migration and two editing transactions. The interior rectangle changes from 9815 × 7815 to 9815 × 8815 mm, increasing area from 76.704225 to 86.519225 m². IFC/GLB bounds and volumes, wall joins, openings, all 129 IFC GUIDs and unrelated geometry are verified. A seed in wall stock rejects with a specific diagnostic and preserves source/export hashes. |
| Site and delivery | Pass. Foot and metre survey inputs with nonzero XYZ origins convert to the expected millimetres. Georeference, winter/summer solar studies and drawings export. A repeated-framing edit changes spacing from 332 to 320 mm: five of six members move, volume remains 0.48384 m³ and 105 unrelated resolved objects remain equal. The selected two-model website contains sixteen allowed files without source models, IFC files or transaction journals. Browser review confirms model switching, the edited six-member framing group and mobile viewport fit. |
| Installed guards and recovery | Pass using a built wheel outside the checkout; all 94 loaded engine modules come from the installation. Stale revision/value guards preserve sixteen source/artifact hashes. A real publication-path obstruction fails after saving; two recoveries preserve the exact revision-3 source hash and publish matching metadata without reapplying the changeset. |
| Installed recipe upgrade and native dimensions | Pass. The packaged prior entrance template is instantiated, then adapted using the documented previous-recipe route. All 83 mapped IDs remain stable and the full inward swing moves onto the landing. Native IFC dimensions for the two doors and window match their hosted openings; both models validate with no diagnostics and export IFC/GLB. |

## Failure-driven improvements

- Roof infill Boolean output can contain contact loops that collapse during
  boundary normalization. Such loops are filtered before triangulation; both
  native reimport and independent triangle volumes must still pass the existing
  tolerance. Regression checks change a mitered, framed roof to 30° and 35° and
  compare native IFC geometry with resolved material volumes.
- Cavity infill failures retain the host ID, source path and layer selector so
  an author can locate the affected material.
- Access and barrier diagnostics expose measured obstruction IDs/volumes or
  gap/coverage evidence directly, making a rejected edit actionable.
- Capability output and composition guidance distinguish frames a component
  provides from its own permitted placement. An empty direct-host target list
  does not prohibit `placement.host` mounting.
- Inspection guidance distinguishes the CLI's root `.data`, resolved-model
  `.elements[]` array and manifest `.elements[ID]` mapping. Evaluators repeatedly
  confuse these when writing supplementary measurement queries; the reference
  includes a focused lookup and directs them to returned artifact paths.
- Electrical guidance starts branch additions with a short coordinated-edit
  workflow, then links to detailed stock, port, fitting and cavity contracts only
  as needed. It distinguishes real box entries from wall cuts, physical fit from
  cavity ownership, and graph membership from geometric contact.
- The public entrance's door-bearing screen baseline is reversed with
  landing-surface locators, making its inward operation agree with the enclosure.
  Recipe adaptation updates the catalog through a guarded revision and preserves
  all identities. A regression checks the complete swing envelope over the landing.
- Native IFC door/window overall dimensions use the hosted opening dimensions;
  nominal stock and clear passage remain separate. The IFC contract documents
  this distinction and a regression checks both fills against their openings.
- Derived rooms offer explicit `geometry.boundaryMode: "interior"` to exclude
  full bounding-wall plan thickness; the default remains `axis`. Resolved
  `areaBasis` makes that distinction visible. Tests cover unequal stock, location
  lines, reversed paths, concavity, holes and invalid/empty/disconnected interiors.
- Stair guidance explicitly distinguishes elevation datums from plan connection
  constraints. Automatic riser selection can shorten the run without a validation
  error; fixed-landing edits must preserve or coordinate the run and verify the
  endpoint. Explicit plan-connection constraints remain proposed work in TODO.

## Discoverability and limits

The skill entry point is 860 words and the focused electrical workflow is 538
words. Evaluators discover commands, migration, prior recipe templates and recovery
through public references without implementation access. Successful discovery is
not always minimal: the interior trial loads about 8,700 words of project guidance
and example data, and the installed recovery/recipe trial loads about 43 KB of
primary reference text. Broad multi-domain reads and supplementary measurement
scripts account for much of that context. Narrow heading reads and saved, focused
inspection reports avoid the large responses some initial attempts encounter.
The entry point links directly to branch extension and starts dependency inspection
with twenty-record pages to make those smaller routes easier to choose.

The measured outcomes establish authoring and export behavior, not construction
certification. Participant relationships do not infer geometric contact or movement;
explicit hosting, constraints and independent measurements remain necessary.
Scheduled fasteners establish counts without individual positions. Circuit checks
retain missing-rating uncertainty instead of inventing equipment specifications.
Interior room area uses the documented gross wall-stock convention, not an inferred
regulatory area standard. Stair plan connection constraints remain proposed work.

IFC files are reopened and selected geometry is measured with IfcOpenShell's native
kernel; GLB geometry and viewer controls are checked separately. Actual FreeCAD
import, CAD edit round trips and every geometric/component permutation remain
outside this evaluation. The CAD interoperability backlog identifies those distinct
validation and development tasks.

## Regression verification

The full Python run passes 951 tests. A focused follow-up passes 69 tests covering
the later room-area, IFC, catalog and installed-package changes, including the
26 added cases. Together these verify all 977 currently collected cases; this is
a full run plus targeted reconciliation, not a claim that one run collects every
new case. Combined coverage exceeds the repository's 80% gate. The isolated
follow-up's 77.43% global coverage is expected for that subset; all its tests pass.

All 90 viewer tests pass, as do Python lint/type checks and viewer type checking,
lint and production build. The skill validator passes, local Markdown links are
checked, and the coverage matrix includes all 38 registered families. A separate
read-only code review reports no substantive correctness or regression findings.
Evaluation sources and generated artifacts stay in temporary workspaces; repository
regressions use public examples and minimal synthetic inputs.
