// Synthesised waveform driven by the BACKEND mic amplitude.
// main.js sets `window.HUD.voice` whenever a `volume` event arrives from
// the Python MicMonitor, so this canvas reflects what Jarvis hears — not
// whatever permission-gated stream the browser tab can grab.

(function () {
  'use strict';

  const canvas = document.getElementById('wave');
  const ctx = canvas.getContext('2d');

  function fit() {
    const r = canvas.getBoundingClientRect();
    canvas.width  = r.width  * devicePixelRatio;
    canvas.height = r.height * devicePixelRatio;
  }
  fit();
  window.addEventListener('resize', fit);

  const FALLBACK = { r: 0, g: 212, b: 255 };
  function pal() {
    return (window.HUD && window.HUD.currentPalette) || FALLBACK;
  }

  let smoothed = 0;

  function draw() {
    const w = canvas.width, h = canvas.height;
    ctx.clearRect(0, 0, w, h);

    const p = pal();
    const r = p.r | 0, g = p.g | 0, b = p.b | 0;

    // Baseline
    ctx.strokeStyle = `rgba(${r}, ${g}, ${b}, 0.18)`;
    ctx.lineWidth = 1 * devicePixelRatio;
    ctx.beginPath(); ctx.moveTo(0, h / 2); ctx.lineTo(w, h / 2); ctx.stroke();

    // Pull current amplitude from the global state (set by main.js).
    // Falls back to a small idle value if the backend feed is silent.
    const target = (window.HUD && window.HUD.voice) || 0.04;
    smoothed += (target - smoothed) * 0.18;

    // Stylised stack of three sine layers, scaled by the smoothed amplitude.
    const t = performance.now() / 200;
    ctx.lineWidth = 2 * devicePixelRatio;
    const grad = ctx.createLinearGradient(0, 0, w, 0);
    grad.addColorStop(0,   `rgba(${r}, ${g}, ${b}, 0.0)`);
    grad.addColorStop(0.5, `rgba(${r}, ${g}, ${b}, 1.0)`);
    grad.addColorStop(1,   `rgba(${r}, ${g}, ${b}, 0.0)`);
    ctx.strokeStyle = grad;
    ctx.shadowColor = `rgb(${r}, ${g}, ${b})`;
    ctx.shadowBlur = 10 * devicePixelRatio;

    ctx.beginPath();
    for (let x = 0; x < w; x += 2) {
      const k = x / w;
      const y = h / 2
        + Math.sin(k * 22 + t)        * h * 0.32 * smoothed
        + Math.sin(k *  9 + t * 0.6)  * h * 0.18 * smoothed
        + Math.sin(k * 41 + t * 1.4)  * h * 0.08 * smoothed;
      x === 0 ? ctx.moveTo(x, y) : ctx.lineTo(x, y);
    }
    ctx.stroke();
    ctx.shadowBlur = 0;

    requestAnimationFrame(draw);
  }
  requestAnimationFrame(draw);
})();
