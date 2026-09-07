# Shared resolved contracts

Canonical JSON stores authoring intent. Domain resolvers produce shared physical
geometry in millimetres; processing stages reconcile it before adapters and reports
consume it. `ResolvedElement` and `MeshData` carry physical meshes, stable source
identity and supplementary JSON metadata. Export adapters use those final meshes.

## Typed boundaries

| Contract | Consumers and invariant |
| --- | --- |
| `LocalFrame` | Host placement, generated stock, service interfaces and IFC ports use an origin and right-handed orthonormal axes. `from_dict` rejects nonfinite or distorted frames. |
| `GeneratedMember` | Member end cuts, generated children, host lookup and schedules share a scoped key, reusable type, role, stock axis/section, frame and explicit length/volume quantities. |
| `AssemblyLayer`, `MaterialShare` | Geometry, material schedules and IFC layer descriptions share one physical thickness and validated concurrent material fractions. Fractions sum to one. |
| `ResolvedPort`, `PortSection` | Network compatibility and IFC ports share oriented, sized interfaces, flow, medium, connection type and optional electrical function. |
| `Quantity` | Measurements carry their unit and dimension. Conversion accepts compatible units and rejects length/area/volume confusion and nonfinite values. IFC length remains millimetres; native area and volume use square/cubic metres. |

Generated-member records retain supplementary details such as end cuts, trimming
relationships, profiles and authored properties. Updating final volume preserves
the scoped identity and nominal stock. Those details remain JSON rather than
requiring every discipline to share one large object hierarchy. Shared consumers
read typed contracts instead of independently decoding the same required fields.

The legacy repeated-framing family exports its existing indexed children. Named
wall, planar and member assemblies use `GeneratedMember` records. Capability
registration distinguishes generated children from assemblies that support scoped
member hosting.

## Construction processing

`ConstructionPipeline` validates its declared order before executing any stage.
Every `ProcessingStage` names its prerequisites. Duplicate stages and missing or
out-of-order prerequisites fail with structured pipeline diagnostics.

The standard sequence performs:

1. Cavity composition, followed by owned cuts and final cavity quantities.
2. Route and insulation refresh, then surviving generated-member quantities.
3. Hardware participants, mounted parts and service interfaces.
4. Service clearances, access spaces and barrier checks.
5. Service networks and circuit schedules using the same resulting port graph.

`ProcessingContext` retains the resolved element registry, pre-cut cavity regions,
network graph and completed stages. A stage failure retains its name alongside
the underlying diagnostic context. Domain stages still own their geometry and
coordination rules; the pipeline defines their exchange order.

When extending processing, declare the evidence the new stage requires and bind
its implementation in the standard pipeline. Test a missing-prerequisite failure
and the physical integration it introduces. Validate IFC/GLB geometry, material
ownership and schedules against the same final result; successful registration
alone does not establish those invariants.
