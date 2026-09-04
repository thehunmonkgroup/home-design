# Project instructions

For any request that creates, inspects, or modifies a home design, read and follow `skills/home-design/SKILL.md` before acting. Use the guarded transaction script for existing designs and treat generated IFC, GLB, resolved JSON, manifests, diagnostics, and build metadata as disposable outputs.

## File change rules

Staging file changes into the git index is *exclusively* a developer operation -- why? Because the developer must review your changes, and you may edit files that already have staged changes (incremental fix staging), and this allows the developer to review just the most recent changes, then stage them.
