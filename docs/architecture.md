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
      └── GLB + render manifest ──→ Three.js viewer
```

The native FreeCAD adapter is a deliberately absent peer of the IFC and glTF adapters. It must consume `ResolvedModel`; it must not become another source of truth.

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
| `changes.py` | Revision/precondition enforcement, operation dispatch, atomic commit |
| `adapters/ifc.py` | IFC4 types, bodies, axes, containment, materials, and relationships |
| `adapters/gltf.py` | Three.js coordinate conversion, materials, GLB, node manifest |
| `build.py` | Staging and atomic multi-adapter artifact publication |
| `cli.py` | Supported validate, inspect, apply, and build workflows |

All geometry stays in canonical millimetres through `ResolvedModel`. The glTF adapter alone converts to Three.js metres/Y-up. IFC declares millimetre project units and consumes resolved vertices without an implicit scale.

## TypeScript components

`web/app/lib/model.ts` is the runtime and static render-manifest contract. `HomeViewer.tsx` loads GLB and manifest together, indexes loader-safe node names back to stable canonical IDs, and owns only presentation state. It does not calculate building geometry.

The viewer uses Vinext/Vite and conditionally enables the Sites Vite plugin when the ignored `web/.openai/hosting.json` exists. That local file contains deployment identity and resource bindings, never application secrets. Ordinary clones build without it and use empty D1/R2 bindings.

The active viewer assets under `web/public/model/` are also ignored because they may represent a private home. The TypeScript integration test reads a committed reference manifest from `web/tests/fixtures/` instead.

## Determinism and identity

- Resolved JSON, GLB, manifest, diagnostics, and metadata are byte-stable for an unchanged source.
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

Component tests target decisions with expensive failure modes: schema rejection, missing or mistyped references, dependency cycles, anchor propagation, watertight profiles with holes, all roof recipes, explicit roof constraints, derived spaces, opening cuts, fill clearance, join connectivity, transaction conflicts, and atomic commit.

Integration tests exercise the supported workflow and cross-adapter contracts: canonical JSON through CLI, resolver, IFC4 validation, stable GUIDs, GLB scene nodes, render manifest, and web asset publication. TypeScript tests cover manifest compatibility, display grouping, scene-object selection, measurement formatting, and the generated Python-to-viewer manifest.

Run every gate before merging:

```bash
pytest --cov --cov-report=term-missing
flake8 src tests
basedpyright --project pyproject.toml

cd web
npm test
npm run typecheck
npm run lint
npm run build
```
