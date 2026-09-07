# Viewer navigation and property contracts

The GLB adapter publishes `home-design-render-manifest-0.1`. Optional navigation,
generated-member and property fields extend that format; older manifests remain
readable. The viewer validates node lists, property values, relationship endpoints
and generated child/parent references before loading a model.

## Construction navigation

`ResolvedModel.component_references` retains typed direct element references from
the canonical graph. Resolved JSON publishes them as `componentReferences`, with
source paths and reference roles. `ViewNavigation` combines these references with
authored relationships; geometric proximity does not create a link.
Scoped member-host references point to the surviving generated child's ID, so its
inspector can navigate directly to components attached to that member.

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

## Generated members and geometry

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
from the manifest's `storeys` registry. Legacy manifests use the existing scalar
presentation fallback when explicit property records are absent.

The repository's compact public fixture `web/tests/fixtures/component-navigation.json`
contains real export IDs, nodes, properties and links from
[`complete-shell-coordination-house.json`](../../examples/complete-shell-coordination-house.json).
Its technical `data` payloads are omitted to keep the fixture compact. Python tests
check its presentation contract against current resolution; TypeScript tests
exercise navigation, picking and dimensioned formatting using that fixture.
