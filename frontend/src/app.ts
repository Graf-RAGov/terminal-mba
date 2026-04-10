// ── TerminalMBA Frontend ──────────────────────────────────────────
// Vanilla TypeScript, no frameworks.

// ── Types ─────────────────────────────────────────────────────

interface Session {
  id: string;
  tool: string;
  project: string;
  project_short: string;
  first_ts: number;
  last_ts: number;
  messages: number;
  first_message: string;
  has_detail: boolean;
  file_size: number;
  detail_messages: number;
  first_time: string;
  last_time: string;
  date: string;
  git_root: string;
  host?: string;
  remote?: boolean;
}

interface ActiveInfo {
  status: string;
  cpu: number;
  memoryMB: number;
  pid: number;
}

// ── State ─────────────────────────────────────────────────────

let allSessions: Session[] = [];
let filteredSessions: Session[] = [];
let currentView = "sessions";
let layout = localStorage.getItem("terminalmba-layout") || "grid";
let searchQuery = "";
let toolFilter: string | null = null;
let hostFilter: string | null = null;
let activeSessions: Record<string, ActiveInfo> = {};
let stars: string[] = JSON.parse(localStorage.getItem("terminalmba-stars") || "[]");
let tags: Record<string, string[]> = JSON.parse(localStorage.getItem("terminalmba-tags") || "{}");
let renderLimit = 60;
const RENDER_PAGE_SIZE = 60;

// ── Color palette ─────────────────────────────────────────────

const PROJECT_COLORS = [
  "#6366f1", "#8b5cf6", "#a855f7", "#d946ef", "#ec4899",
  "#f43f5e", "#ef4444", "#f97316", "#eab308", "#84cc16",
  "#22c55e", "#14b8a6", "#06b6d4", "#3b82f6", "#2563eb",
];
const projectColorMap: Record<string, string> = {};
let colorIdx = 0;

function getProjectColor(project: string): string {
  if (!project) return "#6b7280";
  if (!projectColorMap[project]) {
    projectColorMap[project] = PROJECT_COLORS[colorIdx % PROJECT_COLORS.length];
    colorIdx++;
  }
  return projectColorMap[project];
}

function getProjectName(fullPath: string): string {
  if (!fullPath) return "unknown";
  const parts = fullPath.replace(/\/+$/, "").split("/");
  return parts[parts.length - 1] || "unknown";
}

// ── Utilities ─────────────────────────────────────────────────

function timeAgo(ts: number): string {
  if (!ts) return "";
  const now = Date.now();
  const diff = now - (ts > 1e12 ? ts : ts * 1000);
  const mins = Math.floor(diff / 60000);
  if (mins < 1) return "just now";
  if (mins < 60) return mins + "m ago";
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return hrs + "h ago";
  const days = Math.floor(hrs / 24);
  if (days < 30) return days + "d ago";
  const months = Math.floor(days / 30);
  if (months < 12) return months + "mo ago";
  return Math.floor(months / 12) + "y ago";
}

function escHtml(s: string): string {
  if (!s) return "";
  return s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
}

function showToast(msg: string): void {
  const el = document.getElementById("toast");
  if (!el) return;
  el.textContent = msg;
  el.classList.add("show");
  setTimeout(() => el.classList.remove("show"), 2500);
}

function formatBytes(bytes: number): string {
  if (!bytes || bytes < 1024) return (bytes || 0) + " B";
  if (bytes < 1048576) return (bytes / 1024).toFixed(1) + " KB";
  return (bytes / 1048576).toFixed(1) + " MB";
}

function getToolBadge(tool: string): string {
  const colors: Record<string, string> = {
    claude: "#3b82f6",
    "claude-ext": "#6366f1",
    codex: "#06b6d4",
    opencode: "#a855f7",
    kiro: "#f97316",
    cursor: "#22c55e",
  };
  const color = colors[tool] || "#6b7280";
  return `<span class="tool-badge" style="background:${color}">${escHtml(tool)}</span>`;
}

// ── API ───────────────────────────────────────────────────────

async function fetchSessions(): Promise<void> {
  try {
    const resp = await fetch("/api/sessions");
    allSessions = await resp.json();
    filterAndRender();
    updateHostSidebar();
  } catch (e) {
    console.error("Failed to fetch sessions:", e);
  }
}

async function fetchActive(): Promise<void> {
  try {
    const resp = await fetch("/api/active");
    const active: any[] = await resp.json();
    activeSessions = {};
    for (const a of active) {
      if (a.sessionId) {
        activeSessions[a.sessionId] = {
          status: a.status,
          cpu: a.cpu,
          memoryMB: a.memoryMB,
          pid: a.pid,
        };
      }
    }
    // Re-render to update badges
    filterAndRender();
  } catch {}
}

async function fetchVersion(): Promise<void> {
  try {
    const resp = await fetch("/api/version");
    const data = await resp.json();
    const badge = document.getElementById("versionBadge");
    if (badge) badge.textContent = "v" + data.current;
  } catch {}
}

async function syncRemotes(): Promise<void> {
  const btn = document.getElementById("syncBtn");
  if (btn) btn.classList.add("syncing");
  showToast("Syncing remotes...");
  try {
    const resp = await fetch("/api/remotes/pull", { method: "POST" });
    const results = await resp.json();
    const ok = results.filter((r: any) => r.ok).length;
    const fail = results.filter((r: any) => !r.ok).length;
    if (fail > 0) showToast(`Synced ${ok}, failed ${fail}`);
    else if (ok > 0) showToast(`Synced ${ok} remote${ok > 1 ? "s" : ""}`);
    else showToast("No remotes configured");
    await fetchSessions();
    updateHostSidebar();
  } catch {
    showToast("Sync failed");
  } finally {
    if (btn) btn.classList.remove("syncing");
  }
}

function updateHostSidebar(): void {
  const container = document.getElementById("hostFilters");
  if (!container) return;
  const hosts = new Map<string, number>();
  for (const s of allSessions) {
    const h = s.host || "local";
    hosts.set(h, (hosts.get(h) || 0) + 1);
  }
  if (hosts.size <= 1) {
    container.innerHTML = "";
    return;
  }
  let html = '<div class="sidebar-section">Hosts</div>';
  for (const [host, count] of hosts) {
    const active = hostFilter === host ? "active" : "";
    html += `<div class="sidebar-item ${active}" data-view="host:${escHtml(host)}" onclick="switchView('host:${escHtml(host)}')">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="2" y="3" width="20" height="14" rx="2"/><line x1="8" y1="21" x2="16" y2="21"/><line x1="12" y1="17" x2="12" y2="21"/></svg>
      ${escHtml(host)} <span class="sidebar-count">${count}</span>
    </div>`;
  }
  container.innerHTML = html;
}

// ── Filtering ─────────────────────────────────────────────────

function filterAndRender(): void {
  filteredSessions = allSessions.filter((s) => {
    if (toolFilter && s.tool !== toolFilter) return false;
    if (hostFilter && (s.host || "") !== hostFilter) return false;
    if (currentView === "starred" && !stars.includes(s.id)) return false;
    if (searchQuery) {
      const q = searchQuery.toLowerCase();
      const text = `${s.first_message} ${s.project} ${s.id}`.toLowerCase();
      if (!text.includes(q) && !deepSearchMatchIds.has(s.id)) return false;
    }
    return true;
  });
  render();
}

// ── Rendering ─────────────────────────────────────────────────

function render(): void {
  const content = document.getElementById("content");
  if (!content) return;

  if (currentView === "analytics") {
    renderAnalytics(content);
  } else if (currentView === "changelog") {
    renderChangelog(content);
  } else if (currentView === "settings") {
    renderSettings(content);
  } else if (currentView === "projects") {
    renderProjects(content);
  } else if (currentView === "timeline") {
    renderTimeline(content);
  } else if (currentView === "running") {
    renderRunning(content);
  } else {
    content.className = "content";

    if (filteredSessions.length === 0) {
      content.innerHTML = '<div class="empty-state"><p>No sessions found</p></div>';
      return;
    }

    const layoutClass = layout === "grid" ? "grid-layout" : "list-layout";
    const cards = filteredSessions.slice(0, renderLimit).map((s) => renderCard(s)).join("");
    const loadMore = filteredSessions.length > renderLimit
      ? `<div class="load-more"><button class="btn-sm" onclick="loadMoreSessions()">Load more (${filteredSessions.length - renderLimit} remaining)</button></div>`
      : "";
    content.innerHTML = `<div class="${layoutClass}">${cards}${loadMore}</div>`;
  }

  if (document.documentElement.getAttribute("data-privacy") === "on") applyPrivacyRedaction(true);
}

function renderCard(s: Session): string {
  const active = activeSessions[s.id];
  const activeClass = active ? (active.status === "active" ? "card-active" : "card-waiting") : "";
  const activeBadge = active
    ? `<span class="live-badge ${active.status === "active" ? "live-active" : "live-waiting"}">${active.status === "active" ? "LIVE" : "WAITING"}</span>`
    : "";
  const starred = stars.includes(s.id) ? "starred" : "";
  const projectColor = getProjectColor(s.project_short || s.project);
  const projectName = getProjectName(s.project_short || s.project);
  const sessionTags = tags[s.id] || [];
  const tagBadges = sessionTags.map((t: string) => `<span class="tag-pill">${escHtml(t)}</span>`).join("");

  const hostBadge = s.remote ? `<span class="host-badge">${escHtml(s.host || "remote")}</span>` : "";

  return `<div class="card ${activeClass} ${starred}" onclick="showDetail('${s.id}')" data-id="${s.id}">
    <div class="card-top">
      ${getToolBadge(s.tool)}
      ${hostBadge}
      ${activeBadge}
      <span class="card-time">${timeAgo(s.last_ts)}</span>
    </div>
    <div class="card-title">${escHtml(s.first_message || "(no title)")}</div>
    <div class="card-meta">
      <span class="card-project" style="color:${projectColor}">${escHtml(projectName)}</span>
      <span class="card-msgs">${s.messages} msgs</span>
      <span class="card-size">${formatBytes(s.file_size)}</span>
    </div>
    ${tagBadges ? `<div class="card-tags">${tagBadges}</div>` : ""}
    <div class="card-actions">
      <button class="card-action-btn" onclick="event.stopPropagation(); toggleStar('${s.id}')" title="${stars.includes(s.id) ? "Unstar" : "Star"}">
        ${stars.includes(s.id) ? "&#9733;" : "&#9734;"}
      </button>
    </div>
  </div>`;
}

// ── Detail Panel ──────────────────────────────────────────────

async function showDetail(sessionId: string): Promise<void> {
  const panel = document.getElementById("detail");
  const overlay = document.getElementById("overlay");
  if (!panel) return;

  panel.classList.add("open");
  if (overlay) overlay.classList.add("open");
  panel.innerHTML = '<div class="detail-body"><div class="loading">Loading...</div></div>';

  try {
    const [sessionResp, costResp] = await Promise.all([
      fetch(`/api/session/${sessionId}`),
      fetch(`/api/cost/${sessionId}`),
    ]);
    const detail = await sessionResp.json();
    const cost = await costResp.json();
    const session = allSessions.find((s) => s.id === sessionId);

    let html = `<div class="detail-header">
      <div>
        <h2 style="font-size:16px;font-weight:600;margin:0">${escHtml(session?.first_message || sessionId)}</h2>
        <div class="card-meta" style="margin-top:6px">
          ${getToolBadge(session?.tool || "")}
          <span>${escHtml(session?.project_short || "")}</span>
          <span>${session?.last_time || ""}</span>
        </div>
      </div>
      <button class="detail-close" onclick="closeDetail()" title="Close">&times;</button>
    </div>`;

    html += '<div class="detail-body">';

    if (cost.cost > 0) {
      html += `<div class="cost-badge" style="margin-bottom:12px">
        $${cost.cost.toFixed(2)} (${escHtml(cost.model || "unknown")})
        &middot; ${Math.round(cost.inputTokens / 1000)}K in / ${Math.round(cost.outputTokens / 1000)}K out
      </div>`;
    }

    html += `<div class="detail-info">
      <dt>Session ID</dt><dd class="mono">${sessionId}</dd>
      <dt>Messages</dt><dd>${session?.messages || 0}</dd>
      <dt>File Size</dt><dd>${formatBytes(session?.file_size || 0)}</dd>
      <dt>Date</dt><dd>${session?.date || ""}</dd>
    </div>`;

    html += `<div class="detail-actions">
      <button class="launch-btn btn-secondary" onclick="exportSession('${sessionId}')">Export</button>
      <button class="launch-btn btn-delete" onclick="deleteSession('${sessionId}')">Delete</button>
    </div>`;

    html += '<div class="detail-messages"><h3>Messages</h3>';
    for (const m of detail.messages || []) {
      const roleClass = m.role === "user" ? "msg-user" : "msg-assistant";
      const roleLabel = m.role === "user" ? "You" : "Assistant";
      html += `<div class="message ${roleClass}">
        <div class="msg-role">${roleLabel}</div>
        <div class="msg-content">${escHtml(m.content)}</div>
      </div>`;
    }
    html += "</div></div>";

    panel.innerHTML = html;
    if (document.documentElement.getAttribute("data-privacy") === "on") applyPrivacyRedaction(true);
  } catch (e) {
    panel.innerHTML = '<div class="detail-header"><button class="detail-close" onclick="closeDetail()">&times;</button></div><div class="detail-body"><div class="empty-state"><p>Failed to load session</p></div></div>';
  }
}

function closeDetail(): void {
  const panel = document.getElementById("detail");
  const overlay = document.getElementById("overlay");
  if (panel) panel.classList.remove("open");
  if (overlay) overlay.classList.remove("open");
}

// ── Actions ───────────────────────────────────────────────────

function toggleStar(sessionId: string): void {
  const idx = stars.indexOf(sessionId);
  if (idx >= 0) {
    stars.splice(idx, 1);
  } else {
    stars.push(sessionId);
  }
  localStorage.setItem("terminalmba-stars", JSON.stringify(stars));
  filterAndRender();
}

async function deleteSession(sessionId: string): Promise<void> {
  if (!confirm("Delete this session?")) return;
  try {
    await fetch(`/api/session/${sessionId}`, {
      method: "DELETE",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ project: "" }),
    });
    closeDetail();
    showToast("Session deleted");
    await fetchSessions();
  } catch {
    showToast("Delete failed");
  }
}

function exportSession(sessionId: string): void {
  window.open(`/api/session/${sessionId}/export`, "_blank");
}

// ── View Switching ────────────────────────────────────────────

function switchView(view: string): void {
  currentView = view;
  toolFilter = null;
  hostFilter = null;
  renderLimit = RENDER_PAGE_SIZE;

  // Handle agent filters
  const agentViews: Record<string, string> = {
    "claude-only": "claude",
    "codex-only": "codex",
    "kiro-only": "kiro",
    "cursor-only": "cursor",
    "opencode-only": "opencode",
  };
  if (agentViews[view]) {
    toolFilter = agentViews[view];
    currentView = "sessions";
  }

  // Handle host filters
  if (view.startsWith("host:")) {
    hostFilter = view.slice(5);
    currentView = "sessions";
  }

  // Update sidebar active state
  document.querySelectorAll(".sidebar-item").forEach((el) => {
    el.classList.toggle("active", (el as HTMLElement).dataset.view === view);
  });

  filterAndRender();
}

// ── Layout ────────────────────────────────────────────────────

function toggleLayout(): void {
  layout = layout === "grid" ? "list" : "grid";
  localStorage.setItem("terminalmba-layout", layout);
  render();
}

// ── Search ────────────────────────────────────────────────────

let searchTimeout: ReturnType<typeof setTimeout> | null = null;
const deepSearchCache: Record<string, { sessionId: string; matches: { role: string; snippet: string }[] }[]> = {};
let deepSearchMatchIds: Set<string> = new Set();
let includeSubagents = true;

function onSubagentToggle(checked: boolean): void {
  includeSubagents = checked;
  // Re-trigger deep search if there's an active query
  if (searchQuery.length >= 2) {
    delete deepSearchCache[searchQuery];
    onSearchInput(searchQuery);
  }
}

function onSearchInput(value: string): void {
  searchQuery = value;
  deepSearchMatchIds = new Set();
  const url = new URL(window.location.href);
  if (value) url.searchParams.set("q", value);
  else url.searchParams.delete("q");
  history.replaceState(null, "", url.toString());
  filterAndRender();

  // Deep search with debounce
  if (searchTimeout) clearTimeout(searchTimeout);
  if (value.length >= 2) {
    searchTimeout = setTimeout(async () => {
      if (deepSearchCache[value]) {
        if (searchQuery === value) applyDeepSearchResults(deepSearchCache[value]);
        return;
      }
      try {
        const resp = await fetch(`/api/search?q=${encodeURIComponent(value)}&subagents=${includeSubagents ? "1" : "0"}`);
        const results = await resp.json();
        deepSearchCache[value] = results;
        if (searchQuery === value) applyDeepSearchResults(results);
      } catch {}
    }, 600);
  }
}

function applyDeepSearchResults(results: { sessionId: string; matches: { role: string; snippet: string }[] }[]): void {
  if (!results || results.length === 0) return;

  deepSearchMatchIds = new Set(results.map((r) => r.sessionId));

  // Re-filter to include fuzzy matches that were previously excluded
  filterAndRender();

  // Boost matching sessions to top
  const boosted: Session[] = [];
  const rest: Session[] = [];
  for (const s of filteredSessions) {
    if (deepSearchMatchIds.has(s.id)) {
      boosted.push(s);
    } else {
      rest.push(s);
    }
  }

  filteredSessions = boosted.concat(rest);
  render();

  if (boosted.length > 0) {
    showToast(`Found in ${boosted.length} sessions`);
  }
}

// ── Themes ────────────────────────────────────────────────────

function setTheme(theme: string): void {
  document.documentElement.setAttribute("data-theme", theme);
  localStorage.setItem("terminalmba-theme", theme);
}

// ── Pagination ────────────────────────────────────────────────

function loadMoreSessions(): void {
  renderLimit += RENDER_PAGE_SIZE;
  render();
}

// ── Projects View ─────────────────────────────────────────────

function renderProjects(container: HTMLElement): void {
  container.className = "content";
  const projects: Record<string, { sessions: Session[]; color: string }> = {};
  for (const s of allSessions) {
    const name = getProjectName(s.project_short || s.project);
    if (!projects[name]) {
      projects[name] = { sessions: [], color: getProjectColor(name) };
    }
    projects[name].sessions.push(s);
  }

  const sorted = Object.entries(projects).sort((a, b) => b[1].sessions.length - a[1].sessions.length);

  let html = '<div class="analytics-container"><h2>Projects</h2><div class="projects-grid">';
  for (const [name, info] of sorted) {
    const latest = info.sessions.reduce((a, b) => (a.last_ts > b.last_ts ? a : b));
    html += `<div class="project-card" onclick="switchToProjectFilter('${escHtml(name)}')">
      <div class="project-card-header">
        <div class="group-dot" style="background:${info.color}"></div>
        <span class="project-card-name">${escHtml(name)}</span>
      </div>
      <div class="project-card-stats">
        <span>${info.sessions.length} sessions</span>
        <span>${info.sessions.reduce((a, b) => a + b.messages, 0)} msgs</span>
      </div>
      <div class="project-card-time">${timeAgo(latest.last_ts)}</div>
    </div>`;
  }
  html += "</div></div>";
  container.innerHTML = html;
}

function switchToProjectFilter(projectName: string): void {
  searchQuery = projectName;
  const input = document.getElementById("searchInput") as HTMLInputElement;
  if (input) input.value = projectName;
  switchView("sessions");
}

// ── Timeline View ─────────────────────────────────────────────

function renderTimeline(container: HTMLElement): void {
  container.className = "content";
  const byDate: Record<string, Session[]> = {};
  for (const s of allSessions) {
    const date = s.date || "Unknown";
    if (!byDate[date]) byDate[date] = [];
    byDate[date].push(s);
  }

  const sortedDates = Object.keys(byDate).sort((a, b) => b.localeCompare(a));

  let html = '<div class="analytics-container"><h2>Timeline</h2><div class="timeline">';
  for (const date of sortedDates) {
    const sessions = byDate[date];
    html += `<div class="timeline-date">
      <div class="timeline-date-label">${escHtml(date)}<span class="timeline-count">${sessions.length} sessions</span></div>`;
    for (const s of sessions) {
      const projectColor = getProjectColor(s.project_short || s.project);
      const projectName = getProjectName(s.project_short || s.project);
      html += `<div class="card" onclick="showDetail('${s.id}')" style="margin-bottom:4px">
        <div class="card-top">
          ${getToolBadge(s.tool)}
          <span class="card-time">${s.first_time || ""}</span>
        </div>
        <div class="card-title">${escHtml(s.first_message || "(no title)")}</div>
        <div class="card-meta">
          <span class="card-project" style="color:${projectColor}">${escHtml(projectName)}</span>
          <span class="card-msgs">${s.messages} msgs</span>
        </div>
      </div>`;
    }
    html += "</div>";
  }
  html += "</div></div>";
  container.innerHTML = html;
}

// ── Running View ──────────────────────────────────────────────

function renderRunning(container: HTMLElement): void {
  container.className = "content";
  const activeIds = Object.keys(activeSessions);
  const runningSessions = allSessions.filter((s) => activeIds.includes(s.id));

  let html = '<div class="running-container"><h2>Running Sessions</h2>';

  if (runningSessions.length === 0) {
    html += '<div class="empty-state"><p>No active sessions</p></div>';
  } else {
    html += '<div class="running-grid">';
    for (const s of runningSessions) {
      const info = activeSessions[s.id];
      const statusClass = info.status === "active" ? "running-active" : "running-waiting";
      const projectName = getProjectName(s.project_short || s.project);
      html += `<div class="running-card ${statusClass}" onclick="showDetail('${s.id}')">
        <div class="running-card-header">
          <span class="live-badge ${info.status === "active" ? "live-active" : "live-waiting"}">${info.status === "active" ? "LIVE" : "WAITING"}</span>
          <span class="running-project">${escHtml(projectName)}</span>
          <span class="running-tool">${escHtml(s.tool)}</span>
        </div>
        <div class="card-title">${escHtml(s.first_message || "(no title)")}</div>
        <div class="running-stats">
          <div class="running-stat"><span class="running-stat-val">${s.messages}</span><span class="running-stat-label">Messages</span></div>
          <div class="running-stat"><span class="running-stat-val">${info.cpu ? info.cpu.toFixed(0) + "%" : "-"}</span><span class="running-stat-label">CPU</span></div>
          <div class="running-stat"><span class="running-stat-val">${info.memoryMB ? info.memoryMB.toFixed(0) + "MB" : "-"}</span><span class="running-stat-label">Memory</span></div>
        </div>
      </div>`;
    }
    html += "</div>";
  }
  html += "</div>";
  container.innerHTML = html;
}

// ── Analytics ─────────────────────────────────────────────────

async function renderAnalytics(container: HTMLElement): Promise<void> {
  container.className = "content";
  container.innerHTML = '<div class="loading">Loading analytics...</div>';

  try {
    const resp = await fetch("/api/analytics/cost");
    const data = await resp.json();

    let html = `<div class="analytics-container">
      <h2>Cost Analytics</h2>
      <div class="analytics-summary">
        <div class="analytics-card"><div class="analytics-val">$${data.totalCost.toFixed(2)}</div><div class="analytics-label">Total Cost</div></div>
        <div class="analytics-card"><div class="analytics-val">${data.totalSessions}</div><div class="analytics-label">Sessions</div></div>
        <div class="analytics-card"><div class="analytics-val">${Math.round(data.totalTokens / 1000)}K</div><div class="analytics-label">Total Tokens</div></div>
        <div class="analytics-card"><div class="analytics-val">$${data.dailyRate.toFixed(2)}</div><div class="analytics-label">Daily Rate</div></div>
      </div>`;

    // Agent breakdown as horizontal bar chart
    const agents = Object.entries(data.byAgent || {}) as [string, any][];
    const maxAgentCost = Math.max(...agents.map(([, a]) => a.cost), 0.01);
    html += '<div class="chart-section"><h3>By Agent</h3><div class="hbar-chart">';
    for (const [agent, info] of agents) {
      const pct = (info.cost / maxAgentCost) * 100;
      html += `<div class="hbar-row">
        <span class="hbar-name">${escHtml(agent)}</span>
        <div class="hbar-track"><div class="hbar-fill" style="width:${pct}%"></div></div>
        <span class="hbar-val">$${info.cost.toFixed(2)} (${info.sessions})</span>
      </div>`;
    }
    html += "</div></div>";

    // Host breakdown (only show if multiple hosts)
    const hosts = Object.entries(data.byHost || {}) as [string, any][];
    if (hosts.length > 1) {
      const maxHostCost = Math.max(...hosts.map(([, h]) => h.cost), 0.01);
      html += '<div class="chart-section"><h3>By Host</h3><div class="hbar-chart">';
      for (const [host, info] of hosts) {
        const pct = (info.cost / maxHostCost) * 100;
        html += `<div class="hbar-row">
          <span class="hbar-name">${escHtml(host)}</span>
          <div class="hbar-track"><div class="hbar-fill host-fill" style="width:${pct}%"></div></div>
          <span class="hbar-val">$${info.cost.toFixed(2)} (${info.sessions})</span>
        </div>`;
      }
      html += "</div></div>";
    }

    // Top sessions
    html += '<div class="chart-section"><h3>Top Sessions by Cost</h3><div class="hbar-chart">';
    const topMax = Math.max(...(data.topSessions || []).map((s: any) => s.cost), 0.01);
    for (const s of data.topSessions || []) {
      const pct = (s.cost / topMax) * 100;
      const projName = getProjectName(s.project);
      html += `<div class="hbar-row" onclick="showDetail('${s.id}')" style="cursor:pointer">
        <span class="hbar-name" title="${s.id}">${s.id.slice(0, 8)}... ${escHtml(projName)}</span>
        <div class="hbar-track"><div class="hbar-fill" style="width:${pct}%"></div></div>
        <span class="hbar-val">$${s.cost.toFixed(2)}</span>
      </div>`;
    }
    html += "</div></div></div>";

    container.innerHTML = html;
  } catch {
    container.innerHTML = '<div class="empty-state"><p>Failed to load analytics</p></div>';
  }
}

// ── Changelog ─────────────────────────────────────────────────

async function renderChangelog(container: HTMLElement): Promise<void> {
  container.className = "content";
  try {
    const resp = await fetch("/api/changelog");
    const entries = await resp.json();
    let html = '<div class="changelog-container"><h2>Changelog</h2>';
    for (let i = 0; i < entries.length; i++) {
      const entry = entries[i];
      const isLatest = i === 0;
      html += `<div class="changelog-entry ${isLatest ? "changelog-latest" : ""}">
        <div class="changelog-header">
          <span class="changelog-version">${escHtml(entry.version)}</span>
          ${isLatest ? '<span class="changelog-new">NEW</span>' : ""}
          <span class="changelog-date">${escHtml(entry.date)}</span>
        </div>
        <div class="changelog-title">${escHtml(entry.title)}</div>
        <ul class="changelog-list">${entry.changes.map((c: string) => `<li>${escHtml(c)}</li>`).join("")}</ul>
      </div>`;
    }
    html += "</div>";
    container.innerHTML = html;
  } catch {
    container.innerHTML = '<div class="empty-state"><p>Failed to load changelog</p></div>';
  }
}

// ── Settings ──────────────────────────────────────────────────

function renderSettings(container: HTMLElement): void {
  container.className = "content";
  const theme = localStorage.getItem("terminalmba-theme") || "dark";
  container.innerHTML = `<div class="settings-page">
    <h2>Settings</h2>
    <div class="settings-group">
      <label class="settings-label">Theme</label>
      <div class="settings-theme-btns">
        <button class="theme-btn ${theme === "dark" ? "active" : ""}" onclick="setTheme('dark'); switchView('settings')">Dark</button>
        <button class="theme-btn ${theme === "light" ? "active" : ""}" onclick="setTheme('light'); switchView('settings')">Light</button>
        <button class="theme-btn ${theme === "monokai" ? "active" : ""}" onclick="setTheme('monokai'); switchView('settings')">Monokai</button>
      </div>
    </div>
    <div class="settings-group">
      <label class="settings-label">Layout</label>
      <select class="settings-select" onchange="layout=this.value; localStorage.setItem('terminalmba-layout',this.value); switchView('settings')">
        <option value="grid" ${layout === "grid" ? "selected" : ""}>Grid</option>
        <option value="list" ${layout === "list" ? "selected" : ""}>List</option>
      </select>
    </div>
    <div class="settings-group">
      <label class="settings-label">Starred Sessions</label>
      <div style="font-size:14px;color:var(--text-primary)">${stars.length} starred sessions</div>
      ${stars.length > 0 ? `<button class="btn-sm" style="margin-top:8px" onclick="if(confirm('Clear all stars?')){stars=[];localStorage.setItem('terminalmba-stars','[]');switchView('settings')}">Clear All Stars</button>` : ""}
    </div>
    <div class="settings-group">
      <label class="settings-label">Data</label>
      <div style="font-size:14px;color:var(--text-primary)">${allSessions.length} sessions loaded</div>
    </div>
  </div>`;
}

// ── Privacy Mode ─────────────────────────────────────────────

const PRIVACY_SELECTORS = ".card-title, .card-project, .card-meta .mono, .detail-header h2, .detail-info .mono, .detail-info dd, .msg-content, .project-card, .timeline-item .card-title, .cost-badge";

function randomDigits(len: number): string {
  let s = "";
  for (let i = 0; i < len; i++) s += Math.random() < 0.2 ? " " : String(Math.floor(Math.random() * 10));
  return s;
}

function applyPrivacyRedaction(on: boolean): void {
  document.querySelectorAll(PRIVACY_SELECTORS).forEach((el) => {
    const e = el as HTMLElement;
    if (on) {
      if (!e.dataset.privacyOriginal) e.dataset.privacyOriginal = e.textContent || "";
      e.textContent = randomDigits(e.dataset.privacyOriginal.length);
    } else if (e.dataset.privacyOriginal !== undefined) {
      e.textContent = e.dataset.privacyOriginal;
      delete e.dataset.privacyOriginal;
    }
  });
}

// Reveal original text on hover, re-redact on leave
document.addEventListener("mouseenter", (e) => {
  const el = e.target as HTMLElement;
  if (document.documentElement.getAttribute("data-privacy") !== "on") return;
  if (el.dataset.privacyOriginal !== undefined) {
    el.textContent = el.dataset.privacyOriginal;
  }
}, true);

document.addEventListener("mouseleave", (e) => {
  const el = e.target as HTMLElement;
  if (document.documentElement.getAttribute("data-privacy") !== "on") return;
  if (el.dataset.privacyOriginal !== undefined) {
    el.textContent = randomDigits(el.dataset.privacyOriginal.length);
  }
}, true);

function togglePrivacy(): void {
  const html = document.documentElement;
  const isOn = html.getAttribute("data-privacy") === "on";
  const newState = isOn ? "off" : "on";
  html.setAttribute("data-privacy", newState);
  localStorage.setItem("terminalmba-privacy", newState);
  updatePrivacyButton(newState === "on");
  applyPrivacyRedaction(newState === "on");
}

function updatePrivacyButton(isOn: boolean): void {
  const btn = document.getElementById("privacyToggle");
  const label = document.getElementById("privacyLabel");
  if (!btn) return;
  btn.classList.toggle("active", isOn);
  if (label) label.textContent = isOn ? "ON" : "Privacy";
  // Swap eye icon: open eye vs slashed eye
  const svg = btn.querySelector("svg");
  if (svg) {
    svg.innerHTML = isOn
      ? '<path d="M17.94 17.94A10.07 10.07 0 0112 20c-7 0-11-8-11-8a18.45 18.45 0 015.06-5.94"/><path d="M9.9 4.24A9.12 9.12 0 0112 4c7 0 11 8 11 8a18.5 18.5 0 01-2.16 3.19"/><line x1="1" y1="1" x2="23" y2="23"/>'
      : '<path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/>';
  }
}

// ── Init ──────────────────────────────────────────────────────

// Apply saved theme
const savedTheme = localStorage.getItem("terminalmba-theme") || "dark";
document.documentElement.setAttribute("data-theme", savedTheme);

// Apply saved privacy mode
const savedPrivacy = localStorage.getItem("terminalmba-privacy") || "off";
document.documentElement.setAttribute("data-privacy", savedPrivacy);
requestAnimationFrame(() => updatePrivacyButton(savedPrivacy === "on"));

// Load data
fetchSessions().then(() => {
  const urlQ = new URLSearchParams(window.location.search).get("q");
  if (urlQ) {
    searchQuery = urlQ;
    const input = document.getElementById("searchInput") as HTMLInputElement;
    if (input) input.value = urlQ;
    filterAndRender();
    if (urlQ.length >= 2) onSearchInput(urlQ);
  }
});
fetchVersion();
fetchActive();

// Poll active sessions every 5 seconds
setInterval(fetchActive, 5000);

// Close detail panel on Escape
document.addEventListener("keydown", (e) => {
  if (e.key === "Escape") closeDetail();
});

// Expose functions to global scope for inline handlers
Object.assign(window, {
  switchView,
  toggleLayout,
  togglePrivacy,
  onSearchInput,
  setTheme,
  showDetail,
  closeDetail,
  toggleStar,
  deleteSession,
  exportSession,
  loadMoreSessions,
  switchToProjectFilter,
  syncRemotes,
  onSubagentToggle,
  render,
});
