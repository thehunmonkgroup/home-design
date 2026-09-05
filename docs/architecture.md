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
FreeCAD interoperability uses IFC4 import.

## Python components

| Module | Responsibility |
| --- | --- |
| `loader.py` | JSON loading and Draft 2020-12 schema diagnostics |
| `graph.py` | ID registries, typed references, relationship lookup, dependency cycles |
| `validation/semantic.py` | Cardinality, compatibility, and domain invariants |
| `validation/topology.py` | Profiles, joins, opening fit/overlap, explicit roof planarity |
| `locators.py` | Shared point, axis, station, level, path, and profile resolution |
| `geometry.py` | Polygon, wall-profile, box, and roof-plane geometry primitives |
| `resolver.py` | Element and relationship integration into absolute shared geometry |
| `components.py`, `construction.py` | Typed construction resolution, oriented members, shared-miter sweeps, repeated framing, stairs, guards and screens |
| `roof_controls.py`, `layers.py`, `doors.py`, `screens.py` | Bearing/overhang roof controls, physical material layers, framed doors and profiled screen enclosures |
| `terrain.py`, `survey.py` | Triangulated grade surfaces, bounded elevation queries and revision-checked survey import changes |
| `coordination.py` | Bearing bounds, load paths, drainage connections/outlets, grade exposure and numeric requirements |
| `requirements.py` | Shared numeric requirement evaluation and failure diagnostics |
| `solar.py`, `reports.py` | Geographic solar vectors, sampled geometric shading, schedules and envelope exports |
| `changes.py` | Revision/precondition enforcement, operation dispatch, atomic commit |
| `adapters/ifc.py` | IFC4 types, bodies, axes, containment, materials, and relationships |
| `adapters/ifc_properties.py` | Lossless specification/property data, material layer sets, concurrent cavity constituents and item styles |
| `adapters/drawings.py` | Orthographic SVG projections, mesh-plane sections with holes and explicit dimensions |
| `adapters/gltf.py` | Three.js coordinate conversion, materials, GLB, node manifest |
| `batch.py` | Ordered input expansion, deduplication and per-model validation reports |
| `build.py` | Batch staging, per-model directory replacement and publication rollback |
| `publication.py` | Immutable browser assets, managed cleanup and atomic catalog publication |
| `cli.py` | Validate, inspect, apply, build, import-survey and solar workflows |

All geometry stays in canonical millimetres through `ResolvedModel`. The glTF adapter alone converts to Three.js metres/Y-up. IFC declares millimetre project units and consumes resolved vertices without an implicit scale.

## Batch builds and browser catalog

`BuildService.build_many` validates all inputs and stages all adapter outputs before
replacing any generated model directory. Inputs are processed in order, with the
last source for a filename stem supplying that output. `build` delegates a single
source to the same workflow. Artifact paths in `BuildResult` include the model
subdirectory; the guarded transaction script consumes those returned paths.

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

## Construction resolution and coordination

The authoring schema uses `modelVersion: "0.1"`.
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

1. Add authoring intent to the JSON Schema and a representative fixture.
2. Add typed reference extraction and semantic compatibility rules.
3. Add topology checks that can reject invalid inputs before resolution.
4. Resolve absolute, adapter-neutral geometry and metadata.
5. Map the new resolved kind in IFC.
6. Decide whether it is visible/selectable in GLB and the manifest.
7. Add focused unit tests for its parameters and integration tests for its relationships and both adapters.
8. Update end-user documentation and the project skill's edit guidance.

## Test strategy

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
