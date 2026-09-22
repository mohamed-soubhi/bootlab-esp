// =============================================================================
// bootlab-esp Operations Console Application Engine
// =============================================================================

let categories = [];
let tools = {};
let activeCategory = "diagnostics";
let selectedToolId = null;
let eventSource = null;
let autoscroll = true;
let jobStartTime = null;
let timerInterval = null;

document.addEventListener("DOMContentLoaded", () => {
  initTheme();
  initEventSource();
  loadTools();
  refreshBoards();
  checkActiveJob();

  const autoscrollEl = document.getElementById("autoscroll-toggle");
  if (autoscrollEl) {
    autoscrollEl.addEventListener("change", (e) => {
      autoscroll = e.target.checked;
    });
  }
});

// Theme Management
function initTheme() {
  const saved = localStorage.getItem("bootlab_theme") || "dark";
  document.documentElement.setAttribute("data-theme", saved);
}

function toggleTheme() {
  const current = document.documentElement.getAttribute("data-theme") || "dark";
  const next = current === "dark" ? "light" : "dark";
  document.documentElement.setAttribute("data-theme", next);
  localStorage.setItem("bootlab_theme", next);
}

// SSE Connection
function initEventSource() {
  const statusEl = document.getElementById("connection-status");
  const statusText = document.getElementById("status-text");

  if (eventSource) {
    eventSource.close();
  }
  eventSource = new EventSource("/api/stream");

  eventSource.onopen = () => {
    statusEl.className = "status-pill online";
    statusText.innerText = "Online";
  };

  eventSource.onerror = () => {
    statusEl.className = "status-pill offline";
    statusText.innerText = "Reconnecting...";
  };

  eventSource.addEventListener("log", (e) => {
    try {
      const data = JSON.parse(e.data);
      appendTerminalLine(data.line);
    } catch {
      appendTerminalLine(e.data + "\n");
    }
  });

  eventSource.addEventListener("status", (e) => {
    try {
      const data = JSON.parse(e.data);
      handleJobStatusUpdate(data);
    } catch (err) {
      console.error("Error handling status event:", err);
    }
  });
}

// Check if a job is already running on initial load
async function checkActiveJob() {
  try {
    const res = await fetch("/api/history");
    const data = await res.json();
    if (data.active_job) {
      const btnRun = document.getElementById("btn-run");
      const btnAbort = document.getElementById("btn-abort");
      btnRun.classList.add("hidden");
      btnAbort.classList.remove("hidden");
      jobStartTime = data.active_job.started_at ? data.active_job.started_at * 1000 : Date.now();
      startTimer();
    }
  } catch {
    // Ignore fetch error on startup
  }
}

// Load Tools Catalog
async function loadTools() {
  try {
    const res = await fetch("/api/tools");
    const data = await res.json();
    categories = data.categories || [];
    tools = data.tools || {};
    renderCategories();
    selectCategory(categories[0]?.id || "diagnostics");
  } catch (err) {
    appendTerminalLine(`\x1b[31m[ERROR] Failed to load tools catalog: ${err.message}\x1b[0m\n`);
  }
}

function renderCategories() {
  const tabs = document.getElementById("category-tabs");
  tabs.innerHTML = "";
  categories.forEach((cat) => {
    const btn = document.createElement("button");
    btn.className = `tab-btn ${cat.id === activeCategory ? "active" : ""}`;
    btn.innerText = `${cat.icon || ""} ${cat.name}`;
    btn.onclick = () => selectCategory(cat.id);
    tabs.appendChild(btn);
  });
}

function selectCategory(catId) {
  activeCategory = catId;
  renderCategories();

  const container = document.getElementById("tools-container");
  container.innerHTML = "";

  const catTools = Object.values(tools).filter((t) => t.category === catId);
  catTools.forEach((tool, index) => {
    const item = document.createElement("div");
    item.className = `tool-item ${tool.id === selectedToolId ? "active" : ""}`;
    item.innerHTML = `
      <div class="tool-item-title">${escapeHtml(tool.name)}</div>
      <div class="tool-item-desc">${escapeHtml(tool.description)}</div>
    `;
    item.onclick = () => selectTool(tool.id);
    container.appendChild(item);

    // Auto-select first tool in the category if none selected or selection changed
    if (index === 0 && (!selectedToolId || !tools[selectedToolId] || tools[selectedToolId].category !== catId)) {
      selectTool(tool.id);
    }
  });
}

function selectTool(toolId) {
  selectedToolId = toolId;
  const tool = tools[toolId];
  if (!tool) return;

  document.querySelectorAll(".tool-item").forEach((el) => {
    const titleEl = el.querySelector(".tool-item-title");
    el.classList.toggle("active", titleEl && titleEl.innerText === tool.name);
  });

  document.getElementById("selected-tool-name").innerText = tool.name;
  document.getElementById("selected-tool-desc").innerText = tool.description;
  const badge = document.getElementById("selected-tool-badge");
  badge.innerText = (tool.safety_level || "safe").toUpperCase();
  badge.className = `badge-tag ${
    tool.safety_level === "destructive"
      ? "log-fail"
      : tool.safety_level === "power_sensitive"
      ? "log-warn"
      : ""
  }`;

  const paramsContainer = document.getElementById("dynamic-params");
  paramsContainer.innerHTML = "";

  if (!tool.parameters || tool.parameters.length === 0) {
    paramsContainer.innerHTML =
      '<span class="text-muted" style="grid-column: 1 / -1; font-size: 12.5px; font-style: italic;">No parameters required for this tool.</span>';
  } else {
    tool.parameters.forEach((p) => {
      const group = document.createElement("div");
      group.className = "form-group";
      const label = document.createElement("label");
      label.innerText = p.label + (p.required ? " *" : "");
      label.htmlFor = `param-${p.name}`;

      let input;
      if (p.type === "select") {
        input = document.createElement("select");
        input.name = p.name;
        input.id = `param-${p.name}`;
        (p.options || []).forEach((opt) => {
          const option = document.createElement("option");
          option.value = opt;
          option.innerText = opt;
          if (opt === p.default) option.selected = true;
          input.appendChild(option);
        });
      } else if (p.type === "boolean") {
        input = document.createElement("input");
        input.type = "checkbox";
        input.name = p.name;
        input.id = `param-${p.name}`;
        input.checked = Boolean(p.default);
      } else {
        input = document.createElement("input");
        input.type = p.type === "number" ? "number" : "text";
        input.name = p.name;
        input.id = `param-${p.name}`;
        input.value = p.default !== undefined && p.default !== null ? p.default : "";
        if (p.description) input.placeholder = p.description;
        if (p.required) input.required = true;
      }

      group.appendChild(label);
      group.appendChild(input);
      paramsContainer.appendChild(group);
    });
  }

  document.getElementById("btn-run").disabled = false;
}

// Target Detection
async function refreshBoards() {
  const container = document.getElementById("targets-list");
  container.innerHTML = '<span class="text-muted">Scanning hardware ports and network...</span>';

  try {
    const res = await fetch("/api/boards");
    const data = await res.json();
    container.innerHTML = "";

    if (!data.boards || data.boards.length === 0) {
      container.innerHTML = '<span class="text-muted">No hardware serial or network targets found.</span>';
      return;
    }

    data.boards.forEach((b) => {
      const chip = document.createElement("div");
      chip.className = "target-chip";
      if (b.type === "serial") {
        chip.innerHTML = `<span>🔌</span> <strong>${escapeHtml(b.device)}</strong> (${escapeHtml(b.description || "USB Device")})`;
        chip.title = `Click to autofill serial port: ${b.device}`;
        chip.onclick = () => fillParam("port", b.device);
      } else {
        chip.innerHTML = `<span>🌐</span> <strong>${escapeHtml(b.ip)}</strong> (${escapeHtml(b.stack || "network")} // ${escapeHtml(b.hostname || "target")})`;
        chip.title = `Click to autofill IP: ${b.ip}`;
        chip.onclick = () => {
          fillParam("ip", b.ip);
          fillParam("target", b.ip);
        };
      }
      container.appendChild(chip);
    });
  } catch (err) {
    container.innerHTML = `<span class="log-fail">Scan failed: ${escapeHtml(err.message)}</span>`;
  }
}

function fillParam(name, value) {
  const input = document.querySelector(`[name="${name}"]`);
  if (input) {
    input.value = value;
    input.dispatchEvent(new Event("input", { bubbles: true }));
  }
}

// Command Execution
async function runSelectedTool() {
  if (!selectedToolId) return;

  const form = document.getElementById("tool-form");
  const formData = new FormData(form);
  const params = {};

  const tool = tools[selectedToolId];
  if (tool && tool.parameters) {
    tool.parameters.forEach((p) => {
      if (p.type === "boolean") {
        const el = form.querySelector(`[name="${p.name}"]`);
        params[p.name] = el ? el.checked : false;
      } else if (formData.has(p.name)) {
        params[p.name] = formData.get(p.name);
      }
    });
  }

  const btnRun = document.getElementById("btn-run");
  const btnAbort = document.getElementById("btn-abort");

  btnRun.classList.add("hidden");
  btnAbort.classList.remove("hidden");

  clearConsoleLog();
  appendTerminalLine(`\x1b[36m$ labflash ${selectedToolId} [executing...]\x1b[0m\n\n`);

  jobStartTime = Date.now();
  startTimer();

  try {
    const res = await fetch("/api/run", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ tool_id: selectedToolId, params }),
    });

    if (!res.ok) {
      const err = await res.json().catch(() => ({ error: "Execution failed" }));
      appendTerminalLine(`\x1b[31m[ERROR] ${err.error || "Execution failed"}\x1b[0m\n`);
      finishJobUI();
    }
  } catch (e) {
    appendTerminalLine(`\x1b[31m[ERROR] Network error: ${e.message}\x1b[0m\n`);
    finishJobUI();
  }
}

async function abortJob() {
  try {
    await fetch("/api/abort", { method: "POST" });
    appendTerminalLine(`\n\x1b[33m[!] Abort signal dispatched to runner.\x1b[0m\n`);
  } catch (e) {
    appendTerminalLine(`\x1b[31m[ERROR] Failed to send abort: ${e.message}\x1b[0m\n`);
  }
}

function handleJobStatusUpdate(data) {
  if (data.status === "passed") {
    appendTerminalLine(`\n\x1b[32m✔ Completed successfully with exit code 0 (${data.elapsed}s)\x1b[0m\n`);
    finishJobUI();
  } else if (data.status === "failed") {
    appendTerminalLine(`\n\x1b[31m✘ Failed with exit code ${data.exit_code} (${data.elapsed}s)\x1b[0m\n`);
    finishJobUI();
  } else if (data.status === "aborted") {
    appendTerminalLine(`\n\x1b[33m⏹ Job was aborted by user (${data.elapsed}s)\x1b[0m\n`);
    finishJobUI();
  }
}

function finishJobUI() {
  stopTimer();
  const btnRun = document.getElementById("btn-run");
  const btnAbort = document.getElementById("btn-abort");
  if (btnRun) btnRun.classList.remove("hidden");
  if (btnAbort) btnAbort.classList.add("hidden");
}

function startTimer() {
  stopTimer();
  const timerEl = document.getElementById("job-timer");
  timerInterval = setInterval(() => {
    if (!jobStartTime) return;
    const elapsed = ((Date.now() - jobStartTime) / 1000).toFixed(2);
    if (timerEl) timerEl.innerText = `${elapsed}s`;
  }, 100);
}

function stopTimer() {
  if (timerInterval) {
    clearInterval(timerInterval);
    timerInterval = null;
  }
}

// Client-Side ANSI Escape Parser
function parseAnsi(text) {
  if (!text) return "";
  let clean = text
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");

  const colorMap = {
    "1": '<strong style="color:var(--text-contrast)">',
    "2": '<span style="opacity:0.7">',
    "3": '<em>',
    "4": '<span style="text-decoration:underline">',
    "30": '<span style="color:#64748b">',
    "31": '<span class="log-fail">',
    "32": '<span class="log-pass">',
    "33": '<span class="log-warn">',
    "34": '<span style="color:#60a5fa">',
    "35": '<span style="color:var(--accent-violet)">',
    "36": '<span class="log-cyan">',
    "37": '<span style="color:#f8fafc">',
    "90": '<span class="text-muted">',
    "91": '<span class="log-fail">',
    "92": '<span class="log-pass">',
    "93": '<span class="log-warn">',
    "94": '<span style="color:#60a5fa">',
    "95": '<span style="color:var(--accent-violet)">',
    "96": '<span class="log-cyan">',
    "97": '<span style="color:#ffffff">',
  };

  clean = clean.replace(/\x1b\[([0-9;]+)m/g, (match, codesStr) => {
    const codes = codesStr.split(";");
    let result = "";
    for (const code of codes) {
      if (code === "0" || code === "") {
        result += "</span>";
      } else if (colorMap[code]) {
        result += colorMap[code];
      }
    }
    return result;
  });

  clean = clean.replace(/\x1b\[m/g, "</span>");
  clean = clean.replace(/\x1b\[[0-9;?]*[a-zA-Z]/g, "");

  return clean;
}

function appendTerminalLine(text) {
  const terminal = document.getElementById("terminal-window");
  if (!terminal) return;

  const welcome = terminal.querySelector(".terminal-welcome");
  if (welcome) {
    welcome.remove();
  }

  terminal.innerHTML += parseAnsi(text);
  if (autoscroll) {
    terminal.scrollTop = terminal.scrollHeight;
  }
}

function clearConsoleLog() {
  const terminal = document.getElementById("terminal-window");
  if (terminal) terminal.innerHTML = "";
  const timerEl = document.getElementById("job-timer");
  if (timerEl) timerEl.innerText = "0.00s";
}

function copyConsoleLog() {
  const terminal = document.getElementById("terminal-window");
  if (!terminal) return;
  const text = terminal.innerText;
  if (navigator.clipboard) {
    navigator.clipboard.writeText(text).then(() => {
      showCopyFeedback();
    }).catch(() => {
      fallbackCopy(text);
    });
  } else {
    fallbackCopy(text);
  }
}

function fallbackCopy(text) {
  const ta = document.createElement("textarea");
  ta.value = text;
  document.body.appendChild(ta);
  ta.select();
  try {
    document.execCommand("copy");
    showCopyFeedback();
  } catch (e) {
    console.error("Copy failed", e);
  }
  document.body.removeChild(ta);
}

function showCopyFeedback() {
  const btn = event?.target;
  if (btn && btn.tagName === "BUTTON") {
    const original = btn.innerText;
    btn.innerText = "Copied!";
    setTimeout(() => {
      btn.innerText = original;
    }, 1500);
  }
}

function escapeHtml(str) {
  if (!str) return "";
  return String(str)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}
