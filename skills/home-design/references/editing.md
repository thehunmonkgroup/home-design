# Changesets, verification and recovery

Read this before changing an existing design. Read [composition](composition.md) when shared types or dependencies are involved. Commands run from the design workspace; `home-design resources` locates installed references and public examples.

Use the Python environment where the package is installed. In this pyenv checkout,
the repository's `.python-version` selects `home-design` only while inside the
repository. Activate that environment before moving to another workspace, or use
`PYENV_VERSION=home-design home-design resources` and the same prefix for subsequent
commands. An installed package in another environment uses that environment's
normal activation; the environment name is not an engine requirement.

- [Safe change sequence](#safe-change-sequence)
- [Available transaction operations](#available-transaction-operations)
- [Why a change may be rejected](#why-a-change-may-be-rejected)
- [Reviewing the result](#reviewing-the-result)
- [Recovering from a failure](#recovering-from-a-failure)

## Safe change sequence

Use the guarded workflow for an existing design:

```bash
home-design validate design/home.json --json
home-design inspect design/home.json --object door.south-entry --references --type-users --relationships
home-design inspect design/home.json --object opening.door.south --references --relationships
```

The AI then creates a change file with the current `baseRevision` and value preconditions. A minimal example is [move-window.json](../../../examples/change-sets/move-window.json):

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
home-design transact design/home.json changes/move-window.json --dry-run
```

A successful dry run reports the next revision. Apply it and generate the IFC,
browser assets and reports:

```bash
home-design transact design/home.json changes/move-window.json --web-assets web/public/model
```

Read [inspection](inspection.md) for compact source queries, dependencies, type
users, pagination and resolved members. Use [changeset preparation and preview](changesets.md)
for local type edits, rehosting, removal and review of actual propagation.

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

To move an inspected point anchor, use an absolute position in its existing
dimension, for example `{"op":"moveAnchor","anchorId":"anchor.wall.start",
"position":[2000,2500]}`. A translation of a two-anchor wall normally changes
both positions by the same vector. Guard their original positions and preserve
the IDs so hosted construction follows. The [changeset schema](../../../schema/change-set-0.1.schema.json)
defines each operation's exact fields.

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

The [Browser viewer guide](../../../docs/guides/viewer-guide.md) explains navigation, component
filtering, visibility, isolation, requirement results and section controls.

## Recovering from a failure

Validation rejects a candidate before writing it. Inspect its diagnostics and
revise the same changeset against the unchanged source revision. For deletion,
inspect incoming references with `--references --dependents`, including host
placements, type users, ownership regions and requirements. Put the coordinated
removals in one transaction.

`transact` evaluates and exports every adapter before saving the candidate.
Validation or adapter failures leave the source and published artifacts untouched.
A dry run evaluates only; it does not test exporters. `--output` saves to a separate
model, `--build-directory` selects the generated root (default `build`), and
`--web-assets` optionally merges into a viewer collection.

Saving uses the captured source bytes and a cooperative destination lock. A
`source.changed` error means another writer changed the file, even if its revision
is unchanged; reinspect and prepare against the current source. A `source.locked`
error requires waiting for the other writer. Remove a stale lock only after
confirming that no writer remains active.

After saving, publication is a separate phase. A `transaction.incomplete` error
reports `committed`, `published`, the saved revision and a journal path beneath
`<build-directory>/.transactions/`. Recover with:

```bash
home-design recover /absolute/path/build/.transactions/TRANSACTION.json
```

Recovery rebuilds the exact saved bytes without incrementing the revision or
reapplying the changeset. It also handles a process interruption after saving but
before the journal records that phase. If the source has changed since the commit,
recovery rejects it: inspect the current model and build that revision explicitly.
Report saved-source and artifact status separately. Journals contain local paths;
browser publication excludes them. The older skill script uses the same service,
with its historical default viewer destination and success fields.

If the source is invalid, use source inspection and structured validation
diagnostics before attempting an edit. Use the JSON Schema and the affected
domain reference to identify the specific field or dependency requiring correction.
