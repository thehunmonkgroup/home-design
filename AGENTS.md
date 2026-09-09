# Project instructions

For any request that creates, inspects, or modifies a home design, read and follow `skills/home-design/SKILL.md` before acting. Use the guarded transaction script for existing designs and treat generated IFC, GLB, resolved JSON, manifests, diagnostics, and build metadata as disposable outputs.

## File change rules

Staging file changes into the git index is *exclusively* a developer operation -- why? Because the developer must review your changes, and you may edit files that already have staged changes (incremental fix staging), and this allows the developer to review just the most recent changes, then stage them.

## Design validation and test scope

Maintain design-specific repository regression tests only for public reference JSON models in `examples/`. Validate custom designs through the supported validation, guarded-transaction, build, inspection, and diagnostic workflows; leave repository tests, fixtures, and snapshots unchanged.

When separately authorized to develop engine features or fix engine defects, add general regression coverage using public examples or minimal synthetic fixtures. Keep private design files, their generated outputs, and project-specific requirements outside the repository test suite. If custom design work reveals an engine limitation that requires implementation changes, explain the limitation and obtain authorization for that development work before changing code or tests.

## Documentation rules

- Write documentation as a self-contained, present-tense description of the project's current supported state.
- Keep content focused on enduring capabilities, constraints, and actionable guidance for the intended reader. Describe behavior directly, with all context needed to use it.
- Keep user guides focused on user-visible concepts and controls; place implementation contracts in developer reference material. Document supported workflows at the level needed to carry out the task.
- Collect proposed features and future development work in the root `TODO.md` file.
- Use public, repository-contained or generic examples and references suitable for distribution with the project. Keep private design context confined to its private project materials.

## Special handling of the `design` directory

The `design` directory in the repository root is ignored by .gitignore

The `design` directory is exclusively for 'custom' model builds by end users of this project. The user may choose to maintain this directory as a separate git repository. If so, you should treat is as such, following the `File change rules` as above, and by default placing requests for new 'custom' model builds here unless the user specifies otherwise.
