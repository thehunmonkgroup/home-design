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
  "baseRevision": 0,
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

Before committing:

```bash
home-design apply design/home.json changes/move-window.json --dry-run
```

A successful dry run reports the next revision while leaving source files unchanged. Apply and rebuild after it passes:

```bash
home-design apply design/home.json changes/move-window.json
home-design build design/home.json --output build --web-assets web/public/model
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

Resolve these checks in the canonical source by revising the design transaction or its explicit constraints. Regenerate `build/`, `web/public/model/`, and IFC entities from the accepted revision.

## Reviewing the result

After each accepted revision:

1. Open the web viewer and frame the complete model.
2. Inspect every directly changed component.
3. Inspect integrated components: hosts, openings/fills, joins, supports, attachments, boundaries, and assemblies.
4. Compare the requested invariant with the resolved measurements in the right panel.
5. Import the new IFC into the intended CAD application before relying on downstream edits.
