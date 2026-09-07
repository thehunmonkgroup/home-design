# Browser viewer guide

The browser viewer lets you explore a built home, inspect its components and
requirements, and review section cuts and sun studies. View controls do not change
the saved design or its IFC export.

## Open the viewer

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

A five-step quick-start tour opens after the first successful model load in a
new browser. Use **Next** and **Back** to move through it, or **Skip tour** or Escape
to dismiss it. The **?** button in the top bar restarts the tour. Completion and
dismissal are remembered for this site when browser storage is available, or for
the current session otherwise. The tour temporarily opens the panels it describes
and restores your panel choices when it closes.

## Choose a home

The top-bar model selector lists the published collection alphabetically by
human-readable project name. The first home loads on page load; geometry loads
only for the selected home. Duplicate project names include the filename stem
to distinguish them.

Switching homes refreshes the project title, revision, components, requirements,
details and report links. Each home starts with its default visibility, framed
camera, presentation lighting and **Cut** set to **Off**. Selection, component
filter, isolation mode and sun-study choices are cleared. If a home fails to load,
retry it or choose another home. Reload the page to discover newly published models.

## Navigate the model

| Action | Mouse or touchpad | Touchscreen |
| --- | --- | --- |
| Orbit | Click and drag | Drag with one finger |
| Pan | Right-click and drag, or hold Shift and drag | Drag with two fingers |
| Zoom | Scroll wheel or two-finger scroll | Pinch with two fingers |

**Frame model** fits the complete model to the current viewport with a surrounding
margin. The **Model north** compass rotates with the camera's orbit heading. It
indicates canonical +Y north, not surveyed true north, and is a read-only
orientation aid. Panning and zooming do not change its heading.

Hover over **Orbit**, **Pan**, or **Zoom** for a short instruction popup; the hints
also open on keyboard focus or tap. Press Escape to dismiss a hint.

## Find and inspect components

Use the **Show/Hide Components** and **Show/Hide Details** buttons below the project
title to toggle each panel. This browser remembers your choices for this site
across reloads and model switches, when browser storage is available.

The Components panel groups components by kind, including terrain, stairs, framing
and drainage. Select a component in the model or in the list to inspect its
human-readable name, canonical ID, resolved dimensions and design properties in
the Details panel, including any component-specific requirements.

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

Access volumes and barrier probes start hidden and appear as translucent purple
geometry when enabled in the component tree. Their properties show access
obstructions or local barrier gaps and connectivity. They do not contribute
material or solar shading. Hosted accessories appear with the envelope review
group; inspect their mounting range and net volume after a recess or cavity edit.

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
engineering approval. See [Clearances and executable requirements](model-authoring.md#clearances-and-executable-requirements)
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
after adding or changing persistent studies. See [Solar review](ai-design-workflow.md#solar-review)
for study setup and analysis limits.

## Open drawings and reports

When available, the lower controls link to **Drawings**, **Schedules** and
**Envelope** exports for the selected home. See
[Drawings and schedules](export-and-sharing.md#drawings-and-schedules) and
[Envelope and solar handoff](export-and-sharing.md#envelope-and-solar-handoff)
for their contents, units and handoff limits.
