// Arc reactor + hex grid background. All Canvas, no libs.

(function () {
  'use strict';

  const TAU = Math.PI * 2;

  // Default palette ("dry" mood). main.js can overwrite window.HUD.targetPalette
  // with another mood and the loop below lerps the live palette toward it.
  const DEFAULT_PALETTE = { r: 0, g: 212, b: 255, hr: 120, hg: 230, hb: 255 };

  function rgba(a, hot) {
    const p = (window.HUD && window.HUD.currentPalette) || DEFAULT_PALETTE;
    return hot
      ? `rgba(${p.hr|0}, ${p.hg|0}, ${p.hb|0}, ${a})`
      : `rgba(${p.r|0}, ${p.g|0}, ${p.b|0}, ${a})`;
  }
  function rgb(hot) {
    const p = (window.HUD && window.HUD.currentPalette) || DEFAULT_PALETTE;
    return hot
      ? `rgb(${p.hr|0}, ${p.hg|0}, ${p.hb|0})`
      : `rgb(${p.r|0}, ${p.g|0}, ${p.b|0})`;
  }

  // ─── Hex grid background ─────────────────────────────────────
  const hexCanvas = document.getElementById('hex');
  const hexCtx = hexCanvas.getContext('2d');

  function fitHex() {
    hexCanvas.width  = window.innerWidth  * devicePixelRatio;
    hexCanvas.height = window.innerHeight * devicePixelRatio;
    hexCanvas.style.width  = window.innerWidth  + 'px';
    hexCanvas.style.height = window.innerHeight + 'px';
  }
  fitHex();
  window.addEventListener('resize', fitHex);

  function drawHex() {
    const w = hexCanvas.width, h = hexCanvas.height;
    hexCtx.clearRect(0, 0, w, h);
    const r = 22 * devicePixelRatio;
    const dx = r * Math.sqrt(3);
    const dy = r * 1.5;
    hexCtx.lineWidth = 1 * devicePixelRatio;
    hexCtx.strokeStyle = rgba(0.07);
    for (let row = 0, y = 0; y < h + dy; y += dy, row++) {
      const xOff = (row % 2) * (dx / 2);
      for (let x = -dx; x < w + dx; x += dx) {
        drawHexAt(x + xOff, y, r);
      }
    }
  }
  function drawHexAt(cx, cy, r) {
    hexCtx.beginPath();
    for (let i = 0; i < 6; i++) {
      const a = (Math.PI / 3) * i + Math.PI / 6;
      const x = cx + r * Math.cos(a);
      const y = cy + r * Math.sin(a);
      i === 0 ? hexCtx.moveTo(x, y) : hexCtx.lineTo(x, y);
    }
    hexCtx.closePath();
    hexCtx.stroke();
  }
  drawHex();
  window.addEventListener('resize', drawHex);
  // Hex grid is cheap; redraw periodically so it tracks palette lerp.
  setInterval(drawHex, 250);

  // ─── Arc reactor ─────────────────────────────────────────────
  const canvas = document.getElementById('reactor');
  const ctx = canvas.getContext('2d');

  function fit() {
    const r = canvas.getBoundingClientRect();
    canvas.width  = r.width  * devicePixelRatio;
    canvas.height = r.height * devicePixelRatio;
  }
  fit();
  window.addEventListener('resize', fit);

  // Public state — set by main.js
  const State = {
    mode: 'dormant',          // dormant | awake | listening | thinking | speaking
    energy: 0.18,             // overall brightness [0, 1]
    targetEnergy: 0.18,
    voice: 0,                 // current waveform amplitude [0, 1]
    spinA: 0, spinB: 0, spinC: 0,
    ignitionT: 0,             // 0..1 ramp during wake ignition
    currentPalette: { ...DEFAULT_PALETTE },
    targetPalette:  { ...DEFAULT_PALETTE },
  };
  window.HUD = State;

  function setMode(mode) {
    State.mode = mode;
    State.targetEnergy = ({
      dormant:   0.18,
      awake:     0.85,
      listening: 1.00,
      thinking:  0.75,
      speaking:  0.95,
    })[mode] ?? 0.5;
    if (mode === 'awake') State.ignitionT = 0;
  }
  window.HUD.setMode = setMode;

  // ─── Animation loop ──────────────────────────────────────────
  let last = performance.now();
  function loop(now) {
    const dt = Math.min(0.05, (now - last) / 1000);
    last = now;

    // Smoothly chase the target brightness.
    State.energy += (State.targetEnergy - State.energy) * Math.min(1, dt * 3);
    if (State.mode === 'awake' && State.ignitionT < 1) {
      State.ignitionT = Math.min(1, State.ignitionT + dt * 1.4);
    }
    State.spinA += dt * (0.25 + State.energy * 0.8);
    State.spinB -= dt * (0.18 + State.energy * 0.6);
    State.spinC += dt * (0.45 + State.energy * 1.2);

    // Lerp the palette toward the mood target.
    const cur = State.currentPalette, tgt = State.targetPalette;
    const pk = Math.min(1, dt * 4);
    cur.r  += (tgt.r  - cur.r)  * pk;
    cur.g  += (tgt.g  - cur.g)  * pk;
    cur.b  += (tgt.b  - cur.b)  * pk;
    cur.hr += (tgt.hr - cur.hr) * pk;
    cur.hg += (tgt.hg - cur.hg) * pk;
    cur.hb += (tgt.hb - cur.hb) * pk;

    drawReactor();
    requestAnimationFrame(loop);
  }
  requestAnimationFrame(loop);

  function drawReactor() {
    const w = canvas.width, h = canvas.height;
    ctx.clearRect(0, 0, w, h);
    const cx = w / 2, cy = h / 2;
    const R  = Math.min(w, h) * 0.42;
    const e  = State.energy;
    const voiceBoost = State.voice * (State.mode === 'speaking' || State.mode === 'listening' ? 1 : 0);

    // ── Outer ticked ring ──
    ctx.save();
    ctx.translate(cx, cy);
    ctx.rotate(State.spinA);
    ctx.strokeStyle = rgba(0.25 + 0.3 * e);
    ctx.lineWidth = 1.5 * devicePixelRatio;
    for (let i = 0; i < 72; i++) {
      const a = (i / 72) * TAU;
      const r0 = R * 0.98, r1 = R * (i % 6 === 0 ? 1.06 : 1.02);
      ctx.beginPath();
      ctx.moveTo(r0 * Math.cos(a), r0 * Math.sin(a));
      ctx.lineTo(r1 * Math.cos(a), r1 * Math.sin(a));
      ctx.stroke();
    }
    ctx.restore();

    // ── Outer broken ring (3 arcs) ──
    ctx.save();
    ctx.translate(cx, cy);
    ctx.rotate(State.spinB);
    ctx.lineWidth = 2 * devicePixelRatio;
    ctx.strokeStyle = rgba(0.35 + 0.5 * e);
    ctx.shadowColor = rgb();
    ctx.shadowBlur = 12 * e;
    for (let s = 0; s < 3; s++) {
      const a0 = (s / 3) * TAU + 0.1;
      const a1 = a0 + TAU / 3 - 0.5;
      ctx.beginPath();
      ctx.arc(0, 0, R * 0.92, a0, a1);
      ctx.stroke();
    }
    ctx.restore();

    // ── Mid ring with notches ──
    ctx.save();
    ctx.translate(cx, cy);
    ctx.rotate(State.spinC);
    ctx.strokeStyle = rgba(0.4 + 0.5 * e, true);
    ctx.lineWidth = 1 * devicePixelRatio;
    ctx.beginPath();
    ctx.arc(0, 0, R * 0.78, 0, TAU);
    ctx.stroke();
    for (let i = 0; i < 24; i++) {
      const a = (i / 24) * TAU;
      ctx.beginPath();
      ctx.moveTo(R * 0.74 * Math.cos(a), R * 0.74 * Math.sin(a));
      ctx.lineTo(R * 0.82 * Math.cos(a), R * 0.82 * Math.sin(a));
      ctx.stroke();
    }
    ctx.restore();

    // ── Inner segmented ring (the "iris") ──
    ctx.save();
    ctx.translate(cx, cy);
    ctx.rotate(-State.spinA * 0.6);
    const segs = 12;
    for (let i = 0; i < segs; i++) {
      const a0 = (i / segs) * TAU + 0.03;
      const a1 = a0 + TAU / segs - 0.06;
      const grad = ctx.createLinearGradient(0, -R * 0.6, 0, R * 0.6);
      grad.addColorStop(0, rgba(0.55 * e, true));
      grad.addColorStop(1, rgba(0.35 * e));
      ctx.fillStyle = grad;
      ctx.strokeStyle = rgba(0.7 * e, true);
      ctx.lineWidth = 1 * devicePixelRatio;
      ctx.beginPath();
      ctx.arc(0, 0, R * 0.62, a0, a1);
      ctx.arc(0, 0, R * 0.50, a1, a0, true);
      ctx.closePath();
      ctx.fill();
      ctx.stroke();
    }
    ctx.restore();

    // ── Triangle tri-spokes (Iron Man core motif) ──
    ctx.save();
    ctx.translate(cx, cy);
    ctx.strokeStyle = rgba(0.6 * e);
    ctx.lineWidth = 2 * devicePixelRatio;
    ctx.shadowColor = rgb();
    ctx.shadowBlur = 9 * e;
    const triR = R * 0.42;
    ctx.beginPath();
    for (let i = 0; i < 3; i++) {
      const a = (i / 3) * TAU - Math.PI / 2;
      const x = triR * Math.cos(a), y = triR * Math.sin(a);
      i === 0 ? ctx.moveTo(x, y) : ctx.lineTo(x, y);
    }
    ctx.closePath();
    ctx.stroke();
    ctx.restore();

    // ── Central glowing core ──
    // voiceBoost is capped so the core's gradient never reaches the inner
    // segmented ring at R*0.50, otherwise loud speech washes the iris out.
    // Keep the halo tight (1.35×) and add a mid-stop so the falloff is crisper.
    const coreR = R * 0.22 * (1 + 0.06 * Math.sin(performance.now() / 600) + voiceBoost * 0.10);
    const haloR = coreR * 1.35;
    const coreGrad = ctx.createRadialGradient(cx, cy, 0, cx, cy, haloR);
    coreGrad.addColorStop(0,    `rgba(255, 255, 255, ${0.95 * e})`);
    coreGrad.addColorStop(0.35, rgba(0.85 * e));
    coreGrad.addColorStop(0.75, rgba(0.30 * e));
    coreGrad.addColorStop(1,    'rgba(0, 0, 0, 0)');
    ctx.fillStyle = coreGrad;
    ctx.beginPath();
    ctx.arc(cx, cy, haloR, 0, TAU);
    ctx.fill();

    ctx.fillStyle = `rgba(255, 255, 255, ${0.9 * e})`;
    ctx.beginPath();
    ctx.arc(cx, cy, coreR * 0.45, 0, TAU);
    ctx.fill();

    // ── Ignition flash ──
    if (State.ignitionT > 0 && State.ignitionT < 1) {
      const k = 1 - State.ignitionT;
      ctx.fillStyle = rgba(k * 0.35, true);
      ctx.beginPath();
      ctx.arc(cx, cy, R * (1 + (1 - k) * 0.3), 0, TAU);
      ctx.fill();
    }

    // ── Crosshair ticks ──
    ctx.save();
    ctx.translate(cx, cy);
    ctx.strokeStyle = rgba(0.7 * e, true);
    ctx.lineWidth = 1.5 * devicePixelRatio;
    [0, Math.PI / 2, Math.PI, -Math.PI / 2].forEach((a) => {
      ctx.beginPath();
      ctx.moveTo(R * 1.08 * Math.cos(a), R * 1.08 * Math.sin(a));
      ctx.lineTo(R * 1.14 * Math.cos(a), R * 1.14 * Math.sin(a));
      ctx.stroke();
    });
    ctx.restore();
  }
})();
