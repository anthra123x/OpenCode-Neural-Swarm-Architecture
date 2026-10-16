/**
 * OpenCode Swarm Telemetry & GetBrain Web Application
 * Pure Vanilla JavaScript (ES6+)
 * 
 * Architecture & Features:
 *   - Strict Read-Only Telemetry (Monitoreo Pasivo Cross-Sesion)
 *   - Unbreakable Connection Watchdog (SSE Stream + Failover Active Polling + Auto-Reconnect)
 *   - 5 Dedicated Observability Views (Cockpit, GetBrain, Sentinel, Tester, Learnings)
 *   - 2D Physics Canvas Engine for GetBrain Architectural Knowledge Graph
 *   - Zero emojis across all UI elements and logs
 */

// Application State
const urlParams = new URLSearchParams(window.location.search);
const initialProject = urlParams.get('project') || urlParams.get('p') || 'default';

const state = {
  currentView: 'cockpit',
  project: initialProject.trim(),
  branch: 'main',
  agents: [],
  tasks: [],
  messages: [],
  artifacts: [],
  memories: [],
  learnings: [],
  sentinel: { score: 100, rules: [], audits: [], violations: [] },
  tester: { health: 'HEALTHY', runs: [], probes: [], components: [] },
  brain: { nodes: [], links: [] },
  activeFilter: 'all', // kanban filter
  learningFilter: 'all', // learnings category filter
  learningSearch: '',
  brainFilters: {
    agent: true,
    task: true,
    artifact: true,
    memory: true,
    module: true
  },
  searchQuery: '',
  selectedNode: null
};

function getApiUrl(endpoint) {
  const sep = endpoint.includes('?') ? '&' : '?';
  const proj = state.project && state.project !== 'default' ? state.project : '';
  return proj ? `${endpoint}${sep}project=${encodeURIComponent(proj)}` : endpoint;
}

// ─────────────────────────────────────────────────────────────
// INITIALIZATION
// ─────────────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
  initConnectionWatchdog();
  fetchInitialData();
  initBrainCanvas();
  closeInspector();

  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') {
      closeInspector();
      closeTaskModal();
    }
  });

  // Check URL hash for direct tab navigation
  const hash = window.location.hash;
  if (hash === '#brain') switchView('brain');
  else if (hash === '#sentinel') switchView('sentinel');
  else if (hash === '#tester') switchView('tester');
  else if (hash === '#learnings') switchView('learnings');
});

// View Switcher (5 Views)
function switchView(viewName) {
  state.currentView = viewName;
  document.querySelectorAll('.view-panel').forEach(p => p.classList.remove('active'));
  document.querySelectorAll('.nav-tab').forEach(t => t.classList.remove('active'));

  const viewMap = {
    cockpit: { panel: 'viewCockpit', tab: 'tabCockpit', hash: '' },
    brain: { panel: 'viewBrain', tab: 'tabBrain', hash: '#brain' },
    sentinel: { panel: 'viewSentinel', tab: 'tabSentinel', hash: '#sentinel' },
    tester: { panel: 'viewTester', tab: 'tabTester', hash: '#tester' },
    learnings: { panel: 'viewLearnings', tab: 'tabLearnings', hash: '#learnings' }
  };

  const target = viewMap[viewName] || viewMap.cockpit;
  const panelEl = document.getElementById(target.panel);
  const tabEl = document.getElementById(target.tab);

  if (panelEl) panelEl.classList.add('active');
  if (tabEl) tabEl.classList.add('active');

  try {
    history.replaceState(null, null, target.hash ? target.hash : window.location.pathname);
  } catch (e) {}

  if (viewName === 'brain') {
    requestAnimationFrame(() => {
      resizeCanvas();
      if (state.brain && state.brain.nodes && state.brain.nodes.length > 0) {
        setupBrainSimulation(state.brain.nodes, state.brain.links);
      }
      setTimeout(fitGraphToView, 80);
    });
    fetchBrainGraph();
  } else if (viewName === 'sentinel') {
    fetchSentinelData();
  } else if (viewName === 'tester') {
    fetchTesterData();
  } else if (viewName === 'learnings') {
    fetchLearningsData();
  }
}

// ─────────────────────────────────────────────────────────────
// UNBREAKABLE CONNECTION WATCHDOG (SSE + FAILOVER POLLING)
// ─────────────────────────────────────────────────────────────
let evtSource = null;
let reconnectTimer = null;
let watchdogInterval = null;
let pollingInterval = null;
let reconnectDelay = 1000;
let lastHeartbeatTime = Date.now();
let isPollingActive = false;

function initConnectionWatchdog() {
  connectSSE();

  // Watchdog checks every 5 seconds if connection is dead/stalled
  if (watchdogInterval) clearInterval(watchdogInterval);
  watchdogInterval = setInterval(() => {
    const elapsed = Date.now() - lastHeartbeatTime;
    if (elapsed > 12000) {
      // No message or keepalive received for 12 seconds; force reconnect
      console.warn('[Watchdog] SSE connection stalled, reconnecting...');
      connectSSE();
    }
  }, 5000);
}

function updateConnectionStatus(mode, label, colorClass) {
  const pill = document.getElementById('connectionPill');
  const dot = document.getElementById('connPulseDot');
  const text = document.getElementById('liveStatusText');

  if (pill) {
    pill.classList.remove('sse-reconnecting', 'sse-failover');
    if (colorClass) pill.classList.add(colorClass);
  }

  if (dot) {
    if (mode === 'live') {
      dot.style.backgroundColor = 'var(--term-green)';
    } else if (mode === 'reconnecting') {
      dot.style.backgroundColor = 'var(--term-amber)';
    } else if (mode === 'failover') {
      dot.style.backgroundColor = 'var(--term-blue)';
    }
  }

  if (text) {
    text.textContent = label;
  }
}

function startFailoverPolling() {
  if (isPollingActive) return;
  isPollingActive = true;
  updateConnectionStatus('failover', 'FAILOVER: POLLING ACTIVO', 'sse-failover');

  if (pollingInterval) clearInterval(pollingInterval);
  pollingInterval = setInterval(async () => {
    try {
      await fetchInitialData();
    } catch (e) {
      console.error('[Failover Polling Error]', e);
    }
  }, 2500);
}

function stopFailoverPolling() {
  if (!isPollingActive) return;
  isPollingActive = false;
  if (pollingInterval) {
    clearInterval(pollingInterval);
    pollingInterval = null;
  }
}

function connectSSE() {
  if (evtSource) {
    try {
      evtSource.close();
    } catch (e) {}
    evtSource = null;
  }

  try {
    const streamUrl = getApiUrl('/api/stream');
    evtSource = new EventSource(streamUrl);

    evtSource.onopen = () => {
      lastHeartbeatTime = Date.now();
      reconnectDelay = 1000;
      stopFailoverPolling();
      updateConnectionStatus('live', 'SSE: LIVE', '');
    };

    evtSource.onmessage = (event) => {
      lastHeartbeatTime = Date.now();
      try {
        const data = jsonParseSafe(event.data);
        if (data) {
          updateSwarmUI(data);
        }
      } catch (err) {
        console.error('SSE data parse error:', err);
      }
    };

    evtSource.onerror = () => {
      lastHeartbeatTime = 0;
      startFailoverPolling();
      updateConnectionStatus('reconnecting', `RECONECTANDO (${Math.round(reconnectDelay / 1000)}s)`, 'sse-reconnecting');

      if (evtSource) {
        try { evtSource.close(); } catch (e) {}
        evtSource = null;
      }

      if (reconnectTimer) clearTimeout(reconnectTimer);
      reconnectTimer = setTimeout(() => {
        reconnectDelay = Math.min(reconnectDelay * 1.5, 8000);
        connectSSE();
      }, reconnectDelay);
    };
  } catch (e) {
    console.warn('SSE instantiation failed, falling back to polling');
    startFailoverPolling();
  }
}

// ─────────────────────────────────────────────────────────────
// DATA FETCHING & SYNCHRONIZATION (READ-ONLY)
// ─────────────────────────────────────────────────────────────
async function safeFetchJson(url, fallback = {}) {
  try {
    const res = await fetch(url);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return await res.json();
  } catch (e) {
    return fallback;
  }
}

async function fetchInitialData() {
  try {
    const [resStatus, resTasks, resFeed, resArtifacts, resMemories, resSentinel, resTester, resLearnings, resProjects] = await Promise.all([
      safeFetchJson(getApiUrl('/api/status')),
      safeFetchJson(getApiUrl('/api/tasks')),
      safeFetchJson(getApiUrl('/api/feed')),
      safeFetchJson(getApiUrl('/api/artifacts')),
      safeFetchJson(getApiUrl('/api/memories')),
      safeFetchJson(getApiUrl('/api/sentinel')),
      safeFetchJson(getApiUrl('/api/tester')),
      safeFetchJson(getApiUrl('/api/learnings')),
      safeFetchJson('/api/projects')
    ]);

    if (resStatus.project) {
      state.project = resStatus.project;
    }
    updateProjectDropdown(resProjects);

    updateSwarmUI({
      project: resStatus.project || state.project,
      project_dir: resStatus.project_dir,
      branch: resStatus.branch || state.branch,
      clock: resStatus.clock,
      agents: resStatus.agents || [],
      tasks: resTasks.tasks || [],
      messages: resFeed.feed || []
    });

    renderArtifacts(resArtifacts.artifacts || []);
    renderMemories(resMemories.memories || []);
    updateSentinelUI(resSentinel);
    updateTesterUI(resTester);
    updateLearningsUI(resLearnings);
    fetchBrainGraph();
  } catch (err) {
    console.error('Error fetching initial data:', err);
  }
}

function updateProjectDropdown(data) {
  const select = document.getElementById('projectSelect');
  if (!select) return;

  const projects = (data && data.projects) ? data.projects : [];
  const currentProj = state.project || (data ? data.current : 'default');

  let optionsHtml = '';
  let foundCurrent = false;

  projects.forEach(p => {
    const isSelected = p.name === currentProj;
    if (isSelected) foundCurrent = true;
    const taskBadge = p.tasks > 0 ? `(${p.tasks} tareas)` : '(0 tareas)';
    optionsHtml += `<option value="${escapeHtml(p.name)}" ${isSelected ? 'selected' : ''}>${escapeHtml(p.name)} ${taskBadge}</option>`;
  });

  if (!foundCurrent && currentProj && currentProj !== 'cargando...') {
    optionsHtml = `<option value="${escapeHtml(currentProj)}" selected>${escapeHtml(currentProj)} (actual)</option>` + optionsHtml;
  }

  select.innerHTML = optionsHtml;
}

function onProjectSelect(newProject) {
  if (!newProject || newProject === state.project) return;
  state.project = newProject;

  try {
    const hash = window.location.hash || '';
    const newUrl = `?project=${encodeURIComponent(newProject)}${hash}`;
    history.replaceState(null, null, newUrl);
  } catch (e) {}

  connectSSE();
  fetchInitialData();
}

async function fetchSentinelData() {
  const data = await safeFetchJson(getApiUrl('/api/sentinel'));
  updateSentinelUI(data);
}

async function fetchTesterData() {
  const data = await safeFetchJson(getApiUrl('/api/tester'));
  updateTesterUI(data);
}

async function fetchLearningsData() {
  const data = await safeFetchJson(getApiUrl('/api/learnings'));
  updateLearningsUI(data);
}

async function fetchBrainGraph() {
  try {
    const data = await safeFetchJson(getApiUrl('/api/brain'));
    state.brain = data;
    const countEl = document.getElementById('brainNodesCount');
    if (countEl) countEl.textContent = data.nodes ? data.nodes.length : 0;
    if (state.currentView === 'brain') {
      setupBrainSimulation(data.nodes, data.links);
    }
  } catch (e) {
    console.error('Error fetching brain graph:', e);
  }
}

// ─────────────────────────────────────────────────────────────
// SWARM TELEMETRY UI RENDERERS
// ─────────────────────────────────────────────────────────────
const ROSTER_CONFIG = {
  orchestrator: { glyph: 'SYS', color: '#8B5CF6', title: 'Lead Architect & Orchestrator' },
  backend:      { glyph: 'API', color: '#3B82F6', title: 'Backend Specialist & TDD' },
  frontend:     { glyph: 'UI',  color: '#EC4899', title: 'Frontend Specialist & Tokens' },
  'git-flow':   { glyph: 'GIT', color: '#10B981', title: 'GitFlow & Releases' },
  'qa-auditor': { glyph: 'QA',  color: '#F59E0B', title: 'Sentinel & QA Auditor' },
  devops:       { glyph: 'OPS', color: '#06B6D4', title: 'DevOps & Containers' }
};

function updateSwarmUI(data) {
  if (data.project) {
    state.project = data.project;
    const select = document.getElementById('projectSelect');
    if (select && select.value !== data.project) {
      select.value = data.project;
    }
    const el = document.getElementById('projectName');
    if (el) el.textContent = data.project;
    document.title = `OpenCode Swarm [${data.project}]`;
  }

  if (data.branch) {
    state.branch = data.branch;
    const el = document.getElementById('projectBranch');
    if (el) el.textContent = data.branch;
  }

  if (data.clock) {
    const el = document.getElementById('liveClock');
    if (el) el.textContent = data.clock;
  }

  if (data.agents) {
    state.agents = data.agents;
    renderAgents(data.agents);
  }

  if (data.tasks) {
    state.tasks = data.tasks;
    renderKanban(data.tasks);
  }

  if (data.messages) {
    state.messages = data.messages;
    renderFeed(data.messages);
  }
}

function renderAgents(agentsList) {
  const container = document.getElementById('agentsGrid');
  if (!container) return;

  const agentMap = {};
  agentsList.forEach(a => { agentMap[a.agent_name] = a; });

  let activeCount = 0;
  let html = '';

  Object.keys(ROSTER_CONFIG).forEach(role => {
    const cfg = ROSTER_CONFIG[role];
    const ag = agentMap[role] || {
      agent_name: role,
      status: 'idle',
      current_task: '',
      window_id: '',
      relative_time: 'esperando'
    };

    const isWorking = ag.status === 'working';
    if (isWorking) activeCount++;

    const statusClass = ag.status || 'idle';
    const statusLabel = isWorking ? 'WORKING' : (ag.status ? ag.status.toUpperCase() : 'IDLE');
    const windowTag = ag.window_id ? `<span class="window-tag">[win: ${escapeHtml(ag.window_id)}]</span>` : `<span class="window-tag">[session]</span>`;
    const taskSnippet = ag.current_task ? ag.current_task : 'Listo para asignacion de tareas en pipeline...';

    html += `
      <div class="agent-card" style="--agent-color: ${cfg.color};">
        <div class="agent-header">
          <div class="agent-id">
            <div class="agent-avatar">${cfg.glyph}</div>
            <div class="agent-name-title">
              <span class="agent-name">@${role}</span>
              <span class="agent-role">${cfg.title}</span>
            </div>
          </div>
          <span class="status-pill ${statusClass}">
            ${isWorking ? '<span class="pulse-dot"></span>' : ''}
            ${statusLabel}
          </span>
        </div>

        <div class="agent-task-box">
          <div class="task-label">Tarea / Hito Actual:</div>
          <div class="task-text">${escapeHtml(taskSnippet)}</div>
        </div>

        <div class="agent-footer">
          ${windowTag}
          <span>${ag.relative_time || 'reciente'}</span>
        </div>
      </div>
    `;
  });

  container.innerHTML = html;
  const aab = document.getElementById('activeAgentsBadge');
  if (aab) aab.textContent = `${activeCount} Agente(s) en Ejecucion`;
}

function renderKanban(tasksList) {
  const cols = {
    todo: document.getElementById('cardsTodo'),
    in_progress: document.getElementById('cardsInProgress'),
    review: document.getElementById('cardsReview'),
    completed: document.getElementById('cardsCompleted')
  };

  const counts = { todo: 0, in_progress: 0, review: 0, completed: 0 };
  const htmls = { todo: '', in_progress: '', review: '', completed: '' };

  tasksList.forEach(t => {
    let st = t.status || 'todo';
    if (!cols[st]) st = 'todo';
    counts[st]++;

    if (state.activeFilter !== 'all' && state.activeFilter !== st) return;

    const prio = (t.priority || 'normal').toLowerCase();
    const assigned = t.assigned_to ? `@${t.assigned_to}` : 'sin asignar';

    htmls[st] += `
      <div class="kanban-card prio-${prio}" onclick="inspectTask(${t.id})" title="Clic para inspeccionar detalles (solo lectura)">
        <div class="card-top">
          <span class="card-id">#${t.id}</span>
          <span class="card-prio prio-badge-${prio}">[${prio}]</span>
        </div>
        <div class="card-title-text">${escapeHtml(t.title)}</div>
        <div class="card-bottom">
          <span class="card-assignee">${escapeHtml(assigned)}</span>
          <span class="card-time">${t.relative_time || 'reciente'}</span>
        </div>
      </div>
    `;
  });

  Object.keys(cols).forEach(k => {
    if (cols[k]) {
      cols[k].innerHTML = htmls[k] || '<div class="empty-state">[ vacio ]</div>';
    }
  });

  const totalTasks = counts.todo + counts.in_progress + counts.review + counts.completed;
  if (totalTasks === 0 && cols.todo) {
    cols.todo.innerHTML = `
      <div class="empty-state" style="padding: 14px 10px; line-height: 1.5; text-align: left;">
        <div style="color: var(--term-blue); font-weight: 600; margin-bottom: 6px;">[ SESION ACTIVA: ${escapeHtml(state.project)} ]</div>
        <div style="color: var(--text-muted); font-size: 11px;">Esperando descomposicion de hitos desde terminal. Al procesar tareas con @orchestrator, apareceran en tiempo real en este tablero.</div>
        <div style="margin-top: 8px; font-size: 10px; color: var(--text-dim);">Puedes cambiar de proyecto en el selector superior para ver hitos de otras sesiones.</div>
      </div>
    `;
  }

  const countTodo = document.getElementById('countTodo');
  const countInProg = document.getElementById('countInProgress');
  const countRev = document.getElementById('countReview');
  const countComp = document.getElementById('countCompleted');

  if (countTodo) countTodo.textContent = counts.todo;
  if (countInProg) countInProg.textContent = counts.in_progress;
  if (countRev) countRev.textContent = counts.review;
  if (countComp) countComp.textContent = counts.completed;
}

function filterTasks(status) {
  state.activeFilter = status;
  document.querySelectorAll('#kanbanFilters .pill').forEach(p => {
    p.classList.toggle('active', p.textContent.trim().toLowerCase() === status);
  });
  renderKanban(state.tasks);
}

function renderFeed(messagesList) {
  const container = document.getElementById('feedStream');
  if (!container) return;

  if (!messagesList || messagesList.length === 0) {
    container.innerHTML = '<div class="feed-empty">[ sin eventos recientes en el bus ]</div>';
    return;
  }

  container.innerHTML = messagesList.map(m => {
    const cat = (m.category || 'announcement').toLowerCase();
    const prio = (m.priority || 'normal').toLowerCase();
    const isReactive = m.message && m.message.includes('REACTIVE TRIGGER');
    const isHandoff = cat === 'handoff';

    return `
      <div class="feed-entry ${isReactive ? 'feed-reactive' : ''} ${isHandoff ? 'feed-handoff' : ''}">
        <span class="feed-time">${escapeHtml(m.relative_time || 'ahora')}</span>
        <span class="feed-sender">@${escapeHtml(m.sender || 'system')}</span>
        <span class="feed-cat cat-${cat}">[${cat}]</span>
        <span class="feed-msg">${escapeHtml(m.message || '')}</span>
      </div>
    `;
  }).join('');
}

function renderArtifacts(artifactsList) {
  const container = document.getElementById('artifactsList');
  if (!container) return;

  const countBadge = document.getElementById('artifactsCountBadge');
  if (countBadge) countBadge.textContent = `${artifactsList.length} contratos`;

  if (!artifactsList || artifactsList.length === 0) {
    container.innerHTML = '<div class="empty-state">[ sin contratos publicados ]</div>';
    return;
  }

  container.innerHTML = artifactsList.map(art => {
    return `
      <div class="artifact-card">
        <div class="art-header">
          <div class="art-key">[SPEC] ${escapeHtml(art.artifact_key)} • por @${escapeHtml(art.creator)}</div>
          <span class="art-type">[${escapeHtml(art.artifact_type || 'contract')}]</span>
        </div>
        <div class="art-title">${escapeHtml(art.title)}</div>
        <pre class="art-snippet"><code>${escapeHtml(art.content || '')}</code></pre>
      </div>
    `;
  }).join('');
}

function renderMemories(memoriesList) {
  const container = document.getElementById('memoriesList');
  if (!container) return;

  const countBadge = document.getElementById('memoriesCountBadge');
  if (countBadge) countBadge.textContent = `${memoriesList.length} registros`;

  if (!memoriesList || memoriesList.length === 0) {
    container.innerHTML = '<div class="empty-state">[ sin recuerdos almacenados ]</div>';
    return;
  }

  container.innerHTML = memoriesList.map(m => {
    const isCheckpoint = m.key.includes('checkpoint') || (m.tags && m.tags.includes('checkpoint'));
    return `
      <div class="memory-card ${isCheckpoint ? 'memory-checkpoint' : ''}">
        <div class="mem-header">
          <span class="mem-key">${escapeHtml(m.key)}</span>
          <span class="mem-cat">[${escapeHtml(m.category || 'general')}]</span>
        </div>
        <div class="mem-content">${escapeHtml(m.content || '')}</div>
        <div class="mem-tags">${escapeHtml(m.tags || '')}</div>
      </div>
    `;
  }).join('');
}

// ─────────────────────────────────────────────────────────────
// SWARM SENTINEL COMPLIANCE UI (AUDITORIA CONTINUA)
// ─────────────────────────────────────────────────────────────
function updateSentinelUI(sentinel) {
  if (!sentinel) return;
  state.sentinel = sentinel;

  const score = sentinel.score !== undefined ? sentinel.score : 100;
  const status = sentinel.status || (score >= 80 ? 'COMPLIANT' : 'NON-COMPLIANT');

  const textEl = document.getElementById('sentinelStatusText');
  const pillEl = document.getElementById('sentinelPill');
  const heroBadge = document.getElementById('sentinelHeroBadge');
  const scoreBadge = document.getElementById('sentinelScoreBadge');

  if (textEl) textEl.textContent = `SENTINEL: ${status} (${score}%)`;
  if (scoreBadge) scoreBadge.textContent = `${score}%`;

  if (heroBadge) {
    heroBadge.textContent = `${score}% ${status}`;
    heroBadge.className = status === 'COMPLIANT' ? 'health-badge healthy' : 'health-badge failing';
  }

  if (pillEl) {
    if (status === 'COMPLIANT') {
      pillEl.style.background = 'rgba(63, 185, 80, 0.12)';
      pillEl.style.borderColor = 'rgba(63, 185, 80, 0.3)';
      pillEl.style.color = 'var(--term-green)';
    } else {
      pillEl.style.background = 'rgba(248, 81, 73, 0.12)';
      pillEl.style.borderColor = 'rgba(248, 81, 73, 0.3)';
      pillEl.style.color = 'var(--term-red)';
    }
  }

  const mScore = document.getElementById('mSentinelScore');
  if (mScore) {
    mScore.textContent = `${score}%`;
    mScore.className = status === 'COMPLIANT' ? 'm-val val-green' : 'm-val val-red';
  }

  const mRules = document.getElementById('mSentinelRulesCount');
  if (mRules) {
    mRules.textContent = `${sentinel.rules ? sentinel.rules.length : 7} ACTIVAS`;
  }

  const mAudits = document.getElementById('mSentinelAuditsCount');
  if (mAudits) {
    mAudits.textContent = `${sentinel.audits ? sentinel.audits.length : 0} REGISTRADAS`;
  }

  const mViolations = document.getElementById('mSentinelViolationsCount');
  if (mViolations) {
    const openCount = (sentinel.violations || []).filter(v => v.status === 'open').length;
    mViolations.textContent = `${openCount} DETECTADAS`;
    mViolations.className = openCount === 0 ? 'm-val val-green' : 'm-val val-red';
  }

  renderSentinelRulebook(sentinel.rules || []);
  renderSentinelAudits(sentinel.audits || []);
  renderSentinelViolations(sentinel.violations || []);
}

function renderSentinelRulebook(rules) {
  const container = document.getElementById('sentinelRulebookList');
  if (!container) return;

  if (!rules || rules.length === 0) {
    container.innerHTML = '<div class="empty-state">[ sin reglas registradas ]</div>';
    return;
  }

  const countEl = document.getElementById('rulesCountSub');
  if (countEl) countEl.textContent = `${rules.length} reglas`;

  container.innerHTML = rules.map(r => {
    const isCrit = r.severity === 'critical';
    return `
      <div class="rule-card" style="border-left: 2px solid ${isCrit ? 'var(--term-amber)' : 'var(--term-blue)'};">
        <div class="rule-card-header">
          <span class="rule-code" style="color: ${isCrit ? 'var(--term-amber)' : 'var(--term-blue)'}">[${escapeHtml(r.rule_code)}]</span>
          <span class="rule-title">${escapeHtml(r.title)}</span>
          <span class="rule-agent">@${escapeHtml(r.target_agent)}</span>
        </div>
        <div class="rule-desc">${escapeHtml(r.description)}</div>
      </div>
    `;
  }).join('');
}

function renderSentinelAudits(audits) {
  const container = document.getElementById('sentinelAuditsList');
  if (!container) return;

  const countBadge = document.getElementById('auditsListBadge');
  if (countBadge) countBadge.textContent = `${audits.length} auditorias`;

  if (!audits || audits.length === 0) {
    container.innerHTML = '<div class="empty-state">[ sin auditorias registradas en esta sesion ]</div>';
    return;
  }

  container.innerHTML = audits.map(a => {
    const isPass = a.verdict === 'APPROVED';
    return `
      <div class="test-run-item" style="border-left: 3px solid ${isPass ? 'var(--term-green)' : 'var(--term-red)'};">
        <div class="run-header">
          <span class="run-target">[AUDIT] ${escapeHtml(a.task_title)} (@${escapeHtml(a.agent_name)})</span>
          <span class="run-status ${isPass ? 'pass' : 'fail'}">${isPass ? '[APPROVED]' : '[REJECTED]'}</span>
        </div>
        <div class="run-stats">
          <span>Puntuacion: <strong>${a.score}/100</strong></span>
          <span>Fecha: ${escapeHtml(a.created_at ? a.created_at.split('T')[1].split('.')[0] : 'reciente')}</span>
        </div>
        ${a.feedback ? `<pre class="run-error"><code>${escapeHtml(a.feedback)}</code></pre>` : ''}
      </div>
    `;
  }).join('');
}

function renderSentinelViolations(violations) {
  const container = document.getElementById('sentinelViolationsList');
  if (!container) return;

  const openViolations = (violations || []).filter(v => v.status === 'open');
  if (openViolations.length === 0) {
    container.innerHTML = '<div class="empty-state">[ sin infracciones abiertas // calidad verificada ]</div>';
    return;
  }

  container.innerHTML = openViolations.map(v => {
    return `
      <div class="endpoint-item" style="border-left: 2px solid var(--term-red);">
        <div>
          <span style="font-weight: 700; color: var(--term-red);">[${escapeHtml(v.rule_code)}]</span>
          <span style="color: var(--text-muted); font-size: 11px;">@${escapeHtml(v.agent_name)}</span>
          <div style="font-size: 11px; margin-top: 2px;">${escapeHtml(v.details)}</div>
        </div>
        <span class="probe-status fail">[${escapeHtml(v.severity.toUpperCase())}]</span>
      </div>
    `;
  }).join('');
}

// ─────────────────────────────────────────────────────────────
// SWARM TESTER TELEMETRY UI
// ─────────────────────────────────────────────────────────────
function updateTesterUI(tester) {
  if (!tester) return;
  state.tester = tester;

  const health = tester.health || 'MONITORING';
  const badgeEl = document.getElementById('testerHealthBadge');
  const pillText = document.getElementById('testerStatusText');

  if (badgeEl) {
    badgeEl.textContent = health;
    badgeEl.className = `health-badge ${health.toLowerCase()}`;
  }

  if (pillText) {
    pillText.textContent = `TESTS: ${health}`;
  }

  const runnerBadge = document.getElementById('testRunnerBadge');
  const mValRunner = document.getElementById('mValRunner');
  const runner = tester.detected_runner || 'auto';
  if (runnerBadge) runnerBadge.textContent = `runner: ${runner}`;
  if (mValRunner) mValRunner.textContent = runner.toUpperCase();

  const runs = tester.runs || [];
  const countPass = runs.filter(r => r.status === 'PASS').length;
  const passCounter = document.getElementById('testPassCount');
  if (passCounter) passCounter.textContent = `${countPass}/${runs.length}`;

  const mValAssertions = document.getElementById('mValAssertions');
  const mSubAssertions = document.getElementById('mSubAssertions');
  if (runs.length > 0) {
    const latest = runs[0];
    const isPass = latest.status === 'PASS';
    if (mValAssertions) {
      mValAssertions.textContent = isPass ? '100% GREEN' : 'TESTS FAILING';
      mValAssertions.className = isPass ? 'm-val val-green' : 'm-val val-red';
    }
    if (mSubAssertions) {
      mSubAssertions.textContent = `${latest.passed || 0} pasados, ${latest.failed || 0} fallados (${latest.coverage_percent || 0}% cov)`;
    }
  }

  renderTestRuns(runs);
  renderEndpointProbes(tester.probes || []);
  renderComponentChecks(tester.components || []);
}

function renderTestRuns(runs) {
  const container = document.getElementById('testRunsList');
  if (!container) return;

  if (!runs || runs.length === 0) {
    container.innerHTML = '<div class="empty-state">[ sin ejecuciones de pruebas registradas ]</div>';
    return;
  }

  container.innerHTML = runs.map(r => {
    const isPass = r.status === 'PASS';
    return `
      <div class="test-run-item">
        <div class="run-header">
          <span class="run-target">${escapeHtml(r.target_path || 'Suite Principal')}</span>
          <span class="run-status ${isPass ? 'pass' : 'fail'}">[${r.status}]</span>
        </div>
        <div class="run-stats">
          <span>${r.passed || 0} pasados</span>
          <span>${r.failed || 0} fallados</span>
          <span>${r.skipped || 0} omitidos</span>
          <span>${r.duration_ms || 0}ms</span>
          <span>${r.coverage_percent || 0}% cov</span>
        </div>
      </div>
    `;
  }).join('');
}

function renderEndpointProbes(probes) {
  const container = document.getElementById('endpointProbesList');
  if (!container) return;

  if (!probes || probes.length === 0) {
    container.innerHTML = '<div class="empty-state">[ sin sondeos recientes ]</div>';
    return;
  }

  container.innerHTML = probes.map(p => {
    const isPass = p.status === 'PASS';
    return `
      <div class="endpoint-item">
        <div>
          <span class="probe-method">[${escapeHtml(p.method)}]</span>
          <span class="probe-url">${escapeHtml(p.url)}</span>
          <span class="probe-code">${p.actual_status || p.expected_status || 200}</span>
        </div>
        <div style="display: flex; align-items: center; gap: 8px;">
          <span class="probe-latency">${p.latency_ms || 0}ms</span>
          <span class="probe-status ${isPass ? 'pass' : 'fail'}">[${p.status}]</span>
        </div>
      </div>
    `;
  }).join('');
}

function renderComponentChecks(components) {
  const container = document.getElementById('componentChecksList');
  if (!container) return;

  if (!components || components.length === 0) {
    container.innerHTML = '<div class="empty-state">[ sin verificaciones de componentes ]</div>';
    return;
  }

  container.innerHTML = components.map(c => {
    const isPass = c.status === 'PASS';
    return `
      <div class="endpoint-item">
        <div>
          <span class="probe-method">[${escapeHtml(c.check_type || 'check')}]</span>
          <span class="probe-url">${escapeHtml(c.file_path)}</span>
          ${c.details ? `<div style="font-size: 10px; color: var(--text-dim); margin-top: 2px;">${escapeHtml(c.details)}</div>` : ''}
        </div>
        <div style="display: flex; align-items: center; gap: 8px;">
          <span class="probe-latency">${c.duration_ms || 0}ms</span>
          <span class="probe-status ${isPass ? 'pass' : 'fail'}">[${c.status}]</span>
        </div>
      </div>
    `;
  }).join('');
}

// ─────────────────────────────────────────────────────────────
// CONTINUOUS LEARNINGS & FEEDBACK LOOP ARCHIVE UI
// ─────────────────────────────────────────────────────────────
function updateLearningsUI(data) {
  const learnings = data.learnings || [];
  state.learnings = learnings;

  const countBadge = document.getElementById('learningsCountBadge');
  const totalBadge = document.getElementById('learningsTotalBadge');

  if (countBadge) countBadge.textContent = learnings.length;
  if (totalBadge) totalBadge.textContent = `${learnings.length} INSTINTOS`;

  renderLearnings(learnings);
}

function filterLearnings(category) {
  state.learningFilter = category;
  document.querySelectorAll('#learningsCategoryFilters .pill').forEach(p => {
    p.classList.toggle('active', p.textContent.trim().toLowerCase() === category);
  });
  renderLearnings(state.learnings);
}

function onSearchLearnings(val) {
  state.learningSearch = val.toLowerCase().trim();
  renderLearnings(state.learnings);
}

function renderLearnings(learningsList) {
  const container = document.getElementById('learningsContainer');
  if (!container) return;

  let filtered = learningsList;
  if (state.learningFilter !== 'all') {
    filtered = filtered.filter(l => (l.category || '').toLowerCase() === state.learningFilter);
  }

  if (state.learningSearch) {
    filtered = filtered.filter(l => 
      (l.content || '').toLowerCase().includes(state.learningSearch) ||
      (l.key || '').toLowerCase().includes(state.learningSearch) ||
      (l.tags || '').toLowerCase().includes(state.learningSearch)
    );
  }

  if (!filtered || filtered.length === 0) {
    container.innerHTML = '<div class="empty-state">[ sin aprendizajes que coincidan con el filtro ]</div>';
    return;
  }

  container.innerHTML = filtered.map(l => {
    const cat = (l.category || 'gotcha').toLowerCase();
    const content = l.content || '';
    
    // Attempt parsing structured lesson fields
    let lesson = content;
    let trigger = '';
    let solution = '';

    if (content.includes('**Lesson**:')) {
      const parts = content.split('|');
      parts.forEach(p => {
        const trimmed = p.trim();
        if (trimmed.startsWith('**Lesson**:')) lesson = trimmed.replace('**Lesson**:', '').trim();
        else if (trimmed.startsWith('**Trigger**:')) trigger = trimmed.replace('**Trigger**:', '').trim();
        else if (trimmed.startsWith('**Solution/Rule**:')) solution = trimmed.replace('**Solution/Rule**:', '').trim();
      });
    }

    return `
      <div class="learning-card">
        <div class="learning-card-header">
          <span class="learning-category-badge cat-${cat}">[${cat}]</span>
          <span class="learning-agent-tag">${escapeHtml(l.key)}</span>
        </div>

        <div class="learning-lesson-title">${escapeHtml(lesson)}</div>

        ${trigger ? `
          <div class="learning-trigger-box">
            <label>CONTEXTO / DISPARADOR:</label>
            ${escapeHtml(trigger)}
          </div>
        ` : ''}

        ${solution ? `
          <div class="learning-solution-box">
            <label>SOLUCION / REGLA APRENDIDA:</label>
            ${escapeHtml(solution)}
          </div>
        ` : ''}

        <div class="learning-tags-footer">
          <span>Tags: ${escapeHtml(l.tags || 'none')}</span>
          <span>${l.updated_at ? l.updated_at.split('T')[0] : 'sesion'}</span>
        </div>
      </div>
    `;
  }).join('');
}

// ─────────────────────────────────────────────────────────────
// READ-ONLY TASK INSPECTION MODAL
// ─────────────────────────────────────────────────────────────
function inspectTask(id) {
  const task = state.tasks.find(t => t.id === id);
  if (!task) return;

  const modal = document.getElementById('taskModal');
  const badge = document.getElementById('modalTaskBadge');
  const title = document.getElementById('modalTaskTitle');
  const meta = document.getElementById('modalTaskMeta');
  const desc = document.getElementById('modalTaskDesc');
  const notes = document.getElementById('modalTaskNotes');

  if (badge) badge.textContent = `TAREA #${task.id} [${(task.status || 'TODO').toUpperCase()}]`;
  if (title) title.textContent = task.title;

  if (meta) {
    meta.innerHTML = `
      <span>Asignado a: <strong>@${escapeHtml(task.assigned_to || 'sin asignar')}</strong></span>
      <span>•</span>
      <span>Prioridad: <strong>[${escapeHtml(task.priority || 'normal')}]</strong></span>
      <span>•</span>
      <span>Actualizado: <strong>${escapeHtml(task.relative_time || 'reciente')}</strong></span>
    `;
  }

  if (desc) desc.textContent = task.description || '[sin descripcion detallada]';
  if (notes) notes.textContent = task.notes || '[sin notas de ejecucion registradas]';

  if (modal) modal.style.display = 'flex';
}

function closeTaskModal() {
  const modal = document.getElementById('taskModal');
  if (modal) modal.style.display = 'none';
}

// ─────────────────────────────────────────────────────────────
// GETBRAIN 2D PHYSICS KNOWLEDGE GRAPH (SUPERVISION PURA)
// ─────────────────────────────────────────────────────────────
let canvas, ctx;
let graphNodes = [];
let graphLinks = [];
let animFrameId = null;
let transform = { x: 0, y: 0, k: 1 };
let isDragging = false;
let draggedNode = null;
let hoveredNode = null;
let dragStart = { x: 0, y: 0 };
let simRunning = true;
let simAlpha = 1.0;

function initBrainCanvas() {
  canvas = document.getElementById('brainCanvas');
  if (!canvas) return;
  ctx = canvas.getContext('2d');

  window.addEventListener('resize', () => {
    resizeCanvas();
    if (state.currentView === 'brain') {
      drawGraph();
    }
  });
  resizeCanvas();

  canvas.addEventListener('mousedown', onMouseDown);
  canvas.addEventListener('mousemove', onMouseMove);
  canvas.addEventListener('mouseup', onMouseUp);
  canvas.addEventListener('wheel', onWheel, { passive: false });

  // Touch support for mobile / responsive
  canvas.addEventListener('touchstart', onTouchStart, { passive: false });
  canvas.addEventListener('touchmove', onTouchMove, { passive: false });
  canvas.addEventListener('touchend', onTouchEnd);
}

function resizeCanvas() {
  const container = document.getElementById('canvasContainer');
  if (!container || !canvas) return;
  const dpr = Math.min(window.devicePixelRatio || 1, 2);
  const width = container.clientWidth || 900;
  const height = container.clientHeight || 580;
  if (width === 0 || height === 0) return;

  canvas.width = Math.round(width * dpr);
  canvas.height = Math.round(height * dpr);
  canvas.style.width = width + 'px';
  canvas.style.height = height + 'px';
}

function setupBrainSimulation(nodes, links) {
  if (!nodes || nodes.length === 0) return;

  resizeCanvas();
  const container = document.getElementById('canvasContainer');
  const width = (container ? container.clientWidth : 0) || 900;
  const height = (container ? container.clientHeight : 0) || 580;
  const cx = width / 2;
  const cy = height / 2;

  const existingPos = {};
  graphNodes.forEach(n => {
    if (Number.isFinite(n.x) && Number.isFinite(n.y)) {
      existingPos[n.id] = { x: n.x, y: n.y, vx: n.vx, vy: n.vy };
    }
  });

  const typeAngles = {
    hub: 0,
    agent: Math.PI / 4,
    task: Math.PI / 2,
    artifact: (3 * Math.PI) / 4,
    memory: Math.PI,
    module: (5 * Math.PI) / 4
  };

  graphNodes = nodes.map((n, i) => {
    const prev = existingPos[n.id];
    const baseAngle = typeAngles[n.type] !== undefined ? typeAngles[n.type] : (i / nodes.length) * Math.PI * 2;
    const jitter = ((i * 37) % 100) / 100 - 0.5;
    const radius = n.type === 'hub' ? 0 : (n.type === 'agent' ? 140 : 200 + ((i * 23) % 180));
    const initX = cx + Math.cos(baseAngle + jitter) * radius;
    const initY = cy + Math.sin(baseAngle + jitter) * radius;

    return {
      ...n,
      x: prev ? prev.x : initX,
      y: prev ? prev.y : initY,
      vx: 0,
      vy: 0,
      radius: n.type === 'hub' ? 26 : (n.type === 'agent' ? 20 : 15)
    };
  });

  const nodeMap = {};
  graphNodes.forEach(n => { nodeMap[n.id] = n; });

  graphLinks = (links || []).map(l => ({
    ...l,
    sourceNode: nodeMap[l.source],
    targetNode: nodeMap[l.target]
  })).filter(l => l.sourceNode && l.targetNode);

  simAlpha = 1.0;
  simRunning = true;

  setTimeout(fitGraphToView, 60);

  if (!animFrameId) {
    animFrameId = requestAnimationFrame(renderLoop);
  }
}

function renderLoop() {
  if (state.currentView === 'brain') {
    if (simRunning && simAlpha > 0.005) {
      updatePhysics();
    }
    drawGraph();
  }
  animFrameId = requestAnimationFrame(renderLoop);
}

function updatePhysics() {
  if (!simRunning || simAlpha < 0.005) return;

  const container = document.getElementById('canvasContainer');
  const width = (container ? container.clientWidth : 0) || 900;
  const height = (container ? container.clientHeight : 0) || 580;
  const cx = width / 2;
  const cy = height / 2;

  const kRepulsion = 2200;
  const kSpring = 0.025;
  const targetDist = 80;
  const damping = 0.82;
  const centerGravity = 0.008;

  // Repulsion between nodes
  for (let i = 0; i < graphNodes.length; i++) {
    const a = graphNodes[i];
    if (!isNodeVisible(a)) continue;

    for (let j = i + 1; j < graphNodes.length; j++) {
      const b = graphNodes[j];
      if (!isNodeVisible(b)) continue;

      const dx = b.x - a.x;
      const dy = b.y - a.y;
      const dist = Math.sqrt(dx * dx + dy * dy) || 1;

      if (dist < 320) {
        const eff = Math.max(28.0, dist);
        const force = (kRepulsion / (eff * eff)) * simAlpha;
        const fx = (dx / dist) * force;
        const fy = (dy / dist) * force;

        if (a !== draggedNode) { a.vx -= fx; a.vy -= fy; }
        if (b !== draggedNode) { b.vx += fx; b.vy += fy; }
      }
    }
  }

  // Springs along links
  for (let i = 0; i < graphLinks.length; i++) {
    const link = graphLinks[i];
    const a = link.sourceNode;
    const b = link.targetNode;
    if (!isNodeVisible(a) || !isNodeVisible(b)) continue;

    const dx = b.x - a.x;
    const dy = b.y - a.y;
    const dist = Math.sqrt(dx * dx + dy * dy) || 1;
    const disp = Math.max(-100.0, Math.min(100.0, dist - targetDist));
    const force = disp * kSpring * simAlpha;

    const fx = (dx / dist) * force;
    const fy = (dy / dist) * force;

    if (a !== draggedNode) { a.vx -= fx; a.vy -= fy; }
    if (b !== draggedNode) { b.vx += fx; b.vy += fy; }
  }

  // Center gravity and velocity clamp
  const maxV = 8.0 * simAlpha;
  for (let i = 0; i < graphNodes.length; i++) {
    const n = graphNodes[i];
    if (n === draggedNode) continue;

    n.vx += (cx - n.x) * centerGravity * simAlpha;
    n.vy += (cy - n.y) * centerGravity * simAlpha;

    n.vx *= damping;
    n.vy *= damping;

    n.vx = Math.max(-maxV, Math.min(maxV, n.vx));
    n.vy = Math.max(-maxV, Math.min(maxV, n.vy));

    n.x += n.vx;
    n.y += n.vy;
  }

  simAlpha *= 0.985;
  if (simAlpha < 0.005) {
    simAlpha = 0;
  }
}

function isNodeVisible(n) {
  if (n.type === 'hub') return true;
  if (!state.brainFilters[n.type]) return false;
  return true;
}

function drawGraph() {
  if (!canvas || !ctx) return;
  const dpr = Math.min(window.devicePixelRatio || 1, 2);

  ctx.save();
  ctx.clearRect(0, 0, canvas.width, canvas.height);
  ctx.scale(dpr, dpr);
  ctx.translate(transform.x, transform.y);
  ctx.scale(transform.k, transform.k);

  // Links
  for (let i = 0; i < graphLinks.length; i++) {
    const link = graphLinks[i];
    const a = link.sourceNode;
    const b = link.targetNode;
    if (!isNodeVisible(a) || !isNodeVisible(b)) continue;

    ctx.beginPath();
    ctx.moveTo(a.x, a.y);
    ctx.lineTo(b.x, b.y);

    const isHovered = (hoveredNode && (hoveredNode === a || hoveredNode === b));
    const isSelected = (state.selectedNode && (state.selectedNode === a || state.selectedNode === b));

    if (isSelected || isHovered) {
      ctx.strokeStyle = '#58a6ff';
      ctx.lineWidth = 1.5;
    } else {
      ctx.strokeStyle = '#1e2633';
      ctx.lineWidth = 1;
    }
    ctx.stroke();
  }

  // Nodes
  for (let i = 0; i < graphNodes.length; i++) {
    const n = graphNodes[i];
    if (!isNodeVisible(n)) continue;

    const isSelected = (state.selectedNode === n);
    const radius = n.radius;

    // Body
    ctx.beginPath();
    ctx.arc(n.x, n.y, radius, 0, Math.PI * 2);
    ctx.fillStyle = '#090d13';
    ctx.fill();
    ctx.strokeStyle = isSelected ? '#58a6ff' : (n.color || '#30363d');
    ctx.lineWidth = isSelected ? 2.5 : 1.5;
    ctx.stroke();

    // Text Glyphs inside node (zero emojis)
    let glyphText = 'MOD';
    if (n.type === 'hub') glyphText = 'HUB';
    else if (n.type === 'agent') glyphText = (n.extra && n.extra.glyph) ? n.extra.glyph : 'AGT';
    else if (n.type === 'task') glyphText = 'TSK';
    else if (n.type === 'artifact') glyphText = 'SPEC';
    else if (n.type === 'memory') glyphText = n.category === 'checkpoint' ? 'CHK' : (n.category === 'learning' ? 'LRN' : 'MEM');

    ctx.font = `700 ${Math.round(radius * 0.45)}px "JetBrains Mono", monospace`;
    ctx.fillStyle = n.color || '#58a6ff';
    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';
    ctx.fillText(glyphText, n.x, n.y);

    // Label
    ctx.font = `${isSelected ? '700 11px' : '500 10px'} "JetBrains Mono", monospace`;
    ctx.fillStyle = isSelected ? '#f0f6fc' : '#8b949e';
    ctx.fillText(n.label, n.x, n.y + radius + 13);
  }

  ctx.restore();
}

function fitGraphToView() {
  const visibleNodes = graphNodes.filter(isNodeVisible);
  if (visibleNodes.length === 0) return;

  const container = document.getElementById('canvasContainer');
  const width = (container ? container.clientWidth : 0) || 900;
  const height = (container ? container.clientHeight : 0) || 580;

  let minX = Infinity, maxX = -Infinity, minY = Infinity, maxY = -Infinity;
  for (const n of visibleNodes) {
    if (n.x < minX) minX = n.x;
    if (n.x > maxX) maxX = n.x;
    if (n.y < minY) minY = n.y;
    if (n.y > maxY) maxY = n.y;
  }

  const graphWidth = Math.max((maxX - minX) + 140, 200);
  const graphHeight = Math.max((maxY - minY) + 140, 200);
  const graphCenterX = (minX + maxX) / 2;
  const graphCenterY = (minY + maxY) / 2;

  const scaleX = width / graphWidth;
  const scaleY = height / graphHeight;
  const k = Math.min(Math.max(Math.min(scaleX, scaleY) * 0.88, 0.25), 1.6);

  transform.k = k;
  transform.x = width / 2 - graphCenterX * k;
  transform.y = height / 2 - graphCenterY * k;
  drawGraph();
}

function zoomBrain(factor) {
  const container = document.getElementById('canvasContainer');
  const width = (container ? container.clientWidth : 0) || 900;
  const height = (container ? container.clientHeight : 0) || 580;
  const cx = width / 2;
  const cy = height / 2;

  const newK = Math.min(Math.max(transform.k * factor, 0.15), 3.5);
  transform.x = cx - (cx - transform.x) * (newK / transform.k);
  transform.y = cy - (cy - transform.y) * (newK / transform.k);
  transform.k = newK;
  drawGraph();
}

function toggleSimPhysics() {
  simRunning = !simRunning;
  if (simRunning) {
    simAlpha = 0.5;
  }
  const btn = document.getElementById('btnToggleSim');
  if (btn) btn.textContent = simRunning ? '[pausar]' : '[reanudar]';
  drawGraph();
}

// ─────────────────────────────────────────────────────────────
// CANVAS INTERACTION (PAN, ZOOM, DRAG, INSPECT)
// ─────────────────────────────────────────────────────────────
function getMouseGraphPos(e) {
  const rect = canvas.getBoundingClientRect();
  const screenX = e.clientX - rect.left;
  const screenY = e.clientY - rect.top;
  return {
    screenX,
    screenY,
    x: (screenX - transform.x) / transform.k,
    y: (screenY - transform.y) / transform.k
  };
}

function findNodeAt(x, y) {
  for (let i = graphNodes.length - 1; i >= 0; i--) {
    const n = graphNodes[i];
    if (!isNodeVisible(n)) continue;
    const dx = n.x - x;
    const dy = n.y - y;
    if (dx * dx + dy * dy <= n.radius * n.radius * 1.6) {
      return n;
    }
  }
  return null;
}

function onMouseDown(e) {
  const pos = getMouseGraphPos(e);
  const hit = findNodeAt(pos.x, pos.y);

  if (hit) {
    draggedNode = hit;
    state.selectedNode = hit;
    inspectNode(hit);
    simAlpha = Math.max(simAlpha, 0.3);
  } else {
    isDragging = true;
    dragStart = { x: pos.screenX - transform.x, y: pos.screenY - transform.y };
  }
}

function onMouseMove(e) {
  const pos = getMouseGraphPos(e);

  if (draggedNode) {
    draggedNode.x = pos.x;
    draggedNode.y = pos.y;
    draggedNode.vx = 0;
    draggedNode.vy = 0;
    simAlpha = Math.max(simAlpha, 0.2);
    return;
  }

  if (isDragging) {
    transform.x = pos.screenX - dragStart.x;
    transform.y = pos.screenY - dragStart.y;
    return;
  }

  const hit = findNodeAt(pos.x, pos.y);
  hoveredNode = hit;
  canvas.style.cursor = hit ? 'pointer' : (isDragging ? 'grabbing' : 'grab');
}

function onMouseUp() {
  isDragging = false;
  draggedNode = null;
  canvas.style.cursor = 'grab';
}

function onWheel(e) {
  e.preventDefault();
  const zoomFactor = 1.1;
  const pos = getMouseGraphPos(e);

  const newK = e.deltaY < 0 ? transform.k * zoomFactor : transform.k / zoomFactor;
  if (newK < 0.15 || newK > 4.0) return;

  transform.x = pos.screenX - pos.x * newK;
  transform.y = pos.screenY - pos.y * newK;
  transform.k = newK;
  drawGraph();
}

function onTouchStart(e) {
  if (e.touches.length === 1) {
    const t = e.touches[0];
    const pos = getMouseGraphPos(t);
    const hit = findNodeAt(pos.x, pos.y);
    if (hit) {
      draggedNode = hit;
      state.selectedNode = hit;
      inspectNode(hit);
      simAlpha = Math.max(simAlpha, 0.3);
    } else {
      isDragging = true;
      dragStart = { x: pos.screenX - transform.x, y: pos.screenY - transform.y };
    }
    e.preventDefault();
  }
}

function onTouchMove(e) {
  if (e.touches.length === 1) {
    const t = e.touches[0];
    const pos = getMouseGraphPos(t);
    if (draggedNode) {
      draggedNode.x = pos.x;
      draggedNode.y = pos.y;
      simAlpha = Math.max(simAlpha, 0.2);
    } else if (isDragging) {
      transform.x = pos.screenX - dragStart.x;
      transform.y = pos.screenY - dragStart.y;
    }
    e.preventDefault();
  }
}

function onTouchEnd() {
  isDragging = false;
  draggedNode = null;
}

function toggleFilter(type) {
  state.brainFilters[type] = !state.brainFilters[type];
  const btn = document.querySelector(`.filter-btn[data-type="${type}"]`);
  if (btn) btn.classList.toggle('active', state.brainFilters[type]);
  simAlpha = Math.max(simAlpha, 0.4);
  simRunning = true;
  drawGraph();
}

function inspectNode(node) {
  const panel = document.getElementById('nodeInspector');
  if (!panel) return;

  const badge = document.getElementById('inspBadge');
  const title = document.getElementById('inspTitle');
  const meta = document.getElementById('inspMeta');
  const content = document.getElementById('inspContent');
  const conn = document.getElementById('inspConnections');

  if (badge) badge.textContent = `[${node.type.toUpperCase()}]`;
  if (title) title.textContent = node.label;

  if (meta) {
    meta.innerHTML = `
      <span>Categoria: <strong>${escapeHtml(node.category || 'general')}</strong></span>
      <span>•</span>
      <span>ID: <code>${escapeHtml(node.id)}</code></span>
    `;
  }

  if (content) {
    content.textContent = node.details || '[sin detalles adicionales]';
  }

  if (conn) {
    const linked = graphLinks.filter(l => l.sourceNode === node || l.targetNode === node);
    conn.innerHTML = linked.map(l => {
      const other = l.sourceNode === node ? l.targetNode : l.sourceNode;
      return `<span class="conn-tag" onclick="selectNodeById('${other.id}')">[${other.type}] ${escapeHtml(other.label)}</span>`;
    }).join(' ') || '<span style="color: var(--text-dim);">sin enlaces directos</span>';
  }

  panel.style.display = 'flex';
}

function selectNodeById(id) {
  const node = graphNodes.find(n => n.id === id);
  if (node) {
    state.selectedNode = node;
    inspectNode(node);
  }
}

function closeInspector() {
  const panel = document.getElementById('nodeInspector');
  if (panel) panel.style.display = 'none';
  state.selectedNode = null;
}

// ─────────────────────────────────────────────────────────────
// UTILITIES
// ─────────────────────────────────────────────────────────────
function escapeHtml(str) {
  if (str === null || str === undefined) return '';
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#039;');
}

function jsonParseSafe(str) {
  try {
    return JSON.parse(str);
  } catch (e) {
    return null;
  }
}
