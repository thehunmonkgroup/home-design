# Website export and deployment

Export a complete viewer with exactly the homes you want to share:

```bash
home-design website-export 'examples/*.json' --output build/website
```

Run this from the repository root after the [quick-start setup](../../README.md#quick-start).
The command needs Node/npm and installed viewer dependencies (`npm ci` in `web/`).
It validates and builds the selected homes, then builds the viewer. No account,
API key, Git commit, or hosting service is needed to export.

## What you get

`build/website/` is a self-contained static website: `index.html`, bundled viewer
assets, a model catalog, the selected homes' GLBs and manifests, and their drawings,
schedules, and envelope reports. It also contains `website-export.json`, which
identifies a generated export directory. Hosting requires only static HTTP/HTTPS
file serving, with no Python, Node server, or database at runtime.

Use one or more filenames or quoted globs to select homes. The selection rules
match [`build`](export-and-sharing.md#build-a-collection). The export always uses
exactly that selection, independent of any homes or extra files in
`web/public/`. Canonical JSON, IFC, credentials, and source code are not included.
Model properties and reports can still contain private information; review them
before sharing.

Repeat the export command to update the website. A successful export replaces the
entire previous output directory, including files added there manually. A failed
model or viewer build preserves the previous export. Choose a dedicated output
directory: an existing nonempty directory must be a previous website export.
Local preview assets in `web/public/model/` stay unchanged.

The default output is `build/website`. If the viewer checkout is elsewhere, add
`--web-project /path/to/home-design/web`. The command prints the output path and
included models as JSON; progress and viewer build logs appear on stderr.

## Preview or upload

Preview the exported folder from the repository root:

```bash
python -m http.server 8000 --bind 127.0.0.1 --directory build/website
```

Open `http://localhost:8000/`. Check the model selector, revisions, components,
and downloads. Stop the server with Ctrl+C. Use HTTP rather than opening
`index.html` directly, because the viewer fetches model files.
See the [Browser viewer guide](viewer-guide.md) for review controls.

Upload the **contents of `build/website/`** to any static host, or ZIP those
contents if the host accepts archives. `index.html` belongs at the upload root.
The viewer also works under a subdirectory such as `/homes/`; use its trailing
slash or `/homes/index.html` URL. Publish the complete folder together on every
update so the catalog and assets stay in sync.

## Preview from a source checkout

To preview a production build of the local `web/` project, first publish its model
collection from the repository root:

```bash
home-design build design/home.json --web-assets web/public/model
```

Then run these commands from the `web` directory after installing its dependencies:

```bash
npm run build
npm run start
```

The build copies model assets from `web/public/model/` into `web/dist/`, which the
production preview serves. Rebuild both the models and viewer whenever the design
changes. This preview includes the local published collection, including models
retained by the default merge behavior. For a self-contained website with exactly
the selected homes, use `home-design website-export` as described above.

## Optional: free Cloudflare Pages hosting

Cloudflare Pages offers a free static-hosting plan. Create an account, choose
**Pages → Direct Upload** in the dashboard, upload the exported folder, and deploy.
For updates, create a new deployment on the same project. No repository connection
is needed. See [Cloudflare Pages](https://www.cloudflare.com/products/pages/) and
its [Direct Upload guide](https://developers.cloudflare.com/pages/get-started/direct-upload/).

Wrangler is included in the viewer's npm dependencies. For terminal uploads, run
from `web/`:

```bash
npx wrangler login
npx wrangler pages deploy ../build/website --project-name my-home-review --branch main
```

Replace `my-home-review` with your Pages project name. Login is a one-time browser
authentication step. The deploy command can prompt to create the project on its
first run; choose `main` as its production branch. Repeat only the deploy command
after each export. For an existing project, use its configured production branch
instead of `main`. This uploads the folder as-is; it does not rebuild it.
`--branch` is optional inside a Git checkout: omitting it uses the current Git
branch. A branch matching the Pages production branch updates the main site;
other branches create preview deployments. It labels the deployment rather than
choosing which files are uploaded.
`npm run deploy -- ...` is a shortcut for `npx wrangler pages deploy ...` with the
same arguments.

Treat the deployed website and every included model/report as public unless you
configure and verify host-level access protection. An unlisted URL and hidden
components do not restrict access. Use the [privacy checklist](export-and-sharing.md#sharing-and-privacy)
before sharing private homes.

Cloudflare limits individual assets to 25 MiB. Dashboard uploads allow 1,000 files;
the terminal option allows 20,000. These are host limits, not export limits.
[Cloudflare upload limits](https://developers.cloudflare.com/pages/get-started/direct-upload/#limits)
apply to each new deployment.
