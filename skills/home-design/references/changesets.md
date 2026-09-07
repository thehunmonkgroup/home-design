# Preparing and previewing coordinated changes

Read [editing](editing.md) for revision guards and committing. Use
[inspection](inspection.md) to identify exact source objects and references.
These commands create reviewable changesets or reports; they do not save a model.

## Edit one occurrence of a shared type

Inspect `--type-users` first. Prepare a new type with only the intended occurrence
reassigned:

```bash
home-design prepare MODEL local-type --object window.north \
  --new-type windowType.north-custom --set /nominalWidth=1400 \
  --output CHANGE
```

Each `--set` takes a type-relative JSON Pointer and a JSON value. For strings, use
shell quoting such as `--set '/name="North custom window"'`. Repeat the option for
multiple fields. The changeset copies the full original type and preserves other
users, with preconditions for the original objects and absence of the new ID.
It preserves the component kind. Dimensions still need to fit the existing
opening/host, or be accompanied by explicit coordinated operations.

## Rehost components

```bash
home-design prepare MODEL rehost --object accessory.ledge --host wall.new \
  --output CHANGE
```

This rebinds the selected component's typed references to its previous host,
including cavity ownership, its owned penetrations and relevant `voids`, `attaches`
or `supports` relationships. It preserves local coordinates, stock dimensions
and unrelated placements/labels. An opening's host comes from its `voids` record.

Use `--from-host OLD_ID` when the component has several host references, and
repeat `--include ID` for other components you explicitly intend to coordinate.
Inspect the resulting operations. The new host's dimensions, layers, service
connections and clearances may require additional edits; preparation does not
infer those design decisions. Preview before committing.

## Remove a coordinated set

```bash
home-design prepare MODEL remove --object accessory.ledge \
  --include cut.ledge --include connection.ledge --output CHANGE
```

Every included ID must exist. Incoming references outside the selected set block
preparation and are returned with source paths and owning IDs. Revise those fields
or deliberately include their owning objects, then prepare again. This command
does not silently cascade deletion or remove selected parts from shared systems.
Generic `set`/`remove` operations remain available for precise membership edits.

## Review actual propagation

```bash
home-design preview MODEL CHANGE --output PREVIEW_REPORT
```

With `--output`, the complete paged report is saved and stdout contains a compact
receipt with validation, section counts and the report path. Without `--output`,
stdout contains the full report. Inspect the saved sections needed for the task.
Similarly, `prepare --output` and `migrate --output` save the complete changeset
and print its path, revision and operation/precondition counts; they do not modify
the model. Omit `--output` to stream a full changeset to stdout.

The report contains:

- `authoredChanges`: exact changed source paths and old/new values; large values
  are explicitly summarized with size and fingerprint.
- `resolvedChanges`: added/removed/changed elements, whether directly edited or
  affected through integrations, geometry changes, changed property paths and
  material volumes in cubic metres.
- `unchangedRelated`: related components whose resolved result stays unchanged,
  including other users of an occurrence's shared type.
- `generatedPartChanges`: scoped member identities added, removed or changed.
- `validation` and `coordinationRequired`: candidate diagnostics, including paths
  and subjects where available. Preserve supplied engineering limits when repairing.

The preview validates both source and candidate once each and retains the candidate's
resolved result internally. It never writes the canonical model. An invalid
candidate returns a nonzero status with its structured report intact. Invalid
source geometry can still be repaired; `geometryComparison: "unavailable"` means
a physical before/after comparison could not be performed, not that nothing changed.

Each report section supports `--limit` and `--offset` with explicit continuation
metadata, as described in [inspection](inspection.md). Revision/precondition
conflicts and other command errors use a JSON error object on stderr; inspect
`code`, `path`, `subject_id`, `details` and any `validation` report.

`exportsChecked` is false: a successful preview checks modeling and coordination,
while a completed guarded transaction/build verifies the exported artifacts.
Use the guarded workflow in [editing](editing.md) to commit the reviewed change.
