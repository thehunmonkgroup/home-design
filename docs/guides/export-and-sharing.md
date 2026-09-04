# IFC export and website sharing

One build creates both CAD and browser outputs from the same validated revision.

## Build a revision

```bash
home-design build design/home.json \
  --output build \
  --web-assets web/public/model
```

The operation resolves into a temporary staging directory and publishes complete files only after both adapters succeed. The optional `--web-assets` path receives atomic copies of `model.glb` and `render-manifest.json`.

## Review in the browser

```bash
cd web
npm install
npm run dev
```

The review site provides:

- orbit with the primary pointer,
- pan with the secondary pointer,
- wheel or gesture zoom,
- **Frame model** to restore a complete view,
- direct or index-based component selection,
- resolved dimensions and canonical IDs,
- hidden-by-default space volumes.

The app is a normal production-buildable website:

```bash
npm run build
npm run start
```

The generated site reads the current GLB and manifest from ignored `public/model/` working data. Rebuild those files whenever the canonical design revision changes and keep them in the ignored working directory. A clean clone can run tests and produce a website build while active model assets are absent; generate them before previewing or deploying a design.

## Import IFC into FreeCAD

1. Build `model.ifc` from the desired canonical revision.
2. In FreeCAD, use **File → Import** and select the IFC file.
3. Enable the BIM/Arch IFC importer if your FreeCAD installation asks for a workbench or importer.
4. Confirm units are millimetres.
5. Check the storey, walls, slabs, roof, opening/fill relationships, space, and assembly tree.
6. Preserve the `CanonicalId` property set or IFC `Tag` when creating downstream objects; it is the stable link back to the authoring model.

The IFC contains tessellated body representations because those bodies exactly match the tested preview geometry, plus wall axes, IFC element/type classes, materials, containment, openings/fills, wall path connections, space boundaries, general connections, and aggregation. A future native FreeCAD adapter can add richer `.FCStd` parametric features while preserving the canonical JSON architecture.

Treat downstream FreeCAD edits as proposals to restate through canonical design transactions. A future native adapter and explicit reconciliation protocol can add a controlled CAD-to-canonical workflow.

## Sharing and privacy

A static or hosted deployment contains the built web project and exposes the review experience to visitors. Canonical authoring and Python execution remain in the trusted local workflow; visitors receive inspection capabilities.

Before sharing:

- verify the intended design revision in the header,
- retain only project metadata intended for the selected audience,
- confirm the deployment audience,
- test the model on both pointer and touch-sized layouts,
- share IFC separately when reviewers need BIM/CAD data.
