---
name: home-design
description: Create, inspect, and modify canonical home designs through validated JSON changesets, coordinated components, browser review, and IFC exports. Use the repository development workflow for engine implementation.
---

# Home Design

Canonical home JSON stores design intent. Apply edits to that source through the
guarded transaction workflow, then regenerate IFC, GLB, resolved JSON, manifests,
diagnostics and reports. Generated files are disposable.

## Essential rules

- Keep stable IDs when moving, renaming or resizing existing objects. Store lengths
  in millimetres and angles in degrees; X is east, Y north and Z up.
- Distinguish placement, physical connection, material ownership and design
  requirements. A connection alone does not move geometry, resize hardware or
  create a cut. Shared type edits affect every occurrence using that type.
- For custom designs, use supported validation, transaction, build and inspection
  commands. Keep custom files and outputs outside repository tests and fixtures.
  Engine changes require separate authorization unless the user already requested
  that development. For authorized engine work, follow
  [architecture](../../docs/architecture.md) and public/synthetic regression coverage.
- Preserve supplied engineering inputs and references. Geometry and authored
  requirement checks do not establish structural capacity, service sizing,
  regulatory approval or rated performance.
- Never stage Git changes.

## Choose the references for this task

Read [editing](references/editing.md) before changing an existing model. Use the
relevant sections of [composition](references/composition.md) for shared types,
anchors, hosts or assemblies; read it fully for new designs. Load domain guidance
only for fields or integrations the task changes. A link is a discovery route,
not an instruction to load every linked document.
For a long reference, list its headings first (`rg -n '^#{1,3} ' FILE`) and read
only the relevant section. Moving a shared anchor without changing hosted stock
usually needs editing, inspection and placement semantics; inspect the actual
dependents and preview before loading electrical, plumbing or framing field manuals.

For a simple occurrence-only dimension/type edit, editing, inspection and the
local-type section of changesets are usually sufficient, together with
[shared-type semantics](references/composition.md#shared-types-and-local-changes).
Read only the opening/window section of architectural guidance if fill behavior
is unclear. Delivery guidance is needed when changing publication or sharing,
rather than for the standard transaction build below.

| Task | Reference |
| --- | --- |
| Compact source/measurement queries and dependency discovery | [Inspection](references/inspection.md) |
| Local type edits, rehosting, removal and propagation review | [Changesets](references/changesets.md) |
| Named layers/boundaries, generated-part identity and input-format conversion | [Scoped identities](references/identities.md) |
| Instantiate, duplicate, adapt and combine reusable packages | [Assemblies](references/assemblies.md) |
| Walls, floors/decks, roofs, openings and rooms | [Architectural shell](references/architecture.md) |
| Hosted placement, layer selections, cavities, holes and recesses | [Layers and cuts](references/layers-cuts.md) |
| Studs, joists, rafters, trusses and member overrides | [Framing](references/framing.md) |
| Connectors, fasteners, reinforcement and masonry | [Hardware](references/hardware.md) |
| Ledges, niches, access spaces, sleeves, seals and membranes | [Envelope and accessories](references/envelope.md) |
| Service ports, systems, circuits and connectedness | [Service interfaces](references/services.md) |
| Pipe/duct/cable paths, fittings, insulation and passage masks | [Routes](references/routes.md) |
| Receptacles, boxes, panels, cable stock and circuit schedules | [Electrical](references/electrical.md) |
| Water/waste/vent/gas, equipment and gravity fall | [Plumbing](references/plumbing.md) |
| Air systems, equipment, refrigerant and condensate | [Mechanical](references/mechanical.md) |
| Grade, foundations, stairs, guards, drainage and loads | [Site and construction](references/site.md) |
| Survey import and solar studies | [Site workflows](references/site-workflows.md) |
| Builds, model collections, drawings and sharing | [Delivery](references/delivery.md) |
| Public model selection and worked coordinated edits | [Examples](references/examples.md) |

## Existing model workflow

Run commands from the design workspace. Use `home-design resources` to locate
installed schemas, this skill and public examples when working outside a checkout.
Use `home-design capabilities --kind KIND` when choosing compatible component families.

1. Validate the source with `home-design validate MODEL --json`.
2. Discover IDs with `home-design inspect MODEL`, then inspect affected objects
   with `--object ID --references --dependents --relationships`. Use `--type-users`
   before changing a reusable type. Follow pagination and depth limits; see
   [inspection](references/inspection.md).
3. Write a focused changeset using the inspected revision and preconditions for
   important assumed values. Use [preparation and preview](references/changesets.md)
   for coordinated operations and actual before/after effects. See
   [editing](references/editing.md) for committing and recovery.
4. Dry-run with
   `home-design transact MODEL CHANGE --dry-run`.
5. Apply with
   `home-design transact MODEL CHANGE --web-assets web/public/model`.
6. Verify the completed build, reinspect measurements with `--view resolved`, and review relevant
   quantities, diagnostics and viewer views. Report the saved revision, design
   effects, validation result and artifact paths. A dry run does not test exporters.

Export preparation precedes saving. If publication fails after saving, use the
returned `home-design recover JOURNAL` command to publish that exact revision.
Read the recovery instructions in [editing](references/editing.md).

## New model and measurements

Start with the smallest suitable [public example](references/examples.md). Define
materials/types before their occurrences and explicit relationships after their
participants. Completion requires both `home-design validate MODEL --json` and
`home-design build MODEL --output build --web-assets web/public/model` to succeed.

Convert each US customary length used in geometry with
`home-design convert-length "8 ft 6 1/2 in" --to mm`.
Use its `millimetres` value without extra rounding unless requested. Clarify units
or materially ambiguous design intent when the existing context does not resolve it.
