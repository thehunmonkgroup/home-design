# Viewer navigation and property contracts

The GLB adapter publishes `home-design-render-manifest-0.1`. Optional navigation,
generated-member and property fields describe component navigation and display.
The viewer validates node lists, property values, relationship endpoints
and generated child/parent references before loading a model.

## Construction navigation

`ResolvedModel.component_references` retains typed direct element references from
the canonical graph. Resolved JSON publishes them as `componentReferences`, with
source paths and reference roles. `ViewNavigation` combines these references with
authored relationships; geometric proximity does not create a link.
Scoped member-host references point to the surviving generated child's ID, so its
inspector can navigate directly to components attached to that member.

An owned penetration contributes a host link from its responsible component to
the penetrated construction. This keeps routed services discoverable in wall
contents even when physical holes replace cavity ownership. The link records
explicit passage intent and does not introduce a placement constraint.

The manifest's `navigation` object has format `home-design-navigation-0.1` and a
`links` array. A link includes `sourceId`, `targetId`, `kind`, `sourceLabel`,
`targetLabel` and optional source `path`. Its labels describe navigation from
either endpoint. Kinds include `assembly`, `room`, `host`, `ownership`, `system`,
`connection`, `support`, `placement`, `reference` and `generated`.

Containment-like links point from child to container: part to assembly, wall to
room, hosted device to wall, owned cut to device, and service member to system.
Placement links point from dependent component to its reference. Support links
point from supported component to support. Connections retain their authored
direction and allow navigation in both directions. Duplicate endpoint/kind links
are collapsed for review; canonical source retains every relationship.

Content isolation follows incoming assembly/room/host/ownership/system/generated
links with cycle protection. It does not recursively include every placement or
connection dependency. System isolation includes the selected component's system
and its members. Connected-part isolation traverses explicit connection links.
Grouping preserves components outside named groups in **Other components**.

`reinforcementElementIds` filters content traversal to rendered `reinforcingBar`
and `reinforcingMesh` components. **Reveal reinforcement** isolates and frames
those IDs while retaining the selected assembly or host inspector. It does not
change discipline classification: **Framing** includes concrete and masonry as
structural components and applies across the complete model.

## Generated members and geometry

`selectionHistoryReducer` retains up to 100 component selections, including
deselection, inside the review keyed by model key and asset version. History
navigation changes its cursor; a new selection truncates forward entries, and
reselecting the current ID does not append an entry. Details state is cached by
component ID for the loaded review. History restores that state without changing
visibility, clipping or camera state. History is independent of browser URL history.

`containingElements` exposes the generated parent and immediate outgoing assembly,
host and room links. It does not synthesize one hierarchy from multiple containers.
**Find in Components** filters by canonical/scoped ID and focuses its index row.
**Show in model** restores selection visibility and frames `selectionNodes`, using
content traversal for meshless groups. Pointer picking accepts primary clicks or
taps within five CSS pixels and excludes drags, secondary buttons, cancellation
and multiple pointers.

Generated framing/member-assembly children use the same scoped IDs as IFC export:
`OWNER/member/KEY`. Their manifest entries have `parentId`; the owner's entry has
`children`. Child data, properties and node mappings come from the shared
`MemberAssemblies.children` contract after physical cuts and cavity fitting.
Repeated framing children retain their actual distributed axes, original repeat
indices and individual counts/material volumes, including when earlier indices
are omitted.

GLB contains each physical mesh once. The parent's `nodes` list includes its
member nodes for aggregate selection; each child maps to its own node. Node lists
therefore overlap only as intentional selection metadata. Picking prefers child
entries regardless of manifest object order. Visibility applies parent entries
before child entries, and parent hide/show operations include generated children.
An individual child can be shown while its siblings remain hidden.

The index normally lists canonical components. Searching includes generated
children; a framing inspector also provides bounded member search and links back
to the generating component. Assembly selection can highlight its descendant
geometry even though an assembly has no independent mesh. Context isolation
frames its selected geometry; **Frame model** returns to the complete model.

## Human-readable properties

`propertyFormat: "home-design-view-properties-0.1"` identifies explicit presentation
records in each element's `properties`. Each record has a stable data-relative
`id`, friendly `label`, scalar `value`, declared source `unit` or `null` for text,
and a presentation `group`.

`ViewProperties` declares recognized dimensions and selected construction fields.
Numeric properties must be finite. Source units include `mm`, `mm2`, `mm3`, `deg`,
`N` and `count`; arbitrary metadata keys do not acquire guessed units. The full
resolved `data` remains available under **Technical properties**. New component
measurements extend this explicit field catalog alongside their shared resolved
contract. Walls expose their resolved path length in canonical millimetres.

The viewer converts length, area and volume for metric or US customary display.
Feet/inches round to the nearest sixteenth of an inch for review; source geometry
is unchanged. Areas and volumes retain their physical dimensions, counts remain
unitless counts, and loads retain declared engineering units. Storey labels come
from the manifest's `storeys` registry. Manifests without property records use scalar
presentation fallback when explicit property records are absent.

The repository's compact public fixture `web/tests/fixtures/component-navigation.json`
contains real export IDs, nodes, properties and links from
[`assemblies.json`](../../examples/assemblies.json).
Its technical `data` payloads are omitted to keep the fixture compact. Python tests
check its presentation contract against current resolution; TypeScript tests
exercise navigation, picking and dimensioned formatting using that fixture.

## Reproducible image capture

### Named view sources and publication

`home-design views MODEL` discovers `views/MODEL-STEM/index.json` relative to the
model's parent directory. The index follows `schema/named-views.schema.json` and
lists ordered, unique IDs, titles, descriptions and local JSON filenames. Each
definition follows `schema/render-view.schema.json`. `render --named-view ID`
selects the same definition as `render --view PATH`; capture guards all companion
sources against changes while rendering.

Builds and transactions load the destination model's companions, validate their
component and layer references, and embed them in the render manifest's
`namedViews` array. Definitions and section geometry participate in the existing
immutable publication hash. `build-metadata.json` records companion source hashes.
Canonical model revision and IFC quantities are independent of view edits.

The GLB contains the union of cap planes required by the named views. Cap mesh
metadata includes `inspectionCap`, `capOf` and `section` (axis, position and kept
side). A cap retains the source mesh's component, layer and material identity.
Clients show it only when its source mesh is selected, its plane is active and
section caps are enabled. Uncut views hide all caps. Other active planes clip
the cap normally, preserving intersecting cuts.

The viewer and capture client share selectors, clipped bounds and camera fitting.
The viewer fits to its actual viewport aspect ratio and permits continued orbit,
pan and selection. It switches between perspective and orthographic cameras;
restore reapplies a named view, while reset clears its presentation state.
Named views use neutral inspection lighting without the ground grid; resetting
restores the ordinary presentation. Selection remains interactive. Numeric
image legends belong to capture output; interactive components remain selectable.


`home-design render MODEL --view VIEW.json --output DIRECTORY` validates a captured
source, exports GLB with the normal adapter and renders it through the packaged
Three.js capture entry point. `schema/render-view.schema.json` validates view
requests. The view uses canonical millimetres and Z-up coordinates; camera and
plane conversion share the viewer's conventions. `visual-view.ts` reuses the
viewer navigation and discipline membership and fits retained triangle bounds
after visibility and clipping. Perspective depth bounds account for the retained
scene to preserve thin-layer depth precision.

The additive manifest `meshes` mapping records each node's `elementId`, mesh
`role`, `materialId` and optional `layerId`. Named layers retain their authored
identity; unnamed older layers expose their numeric index. Parent and generated
child node lists retain their normal overlapping selection semantics. Layer
selection uses this mapping instead of parsing changing numbered node names.

Capture-only section faces reuse `DrawingExporter.section_polygons`, including
material holes, and triangulate those regions. A 0.005 mm bias places each cap on
the retained side of its cut plane. Caps carry their originating mesh's identity
and `inspectionCap: true`; ordinary builds have no caps. They do not enter IFC,
resolved quantities or canonical JSON. The capture GLB hash describes this exact
visual artifact, including caps when requested.

The headless capture page loads only temporary local assets through Playwright
request interception. It has no running HTTP server or external model upload.
`RenderRuntime` caches the capture bundle by source content. Wheel resources
contain the capture source and locked Node dependency manifest; `render-setup`
installs Chromium and prepares Node dependencies in the user cache when needed.
The optional Python `render` extra supplies Playwright. The normal viewer and
headless client share model and navigation contracts, with neutral inspection
lighting, optional edge outlines and explicit camera state for captures.

`render.json` binds the source byte hash, revision, view, GLB/manifest hashes,
resolved camera matrices, node selection, renderer version and artifact paths.
`objects.json` supplies canonical/scoped IDs, image numbers, visibility status and
frontmost pixel counts. `object-map.png` encodes object numbers as 24-bit RGB,
with zero background and top-left pixel coordinates. The identification pass
uses opaque materials even for transparent glass; its pixel counts describe that
pass rather than optical transmission. Selected objects removed by clipping,
hidden highlighted objects, and objects without frontmost pixels remain explicit
in the object report. PNGs and their reports are generated outputs.

Capture awaits shader compilation and rendered pixel readback; no model pixels,
invalid selectors, page failures and malformed view requests fail the command.
Errors preserve previous recognized output directories. The source byte guard
rejects concurrent source changes before publishing an image. Captures do not
change canonical models or publish into the interactive viewer's catalog.

Repeated programmatic calls through one `VisualRenderer` instance reuse the last
validated snapshot only when the captured source bytes are identical. Each call
rereads and guards its source. This permits multiple review angles without
repeating solid resolution; a source edit invalidates the retained snapshot.

The [coverage record](visual-inspection-evaluations.md) describes public example,
recipe, image and export checks.
