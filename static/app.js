// Rugas Queue Counter — frontend logic (vanilla JS, no framework)
const API = "";
let token = localStorage.getItem("rugas_token") || "";
let queues = [];
let activeQueueId = null;
let refreshTimer = null;

const $ = (id) => document.getElementById(id);

function authHeaders() {
  return { "Content-Type": "application/json", Authorization: "Bearer " + token };
}

function toast(msg) {
  const t = $("toast");
  t.textContent = msg;
  t.classList.remove("hidden");
  setTimeout(() => t.classList.add("hidden"), 2600);
}

function fmtWait(sec) {
  if (sec < 60) return sec + "s";
  const m = Math.floor(sec / 60);
  if (m < 60) return m + "m " + (sec % 60) + "s";
  return Math.floor(m / 60) + "h " + (m % 60) + "m";
}

async function api(path, method = "GET", body = null) {
  const res = await fetch(API + path, {
    method,
    headers: authHeaders(),
    body: body ? JSON.stringify(body) : null,
  });
  if (res.status === 401) { doLogout(); throw new Error("Session expired, please log in again."); }
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.detail || "Something went wrong");
  return data;
}

// ---------------- login ----------------
$("login-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const err = $("login-error");
  err.classList.add("hidden");
  try {
    const data = await fetch(API + "/api/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ username: $("login-user").value.trim(), password: $("login-pass").value }),
    }).then((r) => r.json().then((d) => ({ ok: r.ok, d })));
    if (!data.ok) throw new Error(data.d.detail || "Login failed");
    token = data.d.token;
    localStorage.setItem("rugas_token", token);
    showApp();
  } catch (ex) {
    err.textContent = ex.message;
    err.classList.remove("hidden");
  }
});

function doLogout() {
  token = "";
  localStorage.removeItem("rugas_token");
  clearInterval(refreshTimer);
  $("app").classList.add("hidden");
  $("login-screen").classList.remove("hidden");
}
$("logout-btn").addEventListener("click", () => {
  fetch(API + "/api/logout", { method: "POST", headers: authHeaders() }).catch(() => {});
  doLogout();
});

// ---------------- data ----------------
async function loadAll() {
  queues = await api("/api/queues");
  if (!queues.length) { activeQueueId = null; }
  else if (!queues.find((q) => q.id === activeQueueId)) { activeQueueId = queues[0].id; }
  renderQueues();
  renderActive();
  await loadDashboard();
}

async function loadDashboard() {
  const d = await api("/api/dashboard");
  $("stat-waiting").textContent = d.total_waiting;
  $("stat-serving").textContent = d.total_serving;
  $("stat-served").textContent = d.total_served;
  $("stat-avg").textContent = fmtWait(d.avg_wait_seconds);
  $("longest-wait").innerHTML = d.longest_waiting
    ? `<b>LONGEST WAITING</b><br>${d.longest_waiting.token_no} · ${escapeHtml(d.longest_waiting.person_name)} — waiting ${fmtWait(d.longest_waiting.wait_seconds)}`
    : "No one waiting right now.";
  const maxW = Math.max(1, ...d.per_queue.map((q) => q.waiting));
  $("per-queue").innerHTML = d.per_queue.length
    ? d.per_queue.map((q) => `
      <div class="pq-row">
        <span class="pq-name">${escapeHtml(q.name)}</span>
        <div class="pq-bar"><i style="width:${Math.round((q.waiting / maxW) * 100)}%"></i></div>
        <span class="pq-num">${q.waiting}</span>
      </div>`).join("")
    : "<p class='meta'>No queues yet.</p>";
  const maxT = Math.max(1, ...d.trend.map((t) => t.tokens));
  $("trend").innerHTML = d.trend.map((t) => `
    <div class="trend-col"><i style="height:${Math.max(3, Math.round((t.tokens / maxT) * 64))}px"></i><span>${t.hour}</span></div>`).join("");
}

function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

// ---------------- render ----------------
function renderQueues() {
  $("queue-list").innerHTML = queues.map((q) => `
    <div class="queue-item ${q.id === activeQueueId ? "active" : ""}" data-id="${q.id}">
      <span class="q-name">${escapeHtml(q.name)}</span>
      <span style="display:flex;gap:6px;align-items:center">
        <span class="q-count">${q.waiting_count} waiting</span>
        <button class="q-del" data-del="${q.id}" title="Delete queue">×</button>
      </span>
    </div>`).join("") || "<p class='meta'>No queues yet. Create one above.</p>";
  document.querySelectorAll(".queue-item").forEach((el) => {
    el.addEventListener("click", (e) => {
      if (e.target.dataset.del) return;
      activeQueueId = Number(el.dataset.id);
      renderQueues();
      renderActive();
    });
  });
  document.querySelectorAll("[data-del]").forEach((btn) => {
    btn.addEventListener("click", async (e) => {
      e.stopPropagation();
      const id = Number(btn.dataset.del);
      const q = queues.find((x) => x.id === id);
      if (!confirm(`Delete queue "${q.name}" and all its tokens?`)) return;
      try { await api(`/api/queues/${id}`, "DELETE"); toast("Queue deleted"); await loadAll(); }
      catch (ex) { toast(ex.message); }
    });
  });
}

function renderActive() {
  const q = queues.find((x) => x.id === activeQueueId);
  const board = $("serving-board");
  const serving = queues.map((x) => x.serving).filter(Boolean);
  board.innerHTML = serving.length
    ? serving.map((t) => `<span class="board-token">${t.token_no}<small>${escapeHtml(t.person_name)}</small></span>`).join("")
    : '<span class="board-empty">Nobody at the counter yet. Call the next token.</span>';

  if (!q) {
    $("active-queue-name").textContent = "No queue selected";
    $("active-queue-meta").textContent = "";
    $("ticket-list").innerHTML = "";
    $("call-next-btn").disabled = true;
    return;
  }
  $("active-queue-name").textContent = q.name + " Queue";
  $("active-queue-meta").textContent = `${q.waiting_count} waiting · token series ${q.prefix}-001, ${q.prefix}-002, …`;
  $("call-next-btn").disabled = q.waiting_count === 0 || !!q.serving;

  const list = $("ticket-list");
  if (!q.tokens.length) {
    list.innerHTML = `<div class="empty-state">Queue is empty.<br>Add the first person below and a token is issued automatically.</div>`;
    return;
  }
  list.innerHTML = q.tokens.map((t, i) => {
    const waitingIdx = q.tokens.filter((x) => x.status === "waiting");
    const isTop = t.status === "waiting" && t.id === waitingIdx[0].id;
    const isLastWaiting = t.status === "waiting" && t.id === waitingIdx[waitingIdx.length - 1].id;
    return `
    <div class="ticket-card ${t.status === "serving" ? "serving" : ""}">
      <div class="stub">${t.token_no}</div>
      <div class="t-body">
        <div class="t-name">${escapeHtml(t.person_name)}</div>
        <div class="t-meta">${t.status === "serving" ? "SERVING · WAITED " + fmtWait(t.wait_seconds) : "WAITING " + fmtWait(t.wait_seconds) + " · POSITION " + t.position}</div>
        ${t.status === "serving" ? '<span class="stamp">NOW SERVING</span>' : ""}
      </div>
      <div class="t-actions">
        ${t.status === "waiting" ? `
          <button class="btn btn-sm" data-move="${t.id}" data-dir="up" ${isTop ? "disabled" : ""}>▲</button>
          <button class="btn btn-sm" data-move="${t.id}" data-dir="down" ${isLastWaiting ? "disabled" : ""}>▼</button>
          ${isTop ? `<button class="btn btn-sm btn-green" data-call="${t.id}">CALL</button>` : ""}
          <button class="btn btn-sm" data-cancel="${t.id}">CANCEL</button>
        ` : `
          <button class="btn btn-sm btn-green" data-complete="${t.id}">DONE ✓</button>
          <button class="btn btn-sm" data-cancel="${t.id}">CANCEL</button>
        `}
      </div>
    </div>`;
  }).join("");

  list.querySelectorAll("[data-move]").forEach((b) => b.addEventListener("click", async () => {
    try { await api(`/api/tokens/${b.dataset.move}/move`, "POST", { direction: b.dataset.dir }); await loadAll(); }
    catch (ex) { toast(ex.message); }
  }));
  list.querySelectorAll("[data-cancel]").forEach((b) => b.addEventListener("click", async () => {
    try { await api(`/api/tokens/${b.dataset.cancel}/cancel`, "POST"); toast("Token cancelled"); await loadAll(); }
    catch (ex) { toast(ex.message); }
  }));
  list.querySelectorAll("[data-complete]").forEach((b) => b.addEventListener("click", async () => {
    try { await api(`/api/tokens/${b.dataset.complete}/complete`, "POST"); toast("Served. Nice one."); await loadAll(); }
    catch (ex) { toast(ex.message); }
  }));
  list.querySelectorAll("[data-call]").forEach((b) => b.addEventListener("click", async () => {
    try { await callNext(); } catch (ex) { toast(ex.message); }
  }));
}

async function callNext() {
  const t = await api(`/api/queues/${activeQueueId}/call-next`, "POST");
  toast(`${t.token_no} called to the counter`);
  await loadAll();
}

$("call-next-btn").addEventListener("click", async () => {
  try { await callNext(); } catch (ex) { toast(ex.message); }
});

// ---------------- forms ----------------
$("new-queue-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const name = $("new-queue-name").value.trim();
  if (!name) return;
  try {
    const q = await api("/api/queues", "POST", { name });
    $("new-queue-name").value = "";
    toast(`Queue "${q.name}" created`);
    await loadAll();
    activeQueueId = q.id;
    renderQueues();
    renderActive();
  } catch (ex) { toast(ex.message); }
});

$("add-token-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const name = $("person-name").value.trim();
  if (!name || !activeQueueId) return;
  try {
    const t = await api(`/api/queues/${activeQueueId}/tokens`, "POST", { person_name: name });
    $("person-name").value = "";
    toast(`Token ${t.token_no} issued to ${t.person_name}`);
    await loadAll();
  } catch (ex) { toast(ex.message); }
});

// ---------------- clock + boot ----------------
function tickClock() {
  $("clock").textContent = new Date().toLocaleTimeString("en-IN", { hour12: false, timeZone: "Asia/Kolkata" });
}
setInterval(tickClock, 1000);
tickClock();

function showApp() {
  $("login-screen").classList.add("hidden");
  $("app").classList.remove("hidden");
  loadAll().catch((ex) => toast(ex.message));
  clearInterval(refreshTimer);
  refreshTimer = setInterval(() => loadAll().catch(() => {}), 5000);
}

if (token) showApp();
