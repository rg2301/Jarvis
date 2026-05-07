// WebSocket client + state plumbing for the HUD.

(function () {
  'use strict';

  // ── Mood palettes ──────────────────────────────────────────
  // r/g/b is the accent; hr/hg/hb is the brighter highlight tone
  // used for inner ring highlights and ignition flashes.
  const PALETTES = {
    dry:       { r:   0, g: 212, b: 255, hr: 120, hg: 230, hb: 255 },
    calm:      { r:  95, g: 212, b: 212, hr: 170, hg: 240, hb: 240 },
    amused:    { r:  77, g: 208, b: 255, hr: 170, hg: 230, hb: 255 },
    concerned: { r: 255, g: 183, b:  77, hr: 255, hg: 215, hb: 140 },
    urgent:    { r: 255, g:  82, b:  82, hr: 255, hg: 150, hb: 150 },
    curious:   { r: 179, g: 136, b: 255, hr: 210, hg: 185, hb: 255 },
  };
  const DEFAULT_PALETTE = PALETTES.dry;

  function applyPalette(mood) {
    const p = PALETTES[mood] || DEFAULT_PALETTE;
    if (window.HUD) window.HUD.targetPalette = p;
    const root = document.documentElement.style;
    root.setProperty('--cyan',      `rgb(${p.r}, ${p.g}, ${p.b})`);
    root.setProperty('--cyan-soft', `rgba(${p.r}, ${p.g}, ${p.b}, 0.55)`);
    root.setProperty('--cyan-dim',  `rgba(${p.r}, ${p.g}, ${p.b}, 0.25)`);
    root.setProperty('--line',      `rgba(${p.r}, ${p.g}, ${p.b}, 0.35)`);
    root.setProperty('--line-hot',  `rgba(${p.hr}, ${p.hg}, ${p.hb}, 0.85)`);
  }
  applyPalette('dry');

  const hud        = document.querySelector('.hud');
  const stateLabel = document.getElementById('state-label');
  const coreState  = document.getElementById('core-state');
  const coreHint   = document.getElementById('core-hint');
  const clockEl    = document.getElementById('clock');
  const convo      = document.getElementById('convo');
  const toolLog    = document.getElementById('tool-log');
  const cpuBar     = document.getElementById('cpu-bar');
  const memBar     = document.getElementById('mem-bar');
  const netBar     = document.getElementById('net-bar');
  const cpuNum     = document.getElementById('cpu-num');
  const memNum     = document.getElementById('mem-num');
  const uptimeEl   = document.getElementById('uptime');

  // ── Clock + uptime ─────────────────────────────────────────
  const bootedAt = Date.now();
  function tick() {
    const d = new Date();
    const pad = (n) => String(n).padStart(2, '0');
    clockEl.textContent = `${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`;
    const s = Math.floor((Date.now() - bootedAt) / 1000);
    uptimeEl.textContent = `${pad(Math.floor(s/3600))}:${pad(Math.floor(s/60)%60)}:${pad(s%60)}`;
  }
  setInterval(tick, 1000); tick();

  // System stats — populated by `stats` events from the backend monitor.
  // Until the first event arrives, the bars stay empty.
  netBar.style.width = '100%';
  function applyStats(cpu, mem) {
    cpuBar.style.width = cpu + '%'; cpuNum.textContent = Math.round(cpu) + '%';
    memBar.style.width = mem + '%'; memNum.textContent = Math.round(mem) + '%';
  }

  // ── State machine ──────────────────────────────────────────
  function setState(state) {
    hud.dataset.state = state;
    const labels = {
      dormant:   ['STANDBY',   'DORMANT',  'Say "Jarvis" to wake'],
      awake:     ['ONLINE',    'ONLINE',   'Awaiting command'],
      listening: ['LISTENING', 'LISTENING','Speak now'],
      thinking:  ['PROCESSING','THINKING', 'Computing response'],
      speaking:  ['SPEAKING',  'SPEAKING', 'Audio output active'],
    };
    const [top, core, hint] = labels[state] ?? labels.dormant;
    stateLabel.textContent = top;
    coreState.textContent  = core;
    coreHint.textContent   = hint;
    if (window.HUD) window.HUD.setMode(state);
  }
  setState('dormant');

  // ── Conversation log helpers ───────────────────────────────
  function appendMsg(who, text, mood) {
    const div = document.createElement('div');
    div.className = 'msg ' + (who === 'user' ? 'user' : 'assistant');

    const head = document.createElement('span');
    head.className = 'who';
    head.textContent = who === 'user' ? 'YOU' : 'JARVIS';

    if (who !== 'user') {
      const p = PALETTES[mood] || DEFAULT_PALETTE;
      div.style.borderLeftColor = `rgba(${p.r}, ${p.g}, ${p.b}, 0.85)`;
      if (mood) {
        const tag = document.createElement('span');
        tag.className = 'mood-tag';
        tag.textContent = mood.toUpperCase();
        tag.style.color = `rgb(${p.r}, ${p.g}, ${p.b})`;
        tag.style.borderColor = `rgba(${p.r}, ${p.g}, ${p.b}, 0.5)`;
        head.appendChild(tag);
      }
    }

    div.appendChild(head);
    div.appendChild(document.createTextNode(text));
    convo.appendChild(div);
    convo.scrollTop = convo.scrollHeight;
    while (convo.children.length > 40) convo.firstChild.remove();
  }

  function appendTool(name, args, result) {
    const li = document.createElement('li');
    const argText = args ? Object.entries(args).map(([k,v]) => `${k}=${JSON.stringify(v)}`).join(' ') : '';
    li.innerHTML = `<b>&#9881; ${escapeHtml(name)}</b> ${escapeHtml(argText)}`;
    if (result) {
      const r = document.createElement('span');
      r.className = 'res';
      r.textContent = '→ ' + result;
      li.appendChild(r);
    }
    toolLog.insertBefore(li, toolLog.firstChild);
    while (toolLog.children.length > 20) toolLog.lastChild.remove();
  }
  function escapeHtml(s) {
    return String(s).replace(/[&<>"']/g, (c) => ({
      '&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'
    }[c]));
  }

  // ── WebSocket ──────────────────────────────────────────────
  let pendingTools = new Map();

  function connect() {
    const proto = location.protocol === 'https:' ? 'wss' : 'ws';
    const ws = new WebSocket(`${proto}://${location.host}/ws`);

    ws.onopen = () => console.log('[hud] connected');
    ws.onclose = () => {
      console.log('[hud] disconnected, retrying...');
      setTimeout(connect, 1500);
    };
    ws.onerror = (e) => console.warn('[hud] ws error', e);

    ws.onmessage = (ev) => {
      let m; try { m = JSON.parse(ev.data); } catch { return; }
      handleEvent(m);
    };
  }

  function handleEvent(m) {
    switch (m.type) {
      case 'hello':
        // initial connection — server sends nothing else automatically
        break;
      case 'state':
        setState(m.state);
        break;
      case 'wake':
        // Force a clean palette + energy snap before the ignition animation
        // so a re-wake after sleep looks identical to a fresh boot.
        applyPalette('dry');
        if (window.HUD && window.HUD.currentPalette && window.HUD.targetPalette) {
          Object.assign(window.HUD.currentPalette, window.HUD.targetPalette);
        }
        setState('awake');
        flashIgnition();
        break;
      case 'user_message':
        if (m.text) appendMsg('user', m.text);
        break;
      case 'transcript':
        // Internal STT event — also fires for confirmation prompts and guest
        // input. The conversation log uses `user_message` instead.
        break;
      case 'stats':
        if (typeof m.cpu === 'number' && typeof m.mem === 'number') applyStats(m.cpu, m.mem);
        break;
      case 'volume':
        if (window.HUD && typeof m.amp === 'number') window.HUD.voice = m.amp;
        break;
      case 'speak_start':
        setState('speaking');
        applyPalette(m.mood);
        if (m.text) appendMsg('assistant', m.text, m.mood);
        break;
      case 'speak_end':
        // Revert to the default palette; the next state event sets the mode.
        applyPalette('dry');
        break;
      case 'tool_call':
        pendingTools.set(m.name, m.args);
        appendTool(m.name, m.args, null);
        break;
      case 'tool_result':
        appendTool(m.name, pendingTools.get(m.name), m.result);
        pendingTools.delete(m.name);
        break;
      default:
        // ignore
    }
  }

  function flashIgnition() {
    document.body.animate(
      [
        { filter: 'brightness(1)' },
        { filter: 'brightness(1.6)' },
        { filter: 'brightness(1)' },
      ],
      { duration: 700, easing: 'ease-out' }
    );
  }

  connect();
})();
