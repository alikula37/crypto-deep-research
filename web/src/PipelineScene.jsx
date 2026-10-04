import { useEffect, useRef, useState } from "react";
import * as THREE from "three";
import { STAGES } from "./howItWorksData.js";
import "./pipelineScene.css";

const COLORS = STAGES.map((stage) => stage.color);
const STEP_NAMES = STAGES.map((stage) => stage.label);
const STAGE_X = [-5.6, -2.8, 0, 2.8, 5.6];

function StaticPipeline({ activeStep, onSelectStep }) {
  return (
    <div className="pipeline-scene-fallback">
      <svg viewBox="0 0 900 220" role="img" aria-label="Kaynaklar, araştırma, bilgi tabanı, soru-cevap ve değerlendirme kavramlarının turu">
        <defs>
          <pattern id="pipeline-static-grid" width="24" height="24" patternUnits="userSpaceOnUse">
            <path d="M 24 0 L 0 0 0 24" fill="none" stroke="#25372e" strokeWidth="0.7" />
          </pattern>
        </defs>
        <rect width="900" height="220" fill="url(#pipeline-static-grid)" />
        <path d="M 90 110 H 810" fill="none" stroke="#52675b" strokeWidth="2" strokeDasharray="5 8" />
        {STEP_NAMES.map((name, index) => {
          const x = 90 + index * 180;
          return (
            <g key={name}>
              <path
                d={`M ${x} 63 L ${x + 38} 86 L ${x + 38} 132 L ${x} 155 L ${x - 38} 132 L ${x - 38} 86 Z`}
                fill={activeStep === index ? "#223c33" : "#172720"}
                stroke={COLORS[index]}
                strokeWidth={activeStep === index ? 2.5 : 1.2}
              />
              <path d={`M ${x} 63 V 109 L ${x + 38} 86 M ${x} 109 L ${x - 38} 86 M ${x} 109 V 155`} fill="none" stroke={COLORS[index]} opacity="0.5" />
              <text x={x} y="188" fill={COLORS[index]} textAnchor="middle" fontSize="13" fontFamily="monospace">0{index + 1}</text>
            </g>
          );
        })}
      </svg>
      <div className="pipeline-scene-fallback-actions" aria-label="Araştırma akışının aşamaları">
        {STEP_NAMES.map((name, index) => (
          <button
            type="button"
            key={name}
            aria-pressed={activeStep === index}
            onClick={() => onSelectStep?.(index)}
          >
            <span>0{index + 1}</span>{name}
          </button>
        ))}
      </div>
      <p>Bu cihazda akış, sabit görselle gösteriliyor.</p>
    </div>
  );
}

/**
 * A self-contained diagram: stages are illustrative, never live telemetry.
 * The parent supplies the equivalent keyboard-accessible stage controls.
 */
export default function PipelineScene({
  activeStep = 0,
  onSelectStep,
  playing = true,
  reducedMotion = false,
  mode = "guide",
}) {
  const hostRef = useRef(null);
  const controllerRef = useRef(null);
  const propsRef = useRef({ activeStep, onSelectStep, playing, reducedMotion, mode });
  const [renderState, setRenderState] = useState("loading");
  propsRef.current = { activeStep, onSelectStep, playing, reducedMotion, mode };

  useEffect(() => {
    const host = hostRef.current;
    if (!host) return undefined;

    const geometries = new Set();
    const materials = new Set();
    let renderer;
    let scene;
    let resizeObserver;
    let intersectionObserver;
    let frame = 0;
    let disposed = false;
    let visible = true;
    let lastTime = 0;
    let elapsed = 0;
    let hoveredStep = -1;
    let pointerDown = null;
    let width = 0;
    let height = 0;
    const stageRecords = [];
    const packetRecords = [];
    const pickTargets = [];
    const raycaster = new THREE.Raycaster();
    const pointer = new THREE.Vector2();
    const packetMatrix = new THREE.Matrix4();
    const packetPosition = new THREE.Vector3();

    function geometry(value) {
      geometries.add(value);
      return value;
    }
    function material(value) {
      materials.add(value);
      return value;
    }
    function stop() {
      if (frame) cancelAnimationFrame(frame);
      frame = 0;
      lastTime = 0;
    }
    function dispose() {
      if (disposed) return;
      disposed = true;
      stop();
      resizeObserver?.disconnect();
      intersectionObserver?.disconnect();
      document.removeEventListener("visibilitychange", visibilityChange);
      window.removeEventListener("resize", resize);
      if (renderer) {
        const canvas = renderer.domElement;
        canvas.removeEventListener("pointermove", pointerMove);
        canvas.removeEventListener("pointerleave", pointerLeave);
        canvas.removeEventListener("pointerdown", pointerStart);
        canvas.removeEventListener("pointerup", pointerEnd);
        canvas.removeEventListener("webglcontextlost", contextLost);
        packetRecords.forEach(({ mesh }) => mesh.dispose());
        geometries.forEach((item) => item.dispose());
        materials.forEach((item) => item.dispose());
        renderer.dispose();
        renderer.forceContextLoss();
        canvas.remove();
      } else {
        geometries.forEach((item) => item.dispose());
        materials.forEach((item) => item.dispose());
      }
      scene?.clear();
      controllerRef.current = null;
    }
    function fail() {
      dispose();
      setRenderState("fallback");
    }
    function contextLost(event) {
      event.preventDefault();
      fail();
    }

    let camera;
    function render() {
      if (disposed || !width || !height) return;
      try {
        renderer.render(scene, camera);
      } catch {
        fail();
      }
    }
    function canAnimate() {
      return !disposed && visible && !document.hidden && propsRef.current.playing && !propsRef.current.reducedMotion;
    }
    function animate(time) {
      frame = 0;
      if (!canAnimate()) return;
      const delta = lastTime ? Math.min((time - lastTime) / 1000, 0.05) : 0;
      lastTime = time;
      elapsed += delta;
      stageRecords.forEach((stage, index) => {
        stage.core.position.y = Math.sin(elapsed * 0.65 + index * 0.7) * 0.075;
        if (stage.rotor) stage.rotor.rotation.y = elapsed * 0.1;
      });
      updatePackets();
      render();
      if (canAnimate()) frame = requestAnimationFrame(animate);
    }
    function syncAnimation() {
      if (canAnimate()) {
        if (!frame) frame = requestAnimationFrame(animate);
      } else {
        stop();
        render();
      }
    }
    function visibilityChange() {
      syncAnimation();
    }
    function resize() {
      if (disposed) return;
      const bounds = host.getBoundingClientRect();
      width = Math.round(bounds.width);
      height = Math.round(bounds.height);
      if (!width || !height) {
        stop();
        return;
      }
      const aspect = width / height;
      const halfWidth = Math.max(7.65, aspect * 2.1);
      const halfHeight = halfWidth / aspect;
      camera.left = -halfWidth;
      camera.right = halfWidth;
      camera.top = halfHeight;
      camera.bottom = -halfHeight;
      camera.updateProjectionMatrix();
      renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 1.75));
      renderer.setSize(width, height, false);
      render();
      syncAnimation();
    }
    function intersect(event) {
      const bounds = renderer.domElement.getBoundingClientRect();
      if (!bounds.width || !bounds.height) return -1;
      pointer.set(
        ((event.clientX - bounds.left) / bounds.width) * 2 - 1,
        -((event.clientY - bounds.top) / bounds.height) * 2 + 1,
      );
      raycaster.setFromCamera(pointer, camera);
      return raycaster.intersectObjects(pickTargets, false)[0]?.object.userData.step ?? -1;
    }
    function pointerMove(event) {
      if (disposed || event.pointerType === "touch") return;
      const nextStep = intersect(event);
      if (nextStep === hoveredStep) return;
      hoveredStep = nextStep;
      renderer.domElement.style.cursor = nextStep >= 0 ? "pointer" : "default";
      updateAppearance();
      render();
    }
    function pointerLeave() {
      if (disposed) return;
      hoveredStep = -1;
      renderer.domElement.style.cursor = "default";
      updateAppearance();
      render();
    }
    function pointerStart(event) {
      if (!disposed) pointerDown = { x: event.clientX, y: event.clientY, id: event.pointerId };
    }
    function pointerEnd(event) {
      if (disposed || !pointerDown || pointerDown.id !== event.pointerId) return;
      const distance = Math.hypot(event.clientX - pointerDown.x, event.clientY - pointerDown.y);
      pointerDown = null;
      if (distance > 8) return;
      const selected = intersect(event);
      if (selected >= 0) propsRef.current.onSelectStep?.(selected);
    }
    function updateAppearance() {
      stageRecords.forEach((stage, index) => {
        const active = index === propsRef.current.activeStep;
        const hovered = index === hoveredStep;
        stage.outline.opacity = active ? 0.95 : hovered ? 0.8 : 0.45;
        stage.body.emissiveIntensity = active ? 0.32 : hovered ? 0.2 : 0.09;
        stage.accent.opacity = active ? 1 : hovered ? 0.92 : 0.65;
        stage.selection.visible = active;
        stage.baseLine.opacity = active ? 0.85 : 0.32;
        stage.core.scale.setScalar(active ? 1.06 : hovered ? 1.035 : 1);
      });
      packetRecords.forEach((packet, index) => {
        packet.mesh.material.opacity = index === propsRef.current.activeStep - 1 || index === propsRef.current.activeStep ? 0.95 : 0.5;
      });
    }
    function updatePackets() {
      packetRecords.forEach(({ mesh, path }, segment) => {
        for (let index = 0; index < mesh.count; index += 1) {
          const progress = (index / mesh.count + elapsed * (propsRef.current.mode === "interview" ? 0.18 : 0.13) + segment * 0.11) % 1;
          path.getPoint(progress, packetPosition);
          packetMatrix.makeTranslation(packetPosition.x, packetPosition.y, packetPosition.z);
          mesh.setMatrixAt(index, packetMatrix);
        }
        mesh.instanceMatrix.needsUpdate = true;
      });
    }

    try {
      renderer = new THREE.WebGLRenderer({ alpha: true, antialias: true, powerPreference: "low-power" });
      renderer.setClearColor(0x000000, 0);
      renderer.outputColorSpace = THREE.SRGBColorSpace;
      renderer.toneMapping = THREE.ACESFilmicToneMapping;
      renderer.toneMappingExposure = 1.25;
      renderer.domElement.setAttribute("aria-hidden", "true");
      renderer.domElement.className = "pipeline-scene-canvas";
      host.appendChild(renderer.domElement);
      scene = new THREE.Scene();
      camera = new THREE.OrthographicCamera(-7.7, 7.7, 3, -3, 0.1, 80);
      camera.position.set(0, 7.4, 12.5);
      camera.lookAt(0, -0.15, 0);
      scene.add(new THREE.HemisphereLight(0xc3e0ce, 0x10231c, 2.4));
      const keyLight = new THREE.DirectionalLight(0xf3e9cb, 2.4);
      keyLight.position.set(-4, 7, 5);
      scene.add(keyLight);
      const fillLight = new THREE.DirectionalLight(0x6dc0cb, 1.5);
      fillLight.position.set(5, 3, -4);
      scene.add(fillLight);

      const grid = new THREE.GridHelper(28, 56, 0x3d5949, 0x294135);
      geometry(grid.geometry);
      (Array.isArray(grid.material) ? grid.material : [grid.material]).forEach((item) => {
        material(item);
        item.transparent = true;
        item.opacity = 0.34;
      });
      grid.position.set(0, -1.12, -1);
      scene.add(grid);

      const box = geometry(new THREE.BoxGeometry(1, 1, 1));
      const boxEdges = geometry(new THREE.EdgesGeometry(box));
      const baseShape = geometry(new THREE.CylinderGeometry(0.87, 0.87, 0.055, 6));
      const baseEdges = geometry(new THREE.EdgesGeometry(baseShape));
      const smallSphere = geometry(new THREE.SphereGeometry(0.06, 8, 6));
      const hitSphere = geometry(new THREE.SphereGeometry(1.12, 8, 6));
      const pickMaterial = material(new THREE.MeshBasicMaterial({ visible: false }));
      const octahedron = geometry(new THREE.OctahedronGeometry(0.66));
      const octahedronEdges = geometry(new THREE.EdgesGeometry(octahedron));
      const ring = geometry(new THREE.TorusGeometry(0.67, 0.021, 6, 48));
      const selectionRing = geometry(new THREE.TorusGeometry(0.98, 0.012, 4, 48));
      const packetShape = geometry(new THREE.BoxGeometry(0.065, 0.065, 0.065));

      function outlinedMesh(parent, shape, edgeShape, body, outline, position = [0, 0, 0], scale = [1, 1, 1]) {
        const mesh = new THREE.Mesh(shape, body);
        mesh.position.set(...position);
        mesh.scale.set(...scale);
        const edges = new THREE.LineSegments(edgeShape, outline);
        mesh.add(edges);
        parent.add(mesh);
        return mesh;
      }
      function connector(parent, points, colorMaterial) {
        const path = new THREE.CatmullRomCurve3(points.map((point) => new THREE.Vector3(...point)));
        const line = new THREE.Line(geometry(new THREE.BufferGeometry().setFromPoints(path.getPoints(20))), colorMaterial);
        parent.add(line);
        return path;
      }

      STAGE_X.forEach((x, index) => {
        const group = new THREE.Group();
        group.position.x = x;
        const core = new THREE.Group();
        group.add(core);
        const color = new THREE.Color(COLORS[index]);
        const body = material(new THREE.MeshStandardMaterial({
          color: color.clone().multiplyScalar(0.24), emissive: color,
          emissiveIntensity: 0.09, roughness: 0.42, metalness: 0.38,
        }));
        const outline = material(new THREE.LineBasicMaterial({ color, transparent: true, opacity: 0.45 }));
        const accent = material(new THREE.MeshBasicMaterial({ color, transparent: true, opacity: 0.65 }));
        const baseLine = material(new THREE.LineBasicMaterial({ color, transparent: true, opacity: 0.32 }));
        const baseMaterial = material(new THREE.MeshStandardMaterial({ color: 0x183127, metalness: 0.15, roughness: 0.9 }));
        const base = outlinedMesh(group, baseShape, baseEdges, baseMaterial, baseLine, [0, -1.07, 0]);
        base.rotation.y = Math.PI / 6;
        const selection = new THREE.Mesh(selectionRing, accent);
        selection.rotation.x = -Math.PI / 2;
        selection.position.y = -1.018;
        group.add(selection);

        const pick = new THREE.Mesh(hitSphere, pickMaterial);
        pick.position.y = -0.04;
        pick.userData.step = index;
        group.add(pick);
        pickTargets.push(pick);
        let rotor;

        if (index === 0) {
          // Independent source documents, stacked before normalization.
          for (let sheet = 0; sheet < 3; sheet += 1) {
            const documentMesh = outlinedMesh(core, box, boxEdges, body, outline, [-0.17 + sheet * 0.14, -0.13 + sheet * 0.2, -0.16 + sheet * 0.13], [0.95, 0.92, 0.11]);
            documentMesh.rotation.y = -0.12 + sheet * 0.1;
          }
          for (let line = 0; line < 3; line += 1) {
            const bar = new THREE.Mesh(box, accent);
            bar.scale.set(line === 2 ? 0.28 : 0.5, 0.022, 0.012);
            bar.position.set(0.1, 0.29 - line * 0.17, 0.3);
            core.add(bar);
          }
        } else if (index === 1) {
          // An evidence stack and independent analytical feature columns.
          for (let row = 0; row < 3; row += 1) {
            outlinedMesh(core, box, boxEdges, body, outline, [-0.2, -0.48 + row * 0.29, 0], [0.83, 0.18, 0.62]);
          }
          [0.4, 0.72, 0.98].forEach((barHeight, column) => {
            const columnMesh = outlinedMesh(core, box, boxEdges, body, outline, [0.33 + column * 0.18, -0.5 + barHeight / 2, 0.23], [0.09, barHeight, 0.12]);
            columnMesh.rotation.y = 0.05;
          });
        } else if (index === 2) {
          // Text chunks and embeddings meet in the searchable knowledge base.
          rotor = new THREE.Group();
          core.add(rotor);
          outlinedMesh(rotor, octahedron, octahedronEdges, body, outline, [0.08, 0.05, 0]);
          [-1, 1].forEach((side) => {
            outlinedMesh(core, box, boxEdges, body, outline, [-0.8, side * 0.44, 0], [0.22, 0.22, 0.22]);
            connector(core, [[-0.68, side * 0.44, 0], [-0.39, side * 0.4, 0], [-0.18, 0.1, 0]], outline);
          });
          const retrievalRing = new THREE.Mesh(ring, accent);
          retrievalRing.rotation.y = 0.3;
          retrievalRing.position.set(0.08, 0.05, 0);
          core.add(retrievalRing);
        } else if (index === 3) {
          // An answer carries attached source references.
          outlinedMesh(core, box, boxEdges, body, outline, [0, 0.08, 0], [0.98, 1.18, 0.2]);
          for (let line = 0; line < 4; line += 1) {
            const bar = new THREE.Mesh(box, accent);
            bar.scale.set(line === 3 ? 0.36 : 0.63, 0.024, 0.012);
            bar.position.set(line === 3 ? -0.13 : 0, 0.41 - line * 0.16, 0.107);
            core.add(bar);
          }
          [-0.26, 0, 0.26].forEach((citationX) => outlinedMesh(core, box, boxEdges, body, outline, [citationX, -0.67, 0.2], [0.16, 0.14, 0.14]));
        } else {
          // Validation encloses the evidence; a held-out gate is explicit.
          const validationRing = new THREE.Mesh(ring, accent);
          validationRing.scale.setScalar(1.13);
          validationRing.position.y = 0.02;
          core.add(validationRing);
          outlinedMesh(core, octahedron, octahedronEdges, body, outline, [0, 0.02, 0], [0.72, 0.72, 0.72]);
          const check = connector(core, [[-0.28, 0.02, 0.63], [-0.05, -0.19, 0.63], [0.35, 0.26, 0.63]], outline);
          const checkTube = new THREE.Mesh(geometry(new THREE.TubeGeometry(check, 12, 0.025, 5, false)), accent);
          core.add(checkTube);
          [-0.45, 0.45].forEach((gateX) => outlinedMesh(core, box, boxEdges, body, outline, [gateX, -0.8, 0], [0.1, 0.18, 0.18]));
        }

        // Tiny datum markers connect the objects to the common baseline.
        const marker = new THREE.Mesh(smallSphere, accent);
        marker.position.set(0, -1.01, 0.86);
        group.add(marker);
        stageRecords.push({ core, rotor, body, outline, accent, baseLine, selection });
        scene.add(group);
      });

      for (let segment = 0; segment < 4; segment += 1) {
        const start = STAGE_X[segment] + 0.87;
        const end = STAGE_X[segment + 1] - 0.9;
        const pathMaterial = material(new THREE.LineBasicMaterial({ color: 0x506b5c, transparent: true, opacity: 0.7 }));
        const path = connector(scene, [[start, -0.25, 0], [(start + end) / 2, -0.25, 0], [end, -0.25, 0]], pathMaterial);
        const packetMaterial = material(new THREE.MeshBasicMaterial({ color: COLORS[segment + 1], transparent: true, opacity: 0.5 }));
        const packets = new THREE.InstancedMesh(packetShape, packetMaterial, 4);
        packets.instanceMatrix.setUsage(THREE.DynamicDrawUsage);
        packets.frustumCulled = false;
        scene.add(packets);
        packetRecords.push({ mesh: packets, path });
        const arrow = new THREE.Mesh(geometry(new THREE.ConeGeometry(0.052, 0.16, 5)), packetMaterial);
        arrow.rotation.z = -Math.PI / 2;
        arrow.position.set(end - 0.01, -0.25, 0);
        scene.add(arrow);
      }

      updateAppearance();
      updatePackets();
      renderer.domElement.addEventListener("pointermove", pointerMove);
      renderer.domElement.addEventListener("pointerleave", pointerLeave);
      renderer.domElement.addEventListener("pointerdown", pointerStart);
      renderer.domElement.addEventListener("pointerup", pointerEnd);
      renderer.domElement.addEventListener("webglcontextlost", contextLost, false);
      document.addEventListener("visibilitychange", visibilityChange);
      if (typeof ResizeObserver !== "undefined") {
        resizeObserver = new ResizeObserver(resize);
        resizeObserver.observe(host);
      } else window.addEventListener("resize", resize);
      if (typeof IntersectionObserver !== "undefined") {
        intersectionObserver = new IntersectionObserver(([entry]) => {
          visible = entry.isIntersecting;
          syncAnimation();
        }, { threshold: 0.01 });
        intersectionObserver.observe(host);
      }
      controllerRef.current = {
        update() {
          if (disposed) return;
          updateAppearance();
          updatePackets();
          render();
          syncAnimation();
        },
      };
      resize();
      if (!disposed) setRenderState("ready");
    } catch {
      fail();
    }

    return dispose;
  }, []);

  useEffect(() => {
    controllerRef.current?.update();
  }, [activeStep, playing, reducedMotion, mode]);

  return (
    <div
      className="pipeline-scene"
      data-render-state={renderState}
      data-active-step={activeStep}
      data-motion={playing && !reducedMotion ? "playing" : "paused"}
      data-mode={mode}
      role="group"
      aria-label="Etkileşimli araştırma akışı. Aşamaları aşağıdaki düğmelerle de seçebilirsiniz."
    >
      <div className="pipeline-scene-mount" ref={hostRef} hidden={renderState === "fallback"} />
      {renderState === "loading" && <span className="pipeline-scene-loading" role="status">Araştırma akışı hazırlanıyor…</span>}
      {renderState === "fallback" && <StaticPipeline activeStep={activeStep} onSelectStep={onSelectStep} />}
    </div>
  );
}
