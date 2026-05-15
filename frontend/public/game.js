// ── State ──────────────────────────────────────────────────────
const state = {
  activeRoom:    null,
  brief:         null,   // from Researcher
  design:        null,   // from Designer
  product:       null,   // from Factory (after approval)
  chatHistory:   [],
  loading:       false,
  autoResearch:  localStorage.getItem('autoResearch')  === 'true',
  autoDesign:    localStorage.getItem('autoDesign')    === 'true',
  autoApproval:  localStorage.getItem('autoApproval')  === 'true',
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
    approval: '⚖️ APPROVAL ROOM',
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
  const renders = { ceo: renderCeo, research: renderResearch, design: renderDesign, factory: renderFactory, approval: renderApproval };
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
      if (state.autoDesign) setTimeout(() => runDesign(), 400);
    } else if (data.intent === 'design' && data.data?.image_path) {
      state.design = data.data;
      toast('DESIGN READY' + (state.autoApproval ? ' — AUTO-APPROVING...' : ' — OPEN APPROVAL ROOM'));
      if (state.autoApproval) setTimeout(() => _runAutoApprove(), 400);
    } else if (data.intent === 'pipeline') {
      if (data.data?.brief)      state.brief  = data.data.brief;
      if (data.data?.image_path) state.design = data.data;
      toast('PIPELINE COMPLETE — REVIEW DESIGN IN APPROVAL ROOM');
      if (state.design && state.autoApproval) setTimeout(() => _runAutoApprove(), 400);
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
async function renderResearch(body) {
  const briefHtml = state.brief ? `
    <div class="panel-section">
      <div class="panel-section-title">▶ CURRENT BRIEF</div>
      <div class="brief-field">NICHE: <span>${escHtml(state.brief.niche)}</span></div>
      <div class="brief-field">PRODUCT: <span>${escHtml(state.brief.product_type)}</span></div>
      <div class="brief-field">AUDIENCE: <span>${escHtml(state.brief.target_audience)}</span></div>
      <div class="brief-field">KEYWORDS: <span>${(state.brief.keywords || []).join(', ')}</span></div>
      <div class="brief-field">DESIGN: <span>${escHtml(state.brief.design_direction)}</span></div>
    </div>` : `<div class="empty-state">NO BRIEF YET.<br><br>RUN RESEARCH TO FIND A NICHE.</div>`;

  // Fetch autonomous loop status
  let loopStatus = null;
  try {
    const r = await fetch(`${API}/api/rooms/research/autonomous/status`);
    if (r.ok) loopStatus = await r.json();
  } catch (_) {}

  const isRunning = loopStatus?.running;
  const nextRunMins = loopStatus?.next_run_seconds != null
    ? Math.ceil(loopStatus.next_run_seconds / 60) : null;
  const todayCount = loopStatus?.products_today ?? 0;
  const maxPerDay  = loopStatus?.max_per_day ?? 6;

  const loopStatusLine = isRunning
    ? `RUNNING — ${nextRunMins != null ? `NEXT RUN IN ${nextRunMins}m` : 'CYCLE IN PROGRESS'}`
    : 'IDLE';
  const loopBtnStyle = isRunning
    ? 'background:#005929;color:#00ff88;border:2px solid #00994d'
    : 'background:#2d1060;color:#a855f7;border:2px solid #7c3aed';
  const loopBtnLabel = isRunning ? '⏹ STOP LOOP' : '▶ START LOOP';

  body.innerHTML = `
    <div class="room-panel">
      <div class="panel-section" style="${isRunning ? 'border-color:#00994d' : ''}">
        <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:8px">
          <div class="panel-section-title" style="margin-bottom:0">▶ AUTONOMOUS LOOP</div>
          <button onclick="toggleAutonomousLoop(${isRunning})"
                  style="font-family:'Press Start 2P',monospace;font-size:6px;padding:6px 10px;cursor:pointer;letter-spacing:1px;${loopBtnStyle}">
            ${loopBtnLabel}
          </button>
        </div>
        <div class="brief-field">STATUS: <span style="${isRunning ? 'color:var(--green)' : ''}">${loopStatusLine}</span></div>
        <div class="brief-field">CADENCE: <span>EVERY ${loopStatus?.delay_minutes ?? 240} MIN</span></div>
        <div class="brief-field">TODAY: <span>${todayCount} / ${maxPerDay} PRODUCTS</span></div>
        <div class="brief-field" style="margin-top:4px;font-size:6px;color:#666">SOURCES: GOOGLE TRENDS + WEB SEARCH + OLLAMA</div>
      </div>
      <div class="panel-section">
        <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:8px">
          <div class="panel-section-title" style="margin-bottom:0">▶ MANUAL RUN</div>
          ${_autoToggleBtn(state.autoResearch, 'toggleAutoResearch')}
        </div>
        <div class="brief-field" style="margin-bottom:8px">MODE: <span>${state.autoResearch ? 'AUTO — CHAINS INTO DESIGN' : 'MANUAL — BRIEF ONLY'}</span></div>
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

async function toggleAutonomousLoop(isRunning) {
  const endpoint = isRunning ? '/api/rooms/research/autonomous/stop' : '/api/rooms/research/autonomous/start';
  try {
    await fetch(`${API}${endpoint}`, { method: 'POST' });
    toast(isRunning ? 'AUTONOMOUS LOOP STOPPED.' : '⚡ AUTONOMOUS LOOP STARTED — RESEARCHING EVERY 4H');
    renderPanel('research');
  } catch (e) {
    toast('ERROR: ' + e.message);
  }
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
    if (state.autoDesign) {
      closePanel();
      setTimeout(() => runDesign(), 400);
    }
  } catch (e) {
    if (statusEl) statusEl.innerHTML = `<div class="empty-state">ERROR: ${escHtml(e.message)}</div>`;
  }

  state.loading = false;
  if (btn) btn.disabled = false;
}

// ── Design Panel ───────────────────────────────────────────────
function renderDesign(body) {
  const noBrief  = !state.brief;
  const hasImage = state.design?.image_path;

  const imageHtml = hasImage ? `
    <div class="panel-section">
      <div class="panel-section-title">▶ GENERATED DESIGN</div>
      <img class="design-preview" src="${escHtml(state.design.image_path)}" alt="Design">
      <div class="brief-field">NICHE: <span>${escHtml(state.design.niche)}</span></div>
      <div class="brief-field">PRODUCT: <span>${escHtml(state.design.product_type)}</span></div>
      ${state.design.shirt_color ? `<div class="brief-field">SHIRT COLOR: <span>${escHtml(state.design.shirt_color)}</span></div>` : ''}
    </div>` : `<div class="empty-state">NO DESIGN YET.<br><br>GENERATE ONE BELOW.</div>`;

  body.innerHTML = `
    <div class="room-panel">
      <div class="panel-section">
        <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:8px">
          <div class="panel-section-title" style="margin-bottom:0">▶ GENERATE DESIGN</div>
          ${_autoToggleBtn(state.autoDesign, 'toggleAutoDesign')}
        </div>
        <div class="brief-field" style="margin-bottom:8px">MODE: <span>${state.autoDesign ? 'AUTO — RUNS AFTER RESEARCH' : 'MANUAL — YOU TRIGGER'}</span></div>
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
    toast('DESIGN READY' + (state.autoApproval ? ' — AUTO-APPROVING...' : ' — GO TO APPROVAL ROOM'));
    renderPanel('design');
    if (state.autoApproval) {
      setTimeout(() => _runAutoApprove(), 400);
    }
  } catch (e) {
    if (statusEl) statusEl.innerHTML = `<div class="empty-state">ERROR: ${escHtml(e.message)}</div>`;
  }

  state.loading = false;
}

// ── Factory Panel (Published Products Status) ─────────────────
function renderFactory(body) {
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

  const pendingMsg = state.design?.image_path
    ? 'DESIGN AWAITING APPROVAL.<br><br>OPEN THE APPROVAL ROOM TO REVIEW IT.'
    : 'NOTHING IN THE QUEUE.<br><br>RUN RESEARCH → DESIGN → APPROVAL.';

  body.innerHTML = `
    <div class="room-panel">
      <div class="panel-section">
        <div class="panel-section-title">▶ FACTORY STATUS</div>
        <div class="empty-state">${pendingMsg}</div>
        ${state.design?.image_path ? `<button class="btn btn-purple" onclick="closePanel(); setTimeout(() => openPanel('approval'), 50)">▶ GO TO APPROVAL ROOM</button>` : ''}
      </div>
    </div>`;
}

function toggleAutoResearch() {
  state.autoResearch = !state.autoResearch;
  localStorage.setItem('autoResearch', state.autoResearch);
  renderPanel('research');
}

function toggleAutoDesign() {
  state.autoDesign = !state.autoDesign;
  localStorage.setItem('autoDesign', state.autoDesign);
  renderPanel('design');
}

function toggleAutoApproval() {
  state.autoApproval = !state.autoApproval;
  localStorage.setItem('autoApproval', state.autoApproval);
  renderPanel('approval');
}

function _autoToggleBtn(isAuto, onToggle) {
  const style = isAuto
    ? 'background:#005929;color:#00ff88;border:2px solid #00994d'
    : 'background:#2d1060;color:#a855f7;border:2px solid #7c3aed';
  const label = isAuto ? '⚡ AUTO' : '👤 MANUAL';
  return `<button onclick="${onToggle}()" style="font-family:'Press Start 2P',monospace;font-size:6px;padding:6px 10px;cursor:pointer;letter-spacing:1px;${style}">${label}</button>`;
}

// ── Approval Panel ─────────────────────────────────────────────
async function renderApproval(body) {
  const hasDesign  = state.design?.image_path;
  const hasProduct = state.product?.product_url;

  // Load verdict history for context
  let verdicts = [];
  try {
    const res = await fetch(`${API}/api/approval/verdicts`);
    if (res.ok) verdicts = await res.json();
  } catch (_) {}

  const verdictCount = verdicts.length;
  const phase = verdictCount < 100 ? 1 : verdictCount < 200 ? 2 : 3;

  const historyHtml = verdicts.slice(-3).reverse().map(v => `
    <div class="verdict-entry ${v.approved ? 'approved' : 'rejected'}">
      ${v.approved ? '✓ APPROVED' : '✕ REJECTED'} — ${escHtml(v.niche)} — ${escHtml(v.date)}
    </div>`).join('');

  const modeLabel  = state.autoApproval ? 'AUTO — AGENT DECIDES' : 'MANUAL — YOU DECIDE';
  const modeBtnTxt = state.autoApproval ? '⚡ AUTO' : '👤 MANUAL';
  const modeBtnStyle = state.autoApproval
    ? 'background:#005929;color:#00ff88;border:2px solid #00994d'
    : 'background:#2d1060;color:#a855f7;border:2px solid #7c3aed';

  const statsHtml = `
    <div class="panel-section">
      <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:8px">
        <div class="panel-section-title" style="margin-bottom:0">▶ APPROVAL ENGINE — PHASE ${phase}</div>
        <button onclick="toggleAutoApproval()"
                style="font-family:'Press Start 2P',monospace;font-size:6px;padding:6px 10px;cursor:pointer;letter-spacing:1px;${modeBtnStyle}">
          ${modeBtnTxt}
        </button>
      </div>
      <div class="brief-field">MODE: <span>${modeLabel}</span></div>
      <div class="brief-field">VERDICTS COLLECTED: <span>${verdictCount} / 100</span></div>
      ${historyHtml ? `<div class="verdict-history">${historyHtml}</div>` : ''}
    </div>`;

  if (hasProduct) {
    body.innerHTML = `
      <div class="room-panel">
        ${statsHtml}
        <div class="panel-section">
          <div class="panel-section-title">▶ LAST DESIGN APPROVED</div>
          <div class="empty-state">PUBLISHED TO SHOPIFY. PIPELINE COMPLETE.<br><br>START A NEW ONE FROM RESEARCH.</div>
          <button class="btn btn-yellow" onclick="resetPipeline()">▶ START NEW PIPELINE</button>
        </div>
      </div>`;
    return;
  }

  if (!hasDesign) {
    body.innerHTML = `
      <div class="room-panel">
        ${statsHtml}
        <div class="empty-state">NO DESIGN IN QUEUE.<br><br>RUN RESEARCH → DESIGN FIRST.</div>
      </div>`;
    return;
  }

  // ── Auto mode: agent decides immediately ──
  if (state.autoApproval) {
    body.innerHTML = `
      <div class="room-panel">
        ${statsHtml}
        <div class="panel-section" style="border-color:#00994d">
          <div class="panel-section-title" style="color:var(--green)">▶ DESIGN IN QUEUE</div>
          <img class="design-preview" src="${escHtml(state.design.image_path)}" alt="Design">
          <div class="brief-field">NICHE: <span>${escHtml(state.design.niche)}</span></div>
          <div class="brief-field">PRODUCT: <span>${escHtml(state.design.product_type)}</span></div>
          <div id="auto-status">
            <div class="loading-row"><div class="spinner"></div> AGENT DECIDING...</div>
          </div>
        </div>
      </div>`;

    const payload = { approved: true, ...state.brief, ...state.design };
    fetch(`${API}/api/approval/auto-decide`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    })
      .then(r => r.json())
      .then(data => {
        const el = document.getElementById('auto-status');
        if (!el) return;
        if (data.approved) {
          state.product = data.product;
          el.innerHTML = `
            <div class="verdict-entry approved">⚡ AGENT APPROVED — PUBLISHED TO SHOPIFY</div>
            <div style="font-size:7px;line-height:2;color:var(--text);margin-top:8px">${escHtml(data.reasoning || '')}</div>
            <br><button class="btn btn-yellow" onclick="resetPipeline()">▶ START NEW PIPELINE</button>`;
          toast('AGENT APPROVED + PUBLISHED.');
        } else {
          state.design = null;
          el.innerHTML = `
            <div class="verdict-entry rejected">✕ AGENT REJECTED</div>
            <div style="font-size:7px;line-height:2;color:var(--text);margin-top:8px">${escHtml(data.reasoning || '')}</div>
            <br><button class="btn btn-purple" onclick="closePanel()">▶ GENERATE ANOTHER DESIGN</button>`;
          toast('AGENT REJECTED — GENERATE A NEW DESIGN.');
        }
      })
      .catch(e => {
        const el = document.getElementById('auto-status');
        if (el) el.innerHTML = `<div class="empty-state">ERROR: ${escHtml(e.message)}</div>`;
      });
    return;
  }

  // ── Manual mode: owner reviews ──
  body.innerHTML = `
    <div class="room-panel">
      ${statsHtml}
      <div class="panel-section">
        <div class="panel-section-title">▶ DESIGN AWAITING YOUR VERDICT</div>
        <img class="design-preview" src="${escHtml(state.design.image_path)}" alt="Design">
        <div class="brief-field">NICHE: <span>${escHtml(state.design.niche)}</span></div>
        <div class="brief-field">PRODUCT: <span>${escHtml(state.design.product_type)}</span></div>
        <div id="agent-analysis" class="panel-section" style="border-color:#00994d">
          <div class="panel-section-title" style="color:var(--green)">▶ APPROVAL AGENT ANALYSIS</div>
          <div class="loading-row"><div class="spinner"></div> ANALYZING...</div>
        </div>
        <div class="panel-section-title" style="margin-top:10px">▶ YOUR FEEDBACK (REQUIRED ON REJECT)</div>
        <textarea id="approval-feedback" class="feedback-input"
                  placeholder="e.g. Love the vintage style — ship it. / Too generic, needs a unique angle..."></textarea>
        <div id="approval-status"></div>
        <div class="approval-buttons">
          <button class="btn btn-green" id="approve-btn" onclick="approveDesign()">✓ APPROVE</button>
          <button class="btn btn-red"   id="reject-btn"  onclick="rejectDesign()">✕ REJECT</button>
        </div>
      </div>
    </div>`;

  // Fetch analysis in background
  fetch(`${API}/api/approval/analyze`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      niche: state.design.niche,
      product_type: state.design.product_type,
      image_path: state.design.image_path,
      image_prompt: state.design.image_prompt || '',
    }),
  })
    .then(r => r.json())
    .then(data => {
      const el = document.getElementById('agent-analysis');
      if (!el) return;
      el.innerHTML = `
        <div class="panel-section-title" style="color:var(--green)">▶ APPROVAL AGENT ANALYSIS</div>
        <div style="font-size:7px;line-height:2;color:var(--text)">${escHtml(data.analysis || '')}</div>`;
    })
    .catch(() => {
      const el = document.getElementById('agent-analysis');
      if (el) el.innerHTML = `<div class="panel-section-title" style="color:var(--green)">▶ APPROVAL AGENT ANALYSIS</div><div class="empty-state">AGENT UNAVAILABLE</div>`;
    });
}

async function approveDesign() {
  if (state.loading || !state.design) return;
  state.loading = true;

  const feedback = document.getElementById('approval-feedback')?.value.trim() || '';
  const statusEl = document.getElementById('approval-status');
  const appBtn   = document.getElementById('approve-btn');
  const rejBtn   = document.getElementById('reject-btn');

  if (statusEl) statusEl.innerHTML = `<div class="loading-row"><div class="spinner"></div> APPROVING — PUBLISHING TO SHOPIFY...</div>`;
  if (appBtn) appBtn.disabled = true;
  if (rejBtn) rejBtn.disabled = true;

  try {
    const payload = {
      approved: true,
      feedback,
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
    toast('APPROVED + PUBLISHED! CHECK SHOPIFY ADMIN.');
    renderPanel('approval');
  } catch (e) {
    if (statusEl) statusEl.innerHTML = `<div class="empty-state">ERROR: ${escHtml(e.message)}</div>`;
    if (appBtn) appBtn.disabled = false;
    if (rejBtn) rejBtn.disabled = false;
  }

  state.loading = false;
}

async function rejectDesign() {
  const feedback = document.getElementById('approval-feedback')?.value.trim() || '';
  if (!feedback) {
    toast('ADD FEEDBACK BEFORE REJECTING — TEACH THE APPROVAL AGENT.');
    return;
  }

  try {
    const payload = {
      approved: false,
      feedback,
      ...state.brief,
      ...state.design,
    };
    await fetch(`${API}/api/approval/decide`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
  } catch (_) {}

  state.design = null;
  toast('REJECTED + LOGGED — GENERATE A NEW DESIGN.');
  renderPanel('approval');
}

async function _runAutoApprove() {
  if (!state.design) return;
  const payload = { approved: true, ...state.brief, ...state.design };
  try {
    const res = await fetch(`${API}/api/approval/auto-decide`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    const data = await res.json();
    if (data.approved) {
      state.product = data.product;
      toast('⚡ AGENT APPROVED + PUBLISHED TO SHOPIFY');
    } else {
      state.design = null;
      toast('⚡ AGENT REJECTED — GENERATING NEW DESIGN...');
      if (state.autoDesign) setTimeout(() => runDesign(), 800);
    }
    if (state.activeRoom) renderPanel(state.activeRoom);
  } catch (e) {
    toast('AUTO-APPROVAL ERROR — CHECK LOGS');
  }
}

function resetPipeline() {
  state.brief = null;
  state.design = null;
  state.product = null;
  closePanel();
  if (state.autoResearch) {
    toast('PIPELINE RESET — AUTO-RUNNING RESEARCH...');
    setTimeout(() => runResearch(), 600);
  } else {
    toast('PIPELINE RESET — START WITH RESEARCH.');
  }
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

  // 4×4 grid of rooms; gx/gy are grid coords; built=false rooms are dark placeholders
  const ROOMS = [
    // Row 0
    { cx: 512,  cy: 512,  gx: 0, gy: 0, built: true  },  // CEO
    { cx: 1536, cy: 512,  gx: 1, gy: 0, built: true  },  // Research
    { cx: 2560, cy: 512,  gx: 2, gy: 0, built: true  },  // Design
    { cx: 3584, cy: 512,  gx: 3, gy: 0, built: true  },  // Factory
    // Row 1
    { cx: 512,  cy: 1536, gx: 0, gy: 1, built: true  },  // Approval
    { cx: 1536, cy: 1536, gx: 1, gy: 1, built: false },  // CS
    { cx: 2560, cy: 1536, gx: 2, gy: 1, built: false },  // Analytics
    { cx: 3584, cy: 1536, gx: 3, gy: 1, built: false },  // Pricing
    // Row 2
    { cx: 512,  cy: 2560, gx: 0, gy: 2, built: false },  // Shop Health
    { cx: 1536, cy: 2560, gx: 1, gy: 2, built: false },  // Media Bay
    { cx: 2560, cy: 2560, gx: 2, gy: 2, built: false },  // Monitoring
    { cx: 3584, cy: 2560, gx: 3, gy: 2, built: false },  // Radar Bay
    // Row 3
    { cx: 512,  cy: 3584, gx: 0, gy: 3, built: false },  // Armory
    { cx: 1536, cy: 3584, gx: 1, gy: 3, built: false },  // War Room
    { cx: 2560, cy: 3584, gx: 2, gy: 3, built: false },  // Memory Room
    { cx: 3584, cy: 3584, gx: 3, gy: 3, built: false },  // Treasury
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
            const others = ROOMS.filter(r => r !== c.home && r.built);
            if (others.length) startPath(c, others[Math.floor(Math.random() * others.length)]);
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
  const MAP_SIZE = 4096;

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

  const MIN_SCALE = 0.12;

  function fitToViewport() {
    const vw = viewport.clientWidth;
    const vh = viewport.clientHeight;
    // Auto-fit the full map into viewport with a small margin
    const fitScale = Math.min(vw, vh) / MAP_SIZE * 0.88;
    scale = Math.max(MIN_SCALE, Math.min(0.45, fitScale));
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
    const newScale   = Math.max(MIN_SCALE, Math.min(0.45, scale * zoomFactor));

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
