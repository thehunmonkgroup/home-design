# Development backlog

Proposed work is listed here separately from supported capabilities.

## CAD interoperability

- [ ] Add a native FreeCAD adapter that consumes `ResolvedModel` and creates
  `.FCStd` parametric features while preserving canonical IDs, units and geometry.
- [ ] Define a CAD-to-canonical reconciliation workflow that translates downstream
  edits into reviewable, revision-checked design transactions.

## Geometry authoring

- [ ] Evaluate additional parametric recipes or explicitly identified imported
  geometry for complex and organic components.

## Schema evolution

- [ ] Define versioned schema migrations, including compatibility rules for
  additive fields and breaking changes, with deterministic conversion tests.
