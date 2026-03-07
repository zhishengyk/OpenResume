const { contextBridge, shell } = require("electron");

const API_PORT = process.env.OPENRESUME_API_PORT || "38417";

contextBridge.exposeInMainWorld("openResumeDesktop", {
  apiBaseUrl: `http://127.0.0.1:${API_PORT}`,
  openExternal: (url) => shell.openExternal(url)
});
