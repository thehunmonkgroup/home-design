# Site coordination, survey import and solar studies

Read this reference when the task requires these commands. Return to
[editing](editing.md) for guarded transactions.

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
[site reference](site.md) and [architectural shell](architecture.md) for field
examples and limitations.

## Survey import

Use a UTF-8 CSV with numeric `x,y,z` headers in one declared source unit. Subtract
the survey origin in that same unit before conversion to canonical millimetres:

```bash
home-design import-survey design/home.json survey.csv \
  --id terrain.existing --state existing --units ft \
  --origin 2500000 800000 0 --output changes/survey.json
home-design transact design/home.json changes/survey.json --dry-run
home-design transact design/home.json changes/survey.json --web-assets web/public/model
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
[sun-study controls](../../../docs/guides/viewer-guide.md#inspect-sections-and-sun-studies) to review
built results and the [envelope handoff guide](../../../docs/guides/export-and-sharing.md#envelope-and-solar-handoff)
to prepare the analyst's export.

Solar positioning follows the
[NOAA approximate equations](https://gml.noaa.gov/grad/solcalc/solareqns.PDF).
Studies trace a regular grid of direct-sun rays per opening against opaque model
geometry, including decks and porch roofs. They omit atmospheric refraction,
diffuse sky light, heat transfer, unmodeled trees and seasonal foliage. Transparent
materials are not simulated optically. These snapshots inform shading decisions;
annual savings, energy-code compliance and certification require separate analysis.
