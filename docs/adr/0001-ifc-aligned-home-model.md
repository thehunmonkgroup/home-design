# ADR 0001: IFC-aligned home authoring model

- Status: Accepted
- Date: 2026-09-04
- Model version: 0.1

## Context

The only design interface is conversational: an AI translates English requests into changes, validates them, and regenerates a Three.js preview. The same source must later produce stable, editable building data for FreeCAD. A Three.js scene graph or triangle mesh cannot be authoritative because it loses design intent, exact curves, host relationships, reusable types, and BIM semantics. Raw IFC is unsuitable as the authoring format because it is verbose and indirect for routine AI edits.

Existing work informs the decision:

- IFC supplies a mature vocabulary for spatial containment, types, openings, fillings, connections, boundaries, assemblies, and multiple geometric representations.
- Hypar Elements demonstrates a compact, ID-addressable building model that can serialize to JSON, glTF, and IFC.
- BHoM and Speckle demonstrate the value of separating an object model from computation and application adapters.
- IfcOpenShell can deterministically create IFC axes, swept solids, openings, fillings, and connections.
- Current text-to-BIM research supports tool-constrained edits plus rule checking; unconstrained LLM geometry editing is not reliable enough for engineering data.

## Decision

Use a compact, normalized, IFC-aligned JSON authoring graph as the sole source of truth. It is not an IFC serialization. It contains editable design intent and uses IFC-like semantics that adapters can map to a chosen IFC version.

The model has these top-level registries:

- `project`, `units`, and `coordinateSystem`
- `levels` and reusable `anchors`
- `materials` and reusable component `types`
- ID-keyed `elements`
- ID-keyed, role-specific `relationships`

All registry keys are stable IDs. Renaming or moving an object must not change its ID. References use those IDs; array positions never establish identity.

The canonical coordinate system is right-handed, Z-up, X-east, Y-north. Lengths are millimetres and angles are degrees. Georeferencing is stored separately from the local building origin. The Three.js adapter maps canonical `(x, y, z)` to Three.js `(x, z, -y)` and scales millimetres to metres. Export adapters perform their own explicit unit conversions.

Architectural elements retain parametric definitions:

- Walls use a plan path, location line, type, and vertical constraints.
- Slabs use a planar footprint, type, datum, and role such as floor, foundation, or deck.
- Roofs use either a parametric footprint recipe or explicit planar faces.
- Openings retain host-relative placement and a rectangle or profile.
- Doors and windows fill openings and reference reusable types.
- Spaces use an explicit footprint or a seed point for later boundary derivation.

Generated Three.js meshes, tessellations, Boolean results, bounding boxes, IFC entity numbers, and FreeCAD shapes are build artifacts and must not be written back as authoritative geometry.

Relationships are explicit and typed. Version 0.1 includes `voids`, `fills`, `joins`, `supports`, `attaches`, `bounds`, and `aggregates`. Each relationship has semantic role names instead of ambiguous `source` and `target` fields. Mere geometric contact never implies a durable relationship.

Placement constraints and semantic relationships are distinct. For example, a wall may have a base constrained to a slab's top surface while a `supports` relationship records the load/assembly meaning. An opening's local placement is owned by the opening, while `voids` identifies its host and `fills` identifies its door or window.

AI modifications should be applied as transactional domain changes with preconditions, even when implemented initially as JSON patches. A change is committed only after:

1. JSON Schema validation.
2. Reference, type, and dependency-cycle checks.
3. Topology checks such as valid profiles, compatible hosts, and non-overlapping openings.
4. Geometry generation checks.
5. Exportability checks for elements affected by the change.

The Three.js and IFC/FreeCAD outputs are separate deterministic adapters over the same resolved model. IFC is the first CAD interchange target. A later FreeCAD Python adapter may create native `.FCStd` features where doing so preserves useful parametric behavior beyond IFC.

## IFC mapping intent

| Authoring concept | IFC intent |
| --- | --- |
| Storey level | `IfcBuildingStorey` |
| Wall | `IfcWall` with Axis and Body representations |
| Slab / deck | `IfcSlab` with an appropriate predefined type |
| Roof | `IfcRoof` aggregated from slabs or faces as needed |
| Opening and `voids` | `IfcOpeningElement` + `IfcRelVoidsElement` |
| Door/window and `fills` | `IfcDoor`/`IfcWindow` + `IfcRelFillsElement` |
| Space and `bounds` | `IfcSpace` + `IfcRelSpaceBoundary` |
| Reusable type | IFC type object + `IfcRelDefinesByType` |
| Wall join | `IfcRelConnectsPathElements` where applicable |
| Assembly | `IfcRelAggregates` or `IfcRelNests` |

The adapter owns exact IFC-version choices. The authoring schema must not expose IFC EXPRESS entity graphs or STEP line identifiers.

## Consequences

Benefits:

- The AI edits concise, named parameters and relationships instead of triangles.
- Shared anchors and host-relative placement make coordinated changes predictable.
- Three.js preview geometry can be regenerated quickly and discarded safely.
- IFC and FreeCAD adapters receive stable identity, exact dimensions, and explicit semantics.
- JSON Schema versioning and deterministic migrations can evolve the model.

Costs and limitations:

- JSON Schema cannot verify cross-reference existence, polygon topology, dependency cycles, or geometric fit; a semantic validator is required.
- The two geometry adapters require conformance tests so their results do not drift.
- Some complex or organic components will need custom parametric recipes or, as a last resort, imported mesh representations.
- Model version 0.1 intentionally covers the architectural core, not structural analysis, MEP routing, code compliance, fabrication details, or construction documentation.

## Compatibility rule

Readers must reject unsupported major model versions. Additive backward-compatible fields increment the minor version; breaking field or semantic changes require a migration and a new major version.
