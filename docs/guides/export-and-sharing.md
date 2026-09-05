# IFC export and website sharing

One build creates CAD and browser outputs from each selected model's validated revision.

## Build a revision

```bash
home-design build design/home.json \
  --output build \
  --web-assets web/public/model
```

The build produces IFC, browser assets, drawings and reports in
`<output>/<filename-stem>/`. The `--output` root defaults to `build`, and the stem
is the source filename without `.json`. In the command above, `design/home.json`
therefore produces `build/home/`.
Rebuilding replaces that generated model directory. Other model directories and
files outside the replaced directory are preserved.

### Build a collection

```bash
home-design validate 'examples/*.json' --json
home-design build 'examples/*.json' \
  --output build \
  --web-assets web/public/model
```

Both commands accept multiple filenames and glob patterns. Quote patterns for CLI
expansion; unquoted shell-expanded filenames also work. Recursive `**` patterns
are supported. Each pattern's matches are sorted, repeated paths are processed
once, and missing inputs or unmatched patterns fail the command. Every matched
file must be a canonical model, so keep patterns separate from change-set JSON.

Validation reports every selected model's diagnostics and returns a failure exit
code if any model fails. Build validates and stages all selected models before
publishing; validation or export failure leaves completed outputs unchanged.
Matching filename stems replace the same output model, with the last input winning.

The optional `--web-assets` directory holds the complete viewer collection. Each
published home includes its GLB, render manifest, drawings, schedules and envelope
report. The viewer discovers homes through the generated catalog; publish through
the build command rather than manually copying files into the collection.

- `--web-assets-mode merge` is the default: update selected models and retain
  other published homes. Guarded design transactions use this behavior too.
- `--web-assets-mode replace` publishes exactly the selected homes and removes
  other managed models and superseded browser asset versions. Unrelated files
  are preserved. Generated assets can be recreated by rebuilding their sources.

Merge keeps earlier browser asset versions available to open viewers. Replace is
appropriate for preparing a deployment with an explicit set of homes; open
viewers may need a page reload after replacement. Review the published collection
before deploying: merge retains any private homes previously published there.
The build summary lists added, updated, retained and removed model keys.
Website deployment and IFC sharing are separate actions.

## Review in the browser

```bash
cd web
npm install
npm run dev
```

The review site provides:

- a top-bar model selector, alphabetized by human-readable project name,
- orbit with the primary pointer,
- pan with the secondary pointer,
- wheel or gesture zoom,
- **Frame model** to fit the complete model to the current viewport with a surrounding margin,
- direct or index-based component selection,
- resolved dimensions and canonical IDs,
- hidden-by-default space volumes,
- per-kind construction groups, including terrain, stairs, framing and drainage,
- project-wide design requirements and component-specific resolved requirements,
- **Cut** axis and millimetre position controls for interactive clipping,
- **Sun study** choices and selected-opening direct-sun results,
- links to drawings, schedules and envelope exports.

The first home by project name loads on page load. The selector lists the complete
published collection; geometry loads only for the selected home. Duplicate project
names include the filename stem to distinguish them.

Switching homes refreshes the project title, revision, components, requirements,
inspector and report links. Each home starts with its default visibility, framed
camera, presentation lighting and Cut set to Off. Selection and sun-study choices
are cleared. If a home fails to load, retry it or choose another home. Reload the
page to discover newly published models.

The **Model north** compass rotates with the camera's orbit heading. It indicates
canonical +Y north, not surveyed true north, and is a read-only orientation aid.
Panning and zooming do not change its heading. Hover over **Orbit**, **Pan**, or
**Zoom** for a short mouse, touchpad, or touchscreen instruction popup; the hints also open on keyboard
focus or tap. Press Escape to dismiss a hint.

**Design requirements** separates each requirement's result from its violation
severity. **Satisfied** and **Violated** describe the numeric checks for the built
revision, with actual and required values per target. **Not automatically checked**
identifies notes or requirements without a check and target; **Status unavailable**
means the loaded assets provide no evaluation result. Violation severity describes
how a failed check is handled, not whether it failed. Error-level violations block
a build; warning- and info-level violations can appear in a completed build.
These checks cover authored numeric constraints, not engineering approval.

Components with 3D geometry have an eye button to hide or show them. Components
without independent 3D geometry remain selectable in the index for property
inspection and have no visibility button. **Show all** restores all components
with 3D geometry, including space volumes. **Show spaces** is available when the
model contains rendered space volumes. Visibility changes affect only the view;
they do not change the saved design or fill in openings in a host wall.

Clipping is a visual cut, not a capped solid or a model edit. Use the SVG sections
for material-filled cuts. Solar percentages come from the built study; moving the
camera or section plane does not recompute them. The default presentation light is
not a site/date calculation. Rebuild after adding or changing persistent studies.

### Cutaway views of Hillside Deck House

[Hillside Deck House](../../examples/hillside-deck-house.json) includes four exterior walls on each storey, a lower concrete
floor and an upper floor assembly whose underside is the lower ceiling. Both
storeys are open-plan shells. Wall names identify their storey and compass direction.

- Click a wall's eye button in **Components → Walls** to hide just that storey's
  wall, including all of its material layers.
- Doors and windows are independent components: hide their eye buttons too when
  removing a host wall from a cutaway view.
- Hide **Upper — indoor floor / lower ceiling** to look down into the lower floor;
  hide the main roof to look into the upper floor.
- Space volumes start hidden. Leave **Show spaces** off when inspecting interiors.
  **Show all** restores every component, including spaces; uncheck **Show spaces**
  afterward if needed.

Visibility controls affect only the view; the saved design and IFC retain the
complete shell.

## Run a production preview

Run these commands from the `web` directory:

```bash
npm run build
npm run start
```

The build copies model assets from `web/public/model/` into `web/dist/`, which the production preview serves. Generate them with
`home-design build design/home.json --web-assets web/public/model` from the repository root before previewing or deploying
a design, and rebuild both the models and viewer whenever the design changes.
For a self-contained website with exactly the selected homes, use
[`home-design website-export`](website-deployment.md).

## Import IFC into FreeCAD

1. Build `model.ifc` from the desired canonical revision.
2. In FreeCAD, use **File → Import** and select the IFC file.
3. Enable the BIM/Arch IFC importer if your FreeCAD installation asks for a workbench or importer.
4. Confirm units are millimetres.
5. Check the storey, walls, slabs, roof, opening/fill relationships, space, and assembly tree.
6. Preserve the `CanonicalId` property set or IFC `Tag` when creating downstream objects; it is the stable link back to the authoring model.

The IFC contains the same geometry as the browser preview, represented as tessellated bodies. It also includes wall axes, IFC element/type classes, materials, containment, openings/fills, wall path connections, space boundaries, general connections, and aggregation.

Construction exports include native beams, columns, members, footings, stair flights,
railings and terrain. Framing groups expand into individually identified members.
Screens and miscellaneous profile/detail components preserve canonical kind/role
even where IFC uses a proxy. Terrain is an open surface; physical component layers
are separate closed bodies with material-specific styles.

Reusable layered types receive `IfcMaterialLayerSet`. Concurrent framing/insulation
constituents are preserved as JSON in `Pset_HomeDesignComposition`, sharing one
physical layer thickness. `Pset_HomeDesignData` retains resolved product performance,
operation geometry, specifications and applicable requirements. Material definitions
and project-wide requirements/connections are retained in
`Pset_HomeDesignMaterial` and `Pset_HomeDesignProject`. Structured values are JSON text
so downstream tools can recover fields without guessing their units. Importer UI
support for displaying layer sets and JSON properties varies; inspect the IFC data
when a CAD application's property panel omits them.

Apply design changes to the canonical JSON and rebuild the IFC. Edits made in
FreeCAD are independent of the canonical model.

## Drawings and schedules

Every build writes `drawings.svg`, with default level plan cuts and south/east
elevations when no root `drawings` are authored. Custom drawing entries specify
`id`, `name`, `kind: "projection" | "section"`, `axis: "x" | "y" | "z"`, and a
canonical millimetre `position` for the cut/view plane. Optional `includeKinds` filters
the view. `dimensions` contains canonical 3D `start`/`end` points and an optional
`label`. Dimensions measure their projected distance in the selected view, so put
dimension endpoints in the measurement plane.

The output is one SVG sheet with independently fitted view panels, overall
dimensions and authored dimensions. It is a dimensioned coordination drawing, not
a fixed printed scale or completed permit set. Sections intersect the actual
meshes and retain openings/holes; elevations use depth-sorted silhouettes rather
than exact hidden-line removal. Use explicit views to isolate crowded construction
details. Native CAD remains appropriate for final annotation and sheet production.

`schedules.json` includes all components and subsets for openings, framing,
foundations, stairs/guards, drainage, loads and interface details, plus material
volumes and requirements. Stable IDs connect rows to IFC and the viewer. Quantities
come from modeled net geometry; they exclude procurement waste, hidden fasteners,
unmodeled reinforcement and inferred engineering capacity. A framed cavity's
constituents divide its volume; modeling the same framing again as physical members
will add those separate members to the takeoff, so avoid counting both representations
as procurement quantities without reconciliation.

## Envelope and solar handoff

`envelope.json` reports net wall areas, roof surface/slab plan areas, nominal door
and window areas, orientations, layers, performance, explicit thermal-boundary
assignments, all shading geometry and authored solar results. Quantities use m²;
meshes and nested resolved dimensions use mm. U/R values use SI units. Sloping roofs
retain full mesh geometry even when no single azimuth represents the whole roof.

Review `thermalBoundary: null` entries before energy-model import. The format is a
documented JSON handoff, not a native energy-analysis input file. The analyst must assign
zones, constructions and boundary conditions in their analysis tool.

Solar positioning follows the
[NOAA approximate equations](https://gml.noaa.gov/grad/solcalc/solareqns.PDF).
Studies trace a regular grid of direct-sun rays per opening against opaque model
geometry, including decks and porch roofs. They omit atmospheric refraction,
diffuse sky light, heat transfer, unmodeled trees and seasonal foliage. Transparent
materials are not simulated optically. These snapshots inform shading decisions;
annual savings, energy-code compliance and certification require separate analysis.

## Sharing and privacy

A static or hosted deployment contains the built web project and exposes the review experience to visitors. Canonical authoring and Python execution remain in the trusted local workflow; visitors receive inspection capabilities.

To package and upload the viewer, follow [Website export and deployment](website-deployment.md).

Before sharing:

- verify the intended design revision in the header,
- retain only project metadata intended for the selected audience,
- review specifications, survey terrain, load assumptions, interface references and report downloads for private data,
- confirm the deployment audience,
- test the model on both pointer and touch-sized layouts,
- share IFC separately when reviewers need BIM/CAD data.
