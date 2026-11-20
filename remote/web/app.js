/* NEXUS Remote — PHASE 28 · vanilla JS, no build step, GitHub Pages ready */
"use strict";

const CFG = {
  base: localStorage.getItem("nexus_remote_base") || "",
  token: localStorage.getItem("nexus_remote_token") || "",
};

const $ = (id) => document.getElementById(id);
const esc = (s) => String(s ?? "").replace(/[&<>"']/g,
  (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

async function api(path, opts = {}) {
  const headers = Object.assign({}, opts.headers || {});
  if (CFG.token) headers["Authorization"] = "Bearer " + CFG.token;
  if (opts.body) headers["Content-Type"] = "application/json";
  const res = await fetch(CFG.base + path, { ...opts, headers });
  const data = await res.json().catch(() => ({}));
  return { status: res.status, ok: res.ok, data };
}

/* ---------------- connection ---------------- */
let healthy = false;

async function pollHealth() {
  const el = $("conn"), txt = $("conn_txt");
  if (!CFG.base) { el.className = "conn off"; txt.textContent = "غير مقترن"; return; }
  try {
    const r = await api("/api/health");
    healthy = r.ok && r.data && r.data.ok;
    el.className = "conn " + (healthy ? "on" : "off");
    txt.textContent = healthy ? "متصل" : "لا استجابة";
  } catch (e) {
    healthy = false;
    el.className = "conn off"; txt.textContent = "غير متصل";
  }
  if (healthy) refreshStatus();
}

/* ---------------- tabs ---------------- */
document.querySelectorAll("nav button").forEach((b) => {
  b.addEventListener("click", () => {
    document.querySelectorAll("nav button").forEach((x) => x.classList.remove("on"));
    document.querySelectorAll(".tab").forEach((x) => x.classList.remove("on"));
    b.classList.add("on");
    $("tab-" + b.dataset.tab).classList.add("on");
    if (b.dataset.tab === "status") refreshStatus();
    if (b.dataset.tab === "commands") refreshCommands();
    if (b.dataset.tab === "tasks") refreshTasks();
    if (b.dataset.tab === "files") refreshFiles();
  });
});

/* ---------------- pairing ---------------- */
$("in_base").value = CFG.base;
$("in_token").value = CFG.token;
$("btn_pair").addEventListener("click", async () => {
  const base = $("in_base").value.trim().replace(/\/+$/, "");
  const token = $("in_token").value.trim();
  CFG.base = base; CFG.token = token;
  localStorage.setItem("nexus_remote_base", base);
  localStorage.setItem("nexus_remote_token", token);
  $("pair_msg").textContent = "جاري الاختبار…";
  await pollHealth();
  const r = await api("/api/status");
  $("pair_msg").textContent = (r.ok && r.data.ok)
    ? "مقترن ✅ — التوكن مقبول والوصول مفتوح" : "فشل الاقتران — تحقق من العنوان والتوكن";
});

/* ---------------- status ---------------- */
async function refreshStatus() {
  if (!healthy) return;
  const r = await api("/api/status");
  if (!r.ok || !r.data.ok) return;
  const d = r.data;
  $("s_conn").textContent = "يعمل";
  $("s_paused").textContent = d.paused ? "متوقف مؤقتاً ⏸" : "يعمل ▶";
  $("s_paused").style.color = d.paused ? "var(--accent2)" : "var(--ok)";
  $("s_tasks").textContent = d.tasks_count;
  $("s_model").textContent = d.model;
  $("s_version").textContent = d.version;
  $("s_port").textContent = d.port;
}

/* ---------------- commands (28.3) ---------------- */
async function sendCommand(type, payload = {}) {
  const r = await api("/api/commands",
    { method: "POST", body: JSON.stringify({ type, payload }) });
  if (r.status === 201) refreshCommands();
  return r;
}

$("btn_pause").addEventListener("click", () => sendCommand("pause"));
$("btn_resume").addEventListener("click", () => sendCommand("resume"));
$("btn_checkpoint").addEventListener("click", () => sendCommand("checkpoint"));
$("btn_refresh").addEventListener("click", refreshCommands);
$("btn_chat").addEventListener("click", async () => {
  const text = $("in_chat").value.trim();
  if (!text) return;
  $("btn_chat").textContent = "أُرسل ✓";
  await sendCommand("chat", { text });
  $("in_chat").value = "";
  setTimeout(() => ($("btn_chat").textContent = "أرسل للمحادثة"), 1200);
});
$("btn_task").addEventListener("click", async () => {
  const goal = $("in_task").value.trim();
  if (!goal) return;
  $("btn_task").textContent = "أُرسل ✓";
  await sendCommand("task", { goal });
  $("in_task").value = "";
  setTimeout(() => ($("btn_task").textContent = "أنشئ مهمة"), 1200);
});

function badge(state) {
  return `<span class="badge ${esc(state)}">${esc(state)}</span>`;
}

async function refreshCommands() {
  const r = await api("/api/commands");
  if (!r.ok || !r.data.ok) return;
  const list = (r.data.commands || []).slice().reverse();
  $("cmd_list").innerHTML = list.map((c) => `
    <div class="item">
      ${badge(c.state)} <b>${esc(c.type)}</b>
      <span class="t">· ${esc(c.utc || "")}</span>
      <div class="t">${esc(typeof c.payload === "object"
        ? JSON.stringify(c.payload).slice(0, 90) : "")}</div>
      ${c.result ? `<div class="t">${esc(JSON.stringify(c.result).slice(0, 140))}</div>` : ""}
    </div>`).join("") || '<div class="hint">لا أوامر بعد</div>';
}

/* ---------------- tasks ---------------- */
$("btn_tasks_refresh").addEventListener("click", refreshTasks);
async function refreshTasks() {
  const r = await api("/api/tasks");
  const list = (r.data && r.data.tasks) || [];
  $("tasks_list").innerHTML = list.map((t) => `
    <div class="item">
      <b>${esc(t.state || "?")}</b> — ${esc((t.goal || "").slice(0, 110))}
      <div class="t">${esc(t.id)} · ${esc(t.created || "")}</div>
    </div>`).join("") || '<div class="hint">لا مهام — أنشئ واحدة من تبويب الأوامر</div>';
}

/* ---------------- files (28.4) ---------------- */
$("btn_files_refresh").addEventListener("click", refreshFiles);
async function refreshFiles() {
  const r = await api("/api/files");
  const list = (r.data && r.data.files) || [];
  $("files_list").innerHTML = list.map((f) => `
    <div class="item">
      📄 <b>${esc(f.name)}</b> · ${f.size} B
      <div class="t">sha256 ${esc(String(f.sha256 || "").slice(0, 24))}…</div>
      <button data-dl="${esc(f.name)}" style="width:auto;padding:6px 12px;min-height:32px">تنزيل</button>
    </div>`).join("") || '<div class="hint">الـoutbox فارغ</div>';
  document.querySelectorAll("[data-dl]").forEach((b) => {
    b.addEventListener("click", async () => {
      const r2 = await api("/api/files/get?name=" + encodeURIComponent(b.dataset.dl));
      if (!r2.ok) return;
      const bin = atob(r2.data.b64);
      const bytes = new Uint8Array(bin.length);
      for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
      const url = URL.createObjectURL(new Blob([bytes]));
      const a = document.createElement("a");
      a.href = url; a.download = r2.data.name; a.click();
      URL.revokeObjectURL(url);
    });
  });
}

$("btn_push").addEventListener("click", async () => {
  const f = $("in_file").files[0];
  const msg = $("push_msg");
  if (!f) { msg.textContent = "اختر ملفاً أولاً"; return; }
  if (f.size > 8 * 1024 * 1024) { msg.textContent = "الحد 8MB"; return; }
  msg.textContent = "جاري الرفع…";
  const buf = new Uint8Array(await f.arrayBuffer());
  let bin = "";
  for (let i = 0; i < buf.length; i += 0x8000)
    bin += String.fromCharCode.apply(null, buf.subarray(i, i + 0x8000));
  const r = await api("/api/files/push", {
    method: "POST",
    body: JSON.stringify({ name: f.name, b64: btoa(bin) }),
  });
  msg.textContent = r.status === 201
    ? `رُفع ✅ sha256 ${String(r.data.sha256 || "").slice(0, 16)}…`
    : `فشل الرفع (${r.status})`;
  refreshFiles();
});

/* ---------------- boot ---------------- */
pollHealth();
setInterval(pollHealth, 6000);
setInterval(() => { if ($("tab-commands").classList.contains("on")) refreshCommands(); }, 5000);
