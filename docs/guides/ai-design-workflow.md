# AI design workflow

This project treats an AI request as a transaction against a versioned building graph. The transaction boundary matters: a half-applied window move could otherwise leave a door type, opening, wall cut, IFC relationship, and browser mesh disagreeing with one another.

## What to include in a request

Describe the desired outcome and the constraints that must remain true. Stable component names are sufficient; internal IDs are optional.

Good request:

> Widen the south entry door to 1,000 mm. Keep it centered at its current position, update the rough opening to leave 20 mm clearance on each side and above, and keep the attached deck unchanged.

That statement identifies:

- the filled element (`door.south-entry`),
- its reusable door type,
- its host opening and `fills` relationship,
- the opening's host wall and `voids` relationship,
- placement invariants,
- a nearby component to preserve unchanged.

When a request allows materially different outcomes—for example, “make the bedroom bigger” with several movable boundaries—the AI should ask one focused question before committing.

## Safe change sequence

The project-level Codex skill automates this protocol, but the commands are useful for review:

```bash
home-design validate design/home.json --json
home-design inspect design/home.json --element door.south-entry --relationships
home-design inspect design/home.json --element opening.door.south --relationships
```

The AI then creates a change file with the current `baseRevision` and value preconditions. A minimal example is [move-window.json](../../examples/change-sets/move-window.json):

```json
{
  "changeVersion": "0.1",
  "id": "change.move-north-window",
  "description": "Move the north window 500 mm east.",
  "baseRevision": 1,
  "preconditions": [
    {
      "path": "/elements/opening.window.north/placement/station",
      "equals": 4000
    }
  ],
  "operations": [
    {
      "op": "moveOpening",
      "openingId": "opening.window.north",
      "station": 4500
    }
  ]
}
```

For an AI change to an existing design, use the guarded transaction workflow.
A dry run validates the proposed revision without writing files:

```bash
python skills/home-design/scripts/design_transaction.py design/home.json changes/move-window.json --dry-run
```

A successful dry run reports the next revision. Apply it and generate the IFC,
browser assets and reports:

```bash
python skills/home-design/scripts/design_transaction.py design/home.json changes/move-window.json
```

## Available transaction operations

| Operation | Use |
| --- | --- |
| `moveAnchor` | Coordinate connected walls, slabs, roofs, and spaces through one shared point |
| `moveOpening` | Change station, vertical offset, or depth offset while preserving host geometry |
| `putObject` | Add or replace a complete level, anchor, material, type, element, or relationship |
| `removeObject` | Remove a registry object; validation rejects any dangling references |
| `set` | Replace or add one value selected by a JSON Pointer |
| `remove` | Remove one value selected by a JSON Pointer |

Prefer domain operations when they express the requested action. Use `set` for a narrow parameter update and `putObject` when creation requires a complete schema-valid object.

## Why a change may be rejected

Errors are intentionally specific. Common examples include:

- `reference.missing`: a reference points to a missing type, material, anchor, element, or level ID.
- `reference.kind-mismatch`: a window refers to a door type, or another incompatible target.
- `dependency.cycle`: surface or anchor constraints depend on one another recursively.
- `opening.outside-host-path`: a hosted opening extends beyond its wall path.
- `opening.overlap`: two wall openings intersect in elevation.
- `join.disconnected`: endpoints declared as joined are spatially separated.
- `fill.exceeds-opening`: the door or window type is larger than its rough opening.
- `topology.invalid-profile`: a footprint intersects itself, has no area, or has invalid holes.
- `geometry.resolution-failed`: an invalid stair rise, uncovered terrain query, incompatible miter, insufficient section, or other impossible resolved geometry.
- `clearance.insufficient`: a named pair of sampled elevations has less headroom than specified.
- `support.bearing-outside-element`: an explicit bearing point lies outside a participant's bounds.
- `load.incomplete-support-path` / `load.outside-target`: a loaded footprint is unsupported or exceeds its target surface.
- `drainage.disconnected` / `drainage.outlet-near-footing`: connected drainage endpoints disagree or an outlet violates an authored footing exclusion radius.
- `requirement.unsatisfied`: an explicit numeric property check fails (severity comes from the requirement).

Resolve these checks in the canonical source by revising the design transaction or its explicit constraints. Regenerate `build/`, `web/public/model/`, and IFC entities from the accepted revision.

## Reviewing the result

After each accepted revision:

1. Open the web viewer and frame the complete model.
2. Inspect every directly changed component.
3. Inspect integrated components: hosts, openings/fills, joins, supports, attachments, boundaries, and assemblies.
4. Compare the requested invariant with the resolved measurements in the right panel.
5. Import the new IFC into the intended CAD application before relying on downstream edits.

The [Browser viewer guide](viewer-guide.md) explains navigation, component
filtering, visibility, isolation, requirement results and section controls.

## Coordinating hillside construction

1. Establish survey coordinates, finished-floor datums and separate existing/proposed
   terrain. Confirm which surface each foundation or stair endpoint follows.
2. Author shell layers and roof bearing datums. Give the low-slope porch its own roof
   type, attach its elevation to the main roof underside, and check outer-edge
   headroom using explicit surface points. An attachment relationship also records
   interface intent, but does not replace placement constraints.
3. Compose decks and landings from slabs. Use stairs for each flight; connect top
   and bottom elevations to the landings/grade and verify the run fits the site.
   Follow stairs/slab edges with separate guards, handrails and screen panels.
4. Add native members and repeated framing. Record actual beam/post/footing
   supports and load footprints for concentrated loads and structural roof members.
   Author engineer-supplied capacities; validation does not calculate them.
5. Route drainage with profile sweeps and `drainsTo`. Specify fall, a stable outlet
   and footing exclusion distances. Attach reusable waterproofing, flashing and
   air-sealing details to their actual participants.
6. Add type/element performance and requirements. Review typed SI energy values
   before importing US product ratings. Mark conditioned envelope boundaries
   explicitly; do not include outdoor decks in the thermal envelope by accident.
7. Rebuild and review layer sections, opening operation/clear widths, schedules,
   grade exposure and summer/winter solar results. Retain surveyed and engineered
   decisions as canonical data or referenced details, not edits to IFC/GLB files.

These steps can be separate focused transactions; a coordinated change must include
every dependent object needed to keep the revision valid. See the
[authoring guide](model-authoring.md) for field examples and limitations.

## Survey import

Use a UTF-8 CSV with numeric `x,y,z` headers in one declared source unit. Subtract
the survey origin in that same unit before conversion to canonical millimetres:

```bash
home-design import-survey design/home.json survey.csv \
  --id terrain.existing --state existing --units ft \
  --origin 2500000 800000 0 --output changes/survey.json
python skills/home-design/scripts/design_transaction.py design/home.json changes/survey.json --dry-run
python skills/home-design/scripts/design_transaction.py design/home.json changes/survey.json
```

The importer writes a revision/precondition-checked change, never the model. It
validates the proposed surface and coordinated design before returning. Existing
terrain with the same ID can be replaced; non-terrain IDs are protected. Delaunay
triangulation fills the points' convex hull; use authored triangles for breaklines,
holes and concave survey boundaries. No CRS reprojection or survey datum conversion
is performed. Queries outside actual triangles fail instead of extrapolating.

## Solar review

Provide `coordinateSystem.georeference` latitude/longitude and true north, then
author `solarStudies` for persistent viewer choices or run a read-only snapshot:

```bash
home-design solar design/home.json --at 2026-12-21T12:30:00-05:00 \
  --samples 5 --output winter-solar.json
```

The timestamp must include a timezone. Samples are an N-by-N grid per opening;
increase sampling for narrow shadows. Below-horizon or back-facing openings receive
no direct sun. Assess representative winter and summer times, then give the envelope
export to the energy rater. Use the viewer's
[sun-study controls](viewer-guide.md#inspect-sections-and-sun-studies) to review
built results and the [envelope handoff guide](export-and-sharing.md#envelope-and-solar-handoff)
to prepare the analyst's export.

Solar positioning follows the
[NOAA approximate equations](https://gml.noaa.gov/grad/solcalc/solareqns.PDF).
Studies trace a regular grid of direct-sun rays per opening against opaque model
geometry, including decks and porch roofs. They omit atmospheric refraction,
diffuse sky light, heat transfer, unmodeled trees and seasonal foliage. Transparent
materials are not simulated optically. These snapshots inform shading decisions;
annual savings, energy-code compliance and certification require separate analysis.
