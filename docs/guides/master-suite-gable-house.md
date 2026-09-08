# Master Suite Gable House

The [Master Suite Gable House](../../examples/master-suite-gable-house.json)
demonstrates a layered shell with wall, floor, ceiling and roof framing, a
supported south deck, a master bedroom and ensuite, and coordinated electrical
and plumbing systems. Its twelve prepared views provide a tour from the finished
exterior into the rooms and concealed construction.

## Explore the house

Choose **Master Suite Gable House** in the viewer's model selector. Use **Saved
view** above the model to choose a tour stop. Each stop restores its camera,
visible construction, highlights and section cuts. You can then orbit, zoom,
pan or select components normally. **Restore view** reapplies the selected stop
after exploring. **Reset presentation** restores the default visible construction,
perspective camera and an uncut view.

| Saved view | What to examine |
| --- | --- |
| Exterior overview | Gable roof, roof vent, deck and supporting posts and pads |
| Floor plan | North-up layout of the bedroom, ensuite, living/kitchen and utility room |
| Interior from southeast | Room connections and the south deck entrance |
| Interior from northwest | The bathroom and utility partitions from the opposite direction |
| Inside the bedroom | Window placement and outlets from inside the finished room |
| Inside the bathroom | Shower, WC and bathroom window |
| Wall and floor framing | Studs, opening framing, joists and supports |
| Roof framing | Rafters and ridge stock with enclosing surfaces hidden |
| All services | Electrical circuits and water, waste and vent routes |
| Bathroom plumbing | Fixtures, traps, supply branches, waste collection and vent |
| Utility services | Distribution panel, water heater and local connections |
| Bedroom wall contents | North-wall studs and wiring, with two outlets highlighted |

The plan and angled interior views cut through the model without altering its
construction. Eye-level views retain enclosing walls and ceilings. In the wall
contents view, follow a selected outlet's related-component links to inspect its
box, cable and circuit. See the [viewer guide](viewer-guide.md) for selection,
navigation and visibility controls.

## Construction represented

The house has eight framed walls, floor and ceiling joists, roof rafters, deck
joists and boards, twenty supporting members and fifteen concrete pads. Layered
walls include finishes, membranes, sheathing, explicit framing and insulation.

Electrical services include seven protected circuits, nineteen outlets, five
switches, five lights, junction boxes and routed cables. Plumbing includes kitchen
and bathroom fixtures, cold/hot distribution, an electric water heater, waste
traps, drainage and a roof vent. Physical routes have explicit openings through
affected construction. Incoming power, water and outgoing sewer end at modeled
external system boundaries.

| Room | Clear floor area |
| --- | ---: |
| Master bedroom | 18.44 m² |
| Ensuite | 10.80 m² |
| Living/kitchen | 42.83 m² |
| Utility | 2.15 m² |

The finished ceiling is 2.6 m high. Fixtures and equipment use illustrative
geometry. This is a construction and service-coordination example; its geometry
checks do not establish structural capacity, service sizing or regulatory
approval. IFC schema and geometry checks succeed; import in FreeCAD is not
verified.

## Build and reproduce the tour

```bash
home-design build examples/master-suite-gable-house.json \
  --output build --web-assets web/public/model
home-design views examples/master-suite-gable-house.json
home-design render examples/master-suite-gable-house.json \
  --named-view plan --output build/review/master-suite-gable-house/plan
```

The build writes IFC, GLB, drawings, reports and diagnostics beneath
`build/master-suite-gable-house/`. Capture writes an image, component map and
revision report to the requested review directory. These outputs are regenerated
from the canonical model and its [view definitions](../../examples/views/master-suite-gable-house/index.json).
Each listed view ID can be passed to `--named-view`; `--view PATH` also accepts an
individual view file. See [visual inspection](visual-inspection.md) for image review.

To adapt this example in another workspace, copy the model and its companion
`views/master-suite-gable-house/` directory. If the model filename changes,
rename that companion directory to match its new filename stem. Keep component
IDs stable when editing; update affected saved views if an ID is removed or an
eye-level camera needs to move with a revised room layout.
