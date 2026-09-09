# Browser viewer guide

The browser viewer lets you explore a built home, inspect its components and
requirements, and review section cuts and sun studies. View controls do not change
the saved design or its IFC export.

## Open the viewer

A progress bar in the main viewing area shows the model download, including the
percentage and transferred size when the total is known. If the server does not
provide a usable total, the bar stays indeterminate and shows bytes received.
**Preparing model** means the download is complete and the viewer is processing
the 3D view. If loading fails, the error message includes a **Retry model** button.

Models with prepared views show a **View** dropdown near the top of the model.
Choose a view directly there, or open **Views** in the toolbar for the
**Saved view** selector, descriptions and presentation controls. Both selectors
stay synchronized with the selected view.
Choose a view to restore its camera, visible layers and components, highlights
and cuts. The description explains what the view reveals. Orbit, zoom, pan and
select normally after choosing a view; **Restore view** reapplies that stop's
settings. On compact screens, choosing or restoring a view closes the drawer so
you can see the result. **Reset presentation** clears cuts and highlights, restores default
component visibility and frames the model with a perspective camera.

To share a prepared viewpoint, add `?view=VIEW_ID` to the viewer URL (or
`&view=VIEW_ID` if it already has a query string). Use the saved view's exact ID,
the `value` in the **Saved view** menu, rather than its displayed title. The view opens after
the first model finishes loading, with the same settings as selecting it in the
menu. Switching homes starts the newly selected home in its default view.
An unknown or empty ID leaves the default view and displays a message.
Any `view` parameter replaces the automatic full quick start with a one-step
navigation mini-tour after loading. It shows **Explore the 3D view**, the full
tour's third step, explaining orbit, pan, zoom and selection. Choose **Got it**,
**Skip tour** or press Escape to dismiss it. It appears on each visit through a
view link, even if you have already seen the full tour, and keeps your panel
visibility unchanged. Dismissing it does not mark the full tour as completed.
The **?** button still starts the full tour manually.

The [Master Suite Gable House tour](master-suite-gable-house.md) includes fifteen
views, from a north-up floor plan and eye-level interiors to framing and services.
Named section cuts have filled material faces. Open **Tools** to change **Cut** or
construction visibility, or download reports. Changing **Cut** replaces the
saved cut planes; a custom cut has filled faces when it matches an included
named-view plane. Other custom planes use the ordinary unfilled section display.
**Show all** changes component visibility while retaining the current cuts.


Open a shared review site's URL, or start the local viewer after the
[quick-start setup](../../README.md#quick-start):

```bash
cd web
npm install
npm run dev
```

Open the local URL printed by the command. Local models come from the collection
published by [`home-design build`](export-and-sharing.md#build-a-collection).
For a built website preview or deployment, see
[Website export and deployment](website-deployment.md).

A quick-start tour opens after the first successful model load in a
new browser, unless the URL contains a `view` parameter. Models with saved views
include an extra step explaining the **Saved view** controls.
Use **Next** and **Back** to move through it, or **Skip tour** or Escape
to dismiss it. The **?** button in the top bar restarts the tour. Completion and
dismissal are remembered for this site when browser storage is available, or for
the current session otherwise. The tour temporarily opens the panels it describes
and restores your saved panel choices, or the hidden defaults, when it closes.
These temporary openings do not change your saved preferences.

## Make room for the model

The model fills the workspace below a compact header. The toolbar provides
**Views**, **Components**, **Details**, **Tools** and **Frame**. The **i** button
opens model information, including the full name, revision and loading status.

On portrait phones, controls open in a bottom drawer. **Expand** gives it more
room; **Reduce** returns to its initial size. In landscape or a short window,
the toolbar moves to the left edge and drawers open on the right. Scroll inside
a drawer to reach all of its controls. Only one compact drawer opens at a time;
switching drawers preserves the current selection and component filter.

Use a drawer's **×** button, its toolbar button, or Escape while focus is inside
it to close it. The uncovered model stays interactive. On desktop, Components
and Details can remain open side by side. Opening temporary controls never
reduces the canvas height. Rotating the device preserves the viewpoint and
selection; **Frame** fits the complete home to the new screen shape.

The viewer follows the available browser height and keeps controls above the
software keyboard. It also leaves space for device cutouts and home indicators.

## Choose a home

The top-bar model selector lists the published collection alphabetically by
human-readable project name. The first home loads on page load unless the URL
specifies a model; geometry loads only for the selected home. Duplicate project
names include the filename stem to distinguish them.

Use `?model=MODEL_NAME` to open a specific home. The value can be its filename
stem (without `.json`, such as `master-suite-gable-house`) or its exact, unique
project name. Matching is case-sensitive; filename stems take precedence over
project names. URL-encode spaces in project names as `%20` or `+`.
Combine the parameters to open a saved view within the chosen model:
`?model=master-suite-gable-house&view=VIEW_ID`, replacing `VIEW_ID` with its saved
view ID. The model loads directly, then the viewer applies the view and shows
the navigation mini-tour. A `model` parameter alone keeps the normal quick-start
behavior.

If the model value is empty, unknown or matches multiple project names, the
viewer displays a message and lets you choose a home from the model menu.
It does not load another home automatically. Use a filename stem to distinguish
models with the same project name.

Switching homes refreshes the project title, revision, components, requirements,
details and report links. Each home starts with its default visibility, framed
camera, presentation lighting and **Cut** set to **Off**. Selection, component
filter, isolation mode, component navigation history and sun-study choices are cleared. If a home fails to load,
retry it or choose another home. Reload the page to discover newly published models.

## Navigate the model

| Action | Mouse or touchpad | Touchscreen |
| --- | --- | --- |
| Orbit | Click and drag | Drag with one finger |
| Pan | Right-click and drag, or hold Shift and drag | Drag with two fingers |
| Zoom | Scroll wheel or two-finger scroll | Pinch with two fingers |

**Frame** (accessible as **Frame model**) fits the complete model to the current viewport with a surrounding
margin. The **Model north** compass rotates with the camera's orbit heading. It
indicates canonical +Y north, not surveyed true north, and is a read-only
orientation aid. Panning and zooming do not change its heading.

Choose **Gestures** below the compass for navigation help. Hover, focus or tap
**Orbit**, **Pan**, or **Zoom** to read its instructions. Press Escape to dismiss
the help. The quick-start navigation step uses concise touch instructions on
touchscreens and describes the active Orbit or Look around mode.

### Look around rooms and decks

Open **Tools**, then expand **View navigation** to reach the controls. **Orbit** rotates around a target;
**Look around** turns the camera in place, like turning your head. Drag with the
primary mouse button or one finger. Shift/right-drag pans, and scrolling moves
forward or backward. On a touchscreen, two-finger dragging pans and pinching
moves forward or backward. These movements do not enforce wall collisions.
The compass and gesture hints follow the active mode.

Use **Room or deck** to choose a destination. Selecting a room or deck in
Components also chooses it here. The controls offer:

- **Center at eye level** places you inside the footprint at **Eye height (mm)**
  above its floor. The height is limited to below the room ceiling.
- **Upper corner** places you inside an inset upper corner, looking down into
  the room. Both interior presets enter Look around mode.
- **Overview** frames the footprint in Orbit mode.
- **Place viewpoint** lets you click a position inside the chosen footprint,
  using the eye-height setting. A floor plan or downward view makes placement
  easiest. The click projects onto that room's floor plane, so it also works
  when the floor is hidden. Holes and positions outside the footprint are rejected.
- **Set orbit center** lets you click a visible surface and then orbit around it.
  It keeps the camera in place, turns toward the chosen point, and briefly marks
  the new center. Hidden surfaces and geometry beyond a section cut are ignored.

On compact screens, choosing a placement tool closes Tools and shows an
instruction with a **Cancel** button over the model. Room presets also close
Tools so you can explore the resulting view. The two placement tools finish
after a successful click. Use **Cancel** or Escape
to leave a tool without changing the view. Ordinary clicks still select components;
drags preserve the current selection. Room presets and viewpoint tools retain
visibility and section cuts: use **Hide**, **Cut**, or a prepared cutaway when a
roof or wall obscures the area. Presets avoid footprint boundaries and holes but
do not check furniture or equipment; adjust the position if needed.

**Previous view** returns through up to 50 camera relocations, mode changes,
framing actions and saved-view changes, restoring their visibility and cuts.
It does not record every drag or change the Details selection. This history is
separate from the component **Back** and **Forward** buttons and clears when
switching models. **Frame model** returns to Orbit mode. Orthographic floor plans
use Orbit mode; choose an interior preset to enter perspective Look around mode.

Saved interior views restore their Look around mode as well as their position
and initial direction. **Restore view** returns to that starting point after
exploring. Master Suite includes every room and its deck; Hillside includes both
rooms, all three decks and the east entry landing.

## Find and inspect components

Components and Details start hidden unless you have saved a different desktop
preference. Use **Components** and **Details** in the toolbar to toggle them.
Desktop panel choices are remembered for this site when storage is available.
Compact drawers operate independently, so opening them does not overwrite your
desktop layout. If both desktop panels were saved open, a fresh compact session
starts with Components.

Use **Group by** to explore component types, assemblies, rooms, hosts or service
systems. **Other components** retains parts outside the selected groups. Select a component in the model or in the list to inspect its
human-readable name, canonical ID, resolved dimensions and design properties in
the Details panel, including any component-specific requirements.

**Display units** switches between metric and feet/inches without changing the
design. Measurements include their units; **Technical properties** contains the
complete resolved details. Feet/inches are rounded to the nearest sixteenth for
display. Model switching resets grouping and display units along with selection.

### Return to components and find your place

The top of **Details** has **Back** and **Forward** buttons and a **Selection
history** menu. These track selections from the model, Components list, related
links and generated-member lists. Use the menu to jump directly to a visited
component. Selecting a different component after going back starts a new forward
path. **Clear selection** removes the selection; **Back** restores it.

Returning to a component restores its member search, expanded lists, technical
properties disclosure and Details scroll position. History changes the inspected
component without changing the camera, section cut or hidden components. It lasts
for the loaded model and retains up to 100 selections.

Below the selected component's name:

- **Find in Components** opens the Components panel, filters by the selected ID,
  and focuses its row, including individual generated members. Clear the filter
  to browse the full collection. On narrow screens this action closes Details so
  the list is accessible; **Details** reopens the same selection.
- **Show in model** displays the selected component and frames it without hiding
  other components. For an assembly it shows and frames the contents. Other
  geometry can still conceal the selection; use isolation or a section cut to
  look inside. This action is unavailable for components without geometry or
  rendered contents. It leaves the current section cut in place.
- **Hide**, beside **Isolate with contents**, hides the selected component,
  including its generated members, using the Components eye button's visibility
  rules. For an assembly without its own geometry, it hides the assembly's
  contents. The camera and Details selection stay in place; **Show in model**
  restores the selection's geometry. Hide always hides, even when **Isolate on
  eye click** is enabled. It is unavailable when the selection is already hidden
  or has no rendered geometry or contents.
- Labeled upward links lead to the generating component, host, assembly or room
  when those relationships exist. These describe where the part belongs; **Back**
  follows your actual browsing history. A component can belong to several groups.

Dragging to orbit or pan, and using two fingers to navigate, preserves the
selection. A click or tap selects a part; clicking empty model space clears it.

### Follow construction relationships

The **Related components** list links a part to its assembly, room, host,
owned parts, service system and explicit connections. Selecting a link opens that
component's details. **Show more relationships** reveals additional entries.

**Isolate with contents** shows the selected component and its contained or
hosted parts. For a wall, **Reveal wall contents** hides the wall surface and
shows its framing, devices and other modeled contents while retaining the wall's
inspector. **Isolate system** shows the selected service system or the system a
component belongs to. **Isolate connected parts** follows explicit connections.
These actions frame the selected geometry. **Show all** restores visibility;
**Frame model** returns to the complete home.

A framing component represents a set of boards, such as a wall's studs and plates
or a roof's rafters. Select its name, then scroll within Details to **Generated
members**. Search that list and click a member to inspect its stock
dimensions and material volume, with a link back to the generating component.
Members can also be selected directly in the model. Search includes generated
members; the default index keeps them inside their generating components.
Use **Back** to return to the framing list with your search and position retained.

### Find Reveal wall contents

Open **Details**, then select the wall's name in **Components** or click its
surface in the model. **Reveal wall contents** appears in Details below **Display
units**, beside **Isolate with contents**, only when the selected component is a
wall. An assembly, framing component or individual stud has different actions.
Clicking an eye button changes visibility; it does not select the component.

For the **Assemblies** model, search for **Complete exterior wall**, click its
name, then choose **Reveal wall contents**. To inspect individual boards, select
**Studs, double top plate, bottom plate and window framing** and use its
**Generated members** list. The **Framing** and **Services** buttons in the lower
controls isolate those construction groups across the model.

### Inspect service coordination

Service parts with authored coordination checks expose `serviceCoordination`
in their details. Review each obstructing component/member ID, measured overlap
volume and clearance-exclusion reason alongside the physical installation.
Sleeves, protective plates and seals with service-interface declarations appear
in the services review discipline and retain their construction and service IDs.

Use **Filter by name or ID** below the Components heading to find components with
case-insensitive partial matches. Sections remain visible when they contain a
match, with counts showing the matching rows. Clear the filter to restore the
complete list. Filtering does not change visibility in the model.

## Hide, show and isolate components

Components with 3D geometry have an eye button to hide or show them. Components
without independent 3D geometry remain selectable in the index for property
inspection and have no visibility button. **Show all** restores all components
with 3D geometry, including space volumes. Spaces start hidden; **Show spaces**
is available when the model contains rendered space volumes. Hiding a component
does not fill in openings in its host wall.

Each section with rendered components has an eye button for the entire group,
including members excluded by the filter. A partially hidden group has an
underlined eye; clicking it shows all its members.

Enable **Isolate on eye click** in the lower controls to make eye clicks show only
the chosen component or group. Turn it off to hide or show individual members
while keeping the isolated view. Changing the checkbox does not change visibility,
and **Show all** does not change the checkbox. Components with multiple rendered
parts retain all their parts when isolated.

The **Envelope**, **Framing** and **Services** buttons isolate construction groups.
Use **Framing** to expose individually modeled members behind wall and floor
finishes, and **Services** to inspect routed components. A button is unavailable
when the model has no visible geometry in that group. **Show all** restores the
complete model; per-component eye controls remain available after a preset.
The envelope view also includes accessories. Site geometry and space volumes are
excluded from these presets. A framing view shows only framing that is physically
modeled; aggregate cavity percentages do not generate members.

**Framing** includes structural concrete, masonry, reinforcing bars and mesh as
well as timber members. It keeps concrete and masonry visible, so reinforcement
can remain concealed. The lower discipline buttons apply across the whole model,
independently of the selected component.

To expose the steel in the Assemblies foundation, select **Reinforced foundation
and masonry stem wall**, open **Details**, then click **Reveal reinforcement**
below **Display units**. This action isolates and frames the selected component's
modeled reinforcing bars and mesh, hiding concrete, masonry and other components.
It retains the assembly or host selection so **Isolate with contents** restores
its construction. **Show all** restores the complete model.

**Reveal reinforcement** is available when the selected component or its modeled
contents includes rendered reinforcing bars or mesh. It also works for an
individual reinforced footing or wall when the steel is linked as its contents.

Access volumes and barrier probes start hidden and appear as translucent purple
geometry when enabled in the component tree. Their properties show access
obstructions or local barrier gaps and connectivity. They do not contribute
material or solar shading. Hosted accessories appear with the envelope review
group; inspect their mounting range and net volume after a recess or cavity edit.

The Assemblies component **Waterproofing seam continuity probe** is a small
virtual checking region where two waterproofing sheets meet. Search for that
name and select it to inspect modeled coverage and connectivity; click its eye
button to show the purple region. It starts hidden and is not a physical building
part. This local geometry check does not establish that an installed seam is
watertight.

### Cutaway views of Hillside Deck House

[Hillside Deck House](../../examples/hillside-deck-house.json) includes four exterior
walls on each storey, a lower concrete floor and an upper floor assembly whose
underside is the lower ceiling. Both storeys are open-plan shells. Wall names
identify their storey and compass direction.

With **Isolate on eye click** off:

- Click a wall's eye button in **Components → Walls** to hide just that storey's
  wall, including all of its material layers.
- Doors and windows are independent components: hide their eye buttons too when
  removing a host wall from a cutaway view.
- Hide **Upper — indoor floor / lower ceiling** to look down into the lower floor;
  hide the main roof to look into the upper floor.
- Leave **Show spaces** off when inspecting interiors. **Show all** restores every
  component, including spaces; uncheck **Show spaces** afterward if needed.

## Review design requirements

**Design requirements** in the Components panel separates each project-wide
requirement's result from its violation severity. **Satisfied** and **Violated**
describe the numeric checks for the built revision, with actual and required
values per target. **Not automatically checked** identifies notes or requirements
without a check and target; **Status unavailable** means the loaded assets provide
no evaluation result.

Violation severity describes how a failed check is handled, not whether it failed.
Error-level violations block a build; warning- and info-level violations can
appear in a completed build. These checks cover authored numeric constraints, not
engineering approval. See [Clearances and executable requirements](../../skills/home-design/references/site.md#clearances-and-executable-requirements)
to author the checks.

## Inspect sections and sun studies

Use **Cut** in the lower controls to select an axis and set the section position
in millimetres. Set it to **Off** to remove the cut. Clipping is a visual cut, not
a capped solid or a model edit. Use the [SVG drawings](export-and-sharing.md#drawings-and-schedules)
for material-filled sections.

When a model includes sun studies, select one with **Sun study** to set the
lighting. Select an opening to see its direct-sun result in Details. Solar
percentages come from the built study; moving the camera or section plane does
not recompute them. **Presentation light** is not a site/date calculation. Rebuild
after adding or changing persistent studies. See [Terrain and sun studies](ai-design-workflow.md#terrain-and-sun-studies)
for study setup and analysis limits.

## Open drawings and reports

When available, the lower controls link to **Drawings**, **Schedules** and
**Envelope** exports for the selected home. See
[Drawings and schedules](export-and-sharing.md#drawings-and-schedules) and
[Envelope and solar handoff](export-and-sharing.md#envelope-and-solar-handoff)
for their contents, units and handoff limits.
