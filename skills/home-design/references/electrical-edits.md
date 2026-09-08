# Extend an electrical branch

Use this workflow to add an outlet to an existing serviced wall. Read
[editing](editing.md) for transaction mechanics; use [electrical](electrical.md)
for stock and schedule fields. Master Suite Gable House provides a house
distribution network with seven electrical circuits; Assemblies provides a smaller
exterior-wall circuit within the construction catalog.

## Inspect the connection and physical space

Inspect the selected circuit, its scheduled panel/protection/load ports, member
routes and the existing outlet's type. Inspect the wall's named cavity and nearby
generated framing members. Resolved ports supply positions, normals and section
orientation; source locators explain how those positions follow future wall edits.
Use focused queries rather than loading the entire service model.

An outlet type and a box type are separate physical products. Check their actual
fabricated bounds before reusing them: a 60 mm-wide device does not fit a 50 mm
box. Use occurrence-local stock for a differently sized box, preserving other
users of the original type. Inspect its manufactured entries as well as its body.

## Author one coordinated candidate

1. Place the new device and box with wall/component hosts. Keep them clear of
   studs or explicitly author the required construction alteration. A body wholly
   inside a cavity can use `occupies.fit: contained`; a body intentionally spanning
   cavity and finish uses `intersect` to allocate only its cavity intersection.
   This ownership mode does not create a finish recess or excuse physical clashes.
2. Add the box's owned wall recess and any required cable passage. A hole through
   the wall and a manufactured entry through the box are separate solids. Give
   the entry actual geometric clearance around the selected cable; equal nominal
   section labels alone do not guarantee that their tessellated surfaces clear.
3. Branch through a compatible fitting or a device's explicitly connected internal
   terminal group. An external port accepts one mate. Connecting a second route
   to an already-mated port is not a branch. When inserting a tee, retain the
   existing route ID for one segment, add the other segments and replace the old
   endpoint relationship coherently. Follow the [route/fitting reference](routes.md)
   for geometry and [service interfaces](services.md) for internal/external edges.
4. Reference device/fitting ports at route endpoints and retain host-relative
   intermediate controls where appropriate. Match medium, function, section and
   orientation. Add explicit `connectsPorts` relationships; touching endpoints
   alone do not connect a circuit.
5. Update system and circuit membership with every new participating port, including
   both endpoints of each scheduled route and the fitting's branch ports. Keep
   power membership separate from containment entries. Preserve the panel,
   protection, existing load list and supplied ratings. An added unused outlet
   does not imply a new apparent-power load; add a load only when it is supplied.

Guard the inspected objects and new-ID absences in one changeset. Preview and
dry-run rejection leave the source unchanged; use the named participant and
measured collision/fit diagnostic to correct the same candidate.

## Verify the accepted branch

Complete the transaction build. Check every new mate's position and orientation,
the connected circuit graph, required breaker path and complete route membership.
Compare analytic cable lengths with `circuitSchedules`, count each route once,
and preserve existing load/rating entries. Confirm recess and passage volumes,
cavity accounting and framing clearance, then compare unrelated resolved objects.
Review concealed contents in the viewer when visual delivery is part of the task.
