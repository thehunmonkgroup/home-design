---
name: home-design
description: Safely create, inspect, and modify IFC-aligned home designs from natural-language requests. Use for architectural design changes, component or relationship edits, model validation, Three.js preview rebuilds, and IFC exports in this repository. Use the repository development workflow for engine implementation.
---

# Home Design

Use the canonical home JSON as the editable source of every design decision. Apply requested changes through validated transactions against that source, then regenerate `build/`, `web/public/model/`, resolved meshes, GLB nodes, and IFC entities as disposable outputs.

## Existing design

1. Run `home-design validate MODEL --json`.
2. Run `home-design inspect MODEL`; then inspect each affected element with `--element ID --relationships`.
3. Trace integrations before proposing changes: shared anchors, reusable types, hosts/openings/fills, joins, supports, attachments, space boundaries, and assemblies.
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

9. Reinspect changed and integrated elements. Report the new revision, material design effects, validation result, and viewer/IFC artifact paths.

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

Create a schema-valid canonical JSON object using `examples/reference-home-0.1.json` only as a structural reference. Choose semantic, stable IDs before adding cross-references. Add reusable materials and types before elements, add explicit relationships after their participants, then run:

```bash
home-design validate MODEL --json
home-design build MODEL --output build --web-assets web/public/model
```

Completion requires both commands to succeed. IFC4 is the current CAD output; native FreeCAD features and `.FCStd` generation remain future adapter work.

## Modeling rules

- Keep X east, Y north, Z up; keep local geometry near the building origin.
- Distinguish placement constraints from semantic relationships even when both connect the same components.
- Model doors and windows through an opening plus `voids` and `fills`; derive wall cuts from those relationships.
- Use roof surface constraints for walls intended to follow roofs.
- Use an `attaches` relationship for interfaces such as a deck connection so the canonical graph carries durable connection intent.
- Represent spaces explicitly by default. Derive a space from boundary walls when they form one unambiguous closed loop around its seed.
- State version 0.1 limitations explicitly and reserve authoritative structural, MEP, code, fabrication, and construction-document data for future schema and resolver extensions.

Read `docs/guides/model-authoring.md` only when field semantics are needed, and `docs/guides/ai-design-workflow.md` when designing a multi-component transaction.
