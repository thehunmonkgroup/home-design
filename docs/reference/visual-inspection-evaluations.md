# Visual inspection coverage

The capture workflow exercises actual resolved geometry through the packaged GLB
adapter and Three.js client. Review consists of reading the resulting image,
checking the source revision, and comparing suspected spatial defects with
resolved measurements or physical interference diagnostics.

## Public models

| Model | Review views | Construction being inspected |
| --- | --- | --- |
| `examples/hillside-deck-house.json` | Exterior, upper-storey interior and plan | Multiple storeys, hillside supports and deck |
| `examples/assemblies.json` | Overview, framing and services | Assembly collection and concealed construction |
| `examples/master-suite-gable-house.json` | Twelve indexed views: exterior, plan, two cutaways, two rooms, framing and service details | Complete framed shell, master suite, electrical circuits and water/waste/vent coordination |

## Recipe instances

Each recipe is instantiated into a minimal model with its required storey through
`prepare` and `transact`. The resulting model is built and rendered from opposing
angles, with a relevant construction view:

| Recipe | Detail review |
| --- | --- |
| `complete-deck` | Framing and supports |
| `coordinated-deck` | Joists, perimeter stock and supports |
| `exterior-wall` | Wall contents, opening framing and electrical accessories |
| `insulated-floor` | Explicit floor framing |
| `insulated-roof` | Rafters, ridge and roof layers |
| `interior-wet-wall` | Framing, fixture connection, trap and service routes |
| `king-post-truss` | Orthographic front view and connection plates |
| `reinforced-foundation` | Reinforcement reveal, masonry and waterproofing |
| `screened-entrance` | Top view of entrance, deck and stair alignment |
| `serviced-partition` | Framing and concealed rough-in |
| `ventilation-branch` | Duct junction, transitions and terminals |

The archived screened-entrance recipe also receives an instance/build/image
check because existing package instances can refer to it. Its archived source
remains an immutable adaptation reference.

The framing discipline includes some surface stock and foundation material.
Use explicit layer hiding or reinforcement reveal when that stock obscures the
detail being inspected. A successful overview does not establish that a concealed
component is visible.

## Regression checks

Named-view checks cover companion discovery and packaging, duplicate and unsafe
index entries, changed-source guards, stale component references, immutable
publication and cap ownership. Viewer checks exercise switching projections,
restoring visibility/materials, matching cap planes and preserving a current view
when a requested view fails. The master-suite companion index is the authoritative
list of its fifteen tour stops.

- Real Chromium captures check PNG dimensions, nonempty component pixels, layer
  selection, filled sections and preservation of source/previous output on failure.
- An angled opaque-wall comparison checks that concealed members and their edge
  outlines do not appear through the finish.
- Section geometry checks retain holes, material identity, area and orientation.
- Camera and selector tests cover both projections, explicit camera frames,
  generated children, invalid selectors and fully clipped geometry.
- Service diagnostics retain intersection bounds for positioning a targeted view.
- Drawing projections union facets on a one-millionth-millimetre grid, retaining
  holes while stabilizing nearly coincident projected edges.
- Installed-package checks include the schema and capture sources. A cold runtime
  setup and image capture exercise the wheel outside the source checkout.

Rendering uses logarithmic depth and fitted camera clipping distances to preserve
separation between thin layers. Image review complements solid-intersection and
connectivity checks. It does not infer structural or service-system capacity.
