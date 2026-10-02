import { useEffect, useRef, useState } from "react";
import * as THREE from "three";
import "./ragMechanismScene.css";

const CYAN = "#3fb0c4", GOLD = "#e0bb55", GREEN = "#5cd08d";
const PHASE_LABELS = ["Kaynak doküman", "Token pencereleri", "Embedding vektörleri", "İki bağımsız arama", "RRF ile tek sıralama", "Seçilmiş bağlam", "Kaynaklara bağlı yanıt"];
const DEFAULT_RANKINGS = { dense: ["C3", "C1", "C2"], bm25: ["C1", "C2", "C3"], fused: ["C1", "C3", "C2"], selected: ["C1", "C3", "C2"] };
const clampPhase = (phase) => Math.max(0, Math.min(6, Math.round(Number(phase) || 0)));
function sharedText(left, right) {
  if (!left || !right) return "";
  for (let length = Math.min(left.length, right.length, 600); length > 0; length -= 1) {
    const prefix = right.slice(0, length);
    if (left.endsWith(prefix)) return prefix;
  }
  return "";
}

function FallbackGraph({ phase, chunks, rankings, selectedChunkId, onSelectChunk }) {
  const ids = phase < 3 ? chunks.map((chunk) => chunk.id) : (phase === 3 ? rankings.dense : phase === 4 ? rankings.fused : rankings.selected).slice(0, 6);
  return <div className="rag-mechanism-fallback">
    <div className="rag-mechanism-static-track"><span>Doküman</span><b>→</b><span>Token pencereleri</span><b>→</b><span>Vektör + BM25</span><b>→</b><span>RRF</span><b>→</b><span>Bağlam → Yanıt</span></div>
    {phase === 3 && <p>Dense: {rankings.dense.join(" → ")}<br />BM25: {rankings.bm25.join(" → ")}</p>}
    <div className="rag-mechanism-static-cards">{ids.map((id) => <button type="button" key={id} onClick={() => onSelectChunk?.(id)} aria-pressed={id === selectedChunkId}>{id}</button>)}</div>
    <p>Akış bu cihazda sabit görselle gösteriliyor. Altın alanlar, ortak tokenları temsil eder.</p>
  </div>;
}

/** Geometry frames recorded data; rendering never invents passage text, scores or vector values. */
export default function RagMechanismScene({ phase = 0, chunks = [], rankings: rankingInput, vectorsById = {}, fusionScores = {}, sourceInfo = {}, embeddingDimensions, selectedChunkId, onSelectChunk, reducedMotion = false, playing = true }) {
  const hostRef = useRef(null), controllerRef = useRef(null), labelsRef = useRef(new Map()), laneTitlesRef = useRef(new Map());
  const [status, setStatus] = useState("loading");
  const [limits, setLimits] = useState({ sources: 6, ranks: 5 });
  const safePhase = clampPhase(phase);
  const safeChunks = chunks.slice(0, 6);
  const rankings = {
    dense: rankingInput?.dense ?? DEFAULT_RANKINGS.dense,
    bm25: rankingInput?.bm25 ?? DEFAULT_RANKINGS.bm25,
    fused: rankingInput?.fused ?? DEFAULT_RANKINGS.fused,
    selected: rankingInput?.selected ?? (rankingInput?.reranked ?? rankingInput?.fused ?? DEFAULT_RANKINGS.selected).slice(0, 3),
  };
  const model = useRef({});
  model.current = { phase: safePhase, chunks: safeChunks, rankings, selectedChunkId, onSelectChunk, reducedMotion, playing };
  const configKey = JSON.stringify([safeChunks, rankings]);
  const ids = [...new Set([...safeChunks.map((chunk) => chunk.id), ...rankings.fused, ...rankings.selected])].slice(0, 12);
  const labelRecords = [
    ...ids.map((id) => ({ key: `main-${id}`, id, detail: safeChunks.find((chunk) => chunk.id === id) })),
    ...["dense", "bm25"].flatMap((lane) => rankings[lane].slice(0, 5).map((id, rank) => ({ key: `${lane}-${rank}`, id, detail: safeChunks.find((chunk) => chunk.id === id), lane, rank }))),
  ];
  const shownStart = safeChunks.length ? Math.min(...safeChunks.map((chunk) => chunk.start)) : 0;
  const shownEnd = safeChunks.length ? Math.max(...safeChunks.map((chunk) => chunk.end)) : 0;
  const sourceQuantity = safePhase === 0
    ? sourceInfo.tokenCount != null ? `${sourceInfo.tokenCount} token · sıra ve metin sınırları korunur` : `Gösterilen token aralığı: [${shownStart}, ${shownEnd})`
    : safePhase === 1
      ? `İlk ${Math.min(limits.sources, safeChunks.length)} pencere · ${Math.max(0, ...safeChunks.map((chunk) => chunk.tokenCount))} token boyut · ${Math.max(0, ...safeChunks.map((chunk) => chunk.overlapCount))} token ortak alan`
      : `${safeChunks.length} chunk → ${safeChunks.length} kaydedilmiş vektör${embeddingDimensions != null ? ` · d=${embeddingDimensions}` : ""}`;

  useEffect(() => {
    const host = hostRef.current;
    if (!host) return undefined;
    setStatus("loading");
    let renderer, scene, camera, resizeObserver, intersectionObserver;
    let disposed = false, visible = true, frame = 0, lastTime = 0, elapsed = 0, transitioning = false, down = null, viewWidth = 1000, viewHeight = 280;
    const geometrySet = new Set(), materialSet = new Set(), cards = [], picks = [], paths = [];
    const raycaster = new THREE.Raycaster(), pointer = new THREE.Vector2(), projected = new THREE.Vector3();
    const geo = (value) => (geometrySet.add(value), value);
    const mat = (value) => (materialSet.add(value), value);
    function stop() { if (frame) cancelAnimationFrame(frame); frame = 0; lastTime = 0; }
    function cleanup() {
      if (disposed) return;
      disposed = true; stop(); resizeObserver?.disconnect(); intersectionObserver?.disconnect();
      document.removeEventListener("visibilitychange", sync); window.removeEventListener("resize", resize);
      if (renderer) {
        const canvas = renderer.domElement;
        canvas.removeEventListener("pointerdown", pointerDown); canvas.removeEventListener("pointerup", pointerUp);
        canvas.removeEventListener("pointermove", pointerMove); canvas.removeEventListener("pointerleave", pointerLeave);
        canvas.removeEventListener("webglcontextlost", lost);
        renderer.dispose(); renderer.forceContextLoss(); canvas.remove();
      }
      geometrySet.forEach((value) => value.dispose()); materialSet.forEach((value) => value.dispose()); scene?.clear();
      controllerRef.current = null;
    }
    function fail() { cleanup(); setStatus("fallback"); }
    function lost(event) { event.preventDefault(); fail(); }
    function canMove() { return !disposed && visible && !document.hidden && model.current.playing && !model.current.reducedMotion; }
    function pick(event) {
      if (disposed) return null;
      const bounds = renderer.domElement.getBoundingClientRect();
      if (!bounds.width || !bounds.height) return null;
      pointer.set((event.clientX - bounds.left) / bounds.width * 2 - 1, -(event.clientY - bounds.top) / bounds.height * 2 + 1);
      raycaster.setFromCamera(pointer, camera);
      return raycaster.intersectObjects(picks.filter((item) => item.parent.userData.opacity > 0.15), false)[0]?.object.userData.id;
    }
    function pointerDown(event) { down = { id: event.pointerId, x: event.clientX, y: event.clientY }; }
    function pointerUp(event) {
      if (!down || down.id !== event.pointerId) return;
      const moved = Math.hypot(event.clientX - down.x, event.clientY - down.y); down = null;
      if (moved < 8) { const id = pick(event); if (id) model.current.onSelectChunk?.(id); }
    }
    function pointerMove(event) { if (!disposed && event.pointerType !== "touch") renderer.domElement.style.cursor = pick(event) ? "pointer" : "default"; }
    function pointerLeave() { if (!disposed) renderer.domElement.style.cursor = "default"; }
    function resize() {
      if (disposed) return;
      const { width, height } = host.getBoundingClientRect();
      if (!width || !height) { stop(); return; }
      viewWidth = width; viewHeight = height;
      const aspect = width / height, halfWidth = Math.max(6.2, aspect * 2.7);
      camera.left = -halfWidth; camera.right = halfWidth; camera.top = halfWidth / aspect; camera.bottom = -halfWidth / aspect;
      camera.updateProjectionMatrix(); renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 1.5)); renderer.setSize(width, height, false); setTargets(); draw(); sync();
    }
    function setTargets() {
      const { phase: current, chunks: source, rankings: ranked } = model.current;
      const selected = ranked.selected.slice(0, 3);
      const compact = viewWidth < 600, sourceCount = Math.min(source.length, compact ? 4 : 6), rankCount = compact ? 2 : viewWidth < 900 ? 3 : 5;
      setLimits((previous) => previous.sources === (compact ? 4 : 6) && previous.ranks === rankCount ? previous : { sources: compact ? 4 : 6, ranks: rankCount });
      const xUnits = (pixels) => pixels / viewWidth * (camera.right - camera.left);
      const yUnits = (pixels) => pixels / viewHeight * (camera.top - camera.bottom);
      const answerX = xUnits(viewWidth * 0.27), sourceX = -answerX;
      cards.forEach((card) => {
        card.targetOpacity = 0; card.targetScale = 1; card.width = 160; card.height = 80;
        if (!card.lane) {
          const chunkIndex = source.findIndex((chunk) => chunk.id === card.id);
          if (current === 0 && chunkIndex >= 0) {
            card.target.set(chunkIndex * 0.13 - 0.3, -chunkIndex * 0.09 + 0.18, -chunkIndex * 0.14);
            card.targetOpacity = chunkIndex === 0 ? 1 : 0.26;
            card.width = Math.min(390, viewWidth - 44); card.height = 150;
          } else if ((current === 1 || current === 2) && chunkIndex >= 0 && chunkIndex < sourceCount) {
            const cols = Math.min(compact ? 2 : 3, sourceCount);
            const row = Math.floor(chunkIndex / cols), col = chunkIndex % cols;
            card.width = Math.min(260, (viewWidth - 32) / cols - 14); card.height = current === 2 ? 99 : 95;
            card.target.set(xUnits((col - (cols - 1) / 2) * (card.width + 18)), sourceCount > cols ? yUnits(53 - row * 108) : 0, 0);
            card.targetOpacity = 1;
          } else if (current === 4) {
            const count = Math.min(rankCount, ranked.fused.length), rank = ranked.fused.slice(0, count).indexOf(card.id);
            if (rank >= 0) {
              if (card.opacity < 0.005) card.group.position.set(0, -1.45, 0);
              card.width = Math.min(220, (viewWidth - 32) / count - 14); card.height = 96;
              card.target.set(xUnits((rank - (count - 1) / 2) * (card.width + 18)), 0, 0); card.targetOpacity = 1;
            }
          } else if (current >= 5) {
            const rank = selected.indexOf(card.id);
            if (rank >= 0) {
              card.width = current === 6 ? Math.min(320, viewWidth * 0.39) : Math.min(340, viewWidth - 52); card.height = 65;
              card.target.set(current === 6 ? sourceX : 0, yUnits((selected.length - 1) * 39 - rank * 78), 0); card.targetOpacity = 1;
            }
          }
        } else {
          const rank = card.rank, count = Math.min(rankCount, ranked[card.lane].length);
          if (current === 3 && rank < count) {
            card.width = Math.min(220, (viewWidth - 32) / count - 14); card.height = 80;
            card.target.set(xUnits((rank - (count - 1) / 2) * (card.width + 18)), yUnits(card.lane === "dense" ? 64 : -64), 0); card.targetOpacity = 1;
          }
          else if (current >= 4) { card.target.set(0, -1.45, 0); card.targetScale = 0.12; }
          else card.target.set(card.lane === "dense" ? -1 : 1, 0, 0);
        }
        card.targetScaleX = xUnits(card.width) / 1.85 * card.targetScale;
        card.targetScaleY = yUnits(card.height) / 1.15 * card.targetScale;
      });
      prompt.visible = current >= 5; answer.visible = current === 6; hub.visible = current === 4;
      prompt.position.x = current === 6 ? sourceX : 0;
      prompt.scale.x = xUnits(current === 6 ? Math.min(340, viewWidth * 0.42) : Math.min(360, viewWidth - 32));
      prompt.scale.y = yUnits(selected.length * 78 + 14);
      answer.position.x = answerX; answer.scale.set(xUnits(Math.min(340, viewWidth * 0.39)), yUnits(172), 0.3);
      paths.forEach((path, index) => {
        path.line.visible = current === 6 && index < selected.length; path.dot.visible = path.line.visible;
        path.from.set(sourceX + xUnits(Math.min(320, viewWidth * 0.39)) / 2, yUnits((selected.length - 1) * 39 - index * 78), 0);
        path.to.set(answerX - answer.scale.x / 2, yUnits(35 - index * 35), 0);
        const positions = path.line.geometry.attributes.position;
        positions.setXYZ(0, ...path.from.toArray()); positions.setXYZ(1, ...path.to.toArray()); positions.needsUpdate = true;
      });
      transitioning = true;
      update(canMove() ? 0 : 1);
    }
    let prompt, answer, hub;
    function update(factor) {
      let pending = false;
      cards.forEach((card) => {
        card.group.position.lerp(card.target, factor);
        card.opacity += (card.targetOpacity - card.opacity) * factor;
        card.scale += (card.targetScale - card.scale) * factor;
        card.scaleX += (card.targetScaleX - card.scaleX) * factor; card.scaleY += (card.targetScaleY - card.scaleY) * factor;
        card.group.scale.set(card.scaleX, card.scaleY, card.scale);
        card.group.userData.opacity = card.opacity; card.group.visible = card.opacity > 0.005;
        card.body.opacity = card.opacity * 0.82;
        card.edge.opacity = card.opacity * (card.id === model.current.selectedChunkId ? 1 : 0.55);
        card.body.color.set(card.id === model.current.selectedChunkId ? 0x24483d : 0x172c23);
        if (card.group.position.distanceToSquared(card.target) > 0.0001 || Math.abs(card.opacity - card.targetOpacity) > 0.005 || Math.abs(card.scaleX - card.targetScaleX) > 0.005 || Math.abs(card.scaleY - card.targetScaleY) > 0.005) pending = true;
      });
      transitioning = pending;
    }
    function draw() {
      if (disposed) return;
      scene.updateMatrixWorld(true);
      cards.forEach((card) => {
        const label = labelsRef.current.get(card.key);
        if (!label) return;
        card.group.getWorldPosition(projected); projected.project(camera);
        label.style.left = `${(projected.x + 1) * 50}%`; label.style.top = `${(-projected.y + 1) * 50}%`;
        label.style.width = `${1.85 * card.scaleX / (camera.right - camera.left) * viewWidth}px`;
        label.style.height = `${1.15 * card.scaleY / (camera.top - camera.bottom) * viewHeight}px`;
        const show = card.opacity > 0.65 && (model.current.phase !== 0 || card.id === model.current.chunks[0]?.id);
        label.style.opacity = show ? "1" : "0"; label.style.pointerEvents = show ? "auto" : "none";
        label.setAttribute("aria-hidden", show ? "false" : "true"); label.tabIndex = show ? 0 : -1;
      });
      ["dense", "bm25"].forEach((lane) => {
        const title = laneTitlesRef.current.get(lane);
        if (!title) return;
        // Anchor each title above its geometric lane rather than to a viewport percentage.
        projected.set(0, (lane === "dense" ? 1 : -1) * 64 / viewHeight * (camera.top - camera.bottom) + 55 / viewHeight * (camera.top - camera.bottom), 0).project(camera);
        title.style.top = `${(-projected.y + 1) * 50}%`;
      });
      try { renderer.render(scene, camera); } catch { fail(); }
    }
    function tick(time) {
      frame = 0; if (!canMove()) return;
      const dt = lastTime ? Math.min((time - lastTime) / 1000, 0.06) : 0.016; lastTime = time; elapsed += dt;
      if (transitioning) update(1 - Math.exp(-dt * 8));
      paths.forEach((path, index) => { if (path.dot.visible) path.dot.position.lerpVectors(path.from, path.to, (elapsed * 0.25 + index * 0.27) % 1); });
      draw();
      if (canMove() && (transitioning || model.current.phase === 6)) frame = requestAnimationFrame(tick);
    }
    function sync() {
      if (canMove() && (transitioning || model.current.phase === 6)) { if (!frame) frame = requestAnimationFrame(tick); }
      else { stop(); if (!model.current.playing || model.current.reducedMotion) update(1); draw(); }
    }
    try {
      renderer = new THREE.WebGLRenderer({ alpha: true, antialias: true, powerPreference: "low-power" });
      renderer.setClearColor(0, 0); renderer.outputColorSpace = THREE.SRGBColorSpace;
      renderer.domElement.setAttribute("aria-hidden", "true"); renderer.domElement.className = "rag-mechanism-canvas"; host.appendChild(renderer.domElement);
      scene = new THREE.Scene(); camera = new THREE.OrthographicCamera(-7.6, 7.6, 3.5, -3.5, 0.1, 50);
      camera.position.set(0, 1.4, 18); camera.lookAt(0, 0, 0);
      scene.add(new THREE.HemisphereLight(0xd6e8dc, 0x182c21, 2));
      const light = new THREE.DirectionalLight(0xf0ebd3, 2); light.position.set(-3, 4, 7); scene.add(light);
      const cube = geo(new THREE.BoxGeometry(1, 1, 1)), edges = geo(new THREE.EdgesGeometry(cube));
      const sphere = geo(new THREE.SphereGeometry(0.065, 7, 5));
      const grid = new THREE.GridHelper(30, 60, 0x395442, 0x293e31); grid.rotation.x = Math.PI / 2; grid.position.z = -1.7;
      geo(grid.geometry); (Array.isArray(grid.material) ? grid.material : [grid.material]).forEach((value) => { mat(value); value.transparent = true; value.opacity = 0.28; }); scene.add(grid);
      const hiddenMaterial = mat(new THREE.MeshBasicMaterial({ visible: false }));
      function addCard(id, key, lane, rank = 0) {
        const group = new THREE.Group(), body = mat(new THREE.MeshStandardMaterial({ color: 0x172c23, transparent: true, opacity: 0, roughness: 0.7, metalness: 0.12 }));
        const edge = mat(new THREE.LineBasicMaterial({ color: lane === "bm25" ? GOLD : CYAN, transparent: true, opacity: 0 }));
        const shell = new THREE.Mesh(cube, body); shell.scale.set(1.85, 1.15, 0.12); shell.add(new THREE.LineSegments(edges, edge)); group.add(shell);
        const pickBox = new THREE.Mesh(cube, hiddenMaterial); pickBox.scale.set(2, 1.5, 0.4); pickBox.userData.id = id; group.add(pickBox); picks.push(pickBox);
        const record = { id, key, lane, rank, group, body, edge, target: new THREE.Vector3(), opacity: 0, targetOpacity: 0, scale: 1, targetScale: 1, scaleX: 1, scaleY: 1, targetScaleX: 1, targetScaleY: 1 };
        scene.add(group); cards.push(record);
      }
      ids.forEach((id) => addCard(id, `main-${id}`));
      ["dense", "bm25"].forEach((lane) => model.current.rankings[lane].slice(0, 5).forEach((id, rank) => addCard(id, `${lane}-${rank}`, lane, rank)));
      function wireBox(x, y, width, height, color) {
        const box = new THREE.LineSegments(edges, mat(new THREE.LineBasicMaterial({ color, transparent: true, opacity: 0.6 })));
        box.position.set(x, y, -0.25); box.scale.set(width, height, 0.3); scene.add(box); return box;
      }
      prompt = wireBox(0, 0, 2.5, 4.5, 0x8fa9d6);
      answer = wireBox(3.5, 0, 3.1, 2.9, 0x5cd08d);
      hub = wireBox(0, -1.45, 1.3, 0.5, 0xe0bb55);
      for (let index = 0; index < 3; index += 1) {
        const from = new THREE.Vector3(-2.4, 1.3 - index * 1.3, 0), to = new THREE.Vector3(1.95, 0.6 - index * 0.6, 0);
        const line = new THREE.Line(geo(new THREE.BufferGeometry().setFromPoints([from, to])), mat(new THREE.LineBasicMaterial({ color: 0x5cd08d, transparent: true, opacity: 0.45 })));
        const dot = new THREE.Mesh(sphere, mat(new THREE.MeshBasicMaterial({ color: GREEN }))); dot.position.copy(from); scene.add(line, dot); paths.push({ from, to, line, dot });
      }
      renderer.domElement.addEventListener("pointerdown", pointerDown); renderer.domElement.addEventListener("pointerup", pointerUp);
      renderer.domElement.addEventListener("pointermove", pointerMove); renderer.domElement.addEventListener("pointerleave", pointerLeave);
      renderer.domElement.addEventListener("webglcontextlost", lost); document.addEventListener("visibilitychange", sync);
      if (typeof ResizeObserver !== "undefined") { resizeObserver = new ResizeObserver(resize); resizeObserver.observe(host); } else window.addEventListener("resize", resize);
      if (typeof IntersectionObserver !== "undefined") { intersectionObserver = new IntersectionObserver(([entry]) => { visible = entry.isIntersecting; sync(); }, { threshold: 0.01 }); intersectionObserver.observe(host); }
      setTargets(); resize(); sync();
      controllerRef.current = { update() { if (!disposed) { setTargets(); draw(); sync(); } } };
      if (!disposed) setStatus("ready");
    } catch { fail(); }
    return cleanup;
  }, [configKey]);

  useEffect(() => { controllerRef.current?.update(); }, [safePhase, selectedChunkId, playing, reducedMotion, status]);

  return <div className="rag-mechanism" data-render-state={status} data-phase={safePhase} data-motion={playing && !reducedMotion ? "playing" : "paused"} role="group" aria-label={`${PHASE_LABELS[safePhase]}. Aşama düğmeleriyle araştırma akışını inceleyin.`}>
    <div className="rag-mechanism-stage-heading"><span>0{safePhase + 1}</span>{PHASE_LABELS[safePhase]}</div>
    <div ref={hostRef} className="rag-mechanism-mount" hidden={status === "fallback"} />
    {status === "loading" && <span className="rag-mechanism-loading" role="status">Akış hazırlanıyor…</span>}
    {status === "ready" && <div className="rag-mechanism-label-layer">
      {labelRecords.map(({ key, id, detail, lane, rank }) => {
        const sourceIndex = safeChunks.findIndex((chunk) => chunk.id === id);
        const nextChunk = safeChunks[sourceIndex + 1];
        const incoming = safePhase === 1 && sourceIndex > 0 && detail?.overlapCount > 0 ? sharedText(safeChunks[sourceIndex - 1]?.text, detail.text) : "";
        const outgoing = safePhase === 1 && detail && nextChunk && nextChunk.start < detail.end ? sharedText(detail.text, nextChunk.text) : "";
        const coordinates = Array.isArray(vectorsById[id]) ? vectorsById[id].slice(0, 8).filter(Number.isFinite) : [];
        const maxAbs = Math.max(1e-12, ...coordinates.map(Math.abs));
        const citation = rankings.selected.indexOf(id) + 1;
        const score = fusionScores[id];
        return <button type="button" key={key} className={`rag-mechanism-chunk-label ${lane || ""} ${safePhase === 0 ? "source" : ""} ${safePhase === 2 ? "vector" : ""}`} ref={(element) => { if (element) labelsRef.current.set(key, element); else labelsRef.current.delete(key); }} onClick={() => onSelectChunk?.(id)} aria-pressed={id === selectedChunkId} title={safePhase === 0 ? sourceInfo.text : detail?.text}>
          <b>{safePhase === 0 ? sourceInfo.title || "Kaynak doküman" : <>{lane ? `${rank + 1}. ` : safePhase >= 5 && citation > 0 ? `[${citation}] ` : safePhase === 4 ? `${rankings.fused.indexOf(id) + 1}. ` : ""}{id}</>}</b>
          {safePhase === 0 ? <><span>{sourceInfo.tokenCount != null ? `${sourceInfo.tokenCount} gerçek token` : "Kaynak metin"}</span><p>{String(sourceInfo.text || detail?.text || "").slice(0, 140)}</p></> : safePhase === 2 && !lane ? <>
            <p>{String(detail?.text || "").slice(0, 60)}</p>
            {coordinates.length > 0 ? <><div className="rag-mechanism-recorded-vector" aria-label={`${id} için kaydedilmiş ilk ${coordinates.length} koordinat`}>{coordinates.map((value, index) => <i key={index} className={value < 0 ? "negative" : "positive"} style={{ height: `${Math.abs(value) / maxAbs * 46}%`, left: `${(index + 0.5) / coordinates.length * 100}%` }} title={`e${index + 1} = ${value.toFixed(6)}`} />)}</div><code>[{coordinates.slice(0, 4).map((value) => value.toFixed(3)).join(", ")}, …]</code></> : <span>Bu parça için kaydedilmiş vektör yok.</span>}
            <span>{embeddingDimensions != null ? `d=${embeddingDimensions} · ilk ${coordinates.length} koordinat` : `İlk ${coordinates.length} koordinat`}</span>
          </> : <>
            {detail && <span>[{detail.start}, {detail.end}) · {detail.tokenCount} token</span>}
            <p>{String(detail?.text || "").slice(0, safePhase >= 5 ? 130 : 90)}</p>
            {safePhase === 1 && (incoming || outgoing) && <div className="rag-mechanism-shared-text">{incoming && <span>Baş <mark>{incoming.trim().slice(0, 22)}</mark></span>}{outgoing && <span>Son <mark>{outgoing.trim().slice(0, 22)}</mark></span>}</div>}
            {safePhase === 4 && Number.isFinite(score) && <code>RRF = {score.toFixed(5)}</code>}
          </>}
        </button>;
      })}
      {safePhase === 3 && <><span ref={(element) => { if (element) laneTitlesRef.current.set("dense", element); else laneTitlesRef.current.delete("dense"); }} className="rag-mechanism-lane-title dense">DENSE · ilk {Math.min(limits.ranks, rankings.dense.length)} / {rankings.dense.length}</span><span ref={(element) => { if (element) laneTitlesRef.current.set("bm25", element); else laneTitlesRef.current.delete("bm25"); }} className="rag-mechanism-lane-title bm25">BM25 · ilk {Math.min(limits.ranks, rankings.bm25.length)} / {rankings.bm25.length}</span></>}
      {safePhase === 4 && <span className="rag-mechanism-rrf-label">RRF · ilk {Math.min(limits.ranks, rankings.fused.length)} / {rankings.fused.length} aday</span>}
      {safePhase === 5 && <span className="rag-mechanism-prompt-label">TALİMAT + SORU + BAĞLAM</span>}
      {safePhase === 6 && <span className="rag-mechanism-answer-label">YANIT<span>{rankings.selected.slice(0, 3).map((id, index) => <span key={id}>[{index + 1}] {id}</span>)}</span><small>{sourceInfo.title}</small></span>}
    </div>}
    {status === "ready" && safePhase < 3 && <p className="rag-mechanism-quantity">{sourceQuantity}</p>}
    {status === "fallback" && <FallbackGraph phase={safePhase} chunks={safeChunks} rankings={rankings} selectedChunkId={selectedChunkId} onSelectChunk={onSelectChunk} />}
    <div className="rag-mechanism-legend"><span><i className="tokens" />{safePhase === 2 ? "Kaydedilmiş koordinatlar" : "Kaynak metin / chunk"}</span>{safePhase === 1 && <span><i className="overlap" />İki penceredeki aynı metin</span>}{safePhase === 3 && <span><i className="overlap" />BM25 / sözcük eşleşmesi</span>}{safePhase === 4 && <span><i className="overlap" />Hesaplanmış RRF skoru</span>}{safePhase >= 5 && <span><i className="source-link" />Prompt sırasına göre [n]</span>}<small>{safePhase === 2 ? "Çubuk ölçeği: |koordinat| / en büyük |koordinat|" : "Kaydedilmiş örnek veri; canlı sorgu yapılmaz"}</small></div>
  </div>;
}
