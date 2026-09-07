# Architectural shell

Read [identity and composition](composition.md) for shared authoring rules. For physical framing or cavities, continue to [framing](framing.md) and [layers and cuts](layers-cuts.md).

- [Walls](#walls)
- [Slabs, foundations, and decks](#slabs-foundations-and-decks)
- [Roofs](#roofs)
- [Openings, doors, and windows](#openings-doors-and-windows)
- [Spaces](#spaces)

## Walls

A wall has a plan `path`, a reusable layered wall `type`, a `locationLine`, a base constraint, and a top constraint. Paths may be lines, polylines, or shared `axis2` anchors. Each path declares `segmentIds`; each profile declares `boundaryIds`. Read [scoped identities](identities.md) for the complete version 0.2 contract.

Use a height top for a free-standing wall. Use a roof `underside` surface constraint when the wall must follow a roof. Gable ridge and explicit roof-face crossings are inserted into derived geometry while preserving the authoritative wall axis.

Orient exterior wall paths so the left normal points outside (clockwise around a simple building). Layers run from that exterior side inward. The orientation also determines window azimuth and door inward/outward operation. Roof-constrained openings are checked against the actual sloping wall profile.


## Slabs, foundations, and decks

A slab uses a footprint with an outer loop and optional holes, a layered slab type, a level or sampled surface datum, and an `up` or `down` extrusion direction. The `role` carries floor, foundation, deck, landing, ceiling, or roof-slab intent into IFC. Split contiguous deck zones into adjacent slabs and group them in a deck assembly; do not overlap a full deck slab with duplicate zone slabs.

An attached deck remains its own slab element. Express the durable connection to the wall with an `attaches` relationship rather than inferring it from touching geometry.


## Roofs

Parametric roofs support `flat`, `shed`, `gable`, and rectangular `hip` forms. They retain footprint, eave datum, pitch, directional intent, and overhang. Explicit `faceSet` roofs support exact planar 3D boundaries for geometry requiring a custom recipe.

Parametric hip recipes require a rectangular footprint. Use explicit planar faces for irregular hips or multi-ridge roofs.

Pitch is in degrees: 8:12 is approximately `33.690067526`; 1:12 is `4.763641691`. Roof layers measure normal thickness. Surface queries measure the actual underside elevation at the queried X/Y, including that normal thickness.

The default `datumReference: "eave"` places the datum at the overhung footprint's low edge. Use `datumReference: "bearing"` to keep roof planes/ridge fixed relative to the bearing footprint when changing overhangs. `datumSurface: "underside"` makes the datum describe the bearing underside; the default is `"top"`. `edgeOverhangs` maps each named footprint edge to its outward distance and overrides uniform `overhang`; it requires a convex footprint without holes.

A `datumPoint: [x, y]` fixes the chosen roof surface elevation at that child-roof point. Combine it with a sampled parent-roof `eaveDatum` to keep a shed roof below an eave:

```json
{
  "eaveDatum": {
    "kind": "surface", "element": "roof.main", "surface": "underside",
    "point": [3000, 0], "offset": -100
  },
  "datumPoint": [3000, 0]
}
```

The parent sample point and child datum point may differ. Keep a semantic `attaches` relationship when the connection is architectural intent. Add explicit `clearances` to verify porch headroom; a placement connection alone does not guarantee clearance.


## Openings, doors, and windows

An opening owns host-relative station, vertical, and depth placement. Its geometry may be rectangular or a local 2D profile. A `voids` relationship selects its host wall or screen panel. A door or window references a reusable type and uses `fills` to occupy the opening.

The wall body is derived with the cut already applied. IFC also retains the `IfcOpeningElement`, `IfcRelVoidsElement`, and `IfcRelFillsElement`, so downstream BIM tools receive the semantics as well as the visible result.

Door types accept `frameWidth`, `panelCount`, `glazingFraction` and an optional manufacturer `clearOpeningWidth`. Sliding doors generate separate glazed panels and tracks. Single-swing doors accept `handing: "left" | "right"` and `swingDirection: "inward" | "outward"`, plus `swingAngle` in degrees. The resolved data includes a 90-degree swing envelope, nominal dimensions and clear-opening estimates; a manufacturer's clear width takes precedence over the geometric estimate. Nominal door width is not clear passage width.

For a screen door, set `infillMaterial` to the screen material and `infillFraction`
to the desired framed-panel infill fraction (greater than zero and at most one).
These fields are used together, separately from `glazingFraction`. Screen infill
retains its material and opacity in IFC and the viewer, and contributes no glazed
area. Use the normal opening, `voids`, and `fills` relationships so the screen door
has a real host cutout, operation, swing envelope and opening schedule entry.


## Spaces

An explicit space stores its footprint. A derived space stores a seed point and uses its `bounds` wall relationships to select one closed wall loop. The viewer hides space volumes by default; use **Show spaces** to inspect them.
