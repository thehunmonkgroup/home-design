# Development backlog

Proposed work is listed here separately from supported capabilities.

## CAD interoperability

- [ ] Add repeatable import checks against a declared FreeCAD version and import
  mode. Check solids, dimensions, units, placements, openings, individual framing
  children, materials, properties and system/assembly relationships; supplement
  IFC schema validation with geometry-kernel conversion checks.
- [ ] Add a native FreeCAD adapter that consumes `ResolvedModel` and creates
  `.FCStd` parametric features while preserving canonical IDs, units and geometry.
- [ ] Define a CAD-to-canonical reconciliation workflow that translates downstream
  edits into reviewable, revision-checked design transactions.

## Geometry authoring

- [ ] Add explicit stair-to-landing plan-connection constraints so elevation edits
  can diagnose automatic-run changes that separate a flight from its landing.
- [ ] Evaluate additional parametric recipes or explicitly identified imported
  geometry for complex and organic components.
