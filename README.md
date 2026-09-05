# Home Design

Home Design is an AI-oriented architectural authoring system. You describe a change in ordinary language; an AI translates it into a small transactional JSON change, validates the whole building, and regenerates a browser preview and an IFC file.

The editable source is an IFC-aligned JSON graph. Three.js meshes and IFC entities derive from the same resolved geometry, giving the browser view and CAD export one shared design source.

> This early design and coordination tool supports architectural exploration. Structural analysis, code compliance, fabrication, and permit documents require review and production by qualified professionals.

## What is included

- Canonical components for levels, anchors, materials, reusable types, walls, slabs, decks, roofs, openings, doors, windows, spaces, and assemblies.
- Parametric stairs, stringers, guards, handrails, screen panels, structural members, repeated framing, footings, terrain, profile sweeps, loads, and interface details.
- Bearing-referenced roofs, independent edge overhangs, dependent roof elevations, true normal-thickness undersides, and explicit clearance checks.
- Separate finish layers and concurrent framing/insulation cavities, detailed sliding/swing doors, typed product performance, and checked design requirements.
- Explicit `voids`, `fills`, `joins`, `supports`, `attaches`, `drainsTo`, `bounds`, and `aggregates` relationships.
- Layered schema, reference, semantic, topology, geometry, and exportability validation.
- Revision-checked transactions with preconditions and atomic writes.
- Survey CSV import through guarded changes, terrain-connected elevations, support-path and drainage coordination.
- Resolved JSON, IFC4, GLB, render-manifest, diagnostics, build metadata, construction schedules, envelope/shading exports, and dimensioned SVG drawings.
- Geographic date/time solar studies and a responsive Three.js review site with component selection, properties, optional space volumes, section clipping, and study lighting.
- Python and TypeScript component tests plus Python-to-web and Python-to-IFC integration tests.

IFC4 is the CAD interchange format, including for import into FreeCAD.

## Quick start

The repository pins Python through pyenv and requires Node 22.13 or newer.

```bash
pyenv activate home-design
python -m pip install -e '.[dev]'

home-design validate 'examples/*.json'
home-design build 'examples/*.json' \
  --output build \
  --web-assets web/public/model

cd web
npm install
npm run dev
```

Open the local URL printed by the web command. Choose a home in the top-bar model selector.
Select a component in the left index or directly in the model; its resolved measurements appear in the inspector.
The two-storey construction example is
[Hillside Deck House](examples/hillside-deck-house.json).
It demonstrates coordinated terrain, foundations, framing, stairs, screen/guard
separation, a dependent porch roof, drainage, product specifications, and solar
studies. Its dimensions and specifications are illustrative and require
project-specific engineering before construction.
The example has a complete two-storey shell with separate indoor floors and four
independently hideable walls per storey. Use the eye buttons beside **Lower — … wall**
and **Upper — … wall** for cutaway views; the canonical walls remain intact.

## The conversational workflow

Ask the AI for a specific design outcome in ordinary language, for example:

> Move the north living-room window 500 mm east. Keep its sill height and rough opening unchanged.

The AI should:

1. Inspect the affected component, its reusable type, and its relationships.
2. Write a revision-checked change set against the canonical model.
3. Dry-run the transaction to check schema, references, topology, and geometry.
4. Save the canonical JSON after validation succeeds.
5. Rebuild the IFC and browser assets for your review.

See [AI design workflow](docs/guides/ai-design-workflow.md) for the exact safe sequence and [Model authoring guide](docs/guides/model-authoring.md) for the underlying concepts.

## Common commands

```bash
# Structured validation diagnostics
home-design validate design/home.json --json

# Discover stable IDs and component kinds
home-design inspect design/home.json

# Inspect one component and every relationship that mentions it
home-design inspect design/home.json \
  --element wall.north \
  --relationships

# Validate a proposed change while preserving source files
home-design apply design/home.json changes/move-window.json --dry-run

# Save to a new revision file
home-design apply design/home.json changes/move-window.json \
  --output design/home-rev-1.json

# Regenerate CAD and web artifacts
home-design build design/home-rev-1.json \
  --output build \
  --web-assets web/public/model
```

Add `--debug` before the command name for diagnostic logging, such as `home-design --debug build ...`. Use `--schema PATH` before the command only when developing a compatible schema variant.

`validate` and `build` accept multiple files or quoted globs such as `'examples/*.json'`.
Outputs default to `build/<filename-stem>/`. Browser publication keeps other models
by default; add `--web-assets-mode replace` to publish only the selected homes.
See [export and sharing](docs/guides/export-and-sharing.md) for details.

To package a standalone website containing only the selected homes:

```bash
home-design website-export 'examples/*.json' --output build/website
```

Upload the resulting folder to a static host. See [Website export and deployment](docs/guides/website-deployment.md)
for previewing, sharing, and an optional free Cloudflare Pages upload command.

## Generated output artifacts

Every build artifact is a reproducible representation of the canonical home JSON:

| File | Generated representation |
| --- | --- |
| `resolved-model.json` | Absolute coordinates and adapter-neutral meshes |
| `model.ifc` | IFC4 BIM/CAD interchange model |
| `model.glb` | Compact Three.js scene |
| `render-manifest.json` | Stable element-to-scene-node mapping and inspector data |
| `diagnostics.json` | Machine-readable validation result |
| `build-metadata.json` | Source revision, SHA-256, and artifact inventory |
| `schedules.json` | Components, openings, framing, foundations, materials, loads, and interface details |
| `envelope.json` | Areas, orientations, performance, boundary assignments, shading meshes, and solar results |
| `drawings.svg` | Orthographic elevations and section cuts with dimensions |

The canonical home JSON and intentional change-set JSON form the authoring history. Apply design changes there, validate the revision, and regenerate the output artifacts.

## Documentation

- [AI design workflow](docs/guides/ai-design-workflow.md)
- [Model authoring guide](docs/guides/model-authoring.md)
- [IFC export and website sharing](docs/guides/export-and-sharing.md)
- [Website export and deployment](docs/guides/website-deployment.md)
- [Architecture and developer guide](docs/architecture.md)
- [Accepted model ADR](docs/adr/0001-ifc-aligned-home-model.md)
- [Canonical model schema](schema/home-model-0.1.schema.json)
- [Change-set schema](schema/change-set-0.1.schema.json)
- [Development backlog](TODO.md)

## Development checks

```bash
pytest --cov --cov-report=term-missing
flake8 .
basedpyright .

cd web
npm test
npm run typecheck
npm run lint
npm run build
```
