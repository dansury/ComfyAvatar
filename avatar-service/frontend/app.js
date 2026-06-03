/* ComfyAvatar frontend logic.
 * Все настройки сохраняются в localStorage и синхронизируются с backend.
 */

const API = "";
const LS_KEY = "comfyavatar.settings";

const state = {
  photoPath: null,
  voicePath: null,
  mediaRecorder: null,
  recChunks: [],
  recTimer: null,
  recStart: 0,
  ws: null,
};

const $ = (id) => document.getElementById(id);

/* ----------------------------- утилиты ----------------------------- */
function showBanner(message, ok = false) {
  const b = $("banner");
  b.textContent = message;
  b.classList.toggle("ok", ok);
  b.classList.remove("hidden");
}
function hideBanner() { $("banner").classList.add("hidden"); }

async function api(path, opts = {}) {
  const resp = await fetch(API + path, opts);
  if (!resp.ok) {
    let detail = resp.statusText;
    try { detail = (await resp.json()).detail || detail; } catch (_) {}
    throw new Error(detail);
  }
  return resp.json();
}

function loadLocalSettings() {
  try { return JSON.parse(localStorage.getItem(LS_KEY) || "{}"); } catch { return {}; }
}
function saveLocalSettings(obj) {
  const merged = { ...loadLocalSettings(), ...obj };
  localStorage.setItem(LS_KEY, JSON.stringify(merged));
}

/* ----------------------------- статус ----------------------------- */
async function refreshStatus() {
  try {
    const s = await api("/api/status");
    const dot = $("statusDot");
    const txt = $("statusText");
    if (s.comfyui_running) {
      dot.className = "dot ok";
      txt.textContent = "ComfyUI работает";
      $("startComfyBtn").classList.add("hidden");
    } else if (s.comfyui_found) {
      dot.className = "dot warn";
      txt.textContent = "ComfyUI найден, но не запущен";
      $("startComfyBtn").classList.remove("hidden");
    } else {
      dot.className = "dot err";
      txt.textContent = "ComfyUI не найден";
      $("startComfyBtn").classList.remove("hidden");
    }
    // Подтягиваем настройки в форму.
    if (s.settings) {
      $("setComfyPath").value = s.settings.comfyui_path || "";
      $("setComfyUrl").value = s.settings.comfyui_url || "";
      if (s.settings.tts_engine) $("ttsEngine").value = s.settings.tts_engine;
      if (s.settings.language) $("language").value = s.settings.language;
      if (s.settings.last_text && !$("textInput").value) $("textInput").value = s.settings.last_text;
    }
  } catch (e) {
    $("statusDot").className = "dot err";
    $("statusText").textContent = "Backend недоступен";
  }
}

/* ----------------------------- фото ----------------------------- */
function setupPhoto() {
  const drop = $("photoDrop");
  const input = $("photoInput");
  drop.addEventListener("click", () => input.click());
  ["dragover", "dragenter"].forEach((ev) =>
    drop.addEventListener(ev, (e) => { e.preventDefault(); drop.classList.add("drag"); }));
  ["dragleave", "drop"].forEach((ev) =>
    drop.addEventListener(ev, (e) => { e.preventDefault(); drop.classList.remove("drag"); }));
  drop.addEventListener("drop", (e) => {
    if (e.dataTransfer.files.length) uploadPhoto(e.dataTransfer.files[0]);
  });
  input.addEventListener("change", () => { if (input.files.length) uploadPhoto(input.files[0]); });
}

async function uploadPhoto(file) {
  hideBanner();
  const fd = new FormData();
  fd.append("file", file);
  try {
    const r = await api("/api/upload/photo", { method: "POST", body: fd });
    state.photoPath = r.path;
    const img = $("photoPreview");
    img.src = r.url;
    img.classList.remove("hidden");
    $("photoEmpty").classList.add("hidden");
  } catch (e) { showBanner("Ошибка загрузки фото: " + e.message); }
}

/* ----------------------------- голос ----------------------------- */
function setupVoice() {
  $("voiceUploadBtn").addEventListener("click", () => $("voiceInput").click());
  $("voiceInput").addEventListener("change", () => {
    if ($("voiceInput").files.length) uploadVoice($("voiceInput").files[0]);
  });
  $("recordBtn").addEventListener("click", toggleRecording);
}

async function uploadVoice(file) {
  hideBanner();
  const fd = new FormData();
  fd.append("file", file);
  try {
    const r = await api("/api/upload/voice", { method: "POST", body: fd });
    state.voicePath = r.path;
    const p = $("voicePlayer");
    p.src = r.url;
    p.classList.remove("hidden");
  } catch (e) { showBanner("Ошибка загрузки голоса: " + e.message); }
}

async function toggleRecording() {
  if (state.mediaRecorder && state.mediaRecorder.state === "recording") {
    state.mediaRecorder.stop();
    return;
  }
  try {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    state.recChunks = [];
    const mr = new MediaRecorder(stream);
    state.mediaRecorder = mr;
    mr.ondataavailable = (e) => state.recChunks.push(e.data);
    mr.onstop = async () => {
      clearInterval(state.recTimer);
      $("recTimer").classList.add("hidden");
      $("recordBtn").textContent = "🎙️ Записать (5–15 с)";
      stream.getTracks().forEach((t) => t.stop());
      const blob = new Blob(state.recChunks, { type: "audio/webm" });
      await uploadVoice(new File([blob], "recording.webm", { type: "audio/webm" }));
    };
    mr.start();
    state.recStart = Date.now();
    $("recordBtn").textContent = "⏹️ Остановить";
    $("recTimer").classList.remove("hidden");
    state.recTimer = setInterval(() => {
      const sec = (Date.now() - state.recStart) / 1000;
      $("recTimer").textContent = sec.toFixed(1) + " с";
      if (sec >= 15) mr.stop(); // авто-стоп на 15 сек
    }, 100);
  } catch (e) {
    showBanner("Нет доступа к микрофону: " + e.message);
  }
}

/* ----------------------------- генерация ----------------------------- */
function setupGenerate() {
  $("generateBtn").addEventListener("click", startGeneration);
  $("repeatBtn").addEventListener("click", () => {
    $("cardResult").classList.add("hidden");
    window.scrollTo({ top: 0, behavior: "smooth" });
  });
}

async function startGeneration() {
  hideBanner();
  if (!state.photoPath) { showBanner("Сначала загрузите фото."); return; }
  const text = $("textInput").value.trim();
  if (!text) { showBanner("Введите текст для озвучки."); return; }

  saveLocalSettings({ tts_engine: $("ttsEngine").value, language: $("language").value, last_text: text });
  api("/api/settings", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ tts_engine: $("ttsEngine").value, language: $("language").value, last_text: text }),
  }).catch(() => {});

  $("generateBtn").disabled = true;
  $("progressBox").classList.remove("hidden");
  $("cardResult").classList.add("hidden");
  setProgress("Запуск…", 0.02);

  try {
    const r = await api("/api/generate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        photo_path: state.photoPath,
        voice_path: state.voicePath,
        text,
        tts_engine: $("ttsEngine").value,
        language: $("language").value,
      }),
    });
    openProgressSocket(r.job_id);
  } catch (e) {
    finishGeneration();
    showBanner("Не удалось запустить генерацию: " + e.message);
  }
}

function setProgress(text, frac) {
  $("progressText").textContent = text;
  $("barFill").style.width = Math.round((frac || 0) * 100) + "%";
}

function openProgressSocket(jobId) {
  const proto = location.protocol === "https:" ? "wss" : "ws";
  const ws = new WebSocket(`${proto}://${location.host}/ws/${jobId}`);
  state.ws = ws;
  ws.onmessage = (ev) => {
    const data = JSON.parse(ev.data);
    setProgress(data.message || "…", data.progress || 0);
    if (data.status === "done") {
      finishGeneration();
      showResult(data.result);
      showBanner("Аватар готов!", true);
      loadHistory();
    } else if (data.status === "error") {
      finishGeneration();
      showBanner("Ошибка генерации: " + (data.message || "неизвестно"));
      loadHistory();
    }
  };
  ws.onerror = () => { finishGeneration(); showBanner("Ошибка соединения WebSocket."); };
}

function finishGeneration() {
  $("generateBtn").disabled = false;
  $("progressBox").classList.add("hidden");
  if (state.ws) { try { state.ws.close(); } catch {} state.ws = null; }
}

function showResult(result) {
  if (!result || !result.video_url) return;
  $("cardResult").classList.remove("hidden");
  const v = $("resultVideo");
  v.src = result.video_url;
  $("downloadBtn").href = result.video_url;
  $("cardResult").scrollIntoView({ behavior: "smooth" });
}

/* ----------------------------- история ----------------------------- */
async function loadHistory() {
  try {
    const r = await api("/api/history");
    const grid = $("historyGrid");
    grid.innerHTML = "";
    if (!r.history.length) {
      grid.innerHTML = '<p class="empty-hint">Пока нет генераций.</p>';
      return;
    }
    for (const item of r.history) grid.appendChild(renderHistItem(item));
  } catch (e) { /* тихо */ }
}

function renderHistItem(item) {
  const el = document.createElement("div");
  el.className = "hist-item";
  const date = new Date(item.timestamp).toLocaleString("ru-RU");
  const media = item.video_url
    ? `<video src="${item.video_url}" muted></video>`
    : (item.photo_url ? `<img src="${item.photo_url}" alt="" />` : "");
  const badge = item.status === "done"
    ? '<span class="badge done">Готово</span>'
    : '<span class="badge error">Ошибка</span>';
  el.innerHTML = `
    ${media}
    <div class="hist-meta">
      <div class="t">${date} ${badge}</div>
      <div class="txt">${(item.text || "").slice(0, 80)}</div>
      ${item.error ? `<div class="t" style="color:#ef4444">${item.error}</div>` : ""}
    </div>
    <div class="hist-actions">
      ${item.video_url ? `<a class="btn btn-ghost" href="${item.video_url}" download>⬇️</a>` : ""}
      <button class="btn btn-ghost" data-del="${item.id}">🗑️</button>
    </div>`;
  el.querySelector("[data-del]").addEventListener("click", async () => {
    try { await api("/api/history/" + item.id, { method: "DELETE" }); loadHistory(); }
    catch (e) { showBanner("Не удалось удалить: " + e.message); }
  });
  return el;
}

/* ----------------------------- логи ----------------------------- */
function setupLogs() {
  $("toggleLogs").addEventListener("click", async () => {
    const box = $("logBox");
    if (box.classList.contains("hidden")) {
      box.classList.remove("hidden");
      $("toggleLogs").textContent = "Скрыть";
      await loadLogs();
    } else {
      box.classList.add("hidden");
      $("toggleLogs").textContent = "Показать";
    }
  });
  $("copyLogs").addEventListener("click", () => {
    navigator.clipboard.writeText($("logBox").textContent || "").then(
      () => showBanner("Логи скопированы в буфер обмена.", true),
      () => showBanner("Не удалось скопировать логи."));
  });
}

async function loadLogs() {
  try {
    const r = await api("/api/logs?limit=300");
    $("logBox").textContent = r.logs
      .map((l) => `${l.time} [${l.level}] ${l.message}`)
      .join("\n");
    $("logBox").scrollTop = $("logBox").scrollHeight;
  } catch (e) { $("logBox").textContent = "Не удалось загрузить логи: " + e.message; }
}

/* ----------------------------- настройки / ComfyUI ----------------------------- */
function setupSettings() {
  $("settingsBtn").addEventListener("click", () => $("settingsModal").classList.remove("hidden"));
  $("closeSettingsBtn").addEventListener("click", () => $("settingsModal").classList.add("hidden"));
  $("saveSettingsBtn").addEventListener("click", async () => {
    try {
      await api("/api/settings", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ comfyui_path: $("setComfyPath").value, comfyui_url: $("setComfyUrl").value }),
      });
      saveLocalSettings({ comfyui_path: $("setComfyPath").value, comfyui_url: $("setComfyUrl").value });
      $("settingsModal").classList.add("hidden");
      refreshStatus();
    } catch (e) { showBanner("Не удалось сохранить настройки: " + e.message); }
  });
  $("detectBtn").addEventListener("click", async () => {
    $("detectInfo").textContent = "Поиск…";
    try {
      const r = await api("/api/comfyui/detect", { method: "POST" });
      if (r.found) {
        $("setComfyPath").value = r.info.path;
        $("detectInfo").textContent = `Найдено: ${r.info.path}${r.info.portable ? " (portable)" : ""}`;
      } else {
        $("detectInfo").textContent = r.message || "ComfyUI не найден";
      }
    } catch (e) { $("detectInfo").textContent = "Ошибка поиска: " + e.message; }
  });

  $("startComfyBtn").addEventListener("click", async () => {
    $("startComfyBtn").disabled = true;
    showBanner("Запуск ComfyUI… это может занять до минуты.", true);
    try {
      const r = await api("/api/comfyui/start", { method: "POST" });
      showBanner(r.message, r.running);
    } catch (e) { showBanner("Ошибка запуска ComfyUI: " + e.message); }
    $("startComfyBtn").disabled = false;
    refreshStatus();
  });
}

/* ----------------------------- init ----------------------------- */
function init() {
  setupPhoto();
  setupVoice();
  setupGenerate();
  setupLogs();
  setupSettings();

  // Восстановление из localStorage до ответа сервера.
  const ls = loadLocalSettings();
  if (ls.tts_engine) $("ttsEngine").value = ls.tts_engine;
  if (ls.language) $("language").value = ls.language;
  if (ls.last_text) $("textInput").value = ls.last_text;

  refreshStatus();
  loadHistory();
  setInterval(refreshStatus, 15000);

  $("refreshHistory").addEventListener("click", loadHistory);
}

document.addEventListener("DOMContentLoaded", init);
