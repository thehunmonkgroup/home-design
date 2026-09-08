# Assembly catalog authoring

The public [Assemblies model](../../../examples/assemblies.json) contains nine
independent packages expanded from the recipes below. It builds as one ordinary
canonical model. Each part belongs to exactly one catalog assembly; shared
placement origins, hosted locators and connected ports coordinate the geometry.

Read [assemblies](assemblies.md) for instantiation, duplication and adaptation.
Read [editing](editing.md) before changing the source. Load the relevant domain
reference only for the component or interface being changed.

## Choose a package

Each row uses `assembly.<recipe-name>` as its root ID in the public model.

| Recipe | Parameters | Connection points | Domain references |
| --- | --- | --- | --- |
| [exterior-wall](../../../recipes/exterior-wall.json) | `origin` | `wall` | [Architecture](architecture.md), [electrical](electrical.md), [layers and cuts](layers-cuts.md) |
| [insulated-roof](../../../recipes/insulated-roof.json) | `origin` | `roof` | [Architecture](architecture.md), [framing](framing.md), [envelope](envelope.md) |
| [complete-deck](../../../recipes/complete-deck.json) | `origin`, `width`, `length`, `height` | `surface`, `northBeam` | [Framing](framing.md), [hardware](hardware.md), [site](site.md) |
| [insulated-floor](../../../recipes/insulated-floor.json) | `origin`, `width`, `length`, `height` | `surface`, `northBeam` | [Framing](framing.md), [layers and cuts](layers-cuts.md) |
| [interior-wet-wall](../../../recipes/interior-wet-wall.json) | `origin` | `wall`, open `supply` and `waste` ports | [Plumbing](plumbing.md), [envelope](envelope.md) |
| [ventilation-branch](../../../recipes/ventilation-branch.json) | `origin` | Open `inlet` port | [Mechanical](mechanical.md), [routes](routes.md), [services](services.md) |
| [reinforced-foundation](../../../recipes/reinforced-foundation.json) | `origin` | `wall`, `footing` | [Hardware](hardware.md), [envelope](envelope.md), [site](site.md) |
| [screened-entrance](../../../recipes/screened-entrance.json) | `origin` | `landing` | [Site](site.md), [architecture](architecture.md) |
| [king-post-truss](../../../recipes/king-post-truss.json) | `origin` | `truss` | [Framing](framing.md), [hardware](hardware.md) |

All packages require `binding.storey`, an existing storey providing the vertical
datum. `origin` is an XY vector in millimetres. Inspect dimensions and advertised
overrides with `home-design recipes RECIPE`; fixed dimensions are ordinary
canonical stock, not hidden parameters. The small `serviced-partition` and
`coordinated-deck` recipes remain available for simpler starting points.

## Coordinate an edit

Inspect the current revision, then prepare a recipe update. For example, on a
workspace copy of the catalog:

```bash
home-design inspect assemblies.json --object assembly.complete-deck --view assembly
home-design prepare assemblies.json adapt --object assembly.complete-deck \
  --param width=4600 --param length=3400 --param height=1500 \
  --output resize-deck.json
home-design preview assemblies.json resize-deck.json --output resize-preview.json
home-design transact assemblies.json resize-deck.json --dry-run
home-design transact assemblies.json resize-deck.json --web-assets web/public/model
```

Origin adaptation updates both the anchor and recipe provenance. An ordinary
guarded `moveAnchor` also moves the geometry, but records an independent local
edit; later overlapping recipe changes require normal three-way conflict review.
Assemblies do not introduce a shared rotation transform. XY offsets use model
axes. Rotations and structural dimension changes outside advertised parameters
need explicit changes to their dependent geometry.

The entrance's stair origin and its sampled top datum use the landing's shared
anchor. Stair origins, sampled elevation points and surface mounting
points accept either literal XY vectors or the existing point/anchor locators.
This also lets roof drip edges and floor ceiling cuts follow their package origin.
The entrance has six explicitly authored risers and fixed landing dimensions;
changing its rise or width needs a coordinated flight, opening and guard edit.

The exterior wall's conduit owns its physical shell and an explicit bore cut
through insulation. Box recesses and manufactured cable entries are separate
cuts. The floor's ceiling has owned recesses around the support beams. Post
endpoints reserve space for their base and cap seats. Preserve these interfaces
when modifying stock rather than suppressing ownership or passage errors.

The roof selects mitered layer joins so the ceiling and insulation meet the
rafter ridge. Each gutter/downspout junction has separately owned inlet and bore
cuts. The entrance uses plumb stringer tops against its landing. Guard corners
use adjoining framed panels with touching end posts; the screens sit inside the
landing perimeter with their corner frame allowances authored explicitly.
The door-bearing south screen uses a reversed, landing-hosted baseline so its
left normal faces outside and an inward door swing stays over the landing. A slab
edge's traversal direction does not automatically supply that door convention.

Open service ports are declared boundaries. Remove their `open` states only when
authoring a compatible mate and revising system membership. The wet wall exposes
separate cold-water and waste interfaces; it does not infer a faucet, hot-water
network or downstream waste/vent design. Drain outlet stability is an illustrative
authored input in these display packages.

## Component coverage and assembly selection

The inventory covers all 38 supported component families. Thirty-two have
occurrences in this catalog; the remaining six are listed with their appropriate
use rather than being presented as extra physical building assemblies.

| Component families | Catalog coverage or appropriate use |
| --- | --- |
| `assembly` | One explicit root per recipe |
| `wall`, `wallFraming`, `opening`, `window` | Exterior wall and its framed window; interior and masonry walls |
| `roof`, `planarFraming` | Insulated roof rafters; floor/deck joists, rims and individual deck boards |
| `slab`, `member`, `footing` | Floor, deck and entrance platforms with beams, posts and pads; reinforced foundation |
| `memberAssembly` | King-post truss with named members and trimmed joints |
| `hardware`, `fastenerGroup` | Platform post bases/caps, truss gussets, duct hanger and scheduled screws |
| `reinforcingBar`, `reinforcingMesh`, `masonryPart` | Reinforced foundation, separate masonry units, grout and mortar |
| `accessory`, `envelopePart`, `penetration` | Ledge, basin, roof edges, waterproofing, service seals/sleeve, box recesses, conduit bore and ceiling fitting |
| `barrierCheck`, `clearanceZone` | Waterproofing seam and ventilation maintenance access |
| `serviceDevice`, `serviceRoute`, `serviceFitting`, `serviceInsulation` | Receptacle circuit, conduit, water/waste branches and trap, insulated ventilation branch |
| `serviceSystem`, `serviceCircuit` | Explicit connected service networks and scheduled electrical branch |
| `stair`, `railing`, `panel`, `door` | Screened entrance; deck guards |
| `sweep` | Roof fascia/gutters/downspouts and perimeter drain |
| `framing` | Alternative repeated-member authoring; catalog uses boundary-fitted `planarFraming`. Public hillside model demonstrates `framing` |
| `curvedMember` | Optional curved beams, braces or rail returns; not required by the straight catalog packages. See [curved structural members](framing.md#curved-structural-members) |
| `terrain` | Survey/site context for placing assemblies; the separated display bays share a level datum |
| `space` | Rooms bounded by an integrated building, rather than this collection of separated construction samples |
| `load` | Authored loading requirements on actual supports; the hillside example demonstrates an equipment load |
| `detail` | Nongeometric installation instructions connecting participants; the hillside example demonstrates flashing details. Catalog connections have explicit physical parts |

This coverage motivates the additional wet wall, ventilation, foundation,
entrance and truss packages alongside the requested wall, roof and platforms.
Equipment variants such as communications panels, water heaters, pumps and
heat-recovery units use the same service interfaces; their complete layouts depend
on the selected equipment and project networks. Read their domain reference when
adding them rather than treating every device role as a separate house assembly.

The catalog is a set of fully authored examples with declared scope, not a claim
that every product, construction method or jurisdiction has the same component
list. IFC schema and geometry checks verify exported representation; actual
FreeCAD application import remains a separate interoperability check.
