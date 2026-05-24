"use strict";

const state = {
  meta: null,           // { common: [...], programs: [...] }
  currentProgram: null, // program object
  pollTimer: null,
  logSeq: 0,
};

// ---- API helpers --------------------------------------------------------

async function api(path, opts = {}) {
  const res = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...opts,
  });
  if (!res.ok && res.status !== 400) {
    // 400 is also returned with JSON body (validation errors).
    throw new Error(`HTTP ${res.status}`);
  }
  return res.json();
}

// ---- Field rendering ----------------------------------------------------

function makeField(opt, savedValue) {
  const wrapper = document.createElement("div");
  wrapper.className = "field";
  if (opt.required) wrapper.classList.add("required");
  if (opt.multiline || opt.span_2) wrapper.classList.add("span-2");

  const label = document.createElement("label");
  label.textContent = opt.flag
    ? `${opt.name} (${opt.flag})`
    : opt.name;
  label.htmlFor = `f_${opt.name}`;

  let input;
  const current = savedValue !== undefined ? savedValue : opt.default;

  switch (opt.type) {
    case "bool": {
      wrapper.classList.add("field-bool");
      input = document.createElement("input");
      input.type = "checkbox";
      input.id = `f_${opt.name}`;
      input.checked = current === true;
      break;
    }
    case "select": {
      input = document.createElement("select");
      input.id = `f_${opt.name}`;
      for (const [value, lbl] of opt.options || []) {
        const o = document.createElement("option");
        o.value = value;
        o.textContent = lbl;
        if (String(current) === String(value)) o.selected = true;
        input.appendChild(o);
      }
      break;
    }
    case "int":
    case "float": {
      input = document.createElement("input");
      input.type = "number";
      if (opt.type === "float") input.step = "any";
      input.id = `f_${opt.name}`;
      input.value = current === undefined || current === null ? "" : current;
      input.placeholder = String(opt.default ?? "");
      break;
    }
    case "color": {
      wrapper.classList.add("field-color");
      const text = document.createElement("input");
      text.type = "text";
      text.id = `f_${opt.name}`;
      text.placeholder = "r,g,b";
      text.value = current ?? "";

      const picker = document.createElement("input");
      picker.type = "color";
      picker.value = colorTriadToHex(current ?? opt.default ?? "0,0,0");
      picker.addEventListener("input", () => {
        text.value = hexToColorTriad(picker.value);
      });
      text.addEventListener("input", () => {
        const hex = colorTriadToHex(text.value);
        if (hex) picker.value = hex;
      });

      wrapper.appendChild(label);
      wrapper.appendChild(text);
      wrapper.appendChild(picker);
      if (opt.help) {
        const h = document.createElement("span");
        h.className = "help";
        h.textContent = opt.help;
        wrapper.appendChild(h);
      }
      return wrapper;
    }
    case "file": {
      wrapper.classList.add("span-2");
      input = document.createElement("select");
      input.id = `f_${opt.name}`;
      const opt0 = document.createElement("option");
      opt0.value = "";
      opt0.textContent = opt.required ? "-- choisir un fichier --" : "(aucun)";
      input.appendChild(opt0);
      // Populate after async fetch.
      fetchFiles(state.currentProgram.id, opt.name).then(files => {
        for (const f of files) {
          const o = document.createElement("option");
          o.value = f;
          o.textContent = f;
          if (current === f) o.selected = true;
          input.appendChild(o);
        }
        if (current && !files.includes(current)) {
          const o = document.createElement("option");
          o.value = current;
          o.textContent = current + " (inconnu)";
          o.selected = true;
          input.appendChild(o);
        }
      });
      break;
    }
    default: {
      if (opt.multiline) {
        input = document.createElement("textarea");
        input.rows = 2;
      } else {
        input = document.createElement("input");
        input.type = "text";
      }
      input.id = `f_${opt.name}`;
      input.value = current ?? "";
      input.placeholder = String(opt.default ?? "");
      break;
    }
  }

  wrapper.appendChild(label);
  wrapper.appendChild(input);
  if (opt.help) {
    const h = document.createElement("span");
    h.className = "help";
    h.textContent = opt.help;
    wrapper.appendChild(h);
  }
  return wrapper;
}

function readField(opt) {
  const el = document.getElementById(`f_${opt.name}`);
  if (!el) return undefined;
  if (opt.type === "bool") return el.checked;
  if (opt.type === "int") return el.value === "" ? "" : parseInt(el.value, 10);
  if (opt.type === "float") return el.value === "" ? "" : parseFloat(el.value);
  return el.value;
}

function colorTriadToHex(triad) {
  if (!triad) return "#000000";
  const m = triad.match(/^(\d{1,3}),(\d{1,3}),(\d{1,3})$/);
  if (!m) return "#000000";
  const [r, g, b] = [m[1], m[2], m[3]].map(n => Math.max(0, Math.min(255, parseInt(n, 10))));
  return "#" + [r, g, b].map(n => n.toString(16).padStart(2, "0")).join("");
}

function hexToColorTriad(hex) {
  const m = hex.match(/^#([0-9a-f]{2})([0-9a-f]{2})([0-9a-f]{2})$/i);
  if (!m) return "0,0,0";
  return [m[1], m[2], m[3]].map(h => parseInt(h, 16)).join(",");
}

// ---- File listing -------------------------------------------------------

async function fetchFiles(programId, optionName) {
  try {
    const res = await fetch(
      `/api/files?program=${encodeURIComponent(programId)}` +
      `&option=${encodeURIComponent(optionName)}`);
    const data = await res.json();
    return data.files || [];
  } catch (e) {
    console.error(e);
    return [];
  }
}

// ---- Program selection --------------------------------------------------

function selectProgram(prog) {
  state.currentProgram = prog;
  document.querySelectorAll("#program-list li").forEach(li => {
    li.classList.toggle("selected", li.dataset.programId === prog.id);
  });
  document.getElementById("program-title").textContent = prog.name;
  document.getElementById("program-description").textContent =
    prog.description || "";

  const saved = loadSavedValues(prog.id);

  const common = document.getElementById("common-options");
  common.innerHTML = "";
  for (const opt of state.meta.common) {
    common.appendChild(makeField(opt, saved[opt.name]));
  }

  const specific = document.getElementById("specific-options");
  specific.innerHTML = "";
  for (const opt of prog.specific_options || []) {
    if (opt.stdin_only) continue; // rendered separately
    specific.appendChild(makeField(opt, saved[opt.name]));
  }
  document.getElementById("specific-section").style.display =
    (prog.specific_options && prog.specific_options.length) ? "" : "none";

  const stdinSection = document.getElementById("stdin-section");
  const stdinField = prog.stdin_field;
  stdinSection.hidden = !stdinField;
  if (stdinField) {
    const stdinTextEl = document.getElementById("stdin-text");
    stdinTextEl.value = saved[stdinField] ?? "";
    stdinTextEl.placeholder =
      (prog.specific_options.find(o => o.name === stdinField) || {}).help
      || "Texte envoyé sur stdin";
  }
}

// ---- Form -> values dict ------------------------------------------------

function collectValues() {
  const prog = state.currentProgram;
  const values = {};
  for (const opt of state.meta.common) {
    values[opt.name] = readField(opt);
  }
  for (const opt of prog.specific_options || []) {
    if (opt.stdin_only) {
      const el = document.getElementById("stdin-text");
      if (el) values[opt.name] = el.value;
      continue;
    }
    values[opt.name] = readField(opt);
  }
  return values;
}

// ---- localStorage persistence ------------------------------------------

function storageKey(programId) {
  return `rpi-rgb-led-matrix/${programId}`;
}
function saveValues(programId, values) {
  try {
    localStorage.setItem(storageKey(programId), JSON.stringify(values));
  } catch (e) { /* quota / disabled */ }
}
function loadSavedValues(programId) {
  try {
    const raw = localStorage.getItem(storageKey(programId));
    return raw ? JSON.parse(raw) : {};
  } catch (e) {
    return {};
  }
}

// ---- Actions ------------------------------------------------------------

async function doStart(ev) {
  ev.preventDefault();
  const prog = state.currentProgram;
  if (!prog) return;
  const values = collectValues();
  saveValues(prog.id, values);
  setStatus("starting", "Démarrage...");
  const res = await api("/api/start", {
    method: "POST",
    body: JSON.stringify({ program_id: prog.id, values }),
  });
  if (!res.ok) {
    setStatus("error", "Erreur: " + (res.error || "inconnue"));
    appendLog(`[client] ERREUR: ${res.error}`);
    return;
  }
  state.logSeq = 0;
  document.getElementById("log").textContent = "";
}

async function doStop() {
  setStatus("starting", "Arrêt en cours...");
  await api("/api/stop", { method: "POST" });
}

async function doBuild() {
  const prog = state.currentProgram;
  if (!prog) return;
  appendLog(`[build] make -C ${prog.build_dir} ${prog.build_target || ""}`);
  const res = await api("/api/build", {
    method: "POST",
    body: JSON.stringify({ program_id: prog.id }),
  });
  appendLog(res.output || "");
  appendLog(res.ok
    ? `[build] OK (returncode=${res.returncode})`
    : `[build] ECHEC (returncode=${res.returncode})`);
}

async function doSendStdin() {
  const text = document.getElementById("stdin-text").value;
  const res = await api("/api/stdin", {
    method: "POST",
    body: JSON.stringify({ text }),
  });
  if (!res.ok) appendLog(`[stdin] ${res.error}`);
}

async function doUpload(ev) {
  ev.preventDefault();
  const input = document.getElementById("upload-input");
  if (!input.files || !input.files.length) return;
  const form = new FormData();
  for (const f of input.files) form.append("file", f, f.name);
  const status = document.getElementById("upload-status");
  status.textContent = "Envoi en cours...";
  const res = await fetch("/api/upload", { method: "POST", body: form });
  const data = await res.json();
  if (data.ok) {
    status.textContent = `Envoyé: ${data.files.join(", ")}`;
    // Refresh file selects in the current program.
    if (state.currentProgram) selectProgram(state.currentProgram);
  } else {
    status.textContent = "Erreur: " + (data.error || "inconnue");
  }
}

function doReset() {
  if (!state.currentProgram) return;
  localStorage.removeItem(storageKey(state.currentProgram.id));
  selectProgram(state.currentProgram);
}

// ---- Status / log polling ----------------------------------------------

function setStatus(kind, text) {
  const dot = document.getElementById("status-dot");
  dot.classList.remove("idle", "run", "error");
  document.getElementById("status-text").textContent = text;
  if (kind === "run") {
    dot.classList.add("run");
    document.getElementById("btn-stop").disabled = false;
    document.getElementById("btn-start").disabled = true;
  } else if (kind === "error") {
    dot.classList.add("error");
    document.getElementById("btn-stop").disabled = true;
    document.getElementById("btn-start").disabled = false;
  } else if (kind === "starting") {
    dot.classList.add("run");
    document.getElementById("btn-stop").disabled = true;
    document.getElementById("btn-start").disabled = true;
  } else {
    dot.classList.add("idle");
    document.getElementById("btn-stop").disabled = true;
    document.getElementById("btn-start").disabled = false;
  }
}

function appendLog(line) {
  if (!line) return;
  const el = document.getElementById("log");
  el.textContent += line + "\n";
  el.scrollTop = el.scrollHeight;
}

async function poll() {
  try {
    const data = await api(`/api/log?since=${state.logSeq}`);
    if (data.lines && data.lines.length) {
      for (const ln of data.lines) appendLog(ln);
      state.logSeq = data.seq;
    } else if (typeof data.seq === "number") {
      state.logSeq = Math.max(state.logSeq, data.seq);
    }
    const s = data.status || {};
    if (s.running) {
      const prog = state.meta.programs.find(p => p.id === s.program_id);
      setStatus("run", `En cours: ${prog ? prog.name : s.program_id}`);
    } else if (s.exit_code !== null && s.exit_code !== undefined) {
      setStatus(s.exit_code === 0 ? "idle" : "error",
                `Arrêté (code ${s.exit_code})`);
    } else {
      setStatus("idle", "Aucun programme en cours");
    }
  } catch (e) {
    // Network hiccup: try again later.
  }
}

// ---- Bootstrap ----------------------------------------------------------

async function init() {
  state.meta = await api("/api/programs");
  const ul = document.getElementById("program-list");
  ul.innerHTML = "";
  for (const p of state.meta.programs) {
    const li = document.createElement("li");
    li.textContent = p.name;
    li.dataset.programId = p.id;
    li.addEventListener("click", () => selectProgram(p));
    ul.appendChild(li);
  }
  if (state.meta.programs.length) selectProgram(state.meta.programs[0]);

  document.getElementById("program-form").addEventListener("submit", doStart);
  document.getElementById("btn-stop").addEventListener("click", doStop);
  document.getElementById("btn-build").addEventListener("click", doBuild);
  document.getElementById("btn-reset").addEventListener("click", doReset);
  document.getElementById("btn-stdin-send").addEventListener("click", doSendStdin);
  document.getElementById("upload-form").addEventListener("submit", doUpload);

  await poll();
  setInterval(poll, 1000);
}

init().catch(e => {
  document.getElementById("program-pane").innerHTML =
    `<h2>Erreur de chargement</h2><pre>${e}</pre>`;
});
