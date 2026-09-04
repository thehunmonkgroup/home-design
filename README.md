# Home Design

Home Design is an AI-oriented architectural authoring system. You describe a change in ordinary language; an AI translates it into a small transactional JSON change, validates the whole building, and regenerates a browser preview and an IFC file.

The editable source is an IFC-aligned JSON graph. Three.js meshes and IFC entities derive from the same resolved geometry, giving the browser view and CAD export one shared design source.

> This early design and coordination tool supports architectural exploration. Structural analysis, code compliance, fabrication, and permit documents require review and production by qualified professionals.

## What is included

- Canonical components for levels, anchors, materials, reusable types, walls, slabs, decks, roofs, openings, doors, windows, spaces, and assemblies.
- Explicit `voids`, `fills`, `joins`, `supports`, `attaches`, `bounds`, and `aggregates` relationships.
- Layered schema, reference, semantic, topology, geometry, and exportability validation.
- Revision-checked transactions with preconditions and atomic writes.
- Deterministic resolved JSON, IFC4, GLB, render-manifest, diagnostics, and build metadata.
- A responsive Three.js review site with orbit, pan, zoom, component selection, resolved properties, and optional space volumes.
- Python and TypeScript component tests plus Python-to-web and Python-to-IFC integration tests.

IFC4 is the current CAD interchange path. A native FreeCAD adapter is planned for a future version.

## Quick start

The repository pins Python through pyenv and requires Node 22.13 or newer.

```bash
pyenv activate home-design
python -m pip install -e '.[dev]'

home-design validate examples/reference-home-0.1.json
home-design build examples/reference-home-0.1.json \
  --output build \
  --web-assets web/public/model

cd web
npm install
npm run dev
```

Open the local URL printed by the web command. Select a component in the left index or directly in the model; its resolved measurements appear in the inspector.

## The conversational workflow

Ask the AI for a specific design outcome in ordinary language, for example:

> Move the north living-room window 500 mm east. Keep its sill height and rough opening unchanged.

The AI should:

1. Inspect the affected component, its reusable type, and its relationships.
2. Write a revision-checked change set against the canonical model.
3. dry-run the transaction so schema, references, topology, geometry, and exports are checked.
4. Commit the canonical JSON only after validation succeeds.
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

# Commit to a new revision file
home-design apply design/home.json changes/move-window.json \
  --output design/home-rev-1.json

# Regenerate CAD and web artifacts
home-design build design/home-rev-1.json \
  --output build \
  --web-assets web/public/model
```

Add `--debug` before the command name for diagnostic logging, such as `home-design --debug build ...`. Use `--schema PATH` before the command only when developing a compatible schema variant.

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

The canonical home JSON and intentional change-set JSON form the authoring history. Apply design changes there, validate the revision, and regenerate the output artifacts.

## Documentation

- [AI design workflow](docs/guides/ai-design-workflow.md)
- [Model authoring guide](docs/guides/model-authoring.md)
- [IFC export and website sharing](docs/guides/export-and-sharing.md)
- [Architecture and developer guide](docs/architecture.md)
- [Accepted model ADR](docs/adr/0001-ifc-aligned-home-model.md)
- [Canonical model schema](schema/home-model-0.1.schema.json)
- [Change-set schema](schema/change-set-0.1.schema.json)

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
