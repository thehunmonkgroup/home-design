# Site, stairs, guards and drainage

Read [identity and composition](composition.md) for shared authoring rules. Use [architecture](architecture.md) for connected slabs/roofs, [framing](framing.md) for structural parts and [editing](editing.md) for survey import and solar commands.

- [Stairs, guards and screens](#stairs-guards-and-screens)
- [Terrain, drainage and interface details](#terrain-drainage-and-interface-details)
- [Clearances and executable requirements](#clearances-and-executable-requirements)

## Stairs, guards and screens

`stairType` specifies `treadDepth`, `treadThickness`, `maxRiser`, optional `minRiser`/`nosing`, material and a `stringerType`. A `stair` defines plan `origin`, unit `direction`, connected `bottom` and `top` datums, and `clearWidth`. Set `riserCount` for a fixed layout, or let the resolver select uniform risers within the maximum. There is one fewer tread than risers; the upper landing is the final walking surface.

Model landings as slabs with the landing role. For turns or intermediate landings, compose flights and landing slabs into a `stairSystem` assembly. Each flight updates when its datums change; check run and landing alignment after elevation changes. Stair clear width measures the usable flight, with side stringers outside that width.

`railingType` specifies height, post spacing/section, rail section, material and optional baluster infill (`balusterSection`, `maxInfillGap`). `railing.role` distinguishes structural guards from graspable handrails. Use a circular `railSection` for a round handrail. These are geometric/specification controls, not jurisdictional certification.

Railings and `panel` screens accept a 3D `path` or `follow`. A follow references a stair side (`left`/`right`) or slab outer boundary `edge` ID, plus optional outward offset. Stair-following rails account for section width so their inside face preserves stair clear width. Access `openings` are non-overlapping `start`/`end` station intervals measured along the 3D path. A `panelType` defines frame dimensions/material and a separate infill material; use its material opacity to represent screening. Screens never become structural guards implicitly.

A panel's optional `top` overrides its type height with a height or surface
constraint. Use `{"kind": "surface", "element": "roof.porch", "surface":
"underside", "offset": 0}` to close a screen up to a roof. Roof-following panels
and panels hosting openings require a two-point horizontal baseline. Their frame
and infill follow the resolved elevation profile; openings are cut through both,
with framing around the cutout. Out-of-profile and overlapping openings fail
validation. Split panels at roof face changes when the top cannot resolve into
linear segments. Full-height access intervals remain distinct from hosted doors.

Orient screen baselines with their left normal pointing outside the enclosure to
give doors consistent inward/outward operation. Keep screen frames clear of
guards and structural posts, close the perimeter at the house, deck and roof, and
check door swings against adjacent furniture or equipment footprints. Screens and
screen doors are not conditioned-envelope surfaces; set `thermalBoundary: false`
in their specifications.


## Terrain, drainage and interface details

`terrain` contains existing/proposed state and survey `points` in local millimetres. Supply indexed `triangles`, or let the resolver triangulate the point set. Duplicate X/Y coordinates, degenerate/overlapping triangles and out-of-coverage height samples fail. Supply explicit triangles for concave survey boundaries; automatic triangulation covers the convex hull.

Sample terrain `top` in footing, landing and stair datums. An element's optional `grade` terrain reference reports exposure/retained height for walls and foundation/slab perimeters, including terrain-triangle crossings. Retain separate existing and proposed surfaces and reference the intended one explicitly. The [survey workflow](site-workflows.md#survey-import) converts external units/origins without writing the model directly.

`sweepType` reuses the section/material contract. A `sweep` follows a 3D path and identifies gutter, downspout, drain, interceptor, flashing, fascia, soffit or trim intent. Flow runs go upstream to downstream. `minFall` is dimensionless fall per horizontal run; reversed/insufficient falls fail. `drainsTo` connects one run's end to the next run's start. An `outlet` records its name, verified `stable` status and optional footing `exclusionRadius` in mm. Unverified stability warns; discharge inside a footing's exclusion distance fails.

Sweep profiles follow rotation-minimizing frames through shared miter joints,
including holes in a hollow profile. Path reversals and miters that consume a short
segment fail. Start the path in a direction that gives the desired local profile
orientation; the first frame uses world Z as its up reference (world Y for a
vertical start). Use separate runs/details for manufactured elbows or transitions.
Sweeps do not infer bend radii, hydraulic capacity or global self-intersections.

`detailType` supplies a category, reusable instructions, optional reference and material. A `detail` associates it with at least two participants and a 3D location. Use it for flashing, waterproofing, air-sealing transitions and engineer-specified connections. These details appear in schedules/IFC without requiring individually modeled fasteners or membranes.


## Clearances and executable requirements

Any element can carry `clearances`, each with a name, lower and upper sampled/level datums, and a minimum vertical distance in mm. For a porch, sample the low underside and finished deck at the same plan location. Add multiple samples where the critical surfaces vary.

Requirements contain human-readable statements. An optional `check` makes a numeric requirement executable, with a dotted resolved-data `property`, `operator: "atMost" | "atLeast" | "equals"`, and numeric `value`. Apply it to explicit element IDs. Missing/non-numeric properties fail at the requirement's declared severity. For example, use `atMost` to check `performance.uFactorWm2K` against a specified maximum. Certification requires a separate professional assessment.
