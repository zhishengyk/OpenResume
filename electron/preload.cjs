const { contextBridge, ipcRenderer } = require("electron");

const API_PORT = process.env.OPENRESUME_API_PORT || "38417";

contextBridge.exposeInMainWorld("openResumeDesktop", {
  apiBaseUrl: `http://127.0.0.1:${API_PORT}`,
  openExternal: async (url) =>
    ipcRenderer.invoke("desktop:open-external", url),
  openVerificationWindow: async (url, title = "Verification") =>
    ipcRenderer.invoke("desktop:open-verification-window", { url, title }),
});
