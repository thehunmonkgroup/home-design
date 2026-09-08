import { Box3, Color, DirectionalLight, HemisphereLight, EdgesGeometry, LineBasicMaterial, LineSegments, Mesh, MeshBasicMaterial, NoColorSpace, NeutralToneMapping, Scene, SRGBColorSpace, WebGLRenderer, WebGLRenderTarget } from 'three';
import { GLTFLoader } from 'three/examples/jsm/loaders/GLTFLoader.js';
import { isRenderManifest, nodeElementIndex } from './lib/model';
import { disposeSceneResources } from './lib/scene';
import { clippedBounds, highlightedMaterial, inspectionCamera, selectorNodes, toCanonical, viewPlanes, visibleNodes, type VisualView } from './lib/visual-view';

async function renderInspection(view: VisualView) {
  const response = await fetch('./render-manifest.json');
  if (!response.ok) throw new Error(`Manifest request failed: ${response.status}`);
  const manifest: unknown = await response.json();
  if (!isRenderManifest(manifest)) throw new Error('Invalid render manifest');
  const model = (await new GLTFLoader().loadAsync('./model.glb')).scene;
  const scene = new Scene();
  scene.background = new Color('#edf0f2');
  scene.add(model);
  const renderer = new WebGLRenderer({ antialias: true, preserveDrawingBuffer: true, logarithmicDepthBuffer: true });
  const width = view.width ?? 1280, height = view.height ?? 960;
  renderer.setPixelRatio(1); renderer.setSize(width, height);
  renderer.outputColorSpace = SRGBColorSpace;
  renderer.toneMapping = NeutralToneMapping;
  const host = document.createElement('div');
  host.id = 'inspection';
  Object.assign(host.style, { width: `${width}px`, height: `${height}px`, position: 'relative' });
  host.appendChild(renderer.domElement);
  document.body.replaceChildren(host);
  let objectMap: WebGLRenderTarget | undefined;
  const replacementMaterials: MeshBasicMaterial[] = [];
  try {
    const visible = visibleNodes(manifest, view), planes = viewPlanes(view);
    renderer.clippingPlanes = planes;
    const nodeBounds = clippedBounds(model, visible, planes);
    const bounds = new Box3();
    nodeBounds.forEach((box) => bounds.union(box));
    const camera = inspectionCamera(view, bounds);
    scene.add(new HemisphereLight('#ffffff', '#a7a3a0', 2.6));
    const key = new DirectionalLight('#ffffff', 2.5);
    key.position.copy(camera.position); key.target.position.copy(bounds.getCenter(key.target.position));
    scene.add(key, key.target);
    const outlines: LineSegments[] = [];
    const highlighted = view.highlight ? selectorNodes(manifest, view.highlight) : new Set<string>();
    model.traverse((object) => {
      if (object instanceof Mesh && object.visible && view.edges !== false) {
        const lines = new LineSegments(new EdgesGeometry(object.geometry, 25), new LineBasicMaterial({ color: '#43505a', transparent: true, opacity: 0.35 }));
        object.add(lines); outlines.push(lines);
      }
      if (object instanceof Mesh && highlighted.has(object.name)) {
        object.material = highlightedMaterial(object.material);
      }
    });
    await renderer.compileAsync(scene, camera);
    renderer.render(scene, camera);
    const index = nodeElementIndex(manifest);
    const ids = [...new Set([...new Set([...visible, ...highlighted])].map((name) => index.get(name)).filter((id): id is string => Boolean(id)))].sort();
    const numbers = new Map(ids.map((id, i) => [id, i + 1]));
    const originals = new Map<Mesh, Mesh['material']>();
    model.traverse((object) => {
      if (!(object instanceof Mesh) || !object.visible) return;
      const id = index.get(object.name), number = id ? numbers.get(id) ?? 0 : 0;
      const old = Array.isArray(object.material) ? object.material[0] : object.material;
      const material = new MeshBasicMaterial({ color: new Color().setRGB(((number >> 16) & 255) / 255, ((number >> 8) & 255) / 255, (number & 255) / 255, NoColorSpace), side: old.side, toneMapped: false });
      replacementMaterials.push(material); originals.set(object, object.material); object.material = material;
    });
    objectMap = new WebGLRenderTarget(width, height);
    objectMap.texture.colorSpace = NoColorSpace;
    outlines.forEach((line) => { line.visible = false; });
    renderer.setRenderTarget(objectMap); scene.background = new Color(0);
    renderer.render(scene, camera);
    const pixels = new Uint8Array(width * height * 4);
    renderer.readRenderTargetPixels(objectMap, 0, 0, width, height, pixels);
    const stats = new Map<number, { pixels: number; x: number; y: number }>();
    const mapCanvas = document.createElement('canvas'); mapCanvas.width = width; mapCanvas.height = height;
    const context = mapCanvas.getContext('2d')!;
    const data = context.createImageData(width, height);
    for (let y = 0; y < height; y++) for (let x = 0; x < width; x++) {
      const offset = (y * width + x) * 4;
      const number = (pixels[offset] << 16) | (pixels[offset + 1] << 8) | pixels[offset + 2];
      if (numbers.size && number > 0 && number <= ids.length) {
        const stat = stats.get(number) ?? { pixels: 0, x: 0, y: 0 };
        stat.pixels++; stat.x += x; stat.y += height - 1 - y; stats.set(number, stat);
      }
      data.data.set(pixels.subarray(offset, offset + 4), ((height - 1 - y) * width + x) * 4);
    }
    if (!stats.size) throw new Error('No model pixels are visible from the requested camera');
    context.putImageData(data, 0, 0);
    const objectMapPng = mapCanvas.toDataURL('image/png');
    originals.forEach((material, object) => { object.material = material; });
    outlines.forEach((line) => { line.visible = true; });
    renderer.setRenderTarget(null); scene.background = new Color('#edf0f2');
    renderer.render(scene, camera);
    const objects = ids.map((id, i) => {
      const stat = stats.get(i + 1);
      const nodes = manifest.elements[id].nodes;
      const status = stat ? 'visible' : !nodes.some((node) => visible.has(node)) ? 'hidden' : !nodes.some((node) => nodeBounds.has(node)) ? 'clipped' : 'occludedOrOutsideView';
      return { number: i + 1, id, name: manifest.elements[id].name, status, pixels: stat?.pixels ?? 0,
        screenCenter: stat ? [stat.x / stat.pixels, stat.y / stat.pixels] : null,
        highlighted: manifest.elements[id].nodes.some((node) => highlighted.has(node)) };
    });
    const labels = objects.filter((o) => o.pixels > 0 && (!view.highlight || o.highlighted)).sort((a, b) => b.pixels - a.pixels).slice(0, 24);
    const drawLabels = view.labels ?? Boolean(view.highlight);
    if (drawLabels) for (const item of labels) {
      const label = document.createElement('span'); label.textContent = String(item.number);
      Object.assign(label.style, { position: 'absolute', left: `${item.screenCenter![0]}px`, top: `${item.screenCenter![1]}px`, background: '#ffffffed', color: '#14232e', border: '1px solid #30414d', borderRadius: '3px', padding: '2px 4px', font: 'bold 13px sans-serif', transform: 'translate(-50%, -50%)' });
      host.appendChild(label);
    }
    const warnings = objects.filter((o) => o.highlighted && !o.pixels).map((o) => `Highlighted component has no visible pixels: ${o.id}`);
    if (planes.length && view.sectionCaps === false) warnings.push('Section clipping is uncapped; enable sectionCaps to inspect filled material cuts.');
    return { sourceRevision: manifest.sourceRevision, camera: { projection: view.camera?.projection ?? 'perspective', position: toCanonical(camera.position), target: view.camera?.target ?? toCanonical(bounds.getCenter(camera.position.clone())), up: toCanonical(camera.up).map((x) => x / 1000), projectionMatrix: camera.projectionMatrix.toArray(), worldMatrix: camera.matrixWorld.toArray() },
      selectedNodes: [...visible].sort(), retainedNodes: [...nodeBounds.keys()].sort(), objects, labels: drawLabels ? labels.map((o) => o.number) : [], warnings, objectMapPng };
  } finally {
    objectMap?.dispose(); replacementMaterials.forEach((m) => m.dispose());
    disposeSceneResources(scene); renderer.dispose();
  }
}

declare global {
  interface Window { renderInspection: typeof renderInspection }
}
window.renderInspection = renderInspection;
