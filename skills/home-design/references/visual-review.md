# Visual feedback while editing

Use visual review after changing layout, framing, assemblies or service routes,
or when numeric inspection leaves a spatial relationship unclear. Render a
useful overview first, then reveal or section the affected construction. Compare
suspected mistakes with resolved measurements and diagnostics before correcting
through a guarded transaction. Repeat the same view after the correction.

## Capture and read an image

Discover prepared views with `home-design views MODEL`. If the model has a suitable
view, use `home-design render MODEL --named-view ID --output DIRECTORY`. The master
suite example includes fifteen views, such as `plan`, `bedroom`, `wall-framing` and
`bedroom-wall-contents`. `--named-view` and `--view` are mutually exclusive.
The viewer exposes the same definitions through **Saved view**.

Named views live in `views/MODEL-STEM/index.json` alongside the canonical model's
directory. The ordered index contains `id`, `title`, `description` and `file` for
each view; each file follows the render-view schema. Copy the companion directory
when copying a model and rename it if the model filename changes. Build and
transaction publication embed the destination model's companion views. After
changing room geometry, check eye-level camera positions; after removing or
renaming an ID, update affected view selectors. Views are presentation inputs and
do not advance the canonical model revision.

```bash
home-design render home.json --output /tmp/home-overview
home-design render home.json --view interior-view.json --output /tmp/home-interior
```

The command validates a captured source revision and uses the normal resolved
geometry and GLB adapter. It changes neither the canonical source nor published
viewer assets. It renders locally through an isolated Chromium page with network
requests restricted to its temporary assets. No running viewer server is needed.

Read the returned `image` PNG with the client's image-reading tool. A successful
command or image filename alone does not mean the AI has inspected the image.
The stdout receipt includes the source revision/hash and artifact paths. The
`report` records the exact view and camera; `objects` maps image numbers to
canonical or generated-member IDs and frontmost pixel counts. Use those IDs with
`home-design inspect MODEL --object ID --view resolved --limit 20`.

A component selected for display may still be concealed. Read its `status`:
`hidden` and `clipped` identify visibility/section exclusions;
`occludedOrOutsideView` means it survives those controls but contributes no
frontmost pixels. None of these statuses means it is missing from the design.
The object map treats transparent surfaces as opaque for identification; a window
can therefore hide an interior component in that map while the beauty image shows
it through the glass. Highlight warnings identify selected components with no
visible pixels, including components hidden or removed by a section.

For a service clash, use the diagnostic's `details.bounds` to locate a close
review and its component IDs to select or highlight both participants. Render
requires a valid model. Correct a rejected candidate using its diagnostics and
source inspection, then capture the accepted revision to verify the result.

## Choose a view

All coordinates use canonical millimetres: X east, Y north, Z up. Preset compass
directions describe where the camera stands looking toward the fitted geometry.
`top` puts north at the top of the image. Cameras fit the retained geometry after
visibility and section cuts; specify `position` and `target` together for an
interior eye-level view. Add `up` when looking vertically with explicit positions.

For a reusable interior view, set `"navigation": "look"` at the view root,
and provide a perspective camera with explicit `position` and `target`.
Position is where the viewer stands; target establishes the initial direction.
Look around rotates in place, so moving target alone does not move the viewer.
Use a comfortably inset position inside the resolved footprint, outside holes,
walls and equipment. Eye height is floor elevation plus about 1650 mm; give
upper-storey views their absolute Z elevation. Aim toward useful features and
render the result before publishing. Keep canonical up [0, 0, 1] (the default).
Orbit is the default for exterior, framing and orthographic plan views.
The capture CLI uses the same camera pose; navigation affects browser gestures,
not the still image. Room presets in the viewer change presentation only.

The Master Suite tour includes `living`, `utility` and `deck`; Hillside has
`lower-room`, `upper-room`, `lower-deck`, `upper-deck`, `spa-deck` and
`entry-landing`, plus floor plans. Use `home-design views MODEL` for the index.

For a room layout, save this view JSON, adjusting the absolute cut height to the
storey's elevation plus the desired height:

```json
{
  "camera": {"projection": "orthographic", "preset": "top"},
  "sections": [{"axis": "z", "position": 1200}]
}
```

Use `"camera": {"preset": "se"}` with a higher cut for an angled interior view.
Cuts retain the side below the coordinate unless `"keep": "above"` is specified.
Material-filled section faces are display-only geometry derived from the same
section polygons as the SVG drawings; they do not change quantities or exports.
`"sectionCaps": false` disables them. Edge outlines improve construction legibility;
`"edges": false` disables them.

For concealed wall work:

```json
{
  "reveal": {"id": "wall.south", "mode": "contents"},
  "camera": {"preset": "se"},
  "highlight": {"ids": ["device.outlet.south"]}
}
```

Use actual inspected IDs. Reveal modes are `contents` (hide the selected host),
`reinforcement`, `system` and `connected`. Contents follow the viewer's explicit
assembly, host, ownership and generated-member links; proximity does not create
containment. An explicitly owned penetration also links its responsible component
to the penetrated host, so a routed service remains discoverable in wall contents
when it uses holes instead of cavity ownership. A reveal isolates its result
across the model.

`isolate`, each entry in `show`/`hide`, and `highlight` accept a selector:

- `ids`, `kinds`, `storeys`: select matching registry identities; fields intersect.
- `contents: true`: expand matched components through their modeled contents.
- `layers: [{"elementId": "wall.south", "layerId": "gypsum"}]`: select named
  material layers. Inspect the host's resolved `layers` first. Older input formats
  without named layers accept the resolved numeric index.
- `materials` and `roles`: filter by exact material IDs or resolved mesh roles.

Selector arrays contain alternatives within that field. Empty or unmatched
selectors fail. Apply order is defaults → `discipline` → `isolate` → `reveal` →
`show` → `hide`. `discipline` accepts `envelope`, `framing` or `services` with the
same membership as the viewer. Framing includes concrete and masonry; use
reinforcement reveal to expose steel.

Hide a roof with its modeled contents using
`"hide": [{"ids": ["roof.main"], "contents": true}]`. Upper floors or unrelated
ceilings may still obstruct the view; a horizontal cut can remove them together.
A meshless assembly requires `contents: true` when selecting its geometry.

## Output and setup

The default image is 1280 × 960. `width` and `height` accept 256–4096 pixels.
Labels default to highlighted components only; `labels: true` labels up to 24
visible components. Detailed legends remain in `objects.json`. For the optional
`object-map.png`, RGB encodes the object number as `R*65536 + G*256 + B`; zero is
background. Pixel coordinates start at the upper left.

Save view JSON outside the disposable output directory. Reusing an output replaces
only a recognized previous render; failures preserve the previous images. The
[view schema](../../../schema/render-view.schema.json) is the complete option
contract. These review images supplement exact clearance, overlap and connectivity
checks; perspective pixels are not dimensional measurements.

Install the optional runtime once in the active Python environment:

```bash
pip install 'home-design[render]'
home-design render-setup
```

Setup requires Node/npm and downloads Chromium and the capture dependencies.
Packaged viewer sources support installed use outside a checkout. Runtime bundles
are cached by their source content. `--web-project PATH` selects another viewer
source tree; a checkout with installed viewer dependencies can render directly.
