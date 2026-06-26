const clientIdInput = document.getElementById("clientIdInput");
const connectButton = document.getElementById("connectButton");
const spotifyStatus = document.getElementById("spotifyStatus");
const lcdStatusLine = document.getElementById("lcdStatusLine");
const trackLine = document.getElementById("trackLine");
const messageLine = document.getElementById("messageLine");
const fpsInput = document.getElementById("fpsInput");
const saveFpsButton = document.getElementById("saveFpsButton");
const enableStartupButton = document.getElementById("enableStartupButton");
const disableStartupButton = document.getElementById("disableStartupButton");
const startupLine = document.getElementById("startupLine");
const fpsValue = document.getElementById("fpsValue");
const refreshButton = document.getElementById("refreshButton");
const trayStartupButton = document.getElementById("trayStartupButton");

function clampFps(value) {
  const fps = Number(value);
  if (!Number.isFinite(fps)) {
    return 10;
  }
  return Math.min(60, Math.max(10, Math.round(fps)));
}

function renderSettings(settings = {}) {
  const fps = clampFps(settings.lcdFps);
  if (document.activeElement !== fpsInput) {
    fpsInput.value = String(fps);
  }
  fpsValue.textContent = String(clampFps(fpsInput.value || fps));
  startupLine.textContent = `開機自啟動：${settings.launchAtStartup ? "已啟用" : "未啟用"}`;
  trayStartupButton.textContent = settings.startMinimizedToTray ? "已到托盤" : "開機到托盤";
  trayStartupButton.classList.toggle("active", Boolean(settings.startMinimizedToTray));
}

function setSpotifyStatus(state) {
  spotifyStatus.classList.remove("connected", "error");

  if (state.status === "playing" || state.connected) {
    spotifyStatus.textContent = "已連線";
    spotifyStatus.classList.add("connected");
    return;
  }

  if (state.status === "error") {
    spotifyStatus.textContent = "連線失敗";
    spotifyStatus.classList.add("error");
    return;
  }

  spotifyStatus.textContent = "未連線";
}

function applyState(state) {
  setSpotifyStatus(state);
  renderSettings(state.settings);
  lcdStatusLine.textContent = state.lcd?.message || "LCD bridge 尚未啟動";

  if (state.track) {
    trackLine.textContent = `${state.track.title || "Unknown Track"} - ${state.track.artist || ""}`;
    messageLine.textContent = state.track.lyrics ? "歌詞已載入，LCD 正在顯示。" : "已連線，正在等待歌詞。";
  } else {
    trackLine.textContent = state.message || "等待 Spotify";
    messageLine.textContent = state.message || "填入 Client ID 後開始連接。";
  }
}

connectButton.addEventListener("click", async () => {
  const spotifyClientId = clientIdInput.value.trim();
  if (!spotifyClientId) {
    messageLine.textContent = "請先輸入 Spotify Client ID。";
    clientIdInput.focus();
    return;
  }

  connectButton.disabled = true;
  connectButton.textContent = "正在連接...";
  messageLine.textContent = "正在開啟 Spotify 授權頁。";

  try {
    await window.lyricScreen.saveSettings({
      spotifyClientId,
      spotifyRedirectUri: "http://127.0.0.1:17321/callback",
      alwaysOnTop: false,
      lcdFps: clampFps(fpsInput.value),
    });
    await window.lyricScreen.connectSpotify();
  } catch (error) {
    messageLine.textContent = error?.message || "連接失敗，請確認 Client ID。";
  } finally {
    connectButton.disabled = false;
    connectButton.textContent = "儲存並連接 Spotify";
  }
});

saveFpsButton.addEventListener("click", async () => {
  const lcdFps = clampFps(fpsInput.value);
  fpsInput.value = String(lcdFps);
  fpsValue.textContent = String(lcdFps);
  await window.lyricScreen.saveSettings({ lcdFps });
  messageLine.textContent = `LCD FPS 已設定為 ${lcdFps}。`;
});

fpsInput.addEventListener("input", () => {
  fpsValue.textContent = String(clampFps(fpsInput.value));
});

enableStartupButton.addEventListener("click", async () => {
  const result = await window.lyricScreen.setStartup(true);
  startupLine.textContent = `開機自啟動：${result.launchAtStartup ? "已啟用" : "未啟用"}`;
});

disableStartupButton.addEventListener("click", async () => {
  const result = await window.lyricScreen.setStartup(false);
  startupLine.textContent = `開機自啟動：${result.launchAtStartup ? "已啟用" : "未啟用"}`;
});

refreshButton.addEventListener("click", async () => {
  refreshButton.disabled = true;
  refreshButton.textContent = "…";
  try {
    await window.lyricScreen.refresh();
    messageLine.textContent = "已刷新，下一次自動檢查會在 15 秒後進行。";
  } catch (error) {
    messageLine.textContent = error?.message || "刷新失敗。";
  } finally {
    refreshButton.disabled = false;
    refreshButton.textContent = "↻";
  }
});

trayStartupButton.addEventListener("click", async () => {
  const nextValue = !trayStartupButton.classList.contains("active");
  const result = await window.lyricScreen.setStartMinimizedToTray(nextValue);
  renderSettings(result);
});

window.lyricScreen.onState((state) => {
  applyState(state);
});

(async function boot() {
  const settings = await window.lyricScreen.getSettings();
  clientIdInput.value = settings.spotifyClientId || "";
  renderSettings(settings);
})();
