# Home Design

Home Design is an AI-oriented architectural authoring system. You describe a change in ordinary language; an AI translates it into a small transactional JSON change, validates the whole building, and regenerates a browser preview and an IFC file.

The editable source is an IFC-aligned JSON graph. Three.js meshes and IFC entities derive from the same resolved geometry, giving the browser view and CAD export one shared design source.

> This early design and coordination tool supports architectural exploration. Structural analysis, code compliance, fabrication, and permit documents require review and production by qualified professionals.

## What is included

- Canonical components for levels, anchors, materials, reusable types, walls, slabs, decks, roofs, openings, doors, windows, spaces, and assemblies.
- Parametric stairs, stringers, guards, handrails, screen panels, structural members, repeated framing, footings, terrain, profile sweeps, loads, and interface details.
- Host-relative face/layer coordinates and owned penetrations, recesses, notches and bearing seats with actual cut solids and net material quantities.
- Wall framing recipes for plates, opening packages, roof-fitted studs, corner packs, blocking and backing, with stable member references and explicit cavity quantities.
- Floor, deck and roof-face framing layouts that fit polygonal boundaries and holes, with individual perimeter boards, blocking and adjacent-roof miters.
- Authored trusses and member networks with named joints, explicit trimming, beveled end cuts, and circular structural members with controlled tessellation.
- Reusable fabricated connection hardware and scheduled or individually placed fastener groups, with material quantities and native IFC connection participants.
- Analytic route/fitting stations for hangers and other placed parts, retaining exact bend positions and section orientation through service edits.
- Reinforcing bars, rounded ties, wire meshes, masonry units, grout and mortar, with explicit foundation/cavity material ownership and native IFC parts.
- Hosted ledges, niches, access panels and envelope interfaces, with extruded/revolved fabrication shapes, physical mounting fit and native IFC parts/coverings.
- Authored access volumes and local barrier continuity probes, with obstruction/gap diagnostics and nonmaterial coordination geometry.
- Generic fabricated service devices with oriented mating ports, connected systems/circuits, port-based placements and native IFC network relationships.
- Electrical and communications device roles with typed ratings, power/signal/grounding/containment interfaces and concrete native IFC device types.
- Typed cable/conduit stock and power/communications circuit schedules with panel identities, authored rating checks and declared protection-path validation.
- Typed pipe stock, authored operating-condition checks and directional gravity-fall validation, with rigid/flexible native IFC pipe classifications.
- Plumbing device roles for valves, manifolds, fixture connections, cleanouts, heaters, pumps, tanks and meters, plus rounded trap passages and native IFC equipment types.
- Separate physical pipe/duct insulation following routes and fittings, with cavity ownership, local cuts, material quantities and native IFC coverings.
- Circular/rectangular pipe, duct, cable and conduit routes with tangent bends, hollow passages, construction clearances and route-shaped owned host cuts.
- Typed duct stock and signed pressure/temperature checks, with authored airflow inputs and native rigid/flexible IFC classifications.
- Typed mechanical equipment, including dampers, air terminals, fans, heat recovery and coils, with separate air/fluid/power interfaces and native IFC products.
- Reusable service elbows, branched fittings, size/shape transitions and physical caps, with connected passages, generated ports and native IFC fitting families.
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
home-design build 'examples/*.json'

cd web
npm install
npm run dev
```

This publishes the three public examples to the local viewer.

Open the local URL printed by the web command. Choose a model in the top-bar model selector.
Select a component in the left index or directly in the model; its resolved measurements appear in the inspector.
See the [Browser viewer guide](docs/guides/viewer-guide.md) for navigation, filtering,
visibility, isolation, requirements and sun-study controls.
The public collection contains three complementary examples:

| Example | What it demonstrates |
| --- | --- |
| [Assemblies](examples/assemblies.json) | Nine separate construction packages with layers, framing, services and connections. The [catalog guide](docs/guides/assembly-catalog.md) explains inspection and reuse. |
| [Hillside Deck House](examples/hillside-deck-house.json) | A two-storey home with terrain, foundations, deck, stairs, guards/screens, drainage and solar studies. Follow its [cutaway walkthrough](docs/guides/viewer-guide.md#cutaway-views-of-hillside-deck-house). |
| [Master Suite Gable House](examples/master-suite-gable-house.json) | A detailed framed shell, bedroom and ensuite, electrical circuits and plumbing. Its [twelve-view tour](docs/guides/master-suite-gable-house.md) includes interiors, plan, framing and services. |

Select a **Saved view** in the viewer, or discover prepared views with
`home-design views MODEL` and capture one with
`home-design render MODEL --named-view ID --output DIRECTORY`.
The [worked edits](skills/home-design/references/examples.md#complete-changeset-examples)
cover window placement, shared stock, named layers, serviced-wall rotation and
package duplication/adaptation using these same models. Dimensions and product
specifications illustrate authoring capabilities and require project-specific
engineering before construction.

## The conversational workflow

Ask the AI for a specific design outcome in ordinary language, for example:

> Move the north living-room window 500 mm east. Keep its sill height and rough opening unchanged.

The AI should:

1. Inspect the affected component, its reusable type, and its relationships.
2. Write a revision-checked change set against the canonical model.
3. Dry-run the transaction to check schema, references, topology, and geometry.
4. Save the canonical JSON after validation succeeds.
5. Rebuild the IFC and browser assets for your review.

See [Working with the AI](docs/guides/ai-design-workflow.md) for requesting and
reviewing edits and [Understanding your home model](docs/guides/model-authoring.md)
for the underlying concepts. The [home-design skill](skills/home-design/SKILL.md)
routes AI authors to task-specific field references and the guarded edit protocol.

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
home-design transact design/home.json changes/move-window.json --dry-run

# Prepare exports, save a new revision file and publish it
home-design transact design/home.json changes/move-window.json \
  --output design/home-rev-1.json --web-assets web/public/model

# Regenerate CAD and web artifacts
home-design build design/home-rev-1.json \
  --output build \
  --web-assets web/public/model
```

Add `--debug` before the command name for diagnostic logging, such as `home-design --debug build ...`. Use `--schema PATH` before the command only when developing a compatible schema variant.

`home-design resources` locates schemas, public examples, recipes and the progressive skill
in either an installed package or a checkout. `home-design convert-length "8 ft 6 1/2 in"`
returns canonical millimetres. `transact` prepares all adapters before saving and
returns a journal for recovering interrupted publication with `home-design recover JOURNAL`.
See the [editing reference](skills/home-design/references/editing.md) for failure states.

`home-design recipes` discovers reusable partition and deck packages. Their named
parameters coordinate construction; `prepare` creates ordinary changesets for
instantiation, duplication and updates that preserve independent local edits.
See [reusable assemblies](skills/home-design/references/assemblies.md).

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
| `schedules.json` | Components, cavities, framing, hardware, reinforcement, service systems/circuits, materials, loads and interface details |
| `envelope.json` | Areas, orientations, performance, boundary assignments, shading meshes, and solar results |
| `drawings.svg` | Orthographic elevations and section cuts with dimensions |

The canonical home JSON and intentional change-set JSON form the authoring history. Apply design changes there, validate the revision, and regenerate the output artifacts.

## Documentation

- [Working with the AI](docs/guides/ai-design-workflow.md)
- [Understanding your home model](docs/guides/model-authoring.md)
- [Home-design skill and technical authoring references](skills/home-design/SKILL.md)
- [IFC representation contract](docs/reference/ifc-contract.md)
- [Browser viewer guide](docs/guides/viewer-guide.md)
- [Images for AI design review](docs/guides/visual-inspection.md)
- [IFC export and website sharing](docs/guides/export-and-sharing.md)
- [Website export and deployment](docs/guides/website-deployment.md)
- [Architecture and developer guide](docs/architecture.md)
- [Accepted model ADR](docs/adr/0001-ifc-aligned-home-model.md)
- [Canonical model schema](schema/home-model-0.2.schema.json)
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
