const { contextBridge, ipcRenderer } = require("electron");

contextBridge.exposeInMainWorld("lyricScreen", {
  getSettings: () => ipcRenderer.invoke("settings:get"),
  listDisplays: () => ipcRenderer.invoke("display:list"),
  saveSettings: (partial) => ipcRenderer.invoke("settings:save", partial),
  connectSpotify: () => ipcRenderer.invoke("spotify:connect"),
  refresh: () => ipcRenderer.invoke("app:refresh"),
  setStartup: (value) => ipcRenderer.invoke("startup:set", value),
  setStartMinimizedToTray: (value) => ipcRenderer.invoke("tray:set-start-minimized", value),
  setAlwaysOnTop: (value) => ipcRenderer.invoke("window:set-always-on-top", value),
  setFullscreen: (value) => ipcRenderer.invoke("window:set-fullscreen", value),
  setDisplay: (displayId, fullscreen) => ipcRenderer.invoke("window:set-display", displayId, fullscreen),
  syncDisplay: (fullscreen) => ipcRenderer.invoke("window:sync-display", fullscreen),
  onState: (handler) => {
    const wrapped = (_, state) => handler(state);
    ipcRenderer.on("player-state", wrapped);
    return () => ipcRenderer.removeListener("player-state", wrapped);
  },
});
