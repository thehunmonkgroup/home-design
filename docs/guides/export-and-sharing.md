# IFC export and website sharing

One build creates CAD and browser outputs from each selected model's validated revision.
This guide covers generating those artifacts, importing IFC, and handing drawings
and reports to reviewers. See the [Browser viewer guide](viewer-guide.md) for
interactive review and [Website export and deployment](website-deployment.md) for
website packaging, previewing and hosting.

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
elevations when no root `drawings` are authored. See
[Drawing views and dimensions](model-authoring.md#drawing-views-and-dimensions)
to configure the views and annotations in the canonical model.

The output is one SVG sheet with independently fitted view panels, overall
dimensions and authored dimensions. It is a dimensioned coordination drawing, not
a fixed printed scale or completed permit set. Sections intersect the actual
meshes and retain openings/holes; elevations use depth-sorted silhouettes rather
than exact hidden-line removal. Native CAD remains appropriate for final
annotation and sheet production.

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

Authored solar results are geometric direct-sun snapshots. See
[Solar review](ai-design-workflow.md#solar-review) for study setup, sampling and
analysis limits before using the results in a downstream assessment.

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
