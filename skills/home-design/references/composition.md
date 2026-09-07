# Identity, coordinates and composition

Read this for new designs and changes that affect shared types, hosts, references or assemblies.

Use `home-design capabilities --kind KIND` to check a family's reusable type,
supported host coordinate modes, direct host targets, cavity participation,
generated-member support and native IFC default. These are integration capabilities;
read the domain reference for required fields and geometry constraints.

- [Coordinate and identity rules](#coordinate-and-identity-rules)
- [Registries](#registries)
- [Assemblies](#assemblies)
- [Relationships versus constraints](#relationships-versus-constraints)
- [Shared types and local changes](#shared-types-and-local-changes)
- [Composition controls](#composition-controls)

## Coordinate and identity rules

- Lengths are millimetres; angles are degrees.
- The local system is right-handed and Z-up: X east, Y north, Z up.
- Registry keys are stable IDs. A component keeps its ID when it moves or receives a new name.
- Version `0.2` names layers, edges and segments. Preserve those scoped names through reordering; see [identities](identities.md) for migration and removed-part behavior.
- Georeferencing, when present, is separate from local building coordinates.

Three.js receives `(x / 1000, z / 1000, -y / 1000)`. IFC remains millimetre-based. Each adapter performs this conversion explicitly.

Requests may express dimensions in metric or US customary units. Convert source dimensions to canonical millimetres with `home-design convert-length`, then author the resulting metric value. For review, the same command can present a metric value as feet and fractional inches with `--to ft-in`.

For solar/orientation work, `coordinateSystem.trueNorthDegrees` is the clockwise
angle from canonical +Y toward +X pointing to true north; zero makes +Y north.
`coordinateSystem.georeference` supplies geographic latitude/longitude. Survey
coordinates remain local geometry; the importer does not reproject a map CRS.

## Registries

The root object contains:

| Registry | Contents |
| --- | --- |
| `project` | Project, site, and building identities |
| `levels` | Storeys and reference datums |
| `anchors` | Shared points, axes, planes, and element stations |
| `materials` | Physical identity and optional render appearance |
| `types` | Reusable architectural, structural, hardware, accessory, envelope and service definitions |
| `elements` | Placed components, service systems/circuits and coordination checks |
| `relationships` | Durable semantic connections between elements |

The complete field contract is [home-model-0.2.schema.json](../../../schema/home-model-0.2.schema.json). [Single-Story Gable House](../../../examples/single-story-gable-house.json) demonstrates core architectural components. [Hillside Deck House](../../../examples/hillside-deck-house.json) demonstrates a two-storey shell with site, construction and envelope coordination. Example dimensions and member sizes are illustrative and require project-specific engineering before construction.

New models use `modelVersion: "0.2"`; read [scoped identities](identities.md) for required layer, boundary and segment names. Existing version `0.1` models remain readable and migrate through an explicit changeset. Optional root `solarStudies` and `drawings` arrays store reproducible analysis/view requests. Use canonical element IDs for integrations; generated mesh counts and node names depend on resolved geometry.


## Assemblies

An assembly groups parts through an `aggregates` relationship. It carries intent such as a roof, wall, floor, deck, or stair system while reusing the part geometry.

Use [reusable assemblies](assemblies.md) for parameterized packages, duplication,
explicit external bindings and updates that preserve local edits. Anchor-based
point locators support model-axis `offset` vectors in version `0.2`, allowing
vertices and member endpoints to share one origin. Recipe parameters can target
those offsets with explicit scalar scale/offset rules.




## Relationships versus constraints

A placement constraint answers “where is it?” A relationship answers “what durable building meaning connects it?” Keep both when both meanings apply.

Examples:

- A wall base can be constrained to `slab.ground` top while `supports` records the assembly/load intent.
- An opening placement belongs to the opening while `voids` records which wall it cuts.
- A deck datum establishes elevation while `attaches` records its ledger connection to an exterior wall.

Every durable connection uses an explicit relationship; geometric contact supplies supporting spatial evidence.


## Shared types and local changes

Changing a reusable type changes every occurrence using it. For a request affecting only one occurrence, copy its type to a new stable ID, change that copy and assign it only to the selected occurrence in one changeset. Preserve unrelated users and verify both the edited and unchanged occurrences.

## Composition controls

An assembly relationship groups parts; it does not create a shared transform. Coordinate positions through shared anchors, host locators and port frames. A physical connection does not resize stock, establish a placement constraint or create a cut. Trace placement, connection, ownership and requirements separately before an edit. Generated members use scoped keys under their framing/assembly owner; edit their source recipe or supported override rather than generated geometry.
