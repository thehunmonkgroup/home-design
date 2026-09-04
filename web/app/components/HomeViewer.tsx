'use client';

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  Box3,
  Box3Helper,
  Color,
  DirectionalLight,
  GridHelper,
  Group,
  HemisphereLight,
  Mesh,
  PCFSoftShadowMap,
  PerspectiveCamera,
  Raycaster,
  Scene,
  SRGBColorSpace,
  Vector2,
  Vector3,
  WebGLRenderer,
} from 'three';
import { GLTFLoader } from 'three/examples/jsm/loaders/GLTFLoader.js';
import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js';
import {
  applyElementVisibility,
  defaultHiddenElementIds,
  elementIdForObject,
  formatMetric,
  groupElements,
  isRenderManifest,
  nodeElementIndex,
  type ManifestElement,
  type RenderManifest,
} from '../lib/model';
import { configureCameraDepth, configureDirectionalShadow } from '../lib/scene';

const MODEL_URL = '/model/model.glb';
const MANIFEST_URL = '/model/render-manifest.json';

interface SceneHandle {
  controls: OrbitControls;
  camera: PerspectiveCamera;
  model: Group;
  renderer: WebGLRenderer;
  scene: Scene;
}

export default function HomeViewer() {
  const canvasHost = useRef<HTMLDivElement>(null);
  const sceneHandle = useRef<SceneHandle | null>(null);
  const highlight = useRef<Box3Helper | null>(null);
  const manifestRef = useRef<RenderManifest | null>(null);
  const hiddenIdsRef = useRef<ReadonlySet<string>>(new Set());
  const [manifest, setManifest] = useState<RenderManifest | null>(null);
  const [hiddenIds, setHiddenIds] = useState<ReadonlySet<string>>(new Set());
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [status, setStatus] = useState<'loading' | 'ready' | 'error'>('loading');
  const [message, setMessage] = useState('Reading the resolved model…');
  const [treeOpen, setTreeOpen] = useState(false);
  const [inspectorOpen, setInspectorOpen] = useState(false);

  const groups = useMemo(() => (manifest ? groupElements(manifest) : []), [manifest]);
  const selected = selectedId && manifest ? manifest.elements[selectedId] : null;
  const spacesVisible = manifest
    ? Object.entries(manifest.elements)
        .filter(([, element]) => element.kind === 'space')
        .every(([elementId]) => !hiddenIds.has(elementId))
    : false;

  const selectElement = useCallback((elementId: string | null) => {
    setSelectedId(elementId);
    if (elementId) setInspectorOpen(true);
    const handle = sceneHandle.current;
    const currentManifest = manifestRef.current;
    if (!handle || !currentManifest) return;
    if (highlight.current) handle.scene.remove(highlight.current);
    highlight.current = null;
    if (!elementId) return;
    const element = currentManifest.elements[elementId];
    const objects = element.nodes
      .map((name) => handle.scene.getObjectByName(name))
      .filter((object): object is NonNullable<typeof object> => Boolean(object));
    if (!objects.length) return;
    const bounds = new Box3();
    for (const object of objects) bounds.expandByObject(object);
    const helper = new Box3Helper(bounds, new Color('#eaa340'));
    helper.name = 'selection-outline';
    handle.scene.add(helper);
    highlight.current = helper;
  }, []);

  const resetView = useCallback(() => {
    const handle = sceneHandle.current;
    if (handle) frameModel(handle.camera, handle.controls, handle.model);
  }, []);

  useEffect(() => {
    const host = canvasHost.current;
    if (!host) return;
    const scene = new Scene();
    scene.background = new Color('#d9ddd8');
    const camera = new PerspectiveCamera(42, 1, 0.02, 500);
    const renderer = new WebGLRenderer({ antialias: true, powerPreference: 'high-performance' });
    renderer.outputColorSpace = SRGBColorSpace;
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    renderer.shadowMap.enabled = true;
    renderer.shadowMap.type = PCFSoftShadowMap;
    host.appendChild(renderer.domElement);

    const controls = new OrbitControls(camera, renderer.domElement);
    controls.enableDamping = true;
    controls.dampingFactor = 0.08;
    controls.screenSpacePanning = true;
    controls.maxPolarAngle = Math.PI * 0.495;

    scene.add(new HemisphereLight('#f3f5ef', '#77766d', 2.1));
    const sun = new DirectionalLight('#fff3da', 3.2);
    sun.position.set(-7, 12, 5);
    sun.castShadow = true;
    scene.add(sun, sun.target);
    const grid = new GridHelper(40, 80, '#8d948e', '#b7bcb6');
    grid.position.y = -0.205;
    scene.add(grid);

    const raycaster = new Raycaster();
    const pointer = new Vector2();
    let model = new Group();
    scene.add(model);
    sceneHandle.current = { camera, controls, model, renderer, scene };

    const resize = () => {
      const width = host.clientWidth;
      const height = host.clientHeight;
      camera.aspect = width / Math.max(height, 1);
      camera.updateProjectionMatrix();
      renderer.setSize(width, height, false);
    };
    const observer = new ResizeObserver(resize);
    observer.observe(host);
    resize();

    let frame = 0;
    const animate = () => {
      controls.update();
      renderer.render(scene, camera);
      frame = requestAnimationFrame(animate);
    };
    animate();

    Promise.all([
      fetch(MANIFEST_URL).then(async (response) => {
        if (!response.ok) throw new Error(`Manifest request failed (${response.status})`);
        const value: unknown = await response.json();
        if (!isRenderManifest(value)) throw new Error('The render manifest has an unsupported format');
        return value;
      }),
      new GLTFLoader().loadAsync(MODEL_URL),
    ])
      .then(([loadedManifest, gltf]) => {
        scene.remove(model);
        model = gltf.scene;
        model.name = 'resolved-home';
        model.traverse((object) => {
          if (object instanceof Mesh) {
            object.castShadow = true;
            object.receiveShadow = true;
          }
        });
        scene.add(model);
        configureDirectionalShadow(sun, new Box3().setFromObject(model));
        sceneHandle.current = { camera, controls, model, renderer, scene };
        for (const [elementId, element] of Object.entries(loadedManifest.elements)) {
          applyElementVisibility(scene, element, element.defaultVisible);
          const object = scene.getObjectByName(element.nodes[0] ?? '');
          if (object) object.userData.homeDesignId = elementId;
        }
        const initiallyHidden = defaultHiddenElementIds(loadedManifest);
        hiddenIdsRef.current = initiallyHidden;
        setHiddenIds(initiallyHidden);
        manifestRef.current = loadedManifest;
        setManifest(loadedManifest);
        setStatus('ready');
        setMessage('Model ready');
        frameModel(camera, controls, model);
      })
      .catch((error: unknown) => {
        setStatus('error');
        setMessage(error instanceof Error ? error.message : 'The model could not be loaded');
      });

    const onPointerUp = (event: PointerEvent) => {
      const currentManifest = manifestRef.current;
      if (!sceneHandle.current || !currentManifest) return;
      const rect = renderer.domElement.getBoundingClientRect();
      pointer.set(
        ((event.clientX - rect.left) / rect.width) * 2 - 1,
        -((event.clientY - rect.top) / rect.height) * 2 + 1,
      );
      raycaster.setFromCamera(pointer, camera);
      const index = nodeElementIndex(currentManifest);
      const hit = raycaster
        .intersectObject(sceneHandle.current.model, true)
        .find((intersection) => {
          const elementId = elementIdForObject(intersection.object, index);
          return elementId && !hiddenIdsRef.current.has(elementId);
        });
      selectElement(hit ? elementIdForObject(hit.object, index) : null);
    };
    renderer.domElement.addEventListener('pointerup', onPointerUp);

    return () => {
      cancelAnimationFrame(frame);
      observer.disconnect();
      renderer.domElement.removeEventListener('pointerup', onPointerUp);
      controls.dispose();
      renderer.dispose();
      host.replaceChildren();
      sceneHandle.current = null;
      manifestRef.current = null;
    };
  }, [selectElement]);

  useEffect(() => {
    if (!manifest || !sceneHandle.current) return;
    hiddenIdsRef.current = hiddenIds;
    for (const [elementId, element] of Object.entries(manifest.elements)) {
      applyElementVisibility(sceneHandle.current.scene, element, !hiddenIds.has(elementId));
    }
  }, [hiddenIds, manifest]);

  const setElementVisible = useCallback((elementId: string, visible: boolean) => {
    if (!visible && selectedId === elementId) selectElement(null);
    setHiddenIds((current) => {
      const next = new Set(current);
      if (visible) next.delete(elementId);
      else next.add(elementId);
      hiddenIdsRef.current = next;
      return next;
    });
  }, [selectElement, selectedId]);

  const setSpacesVisible = useCallback((visible: boolean) => {
    if (!manifest) return;
    if (!visible && selectedId && manifest.elements[selectedId]?.kind === 'space') {
      selectElement(null);
    }
    setHiddenIds((current) => {
      const next = new Set(current);
      for (const [elementId, element] of Object.entries(manifest.elements)) {
        if (element.kind !== 'space') continue;
        if (visible) next.delete(elementId);
        else next.add(elementId);
      }
      hiddenIdsRef.current = next;
      return next;
    });
  }, [manifest, selectElement, selectedId]);

  const showAll = useCallback(() => {
    const next = new Set<string>();
    hiddenIdsRef.current = next;
    setHiddenIds(next);
  }, []);

  return (
    <main className="review-shell">
      <header className="review-header">
        <div className="brand-mark" aria-hidden="true"><span /><span /><span /></div>
        <div className="brand-copy">
          <p>IFC-aligned model</p>
          <h1>{manifest?.project.name ?? 'Home Design Review'}</h1>
        </div>
        <div className="header-status">
          <span className={`status-dot status-${status}`} />
          <span>{message}</span>
          {manifest && <span className="revision-badge">rev {manifest.sourceRevision}</span>}
        </div>
      </header>

      <button className="mobile-panel-button tree-button" onClick={() => setTreeOpen((open) => !open)}>
        Components
      </button>
      <aside className={`model-tree ${treeOpen ? 'panel-open' : ''}`} aria-label="Model components">
        <div className="panel-heading">
          <div><p>Model index</p><h2>Components</h2></div>
          <span>{manifest ? Object.keys(manifest.elements).length : '—'}</span>
        </div>
        <nav className="tree-groups">
          {groups.map((group) => (
            <section key={group.kind}>
              <h3>{group.label}<span>{group.elements.length}</span></h3>
              {group.elements.map(([elementId, element]) => {
                const visible = !hiddenIds.has(elementId);
                return (
                  <div className={`component-row ${visible ? '' : 'component-hidden'}`} key={elementId}>
                    <button
                      className={`component-select ${selectedId === elementId ? 'selected' : ''}`}
                      onClick={() => { selectElement(elementId); setTreeOpen(false); }}
                    >
                      <span className={`kind-swatch kind-${element.kind}`} />
                      <span><strong>{element.name}</strong><small>{elementId}</small></span>
                    </button>
                    <button
                      className="visibility-toggle"
                      type="button"
                      aria-label={`${visible ? 'Hide' : 'Show'} ${element.name}`}
                      aria-pressed={!visible}
                      title={`${visible ? 'Hide' : 'Show'} ${element.name}`}
                      onClick={() => setElementVisible(elementId, !visible)}
                    >
                      <VisibilityIcon visible={visible} />
                    </button>
                  </div>
                );
              })}
            </section>
          ))}
        </nav>
      </aside>

      <section className="viewport" aria-label="Interactive three-dimensional home model">
        <div ref={canvasHost} className="canvas-host" />
        {status === 'loading' && <div className="loading-card"><span /><p>Resolving the building view</p></div>}
        {status === 'error' && <div className="error-card"><strong>Preview unavailable</strong><p>{message}</p></div>}
        <div className="viewport-tools">
          <button onClick={resetView} title="Frame the complete model">Frame model</button>
          <button onClick={showAll} disabled={hiddenIds.size === 0} title="Show every component">
            Show all
          </button>
          <label>
            <input
              type="checkbox"
              checked={spacesVisible}
              onChange={(event) => setSpacesVisible(event.target.checked)}
            />
            <span>Show spaces</span>
          </label>
        </div>
        <div className="axis-key" aria-label="View orientation"><span>N</span><i /><small>Orbit · pan · zoom</small></div>
      </section>

      <button
        className="mobile-panel-button inspector-button"
        onClick={() => setInspectorOpen((open) => !open)}
      >
        Details
      </button>
      <aside className={`inspector ${inspectorOpen ? 'panel-open' : ''}`} aria-label="Element details">
        <div className="panel-heading">
          <div><p>Selection</p><h2>{selected ? selected.kind : 'Nothing selected'}</h2></div>
          {selected && <span className={`large-swatch kind-${selected.kind}`} />}
        </div>
        {selected && selectedId ? (
          <ElementDetails elementId={selectedId} element={selected} />
        ) : (
          <div className="empty-selection">
            <div className="selection-glyph" aria-hidden="true" />
            <p>Select a component in the model or index to inspect its resolved design data.</p>
          </div>
        )}
        <footer>
          <p>Canonical coordinates</p>
          <span>X east · Y north · Z up</span>
          <span>millimetres · degrees</span>
        </footer>
      </aside>
    </main>
  );
}

function VisibilityIcon({ visible }: { visible: boolean }) {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true">
      <path d="M2.5 12s3.5-6 9.5-6 9.5 6 9.5 6-3.5 6-9.5 6-9.5-6-9.5-6Z" />
      <circle cx="12" cy="12" r="2.5" />
      {!visible && <path className="visibility-slash" d="m4 4 16 16" />}
    </svg>
  );
}

function ElementDetails({ elementId, element }: { elementId: string; element: ManifestElement }) {
  const measurements = Object.entries(element.data)
    .map(([key, value]) => [key, formatMetric(value)] as const)
    .filter((entry): entry is readonly [string, string] => Boolean(entry[1]));
  return (
    <div className="element-details">
      <h3>{element.name}</h3>
      <code>{elementId}</code>
      <dl>
        <div><dt>Kind</dt><dd>{element.kind}</dd></div>
        <div><dt>Storey</dt><dd>{element.storeyId ?? 'Hosted / none'}</dd></div>
        {measurements.map(([key, value]) => (
          <div key={key}><dt>{humanize(key)}</dt><dd>{value}</dd></div>
        ))}
      </dl>
      <details>
        <summary>Resolved properties</summary>
        <pre>{JSON.stringify(element.data, null, 2)}</pre>
      </details>
    </div>
  );
}

function frameModel(camera: PerspectiveCamera, controls: OrbitControls, model: Group) {
  const box = new Box3().setFromObject(model);
  if (box.isEmpty()) return;
  const size = box.getSize(new Vector3());
  const center = box.getCenter(new Vector3());
  const radius = Math.max(size.x, size.y, size.z);
  camera.position.set(center.x + radius * 1.15, center.y + radius * 0.85, center.z + radius * 1.25);
  configureCameraDepth(camera, box);
  controls.target.copy(center);
  controls.update();
}

function humanize(value: string) {
  return value.replace(/([A-Z])/g, ' $1').replace(/^./, (letter) => letter.toUpperCase());
}
