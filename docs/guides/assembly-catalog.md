# Construction assembly catalog

[Assemblies](../../examples/assemblies.json) displays nine separate construction
examples in one model. Each example groups its layers, structural members,
connections and services into a selectable assembly. The examples are spaced
apart so you can inspect their construction without neighboring house walls
covering the view.

| Assembly | What you can inspect |
| --- | --- |
| Exterior wall | Siding, weather barrier, sheathing, insulation, studs, plates, window framing, air-control membrane and drywall; recessed electrical boxes, breaker, receptacle, cable and hollow conduit |
| Insulated roof | Shingles, underlay, sheathing, insulated rafters, air-control membrane and gypsum ceiling; fascia, drip edges, gutters and downspouts |
| Raised deck | Individual deck boards, joists, rim boards, beams, posts, concrete pads, steel post bases/caps, connection screw quantities and four perimeter guards |
| Insulated floor | Timber finish, structural subfloor, insulated joists, underside gypsum fitted around support beams, posts, pads and connections |
| Interior wet wall | Insulated framing, drywall, service ledge, washbasin, drain connection and trap; cold-water valve and branch pipes, sleeve, protective plate and separate seal rings |
| Ventilation branch | Air handler, balancing damper, tee, insulated supply ducts, registers, supporting frame and hanger, and maintenance access space |
| Reinforced foundation | Concrete strip, individual reinforcing bars and mesh, hollow masonry units, grout, mortar, parge coat, waterproofing sheets and perimeter drain |
| Screened entrance | Supported landing, stair treads and stringers, guards, round handrails, screen panels and a framed screen door |
| King-post truss | Bottom chord, top chords and king post with fitted joints, steel gussets and connection screw quantities |

## Open and explore

Build the model and start the viewer from the checkout:

```bash
home-design build examples/assemblies.json --web-assets web/public/model
cd web
npm run dev
```

Choose **Assemblies** in the model selector and **Assembly** under **Group by**.
Use the group visibility control with **Isolate on eye click** to focus on one
example. **Show all** restores the collection.

For the exterior wall, search the Components list for **Complete exterior wall**
and click its name. Open **Show Details** if needed, then choose **Reveal wall
contents** below **Display units**. This action appears when the wall itself is
selected. Selecting the assembly or clicking an eye button does not enable it.

Select **Studs, double top plate, bottom plate and window framing**, then scroll
within Details to **Generated members** to browse individual boards. **Back**
returns from a member to your previous selection. Roof and floor framing provide
similar member lists. The lower **Framing** and **Services** buttons isolate
construction groups across the model.

To expose the foundation's steel, select **Reinforced foundation and masonry stem
wall**, then click **Reveal reinforcement** in Details below **Display units**.
This isolates its bars and mesh while hiding the concrete and masonry. **Isolate
with contents** restores the selected assembly. The lower **Framing** button
includes structural concrete and masonry, so it can leave reinforcement concealed.

**Waterproofing seam continuity probe** is a virtual checking region
where two waterproofing sheets meet. It starts hidden; select it to inspect
coverage and connectivity, or click its eye button to display it in purple.
See the [viewer guide](viewer-guide.md#return-to-components-and-find-your-place)
for navigation, concealed construction and inspection controls.

The generated `build/assemblies/model.ifc` contains the collection with its
assembly relationships and individual construction parts. Schedules retain material quantities, generated
members, service circuits and connection fastener counts. Scheduled screws are
quantities rather than individually positioned solids.

## Reuse an example

Ask the AI to copy an assembly into your design, connect it to your building, or
adapt its dimensions. Every catalog assembly has a corresponding reusable recipe.
The deck and insulated floor expose width, length and height; the other packages
expose their position and use explicitly authored stock and dimensions.

A copied package needs an appropriate building location and actual connections.
The collection includes open service interfaces so examples can be connected to
a larger design: it is not a complete house-wide plumbing, electrical or air
network. The wet wall's cold-water rough-in and basin waste are separate examples;
the trap arm awaits its downstream waste and vent arrangement.

The dimensions and ratings illustrate construction modeling. Member capacities,
product selection, service sizing and regulatory approval remain project inputs.
The AI's [catalog reference](../../skills/home-design/references/catalog.md)
describes recipe interfaces, coordinated edits and component coverage.
