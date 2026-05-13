// ── State ──────────────────────────────────────────────────────
const state = {
  activeRoom:  null,
  brief:       null,   // from Researcher
  design:      null,   // from Designer
  product:     null,   // from Factory (after approval)
  chatHistory: [],
  loading:     false,
};

const API = '';  // same origin — server on port 9000 serves both UI and API

// ── Panel ──────────────────────────────────────────────────────
function openPanel(room) {
  state.activeRoom = room;

  document.querySelectorAll('.room').forEach(r => r.classList.remove('active'));
  document.getElementById(`room-${room}`)?.classList.add('active');

  document.getElementById('panel').classList.add('open');
  document.getElementById('map-viewport').classList.add('panel-open');

  const titles = {
    ceo:      '⚡ CAPTAIN\'S ROOM — ZURG',
    research: '🔍 RESEARCH ROOM',
    design:   '🎨 DESIGN ROOM',
    factory:  '🏭 FACTORY ROOM',
  };
  document.getElementById('panel-title').textContent = titles[room] || room.toUpperCase();

  renderPanel(room);
}

function closePanel() {
  document.getElementById('panel').classList.remove('open');
  document.getElementById('map-viewport').classList.remove('panel-open');
  document.querySelectorAll('.room').forEach(r => r.classList.remove('active'));
  state.activeRoom = null;
}

function renderPanel(room) {
  const body = document.getElementById('panel-body');
  const renders = { ceo: renderCeo, research: renderResearch, design: renderDesign, factory: renderFactory };
  (renders[room] || (() => { body.innerHTML = ''; }))(body);
}

// ── CEO Panel ──────────────────────────────────────────────────
async function renderCeo(body) {
  body.innerHTML = `
    <div id="chat-history"></div>
    <div id="chat-input-row">
      <input id="chat-input" class="text-input" type="text"
             placeholder="talk to zurg..."
             onkeydown="if(event.key==='Enter') sendChat()">
      <button class="btn btn-purple" onclick="sendChat()">SEND ▶</button>
    </div>`;

  // Load shared history from server
  try {
    const res = await fetch(`${API}/api/chat/history`);
    const history = await res.json();
    if (history.length > 0) {
      state.chatHistory = history.map(m => ({ role: m.role, text: m.text }));
    }
  } catch (_) {}

  redrawChatHistory();

  if (state.chatHistory.length === 0) {
    appendChat('zurg', 'Zurg online. What do you need, Max?');
  }
}

function redrawChatHistory() {
  const el = document.getElementById('chat-history');
  if (!el) return;
  el.innerHTML = '';
  state.chatHistory.forEach(msg => {
    el.appendChild(buildChatBubble(msg.role, msg.text));
  });
  el.scrollTop = el.scrollHeight;
}

function buildChatBubble(role, text) {
  const wrap = document.createElement('div');
  wrap.className = `chat-msg ${role}`;
  wrap.innerHTML = `
    <div class="chat-msg-label">${role === 'owner' ? 'MAX' : 'ZURG'}</div>
    <div class="chat-msg-text">${escHtml(text)}</div>`;
  return wrap;
}

function appendChat(role, text) {
  state.chatHistory.push({ role, text });
  const el = document.getElementById('chat-history');
  if (!el) return;
  el.appendChild(buildChatBubble(role, text));
  el.scrollTop = el.scrollHeight;
}

function setChatDisabled(disabled) {
  const input = document.getElementById('chat-input');
  const btn   = document.querySelector('#chat-input-row .btn');
  if (input) input.disabled = disabled;
  if (btn)   btn.disabled   = disabled;
}

async function sendChat() {
  const input = document.getElementById('chat-input');
  if (!input) return;
  const message = input.value.trim();
  if (!message || state.loading) return;

  input.value = '';
  appendChat('owner', message);
  state.loading = true;
  setChatDisabled(true);

  // Thinking placeholder
  const el = document.getElementById('chat-history');
  const bubble = document.createElement('div');
  bubble.className = 'chat-msg zurg';
  bubble.innerHTML = `
    <div class="chat-msg-label">ZURG</div>
    <div class="chat-msg-text"><span class="chat-cursor"></span></div>`;
  el?.appendChild(bubble);
  el && (el.scrollTop = el.scrollHeight);

  let response = '';
  try {
    const res  = await fetch(`${API}/api/chat/ceo/instruct`, {
      method:  'POST',
      headers: { 'Content-Type': 'application/json' },
      body:    JSON.stringify({ message, brief: state.brief || {}, design: state.design || {} }),
    });
    const data = await res.json();
    response   = data.response || '';

    if (data.intent === 'research' && data.data?.niche) {
      state.brief = data.data;
      toast('RESEARCH COMPLETE — ' + data.data.niche.toUpperCase());
    } else if (data.intent === 'design' && data.data?.image_path) {
      state.design = data.data;
      toast('DESIGN READY — OPEN FACTORY TO APPROVE');
    } else if (data.intent === 'pipeline') {
      if (data.data?.brief)      state.brief  = data.data.brief;
      if (data.data?.image_path) state.design = data.data;
      toast('PIPELINE COMPLETE — REVIEW DESIGN IN FACTORY');
    } else if (data.intent === 'publish' && data.data?.product_url) {
      state.product = data.data;
      toast('PUBLISHED TO SHOPIFY');
    }
  } catch (e) {
    response = '[error — check server logs]';
  }

  bubble.remove();
  if (response) appendChat('zurg', response);
  state.loading = false;
  setChatDisabled(false);
}

// ── Research Panel ─────────────────────────────────────────────
function renderResearch(body) {
  const briefHtml = state.brief ? `
    <div class="panel-section">
      <div class="panel-section-title">▶ CURRENT BRIEF</div>
      <div class="brief-field">NICHE: <span>${escHtml(state.brief.niche)}</span></div>
      <div class="brief-field">PRODUCT: <span>${escHtml(state.brief.product_type)}</span></div>
      <div class="brief-field">AUDIENCE: <span>${escHtml(state.brief.target_audience)}</span></div>
      <div class="brief-field">KEYWORDS: <span>${(state.brief.keywords || []).join(', ')}</span></div>
      <div class="brief-field">DESIGN: <span>${escHtml(state.brief.design_direction)}</span></div>
    </div>` : `<div class="empty-state">NO BRIEF YET.<br><br>RUN RESEARCH TO FIND A NICHE.</div>`;

  body.innerHTML = `
    <div class="room-panel">
      <div class="panel-section">
        <div class="panel-section-title">▶ RUN RESEARCH</div>
        <div class="direction-row">
          <input id="research-direction" class="text-input" type="text"
                 placeholder="optional direction (e.g. cats, hiking, coffee)...">
          <button class="btn btn-purple" id="research-btn" onclick="runResearch()">RUN ▶</button>
        </div>
        <div id="research-status"></div>
      </div>
      ${briefHtml}
    </div>`;
}

async function runResearch() {
  if (state.loading) return;
  state.loading = true;

  const direction = document.getElementById('research-direction')?.value.trim() || '';
  const statusEl = document.getElementById('research-status');
  const btn = document.getElementById('research-btn');

  if (statusEl) statusEl.innerHTML = `<div class="loading-row"><div class="spinner"></div> RESEARCHING NICHES...</div>`;
  if (btn) btn.disabled = true;

  try {
    const res = await fetch(`${API}/api/rooms/research/run`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ direction }),
    });
    const data = await res.json();
    state.brief = data;
    toast('RESEARCH COMPLETE — ' + data.niche.toUpperCase());
    renderPanel('research');
  } catch (e) {
    if (statusEl) statusEl.innerHTML = `<div class="empty-state">ERROR: ${escHtml(e.message)}</div>`;
  }

  state.loading = false;
  if (btn) btn.disabled = false;
}

// ── Design Panel ───────────────────────────────────────────────
function renderDesign(body) {
  const noBrief = !state.brief;
  const hasImage = state.design?.image_path;

  const imageHtml = hasImage ? `
    <div class="panel-section">
      <div class="panel-section-title">▶ GENERATED DESIGN</div>
      <img class="design-preview" src="${escHtml(state.design.image_path)}" alt="Design">
      <div class="brief-field">NICHE: <span>${escHtml(state.design.niche)}</span></div>
      <div class="brief-field">PRODUCT: <span>${escHtml(state.design.product_type)}</span></div>
    </div>` : `<div class="empty-state">NO DESIGN YET.<br><br>GENERATE ONE BELOW.</div>`;

  body.innerHTML = `
    <div class="room-panel">
      <div class="panel-section">
        <div class="panel-section-title">▶ GENERATE DESIGN</div>
        ${noBrief ? '<div class="empty-state">RUN RESEARCH FIRST TO GET A BRIEF.</div>' : ''}
        <button class="btn btn-purple" id="design-btn" onclick="runDesign()"
                ${noBrief ? 'disabled' : ''}>GENERATE ▶</button>
        <div id="design-status"></div>
      </div>
      ${imageHtml}
    </div>`;
}

async function runDesign() {
  if (state.loading || !state.brief) return;
  state.loading = true;

  const statusEl = document.getElementById('design-status');
  const btn = document.getElementById('design-btn');

  if (statusEl) statusEl.innerHTML = `<div class="loading-row"><div class="spinner"></div> GENERATING DESIGN — THIS TAKES ~15s...</div>`;
  if (btn) btn.disabled = true;

  try {
    const res = await fetch(`${API}/api/rooms/design/run`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(state.brief),
    });
    const data = await res.json();
    state.design = data;
    toast('DESIGN READY — GO TO FACTORY TO APPROVE');
    renderPanel('design');
  } catch (e) {
    if (statusEl) statusEl.innerHTML = `<div class="empty-state">ERROR: ${escHtml(e.message)}</div>`;
  }

  state.loading = false;
}

// ── Factory Panel (Approval Gate) ──────────────────────────────
function renderFactory(body) {
  const hasDesign = state.design?.image_path;
  const hasProduct = state.product?.product_url;

  if (hasProduct) {
    body.innerHTML = `
      <div class="room-panel">
        <div class="panel-section">
          <div class="panel-section-title">▶ PUBLISHED TO SHOPIFY</div>
          <div class="brief-field">TITLE: <span>${escHtml(state.product.title)}</span></div>
          <div class="product-link">
            ADMIN: <a href="${escHtml(state.product.product_url)}" target="_blank">${escHtml(state.product.product_url)}</a>
          </div>
          <br>
          <button class="btn btn-yellow" onclick="resetPipeline()">▶ START NEW PIPELINE</button>
        </div>
      </div>`;
    return;
  }

  if (!hasDesign) {
    body.innerHTML = `<div class="empty-state">NO DESIGN AWAITING APPROVAL.<br><br>RUN RESEARCH → DESIGN FIRST.</div>`;
    return;
  }

  body.innerHTML = `
    <div class="room-panel">
      <div class="panel-section">
        <div class="panel-section-title">▶ APPROVE THIS DESIGN?</div>
        <img class="design-preview" src="${escHtml(state.design.image_path)}" alt="Design">
        <div class="brief-field">NICHE: <span>${escHtml(state.design.niche)}</span></div>
        <div class="brief-field">PRODUCT: <span>${escHtml(state.design.product_type)}</span></div>
        <div id="factory-status"></div>
        <div class="approval-buttons">
          <button class="btn btn-green" id="approve-btn" onclick="approveDesign()">✓ APPROVE</button>
          <button class="btn btn-red"   id="reject-btn"  onclick="rejectDesign()">✕ REJECT</button>
        </div>
      </div>
    </div>`;
}

async function approveDesign() {
  if (state.loading || !state.design) return;
  state.loading = true;

  const statusEl = document.getElementById('factory-status');
  const appBtn = document.getElementById('approve-btn');
  const rejBtn = document.getElementById('reject-btn');

  if (statusEl) statusEl.innerHTML = `<div class="loading-row"><div class="spinner"></div> PUBLISHING TO SHOPIFY...</div>`;
  if (appBtn) appBtn.disabled = true;
  if (rejBtn) rejBtn.disabled = true;

  try {
    const payload = {
      approved: true,
      ...state.brief,
      ...state.design,
    };
    const res = await fetch(`${API}/api/approval/decide`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    const data = await res.json();
    state.product = data.product;
    toast('PUBLISHED! CHECK YOUR SHOPIFY ADMIN.');
    renderPanel('factory');
  } catch (e) {
    if (statusEl) statusEl.innerHTML = `<div class="empty-state">ERROR: ${escHtml(e.message)}</div>`;
    if (appBtn) appBtn.disabled = false;
    if (rejBtn) rejBtn.disabled = false;
  }

  state.loading = false;
}

function rejectDesign() {
  state.design = null;
  toast('DESIGN REJECTED — GENERATE A NEW ONE IN THE DESIGN ROOM.');
  renderPanel('factory');
}

function resetPipeline() {
  state.brief = null;
  state.design = null;
  state.product = null;
  toast('PIPELINE RESET — START WITH RESEARCH.');
  closePanel();
}

// ── Toast ──────────────────────────────────────────────────────
let toastTimer = null;
function toast(msg) {
  const el = document.getElementById('toast');
  el.textContent = msg;
  el.classList.add('show');
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => el.classList.remove('show'), 3500);
}

// ── Util ───────────────────────────────────────────────────────
function escHtml(str) {
  return String(str ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

// ── Shooting Stars ────────────────────────────────────────────
(function initShootingStars() {
  const canvas = document.getElementById('shooting-stars');
  const ctx    = canvas.getContext('2d');
  const stars  = [];

  function resize() {
    const vp      = canvas.parentElement;
    canvas.width  = vp.clientWidth;
    canvas.height = vp.clientHeight;
  }
  resize();
  window.addEventListener('resize', resize);

  function spawn() {
    const angle  = (Math.random() * Math.PI / 2) + Math.PI / 6; // downward-ish
    const speed  = 6 + Math.random() * 8;
    stars.push({
      x:       Math.random() * canvas.width,
      y:       Math.random() * canvas.height * 0.6,
      vx:      Math.cos(angle) * speed,
      vy:      Math.sin(angle) * speed,
      trail:   60 + Math.random() * 80,
      opacity: 1,
    });
    setTimeout(spawn, 1500 + Math.random() * 4000);
  }
  spawn();

  function draw() {
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    for (let i = stars.length - 1; i >= 0; i--) {
      const s   = stars[i];
      const spd = Math.hypot(s.vx, s.vy);
      const tx  = s.x - (s.vx / spd) * s.trail;
      const ty  = s.y - (s.vy / spd) * s.trail;
      const grad = ctx.createLinearGradient(s.x, s.y, tx, ty);
      grad.addColorStop(0, `rgba(255,255,255,${s.opacity})`);
      grad.addColorStop(1, 'rgba(255,255,255,0)');
      ctx.beginPath();
      ctx.moveTo(s.x, s.y);
      ctx.lineTo(tx, ty);
      ctx.strokeStyle = grad;
      ctx.lineWidth   = 1.5;
      ctx.stroke();
      s.x += s.vx;
      s.y += s.vy;
      s.opacity -= 0.012;
      if (s.opacity <= 0 || s.x > canvas.width + 100 || s.y > canvas.height + 100) {
        stars.splice(i, 1);
      }
    }
    requestAnimationFrame(draw);
  }
  draw();
})();

// ── Zurg Spritesheet (canvas) ──────────────────────────────────
(function initZurgSprite() {
  const FRAMES     = 15;
  const FRAME_W    = 224;   // 3360 / 15
  const FRAME_H    = 240;
  const DISPLAY    = 160;
  const FPS        = 10;

  const canvas = document.getElementById('sprite-zurg');
  if (!canvas) return;
  const ctx = canvas.getContext('2d');
  canvas.width  = DISPLAY;
  canvas.height = DISPLAY;

  const img = new Image();
  img.src = '/assets/zurg-sprite.png';
  let frame = 0;

  img.onload = () => {
    setInterval(() => {
      ctx.clearRect(0, 0, DISPLAY, DISPLAY);
      ctx.drawImage(
        img,
        frame * FRAME_W, 0, FRAME_W, FRAME_H,
        0, 0, DISPLAY, DISPLAY
      );
      frame = (frame + 1) % FRAMES;
    }, 1000 / FPS);
  };
})();

// ── Character Movement (grid path + circle wander) ─────────────
(function initCharacterMovement() {
  const RADIUS       = 260;
  const CIRCLE_SPEED = 0.002;
  const TRAVEL_SPEED = CIRCLE_SPEED * RADIUS;  // match arc walking speed
  const VISIT_MIN    = 8000;
  const VISIT_MAX    = 20000;
  const VISIT_CHANCE = 0.0002;

  // 2×2 grid of rooms; gx/gy are grid coords
  const ROOMS = [
    { cx: 512,  cy: 512,  gx: 0, gy: 0 },  // CEO
    { cx: 1536, cy: 512,  gx: 1, gy: 0 },  // Research
    { cx: 512,  cy: 1536, gx: 0, gy: 1 },  // Design
    { cx: 1536, cy: 1536, gx: 1, gy: 1 },  // Factory
  ];

  function cardinalAngle(fx, fy, tx, ty) {
    return Math.atan2(ty - fy, tx - fx);
  }

  // Returns { exitAngle, waypoints[], arrivalAngle } for straight-line grid travel
  function buildPath(src, dst) {
    const waypoints = [];
    let exitAngle, arrivalAngle;

    if (src.gx === dst.gx || src.gy === dst.gy) {
      // Adjacent rooms — single corridor segment
      exitAngle    = cardinalAngle(src.cx, src.cy, dst.cx, dst.cy);
      arrivalAngle = exitAngle + Math.PI;
      waypoints.push({
        x: dst.cx + RADIUS * Math.cos(arrivalAngle),
        y: dst.cy + RADIUS * Math.sin(arrivalAngle),
      });
    } else {
      // Diagonal — route through one intermediate room center as junction
      const mid = (Math.random() < 0.5)
        ? ROOMS.find(r => r.gx === dst.gx && r.gy === src.gy)  // horizontal first
        : ROOMS.find(r => r.gx === src.gx && r.gy === dst.gy); // vertical first
      exitAngle = cardinalAngle(src.cx, src.cy, mid.cx, mid.cy);
      waypoints.push({ x: mid.cx, y: mid.cy });
      const leg2   = cardinalAngle(mid.cx, mid.cy, dst.cx, dst.cy);
      arrivalAngle = leg2 + Math.PI;
      waypoints.push({
        x: dst.cx + RADIUS * Math.cos(arrivalAngle),
        y: dst.cy + RADIUS * Math.sin(arrivalAngle),
      });
    }

    return { exitAngle, waypoints, arrivalAngle };
  }

  function makeChar(id, w, h, homeIdx) {
    const el = document.getElementById(id);
    if (!el) return null;
    const home  = ROOMS[homeIdx];
    const angle = Math.random() * Math.PI * 2;
    return {
      el, w, h, home,
      currentRoom:  home,
      state:        'wandering',
      angle,
      circleTarget: Math.random() * Math.PI * 2,
      pauseUntil:   0,
      posX: home.cx + RADIUS * Math.cos(angle),
      posY: home.cy + RADIUS * Math.sin(angle),
      exitAngle:    0,
      waypoints:    [],
      arrivalAngle: 0,
      destRoom:     null,
      visitUntil:   0,
    };
  }

  const chars = [
    makeChar('sprite-zurg',       160, 160, 0),
    makeChar('sprite-researcher', 144, 144, 1),
    makeChar('sprite-designer',   144, 144, 2),
  ].filter(Boolean);

  function place(c) {
    c.el.style.left = (c.posX - c.w / 2) + 'px';
    c.el.style.top  = (c.posY - c.h)     + 'px';
  }

  function stepCircle(c, now) {
    if (now < c.pauseUntil) return;
    let diff = c.circleTarget - c.angle;
    while (diff >  Math.PI) diff -= Math.PI * 2;
    while (diff < -Math.PI) diff += Math.PI * 2;
    if (Math.abs(diff) < CIRCLE_SPEED * 2) {
      c.angle        = c.circleTarget;
      c.pauseUntil   = now + 600 + Math.random() * 1800;
      c.circleTarget = Math.random() * Math.PI * 2;
    } else {
      c.angle += Math.sign(diff) * CIRCLE_SPEED;
    }
    c.posX = c.currentRoom.cx + RADIUS * Math.cos(c.angle);
    c.posY = c.currentRoom.cy + RADIUS * Math.sin(c.angle);
  }

  // Arc along the current circle to targetAngle; returns true when arrived
  function arcToExit(c, targetAngle) {
    let diff = targetAngle - c.angle;
    while (diff >  Math.PI) diff -= Math.PI * 2;
    while (diff < -Math.PI) diff += Math.PI * 2;
    if (Math.abs(diff) < CIRCLE_SPEED * 2) {
      c.angle = targetAngle;
      c.posX  = c.currentRoom.cx + RADIUS * Math.cos(c.angle);
      c.posY  = c.currentRoom.cy + RADIUS * Math.sin(c.angle);
      return true;
    }
    c.angle += Math.sign(diff) * CIRCLE_SPEED;
    c.posX   = c.currentRoom.cx + RADIUS * Math.cos(c.angle);
    c.posY   = c.currentRoom.cy + RADIUS * Math.sin(c.angle);
    return false;
  }

  function stepToward(c, tx, ty) {
    const dx = tx - c.posX, dy = ty - c.posY;
    const dist = Math.hypot(dx, dy);
    if (dist <= TRAVEL_SPEED) { c.posX = tx; c.posY = ty; return true; }
    c.posX += (dx / dist) * TRAVEL_SPEED;
    c.posY += (dy / dist) * TRAVEL_SPEED;
    return false;
  }

  function startPath(c, dst) {
    const path    = buildPath(c.currentRoom, dst);
    c.exitAngle   = path.exitAngle;
    c.waypoints   = path.waypoints;
    c.arrivalAngle = path.arrivalAngle;
    c.destRoom    = dst;
    c.state       = 'to_exit';
  }

  function tick(now) {
    chars.forEach(c => {
      switch (c.state) {

        case 'wandering':
          stepCircle(c, now);
          if (Math.random() < VISIT_CHANCE) {
            const others = ROOMS.filter(r => r !== c.home);
            startPath(c, others[Math.floor(Math.random() * others.length)]);
          }
          break;

        case 'to_exit':
          if (arcToExit(c, c.exitAngle)) c.state = 'corridor';
          break;

        case 'corridor': {
          if (c.waypoints.length === 0) {
            // Arrived
            c.currentRoom = c.destRoom;
            c.angle        = c.arrivalAngle;
            c.circleTarget = Math.random() * Math.PI * 2;
            c.pauseUntil   = 0;
            if (c.destRoom === c.home) {
              c.state = 'wandering';
            } else {
              c.visitUntil = now + VISIT_MIN + Math.random() * (VISIT_MAX - VISIT_MIN);
              c.state = 'visiting';
            }
            break;
          }
          const wp = c.waypoints[0];
          if (stepToward(c, wp.x, wp.y)) c.waypoints.shift();
          break;
        }

        case 'visiting':
          stepCircle(c, now);
          if (now > c.visitUntil) startPath(c, c.home);
          break;
      }
      place(c);
    });
    requestAnimationFrame(tick);
  }

  requestAnimationFrame(tick);
})();

// ── Zoom & Pan ─────────────────────────────────────────────────
(function initMapControls() {
  const viewport = document.getElementById('map-viewport');
  const map      = document.getElementById('map');
  const MAP_SIZE = 2048;

  let scale  = 1;
  let panX   = 0;
  let panY   = 0;
  let dragging   = false;
  let dragStartX = 0;
  let dragStartY = 0;
  let panStartX  = 0;
  let panStartY  = 0;
  let didDrag    = false;  // distinguish click vs drag

  function clampPan(x, y) {
    const vw = viewport.clientWidth;
    const vh = viewport.clientHeight;
    const scaledW = MAP_SIZE * scale;
    const scaledH = MAP_SIZE * scale;
    const margin = 120; // min px of map that must stay visible
    return {
      x: Math.max(margin - scaledW, Math.min(vw - margin, x)),
      y: Math.max(margin - scaledH, Math.min(vh - margin, y)),
    };
  }

  function applyTransform() {
    map.style.transform = `translate(${panX}px, ${panY}px) scale(${scale})`;
  }

  const MIN_SCALE = 0.2;

  function fitToViewport() {
    const vw = viewport.clientWidth;
    const vh = viewport.clientHeight;
    scale = MIN_SCALE;
    // Center the map in the viewport at min zoom
    panX = (vw - MAP_SIZE * scale) / 2;
    panY = (vh - MAP_SIZE * scale) / 2;
    applyTransform();
  }

  function clampOnResize() {
    const clamped = clampPan(panX, panY);
    panX = clamped.x;
    panY = clamped.y;
    applyTransform();
  }

  // Zoom on scroll
  viewport.addEventListener('wheel', e => {
    e.preventDefault();
    const rect   = viewport.getBoundingClientRect();
    const mouseX = e.clientX - rect.left;
    const mouseY = e.clientY - rect.top;

    const zoomFactor = e.deltaY < 0 ? 1.1 : 0.9;
    const newScale   = Math.max(0.2, Math.min(0.755, scale * zoomFactor));

    // Zoom toward mouse position
    panX = mouseX - (mouseX - panX) * (newScale / scale);
    panY = mouseY - (mouseY - panY) * (newScale / scale);
    scale = newScale;

    const clamped = clampPan(panX, panY);
    panX = clamped.x;
    panY = clamped.y;
    applyTransform();
  }, { passive: false });

  // Drag to pan
  viewport.addEventListener('mousedown', e => {
    if (e.target.closest('button, input')) return;
    e.preventDefault();
    dragging   = true;
    didDrag    = false;
    dragStartX = e.clientX;
    dragStartY = e.clientY;
    panStartX  = panX;
    panStartY  = panY;
    viewport.classList.add('dragging');
  });

  window.addEventListener('mousemove', e => {
    if (!dragging) return;
    const dx = e.clientX - dragStartX;
    const dy = e.clientY - dragStartY;
    if (Math.abs(dx) > 4 || Math.abs(dy) > 4) didDrag = true;
    const clamped = clampPan(panStartX + dx, panStartY + dy);
    panX = clamped.x;
    panY = clamped.y;
    applyTransform();
  });

  window.addEventListener('mouseup', () => {
    dragging = false;
    viewport.classList.remove('dragging');
  });

  // Block room clicks if user was dragging
  viewport.addEventListener('click', e => {
    if (didDrag) {
      e.stopPropagation();
      didDrag = false;
    }
  }, true);

  // Initial fit
  fitToViewport();
  window.addEventListener('resize', clampOnResize);
})();

// ── Init ───────────────────────────────────────────────────────
window.addEventListener('keydown', e => {
  if (e.key === 'Escape') closePanel();
});
