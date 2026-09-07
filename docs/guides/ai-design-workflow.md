# Working with the AI on a design

Describe the outcome you want and the constraints that must remain true. The AI
inspects the saved model, prepares a focused change, validates it, and rebuilds
the viewer and IFC for your review.

## What to include in a request

Use recognizable component or room names and dimensions with units. Examples:

> Move the service partition two feet north. Keep its outlets and water connections
> mounted to it, and preserve the independent air-conditioning branch.

> Make this window wider while leaving the other windows unchanged.

> Add another layer of exterior insulation. Keep the framing and installed
> components associated with their existing construction layers.

State important requirements such as access, ceiling height, drainage direction,
materials or objects that must stay fixed. The AI may ask a focused question when
the request allows materially different designs.

## What the AI checks

The AI examines affected components, reusable specifications and connected
parts. It prepares a revision-checked changeset so assumptions about the existing
model are checked before saving.

A dry run evaluates the proposed design without changing the source. After it
passes, the AI prepares the exports, saves the revision and publishes its outputs. Validation checks model
structure, references, geometry and applicable authored requirements. It does not
replace professional engineering or regulatory review.

The command protocol and JSON operations are in the AI's
[editing reference](../../skills/home-design/references/editing.md).

## When a change needs correction

A change can fail because an opening no longer fits, a connection separates, an
access space becomes obstructed, a drainage span rises, or an explicitly supplied
limit is exceeded. The AI should explain the affected part and revise the proposal
or ask for a missing design decision.

An export failure leaves the source unchanged. Publication can fail after saving;
the AI should report which revision is saved and recover its outputs before
presenting the work as complete.

## Review the result

- Check the model name and revision in the viewer.
- Compare the requested dimensions and constraints you wanted preserved.
- Use **Framing**, **Services** and section cuts to inspect concealed work.
- Review affected quantities and requirements; ask about unchecked requirements.
- Confirm connected components remain coherent and unrelated components remain
  unchanged where requested.

See the [viewer guide](viewer-guide.md) for navigation and
[export and sharing](export-and-sharing.md) for IFC, drawings and reports.

## Terrain and sun studies

For site work, provide survey units and a known coordinate origin. Preserve
existing and proposed terrain separately. Unknown grade is not extrapolated.

For sun studies, provide a location, date and time with timezone, and the openings
or rooms you want to assess. The viewer shows calculated direct-sun snapshots.
These omit annual heat transfer, diffuse sky light and unmodeled obstructions;
an energy analyst needs the appropriate separate analysis.

The AI can find the commands in
[survey import](../../skills/home-design/references/site-workflows.md#survey-import) and
[solar review](../../skills/home-design/references/site-workflows.md#solar-review).
