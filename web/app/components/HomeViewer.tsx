'use client';

import { useCallback, useEffect, useMemo, useReducer, useRef, useState } from 'react';
import {
  Box3,
  Box3Helper,
  Color,
  DirectionalLight,
  GridHelper,
  Group,
  HemisphereLight,
  Mesh,
  NeutralToneMapping,
  NoToneMapping,
  OrthographicCamera,
  PCFSoftShadowMap,
  PerspectiveCamera,
  Raycaster,
  Scene,
  SRGBColorSpace,
  Vector2,
  Vector3,
  WebGLRenderer,
} from 'three';
import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js';
import {
  applyElementVisibility,
  canToggleVisibility,
  defaultHiddenElementIds,
  elementIdForObject,
  filterElementGroups,
  generatedElementIds,
  isolateElements,
  nodeElementIndex,
  reviewElementIds,
  withElementVisibility,
  type RenderManifest,
  type ReviewPreset,
} from '../lib/model';
import { canonicalSectionPlane, configureDirectionalShadow, configureOrbitControls, disposeSceneResources, frameBounds, frameModel, isObjectVisible, modelNorthRotation } from '../lib/scene';
import { loadCatalog, loadModelAssets, modelAssetUrl, modelLabel, type CatalogModel } from '../lib/catalog';
import ViewOrientation from './ViewOrientation';
import DesignRequirements from './DesignRequirements';
import PanelControls from './PanelControls';
import QuickStart from './QuickStart';
import ElementDetails, { initialDetailsView, type DetailsView } from './ElementDetails';
import SelectionHistory from './SelectionHistory';
import { emptySelectionHistory, selectionHistoryReducer } from '../lib/selection-history';
import { PickGesture } from '../lib/pick-gesture';
import { contextElementIds, navigationGroups, reinforcementElementIds, selectionNodes, type ContextAction, type NavigationGrouping } from '../lib/navigation';
import type { DisplayUnits } from '../lib/properties';
import { readPanelVisibility, savePanelVisibility, type PanelVisibility, type ReviewPanel } from '../lib/panels';
import { NamedViewPresentation } from '../lib/named-views';
import { activeCapNodes, type VisualView } from '../lib/visual-view';

interface SceneHandle {
  controls: OrbitControls;
  camera: PerspectiveCamera | OrthographicCamera;
  model: Group;
  renderer: WebGLRenderer;
  scene: Scene;
  sun: DirectionalLight;
  presentation: NamedViewPresentation;
  setCamera: (camera: PerspectiveCamera | OrthographicCamera, target: Vector3) => void;
  setInspectionLighting: (enabled: boolean) => void;
}

export default function HomeViewer() {
  const [panels, setPanels] = useState(readPanelVisibility);
  const togglePanel = (panel: ReviewPanel) => {
    const visible = !panels[panel];
    setPanels((current) => ({ ...current, [panel]: !current[panel] }));
    savePanelVisibility(panel, visible);
  };
  const [models, setModels] = useState<CatalogModel[]>([]);
  const [selectedKey, setSelectedKey] = useState('');
  const [catalogMessage, setCatalogMessage] = useState('Reading the model catalog…');
  const [catalogStatus, setCatalogStatus] = useState<'loading' | 'error'>('loading');

  useEffect(() => {
    const controller = new AbortController();
    loadCatalog(controller.signal).then((catalog) => {
      if (controller.signal.aborted) return;
      setModels(catalog.models);
      setSelectedKey(catalog.models[0]?.key ?? '');
      if (!catalog.models.length) {
        setCatalogStatus('error');
        setCatalogMessage('No models are published. Build a model with --web-assets web/public/model.');
      }
    }).catch((error: unknown) => {
      if (controller.signal.aborted) return;
      setCatalogStatus('error');
      setCatalogMessage(`${error instanceof Error ? error.message : 'Catalog unavailable'}. Build models with --web-assets web/public/model, then reload.`);
    });
    return () => controller.abort();
  }, []);

  const entry = models.find((model) => model.key === selectedKey);
  return <ModelReview
    key={entry ? `${entry.key}/${entry.version}` : catalogMessage}
    entry={entry} models={models} onSwitch={setSelectedKey}
    catalogMessage={catalogMessage} catalogStatus={catalogStatus}
    panels={panels} onTogglePanel={togglePanel}
  />;
}

function ModelReview({ entry, models, onSwitch, catalogMessage, catalogStatus, panels, onTogglePanel }: {
  entry?: CatalogModel;
  models: CatalogModel[];
  onSwitch: (key: string) => void;
  catalogMessage: string;
  catalogStatus: 'loading' | 'error';
  panels: PanelVisibility;
  onTogglePanel: (panel: ReviewPanel) => void;
}) {
  const canvasHost = useRef<HTMLDivElement>(null);
  const sceneHandle = useRef<SceneHandle | null>(null);
  const highlight = useRef<Box3Helper | null>(null);
  const manifestRef = useRef<RenderManifest | null>(null);
  const hiddenIdsRef = useRef<ReadonlySet<string>>(new Set());
  const nodeMask = useRef<Set<string> | null>(null);
  const activeView = useRef<VisualView>({});
  const [namedViewId, setNamedViewId] = useState('');
  const [viewMessage, setViewMessage] = useState('');
  const [manifest, setManifest] = useState<RenderManifest | null>(null);
  const [hiddenIds, setHiddenIds] = useState<ReadonlySet<string>>(new Set());
  const [history, dispatchSelection] = useReducer(selectionHistoryReducer, emptySelectionHistory);
  const selectedId = history.entries[history.index];
  const [detailsViews, setDetailsViews] = useState<Record<string, DetailsView>>({});
  const [listRequest, setListRequest] = useState<{ id: string } | null>(null);
  const componentList = useRef<HTMLElement>(null);
  const [status, setStatus] = useState<'loading' | 'ready' | 'error'>(entry ? 'loading' : catalogStatus);
  const [message, setMessage] = useState(entry ? 'Loading model…' : catalogMessage);
  const [loadAttempt, setLoadAttempt] = useState(0);
  const [solarStudyId, setSolarStudyId] = useState('');
  const [sectionAxis, setSectionAxis] = useState<'none' | 'x' | 'y' | 'z'>('none');
  const [sectionOffset, setSectionOffset] = useState(0);
  const [northRotation, setNorthRotation] = useState(0);
  const [componentQuery, setComponentQuery] = useState('');
  const [grouping, setGrouping] = useState<NavigationGrouping>('kind');
  const [displayUnits, setDisplayUnits] = useState<DisplayUnits>('metric');
  const [isolateOnClick, setIsolateOnClick] = useState(false);
  const [tourPanel, setTourPanel] = useState<ReviewPanel | 'none' | null>(null);
  const displayedPanels = tourPanel ? { components: tourPanel === 'components', details: tourPanel === 'details' } : panels;

  const groups = useMemo(() => (manifest ? navigationGroups(manifest, grouping, Boolean(componentQuery.trim())) : []), [manifest, grouping, componentQuery]);
  const filteredGroups = useMemo(() => filterElementGroups(groups, componentQuery), [groups, componentQuery]);
  const matchCount = new Set(filteredGroups.flatMap((group) => group.elements.map(([id]) => id))).size;
  const selected = selectedId && manifest ? manifest.elements[selectedId] : null;
  const selectedVisibilityIds = manifest && selected && selectedId
    ? [...generatedElementIds(manifest, selected.nodes.length ? [selectedId] : contextElementIds(manifest, selectedId))]
        .filter((id) => canToggleVisibility(manifest.elements[id]))
    : [];
  const spaceIds = useMemo(() => manifest
    ? Object.entries(manifest.elements)
        .filter(([, element]) => element.kind === 'space' && canToggleVisibility(element))
        .map(([elementId]) => elementId)
    : [], [manifest]);
  const spacesVisible = spaceIds.length > 0 && spaceIds.every((id) => !hiddenIds.has(id));

  const selectElement = useCallback((elementId: string | null) => {
    dispatchSelection({ type: 'visit', id: elementId });
  }, []);

  useEffect(() => {
    const handle = sceneHandle.current;
    const currentManifest = manifestRef.current;
    if (!handle || !currentManifest) return;
    if (highlight.current) {
      handle.scene.remove(highlight.current);
      disposeSceneResources(highlight.current);
    }
    highlight.current = null;
    if (!selectedId) return;
    const element = currentManifest.elements[selectedId];
    if (!element) return;
    const objects = selectionNodes(currentManifest, selectedId)
      .map((name) => handle.scene.getObjectByName(name))
      .filter((object): object is NonNullable<typeof object> => Boolean(object));
    if (!objects.length) return;
    const bounds = new Box3();
    for (const object of objects) bounds.expandByObject(object);
    const helper = new Box3Helper(bounds, new Color('#eaa340'));
    helper.name = 'selection-outline';
    helper.visible = objects.some(isObjectVisible);
    handle.scene.add(helper);
    highlight.current = helper;
  }, [selectedId, manifest]);

  useEffect(() => {
    if (!listRequest || !displayedPanels.components) return;
    const row = [...(componentList.current?.querySelectorAll<HTMLButtonElement>('[data-component-id]') ?? [])]
      .find((button) => button.dataset.componentId === listRequest.id);
    row?.scrollIntoView({ block: 'nearest' });
    row?.focus({ preventScroll: true });
  }, [listRequest, displayedPanels.components]);

  const resetView = useCallback(() => {
    const handle = sceneHandle.current;
    if (handle) frameModel(handle.camera, handle.controls, handle.model);
  }, []);

  const applySolarStudy = useCallback((studyId: string) => {
    setSolarStudyId(studyId);
    const handle = sceneHandle.current;
    const study = manifestRef.current?.solarStudies?.find((entry) => entry.id === studyId);
    if (!handle) return;
    handle.setInspectionLighting(false);
    const direction = study ? new Vector3(study.sunDirection[0], study.sunDirection[2], -study.sunDirection[1]) : undefined;
    handle.sun.intensity = study && study.altitudeDegrees <= 0 ? 0 : 3.2;
    configureDirectionalShadow(handle.sun, new Box3().setFromObject(handle.model), direction);
  }, []);

  const applySection = useCallback((axis: 'none' | 'x' | 'y' | 'z', offset: number) => {
    setSectionAxis(axis);
    setSectionOffset(offset);
    const handle = sceneHandle.current;
    if (handle) {
      handle.renderer.clippingPlanes = axis === 'none' ? [] : [canonicalSectionPlane(axis, offset)];
      activeView.current = { ...activeView.current, sections: axis === 'none' ? [] : [{ axis, position: offset }] };
      const currentManifest = manifestRef.current;
      if (currentManifest) {
        const visible = new Set<string>();
        handle.model.traverse((object) => { if (object instanceof Mesh && object.visible) visible.add(object.name); });
        const next = activeCapNodes(currentManifest, visible, activeView.current);
        handle.model.traverse((object) => { if (object instanceof Mesh) object.visible = next.has(object.name); });
      }
      setNamedViewId('');
      setViewMessage('Custom section. Select a named view to restore its settings.');
    }
  }, []);

  const applyNamedView = (id: string) => {
    const handle = sceneHandle.current;
    const host = canvasHost.current;
    if (!manifest || !handle || !host) return;
    const entry = manifest.namedViews?.find((item) => item.id === id);
    if (!entry) return;
    try {
      const result = handle.presentation.apply(handle.model, manifest, entry.view, Math.max(host.clientWidth, 1), Math.max(host.clientHeight, 1));
      handle.renderer.clippingPlanes = result.planes;
      handle.setCamera(result.camera, result.target);
      handle.setInspectionLighting(true);
      setSolarStudyId('');
      nodeMask.current = result.visible;
      activeView.current = entry.view;
      hiddenIdsRef.current = result.hidden;
      setHiddenIds(result.hidden);
      const section = entry.view.sections?.[0];
      setSectionAxis(section?.axis ?? 'none');
      setSectionOffset(section?.position ?? 0);
      selectElement(null);
      setNamedViewId(id);
      setViewMessage(entry.description);
    } catch (error) {
      setViewMessage(`View unavailable: ${error instanceof Error ? error.message : String(error)}`);
    }
  };

  const resetPresentation = () => {
    const handle = sceneHandle.current;
    if (!handle || !manifest) return;
    handle.presentation.clear();
    handle.setInspectionLighting(false);
    activeView.current = {};
    nodeMask.current = null;
    handle.renderer.clippingPlanes = [];
    setSectionAxis('none'); setSectionOffset(0);
    setNamedViewId(''); setViewMessage('Default presentation restored.');
    const camera = new PerspectiveCamera(42, Math.max(handle.renderer.domElement.clientWidth, 1) / Math.max(handle.renderer.domElement.clientHeight, 1), 0.02, 500);
    handle.setCamera(camera, new Vector3());
    setHiddenIds(defaultHiddenElementIds(manifest));
    frameModel(camera, handle.controls, handle.model);
  };

  useEffect(() => {
    const host = canvasHost.current;
    if (!host || !entry) return;
    const controller = new AbortController();
    const scene = new Scene();
    scene.background = new Color('#d9ddd8');
    let camera: PerspectiveCamera | OrthographicCamera = new PerspectiveCamera(42, 1, 0.02, 500);
    const renderer = new WebGLRenderer({ antialias: true, powerPreference: 'high-performance', logarithmicDepthBuffer: true });
    renderer.outputColorSpace = SRGBColorSpace;
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    renderer.shadowMap.enabled = true;
    renderer.shadowMap.type = PCFSoftShadowMap;
    host.appendChild(renderer.domElement);

    let controls = new OrbitControls(camera, renderer.domElement);
    configureOrbitControls(controls);
    const updateOrientation = () => setNorthRotation(modelNorthRotation(camera));
    controls.addEventListener('change', updateOrientation);
    updateOrientation();

    const ambient = new HemisphereLight('#f3f5ef', '#77766d', 2.1);
    scene.add(ambient);
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
    const presentation = new NamedViewPresentation();
    const setInspectionLighting = (enabled: boolean) => {
      grid.visible = !enabled;
      renderer.shadowMap.enabled = !enabled;
      renderer.toneMapping = enabled ? NeutralToneMapping : NoToneMapping;
      scene.background = new Color(enabled ? '#edf0f2' : '#d9ddd8');
      ambient.color.set(enabled ? '#ffffff' : '#f3f5ef');
      ambient.groundColor.set(enabled ? '#a7a3a0' : '#77766d');
      ambient.intensity = enabled ? 2.6 : 2.1;
      sun.color.set(enabled ? '#ffffff' : '#fff3da');
      sun.intensity = enabled ? 2.5 : 3.2;
      if (enabled) { sun.position.copy(camera.position); sun.target.position.copy(controls.target); }
      else configureDirectionalShadow(sun, new Box3().setFromObject(model));
    };
    const setCamera = (next: PerspectiveCamera | OrthographicCamera, target: Vector3) => {
      controls.removeEventListener('change', updateOrientation);
      controls.dispose();
      camera = next;
      controls = new OrbitControls(camera, renderer.domElement);
      configureOrbitControls(controls);
      controls.target.copy(target);
      controls.update();
      controls.addEventListener('change', updateOrientation);
      updateOrientation();
      if (sceneHandle.current) { sceneHandle.current.camera = camera; sceneHandle.current.controls = controls; }
    };
    sceneHandle.current = { camera, controls, model, renderer, scene, sun, presentation, setCamera, setInspectionLighting };

    const resize = () => {
      const width = host.clientWidth;
      const height = host.clientHeight;
      const aspect = Math.max(width, 1) / Math.max(height, 1);
      if (camera instanceof PerspectiveCamera) camera.aspect = aspect;
      else {
        const half = (camera.top - camera.bottom) / 2;
        camera.left = -half * aspect; camera.right = half * aspect;
      }
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

    loadModelAssets(entry, controller.signal)
      .then(({ manifest: loadedManifest, model: loadedModel }) => {
        if (controller.signal.aborted) {
          disposeSceneResources(loadedModel);
          return;
        }
        scene.remove(model);
        model = loadedModel;
        model.name = 'resolved-home';
        model.traverse((object) => {
          if (object instanceof Mesh) {
            object.castShadow = true;
            object.receiveShadow = true;
          }
        });
        scene.add(model);
        configureDirectionalShadow(sun, new Box3().setFromObject(model));
        sceneHandle.current = { camera, controls, model, renderer, scene, sun, presentation, setCamera, setInspectionLighting };
        for (const [elementId, element] of Object.entries(loadedManifest.elements)) {
          applyElementVisibility(scene, element, element.defaultVisible);
          const object = scene.getObjectByName(element.nodes[0] ?? '');
          if (object) object.userData.homeDesignId = elementId;
        }
        for (const [node, mesh] of Object.entries(loadedManifest.meshes ?? {})) {
          if (mesh.inspectionCap) { const object = model.getObjectByName(node); if (object) object.visible = false; }
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
        if (controller.signal.aborted) return;
        setStatus('error');
        setMessage(error instanceof Error ? error.message : 'The model could not be loaded');
      });

    const gesture = new PickGesture();
    const onPointerDown = (event: PointerEvent) => gesture.down(event);
    const onPointerMove = (event: PointerEvent) => gesture.move(event);
    const onPointerCancel = (event: PointerEvent) => gesture.cancel(event.pointerId);
    const onPointerUp = (event: PointerEvent) => {
      if (!gesture.up(event) || event.shiftKey || event.ctrlKey || event.metaKey || event.altKey) return;
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
          return elementId && isObjectVisible(intersection.object) && !hiddenIdsRef.current.has(elementId)
            && renderer.clippingPlanes.every((plane) => plane.distanceToPoint(intersection.point) >= 0);
        });
      selectElement(hit ? elementIdForObject(hit.object, index) : null);
    };
    renderer.domElement.addEventListener('pointerdown', onPointerDown);
    renderer.domElement.addEventListener('pointermove', onPointerMove);
    renderer.domElement.addEventListener('pointercancel', onPointerCancel);
    renderer.domElement.addEventListener('lostpointercapture', onPointerCancel);
    renderer.domElement.addEventListener('pointerup', onPointerUp);

    return () => {
      controller.abort();
      cancelAnimationFrame(frame);
      observer.disconnect();
      renderer.domElement.removeEventListener('pointerdown', onPointerDown);
      renderer.domElement.removeEventListener('pointermove', onPointerMove);
      renderer.domElement.removeEventListener('pointercancel', onPointerCancel);
      renderer.domElement.removeEventListener('lostpointercapture', onPointerCancel);
      renderer.domElement.removeEventListener('pointerup', onPointerUp);
      controls.dispose();
      controls.removeEventListener('change', updateOrientation);
      presentation.clear();
      disposeSceneResources(scene);
      sun.shadow.dispose();
      renderer.dispose();
      renderer.forceContextLoss();
      host.replaceChildren();
      sceneHandle.current = null;
      manifestRef.current = null;
      highlight.current = null;
    };
  }, [entry, loadAttempt, selectElement]);

  useEffect(() => {
    if (!manifest || !sceneHandle.current) return;
    hiddenIdsRef.current = hiddenIds;
    for (const [elementId, element] of Object.entries(manifest.elements).sort(([, left], [, right]) => Number(Boolean(left.parentId)) - Number(Boolean(right.parentId)))) {
      applyElementVisibility(sceneHandle.current.scene, element, !hiddenIds.has(elementId));
    }
    const visible = new Set<string>();
    sceneHandle.current.model.traverse((object) => {
      if (object instanceof Mesh && object.visible && (!nodeMask.current || nodeMask.current.has(object.name))) visible.add(object.name);
    });
    const nodes = activeCapNodes(manifest, visible, activeView.current);
    sceneHandle.current.model.traverse((object) => { if (object instanceof Mesh) object.visible = nodes.has(object.name); });
    if (highlight.current && selectedId) {
      highlight.current.visible = selectionNodes(manifest, selectedId).some((name) => {
        const object = sceneHandle.current!.model.getObjectByName(name);
        return object !== undefined && isObjectVisible(object);
      });
    }
  }, [hiddenIds, manifest, selectedId]);

  const clickVisibility = (elementIds: string[]) => {
    if (!manifest) return;
    const visible = elementIds.every((id) => !hiddenIdsRef.current.has(id));
    if (isolateOnClick) nodeMask.current = null;
    else if (!visible && nodeMask.current) for (const id of elementIds) for (const node of selectionNodes(manifest, id)) nodeMask.current.add(node);
    const next = isolateOnClick
      ? isolateElements(manifest, elementIds)
      : withElementVisibility(manifest, hiddenIdsRef.current, elementIds, !visible);
    if (selectedId && next.has(selectedId)) selectElement(null);
    hiddenIdsRef.current = next;
    setHiddenIds(next);
  };

  const setSpacesVisible = useCallback((visible: boolean) => {
    if (!manifest) return;
    if (visible && nodeMask.current) for (const id of spaceIds) for (const node of selectionNodes(manifest, id)) nodeMask.current.add(node);
    if (!visible && selectedId && spaceIds.includes(selectedId)) {
      selectElement(null);
    }
    setHiddenIds((current) => {
      const next = withElementVisibility(manifest, current, spaceIds, visible);
      hiddenIdsRef.current = next;
      return next;
    });
  }, [manifest, selectElement, selectedId, spaceIds]);

  const showAll = useCallback(() => {
    nodeMask.current = null;
    const next = new Set<string>();
    hiddenIdsRef.current = next;
    setHiddenIds(next);
  }, []);

  const showDiscipline = (preset: ReviewPreset) => {
    if (!manifest) return;
    nodeMask.current = null;
    const next = isolateElements(manifest, reviewElementIds(manifest, preset));
    if (selectedId && next.has(selectedId)) selectElement(null);
    hiddenIdsRef.current = next;
    setHiddenIds(next);
  };

  const isolateContext = (scope: ContextAction) => {
    if (!manifest || !selectedId) return;
    nodeMask.current = null;
    const ids = scope === 'reinforcement' ? reinforcementElementIds(manifest, selectedId)
      : contextElementIds(manifest, selectedId, scope === 'reveal' ? 'contents' : scope)
        .filter((id) => scope !== 'reveal' || id !== selectedId);
    const next = isolateElements(manifest, ids);
    hiddenIdsRef.current = next;
    setHiddenIds(next);
    if (scope !== 'reveal' && scope !== 'reinforcement' && next.has(selectedId)) selectElement(null);
    const handle = sceneHandle.current;
    if (handle) {
      const bounds = new Box3();
      for (const id of ids) for (const name of manifest.elements[id].nodes) {
        const object = handle.scene.getObjectByName(name);
        if (object) bounds.expandByObject(object);
      }
      frameBounds(handle.camera, handle.controls, bounds);
    }
  };

  const findSelection = () => {
    if (!selectedId) return;
    setComponentQuery(selectedId);
    setListRequest({ id: selectedId });
    if (!panels.components) onTogglePanel('components');
    // On narrow screens the inspector overlays the component list.
    if (window.matchMedia('(max-width: 1000px)').matches && panels.details) onTogglePanel('details');
  };

  const showSelection = () => {
    const handle = sceneHandle.current;
    if (!manifest || !selectedId || !handle) return;
    const ids = manifest.elements[selectedId].nodes.length ? [selectedId] : contextElementIds(manifest, selectedId);
    if (nodeMask.current) for (const id of ids) for (const node of selectionNodes(manifest, id)) nodeMask.current.add(node);
    const next = withElementVisibility(manifest, hiddenIdsRef.current, ids, true);
    hiddenIdsRef.current = next;
    setHiddenIds(next);
    const bounds = new Box3();
    for (const name of selectionNodes(manifest, selectedId)) {
      const object = handle.scene.getObjectByName(name);
      if (object) bounds.expandByObject(object);
    }
    frameBounds(handle.camera, handle.controls, bounds);
  };

  const hideSelection = () => {
    if (!manifest || !selectedId) return;
    const ids = manifest.elements[selectedId].nodes.length ? [selectedId] : contextElementIds(manifest, selectedId);
    const next = withElementVisibility(manifest, hiddenIdsRef.current, ids, false);
    hiddenIdsRef.current = next;
    setHiddenIds(next);
  };

  return (
    <main className={`review-shell ${displayedPanels.components ? '' : 'components-hidden'} ${displayedPanels.details ? '' : 'details-hidden'}`}>
      <header className="review-header">
        <div className="brand-mark" aria-hidden="true"><span /><span /><span /></div>
        <div className="brand-copy">
          <p>IFC-aligned model</p>
          <h1>{manifest?.project.name ?? entry?.name ?? 'Home Design Review'}</h1>
        </div>
        <div className="header-status">
          <span className={`status-dot status-${status}`} />
          <span className="model-status-message" role="status">{status === 'error' ? 'Model unavailable' : message}</span>
          {models.length > 0 && <select
            className="model-switcher" aria-label="Model" value={entry?.key ?? ''}
            onChange={(event) => onSwitch(event.target.value)}
          >
            {models.map((model) => <option key={model.key} value={model.key}>{modelLabel(model, models)}</option>)}
          </select>}
          {manifest && <span className="revision-badge">rev {manifest.sourceRevision}</span>}
        </div>
        <QuickStart ready={status === 'ready'} onPanelFocus={setTourPanel} />
      </header>

      <PanelControls visibility={displayedPanels} onToggle={onTogglePanel} />
      <aside id="components-panel" className="model-tree" hidden={!displayedPanels.components} aria-label="Model components">
        <div className="panel-heading">
          <div><p>Model index</p><h2>Components</h2></div>
          <span>{manifest ? Object.values(manifest.elements).filter((element) => !element.parentId).length : '—'}</span>
        </div>
        <div className="component-filter" id="component-filter">
          <label htmlFor="component-grouping">Group by</label>
          <select id="component-grouping" value={grouping} onChange={(event) => setGrouping(event.target.value as NavigationGrouping)}>
            <option value="kind">Component type</option><option value="assembly">Assembly</option><option value="room">Room</option><option value="host">Host</option><option value="system">Service system</option>
          </select>
          <label htmlFor="component-search">Filter by name or ID</label>
          <div className="component-search-field">
            <input id="component-search" type="search" value={componentQuery}
              placeholder="Find components…" onChange={(event) => setComponentQuery(event.target.value)} />
            {componentQuery && <button type="button" aria-label="Clear component filter" onClick={() => setComponentQuery('')}>×</button>}
          </div>
          <span role="status">{componentQuery.trim() ? `${matchCount} matching components` : `${matchCount} components`}</span>
        </div>
        <nav className="tree-groups" ref={componentList}>
          {manifest && <DesignRequirements manifest={manifest} />}
          {manifest && filteredGroups.length === 0 && <p className="no-components">No matching components.</p>}
          {filteredGroups.map((group) => {
            const fullGroup = groups.find((entry) => (entry.id ?? entry.kind) === (group.id ?? group.kind))!;
            const groupIds = fullGroup.elements.filter(([, element]) => canToggleVisibility(element)).map(([id]) => id);
            const visibleCount = groupIds.filter((id) => !hiddenIds.has(id)).length;
            const groupVisible = visibleCount > 0;
            const mixed = groupVisible && visibleCount < groupIds.length;
            const groupAction = isolateOnClick ? 'Isolate' : visibleCount === groupIds.length ? 'Hide' : 'Show';
            return <section key={group.id ?? group.kind}>
              <div className="component-group-heading">
                <h3>{group.label}<span>{group.elements.length}</span></h3>
                {groupIds.length > 0 && <button type="button" className="visibility-toggle"
                  aria-label={`${groupAction} ${group.label} group`}
                  aria-pressed={mixed ? 'mixed' : !groupVisible}
                  title={`${groupAction} entire ${group.label} group${mixed ? ' (partially hidden)' : ''}`}
                  onClick={() => clickVisibility(groupIds)}>
                  <VisibilityIcon visible={groupVisible} mixed={mixed} />
                </button>}
              </div>
              {group.elements.map(([elementId, element]) => {
                const canToggle = canToggleVisibility(element);
                const visible = !canToggle || !hiddenIds.has(elementId);
                return (
                  <div className={`component-row ${visible ? '' : 'component-hidden'}`} key={elementId}>
                    <button
                      className={`component-select ${selectedId === elementId ? 'selected' : ''}`}
                      data-component-id={elementId}
                      aria-current={selectedId === elementId ? 'true' : undefined}
                      onClick={() => selectElement(elementId)}
                    >
                      <span className={`kind-swatch kind-${element.kind}`} />
                      <span><strong>{element.name}</strong><small>{elementId}</small></span>
                    </button>
                    {canToggle && <button
                      className="visibility-toggle"
                      type="button"
                      aria-label={`${isolateOnClick ? 'Isolate' : visible ? 'Hide' : 'Show'} ${element.name}`}
                      aria-pressed={!visible}
                      title={`${isolateOnClick ? 'Isolate' : visible ? 'Hide' : 'Show'} ${element.name}`}
                      onClick={() => clickVisibility([elementId])}
                    >
                      <VisibilityIcon visible={visible} />
                    </button>}
                  </div>
                );
              })}
            </section>;
          })}
        </nav>
      </aside>

      <section className={`viewport ${manifest?.namedViews?.length ? 'has-named-views' : ''}`} aria-label="Interactive three-dimensional home model">
        <div ref={canvasHost} className="canvas-host" />
        {!!manifest?.namedViews?.length && <div className="named-view-tools">
          <label>Saved view <select aria-label="Saved view" value={namedViewId} onChange={(event) => applyNamedView(event.target.value)}>
            <option value="" disabled>Choose a view…</option>
            {manifest.namedViews.map((view) => <option key={view.id} value={view.id}>{view.title}</option>)}
          </select></label>
          <button type="button" onClick={() => applyNamedView(namedViewId)} disabled={!namedViewId}>Restore view</button>
          <button type="button" onClick={resetPresentation}>Reset presentation</button>
          <p role="status">{viewMessage || 'Choose a prepared view, then orbit, pan or inspect components.'}</p>
        </div>}
        {status === 'loading' && <div className="loading-card"><span /><p>Resolving the building view</p></div>}
        {status === 'error' && <div className="error-card" role="alert"><strong>Preview unavailable</strong><p>{message}</p>
          {entry && <button onClick={() => { setStatus('loading'); setMessage('Loading model…'); setLoadAttempt((attempt) => attempt + 1); }}>Retry model</button>}
        </div>}
        <div className="viewport-tools">
          <button onClick={resetView} title="Frame the complete model">Frame model</button>
          <button onClick={showAll} disabled={hiddenIds.size === 0} title="Show every component with 3D geometry">
            Show all
          </button>
          {(['envelope', 'framing', 'services'] as const).map((preset) => (
            <button key={preset} onClick={() => showDiscipline(preset)}
              disabled={!manifest || reviewElementIds(manifest, preset).length === 0}
              title={`Show only ${preset} components`}>
              {preset[0].toUpperCase() + preset.slice(1)}
            </button>
          ))}
          <label title="Eye clicks show only the chosen component or group. Turning this off keeps current visibility.">
            <input type="checkbox" checked={isolateOnClick} onChange={(event) => setIsolateOnClick(event.target.checked)} />
            <span>Isolate on eye click</span>
          </label>
          <label>
            <input
              type="checkbox"
              checked={spacesVisible}
              disabled={spaceIds.length === 0}
              onChange={(event) => setSpacesVisible(event.target.checked)}
            />
            <span>Show spaces</span>
          </label>
          {!!manifest?.solarStudies?.length && (
            <label>
              <span>Sun study</span>
              <select aria-label="Sun study" value={solarStudyId} onChange={(event) => applySolarStudy(event.target.value)}>
                <option value="">Presentation light</option>
                {manifest.solarStudies.map((study) => <option key={study.id} value={study.id}>{study.name}</option>)}
              </select>
            </label>
          )}
          {manifest?.reports && entry && <a href={modelAssetUrl(entry, manifest.reports.drawings)} target="_blank" rel="noreferrer">Drawings</a>}
          {manifest?.reports && entry && <a href={modelAssetUrl(entry, manifest.reports.schedules)} download>Schedules</a>}
          {manifest?.reports && entry && <a href={modelAssetUrl(entry, manifest.reports.envelope)} download>Envelope</a>}
          <label>
            <span>Cut</span>
            <select aria-label="Section axis" value={sectionAxis} onChange={(event) => applySection(event.target.value as 'none' | 'x' | 'y' | 'z', sectionOffset)}>
              <option value="none">Off</option><option value="x">X</option><option value="y">Y</option><option value="z">Z</option>
            </select>
          </label>
          {sectionAxis !== 'none' && <label><span>mm</span><input aria-label="Section position in millimetres" type="number" step="100" value={sectionOffset} onChange={(event) => applySection(sectionAxis, Number(event.target.value))} /></label>}
        </div>
        <ViewOrientation northRotation={northRotation} />
      </section>

      <aside id="details-panel" className="inspector" hidden={!displayedPanels.details} aria-label="Element details">
        <div className="panel-heading">
          <div><p>Selection</p><h2>{selected ? selected.kindLabel ?? selected.kind : 'Nothing selected'}</h2></div>
          {selected && <span className={`large-swatch kind-${selected.kind}`} />}
        </div>
        <SelectionHistory history={history} manifest={manifest} onGo={(index) => dispatchSelection({ type: 'go', index })} onClear={() => selectElement(null)} />
        {selected && selectedId && manifest ? (
          <>
            <ElementDetails key={selectedId} elementId={selectedId} manifest={manifest} units={displayUnits} onUnits={setDisplayUnits} onSelect={selectElement} onIsolate={isolateContext}
              view={detailsViews[selectedId] ?? initialDetailsView}
              onView={(changes) => setDetailsViews((views) => ({ ...views, [selectedId]: { ...(views[selectedId] ?? initialDetailsView), ...changes } }))}
              onFind={findSelection} onShow={showSelection} onHide={hideSelection} hasGeometry={selectionNodes(manifest, selectedId).length > 0}
              hidden={selectedVisibilityIds.length > 0 && selectedVisibilityIds.every((id) => hiddenIds.has(id))} />
            {manifest?.solarStudies?.filter((study) => study.id === solarStudyId).map((study) => {
              const opening = study.openings.find((entry) => entry.elementId === selectedId);
              return opening ? <p className="solar-result" key={study.id}>{study.name}: {Math.round(opening.unshadedFraction * 100)}% of sampled opening receives direct sun. {study.at}</p> : null;
            })}
          </>
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

function VisibilityIcon({ visible, mixed = false }: { visible: boolean; mixed?: boolean }) {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true">
      <path d="M2.5 12s3.5-6 9.5-6 9.5 6 9.5 6-3.5 6-9.5 6-9.5-6-9.5-6Z" />
      <circle cx="12" cy="12" r="2.5" />
      {!visible && <path className="visibility-slash" d="m4 4 16 16" />}
      {mixed && <path className="visibility-slash" d="M3 21h18" />}
    </svg>
  );
}
