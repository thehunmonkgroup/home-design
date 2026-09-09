# Builds, collections and drawings

Read this for model publication, drawings or export delivery. For user handoff, see [export and sharing](../../../docs/guides/export-and-sharing.md). Native entity/property details live in the [IFC contract](../../../docs/reference/ifc-contract.md).

- [Model collections](#model-collections)
- [Construction review](#construction-review)
- [Drawing views and dimensions](#drawing-views-and-dimensions)

## Model collections

Models can carry a companion `views/MODEL-STEM/index.json` and view definitions.
Builds publish these as named views in the viewer; `home-design views MODEL`
discovers them for AI capture. Keep the companion directory with a copied model,
matching its filename stem. See [visual feedback](visual-review.md).

`validate` and `build` accept multiple paths or quoted glob patterns, such as
`home-design build 'examples/*.json' --web-assets web/public/model`. JSON reports
use a `models` array for any input count. Keep patterns limited to canonical model
files, excluding change sets and generated JSON.

Build artifacts are under `<output>/<filename-stem>/`, where `--output` defaults
to `build` and the stem is the source filename without `.json`. Rebuilding replaces
that generated model directory. Relative paths use the working directory. Without
`--web-assets`, `build` searches that directory and its parents for the nearest
Home Design viewer (in the directory itself or its `web/` child) and publishes to
its `public/model/`. Outside a viewer workspace it writes artifacts only. Use
`--web-assets PATH` to override discovery or `--no-web-assets` to skip publication.
Discovery does not use the model's location or the installed package resources.
The last input with a matching stem wins. Browser
publication defaults to `--web-assets-mode merge`, retaining other homes. The
guarded transaction command also merges its rebuilt model when `--web-assets` is supplied.
Use `--web-assets-mode replace` when the selected sources define the intended
complete publication set; it removes other managed models and superseded browser
versions. For the three public showcases, use
`home-design build 'examples/*.json' --web-assets-mode replace`.
Check the collection before sharing because merge retains previously
published private homes. Use the returned artifact paths and the viewer's model
selector to review the intended home; the viewer initially opens the first by
project name. Read `docs/guides/export-and-sharing.md` for collection workflows.

For a shareable static website, use `home-design website-export MODEL... --output
build/website`. This builds an isolated collection containing exactly the selected
homes and packages the viewer without changing local preview assets. Node/npm
and installed `web/` dependencies are required. The output directory is disposable
and replaced on subsequent exports. Exports include compressed model/manifest
copies and the viewer shows download and preparation progress. Upload the complete
output, including `.gz` files; no host compression setup is required.
Exporting is local; upload only when the user
requests deployment to the intended audience. Read
`docs/guides/website-deployment.md` for preview and hosting options.


## Construction review

The viewer groups components by type, assembly, room, host or service system.
Use related-component links and **Reveal wall contents** to review concealed
construction. A framing inspector lists searchable generated members with the
same scoped IDs used by CLI inspection and IFC. **Isolate with contents** and
**Isolate system** frame relevant geometry; **Show all** restores visibility.
Metric and feet/inches display do not change source dimensions. Follow the
[viewer guide](../../../docs/guides/viewer-guide.md) for controls. Edit canonical
sources through transactions, including a generating component's supported
overrides when changing an individual generated member.

## Drawing views and dimensions

The optional root `drawings` array stores reproducible views for the exported
SVG sheet. Each entry specifies `id`, `name`, `kind: "projection" | "section"`,
`axis: "x" | "y" | "z"`, and a canonical millimetre `position` for the cut/view
plane. Optional `includeKinds` filters the view. Use explicit views to isolate
crowded construction details.

`dimensions` contains canonical 3D `start`/`end` points and an optional `label`.
Dimensions measure their projected distance in the selected view, so put dimension
endpoints in the measurement plane. Rebuild after changing views or dimensions.
See [Drawings and schedules](../../../docs/guides/export-and-sharing.md#drawings-and-schedules) for
default views, exported sheet contents and output limitations.

For command-driven images of edited geometry, use [visual feedback](visual-review.md).
It provides camera, layer visibility and material-filled cutaway controls without
editing the design or requiring a running viewer.
