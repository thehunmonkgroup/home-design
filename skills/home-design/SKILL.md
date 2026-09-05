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
- Model doors and windows through an opening plus `voids` and `fills`; derive wall or screen-panel cuts from those relationships.
- Use roof surface constraints for walls intended to follow roofs.
- Use bearing-referenced roofs when overhang edits must preserve plate/ridge geometry. Roof layer thickness is normal to the slope; sample actual undersides and add explicit porch/entry clearance checks.
- Compose decks and stair landings with slabs, flights with stairs, repeated framing with member arrays, and stepped foundations with coordinated footing/wall segments. Screens and structural guards are separate components; preserve clear stair widths with following handrails.
- For enclosed porches, use roof-constrained screen tops on horizontal two-point baselines. Check closure at the roof, deck and house, and separation from guards/posts. Host screen doors in panels with explicit screen infill materials and review their swing envelopes against adjacent equipment.
- Record explicit loads and support paths for ridge/spa/deck systems. Bearing-point and connectivity checks do not calculate capacity or certify structure.
- Preserve existing/proposed terrain separately. Use `home-design import-survey` to prepare a revision-checked change; review coordinate units/origin before the guarded transaction. Never extrapolate unknown grade.
- Use one physical cavity layer with concurrent material fractions, not stacked insulation and framing depths. Preserve energy inputs in unit-explicit performance fields and record consultant requirements/references.
- Use profile sweeps for drainage/trim and details for reusable interface instructions. Check drainage fall, connected endpoints and outlet/footing exclusions.
- Use an `attaches` relationship for interfaces such as a deck connection so the canonical graph carries durable connection intent.
- Represent spaces explicitly by default. Derive a space from boundary walls when they form one unambiguous closed loop around its seed.
- State analysis limits explicitly: coordination geometry and authored requirements do not replace structural engineering, hydraulic analysis, annual energy/certification modeling, code review or permit/fabrication drawings. Preserve professional inputs without claiming independent verification.

Read `docs/guides/model-authoring.md` when field semantics are needed, `docs/guides/ai-design-workflow.md` for coordinated transactions/survey/solar workflows, and `docs/guides/export-and-sharing.md` for IFC, drawings, schedules and energy handoffs. For authorized engine changes, follow `docs/architecture.md`: extend schema, reference/validation, shared resolution, adapters, focused tests and user guides together. Never edit generated outputs as implementation fixes or stage Git changes.
