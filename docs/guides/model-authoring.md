# Understanding your home model

A home model records the design choices behind the building: its rooms, walls,
floors, roof, openings, structural parts and services. The AI edits that model from
your requests. The browser view, drawings, quantities and IFC file are generated
from the same saved revision.

You can describe outcomes in ordinary language. Component names are useful;
internal IDs and JSON syntax are optional.

## Describe the result and what should stay fixed

For example:

> Widen the entry door to 40 inches. Keep it centered, preserve its sill height,
> and adjust its opening and framing to fit. Leave the other doors unchanged.

Tell the AI which dimensions, room boundaries, access spaces, materials or
connected parts should remain fixed. Metric and feet/inches requests are supported.

A shared specification may be used in several places. Ask for “this window only”
when the change is local, or “all windows using this specification” when it should
apply throughout the home.

## How parts stay together

Components can follow shared reference points, host surfaces or equipment
connections. Moving a wall can therefore move its framing, mounted devices and
service openings together. The effect depends on how those parts are connected in
the model; nearby objects do not automatically follow each other.

An assembly groups related parts such as a deck or wall system. Grouping does not
by itself make every part move together. Ask the AI to inspect the assembly's
connections before relocating or resizing it.

Reusable packages provide coordinated dimensions for common assemblies. The
public library includes a framed partition with an electrical rough-in box and a
raised deck with its framing and supports. Ask the AI to place a package, adjust
its dimensions or make an independent copy. Local names and independent edits
remain during updates; conflicting changes require a deliberate choice.

For a substantial edit, ask for a description of the affected parts and anything
that requires additional decisions. Review the result using the
[AI design workflow](ai-design-workflow.md).

## Choose the amount of construction detail

A wall can describe a layered construction with material proportions, or explicitly
model framing and services within its cavities. The framing view shows individual
members only when they are modeled. The same applies to hardware and other
concealed parts.

Tell the AI whether you need an architectural layout, a coordinated shell, or
detailed construction and service parts. More detail requires actual product
dimensions and installation assumptions. The AI should preserve information you
supply and explain information still needed.

## Review a coordinated shell

[Complete Shell Coordination House](../../examples/complete-shell-coordination-house.json)
is a public example with wall, floor, roof and deck framing, concealed services,
an interior ledge and a sealed service penetration. The dimensions and
specifications illustrate authoring capabilities.

[Integrated Authoring House](../../examples/integrated-authoring-house.json) also
provides two windows sharing a product definition and separate reusable wall/deck
packages. Ask the AI to change one window, add a lining layer or copy and resize
a package; the [worked examples](../../skills/home-design/references/examples.md)
describe the expected results.

Use the viewer's **Framing** and **Services** views to expose concealed components.
Select parts, inspect sections, and compare the dimensions and quantities with
your request. See the [viewer guide](viewer-guide.md) for controls.

## Understand the results

Passing validation means the model satisfies the checks the engine performs and
the requirements explicitly entered into it. It does not establish structural
capacity, plumbing or duct sizing, code compliance, or an approved seal assembly.
Those inputs and decisions need the appropriate professional review.

Quantities cover modeled material. They do not automatically include purchasing
waste, unmodeled connectors or construction allowances. IFC carries the modeled
geometry and supported building relationships; see [export and sharing](export-and-sharing.md)
for handoff.

## Technical authoring reference

The AI's [home-design skill](../../skills/home-design/SKILL.md) routes to detailed
field and integration guidance. Advanced authors can use the same references:
[identity and composition](../../skills/home-design/references/composition.md),
[changesets](../../skills/home-design/references/editing.md), and
[public examples](../../skills/home-design/references/examples.md).
The [schema](../../schema/home-model-0.2.schema.json) defines accepted fields.
