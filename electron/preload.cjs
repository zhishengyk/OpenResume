const { contextBridge, shell } = require("electron");

contextBridge.exposeInMainWorld("openResumeDesktop", {
  apiBaseUrl: "http://127.0.0.1:8000",
  openExternal: (url) => shell.openExternal(url)
});
