const { app, BrowserWindow, shell } = require("electron");
const { spawn } = require("child_process");
const path = require("path");
const fs = require("fs");

const API_PORT = process.env.OPENRESUME_API_PORT || "8000";
const RENDERER_URL = process.env.OPENRESUME_RENDERER_URL || "http://127.0.0.1:5173";
let backendProcess = null;

function logBackend(stream, label) {
  stream?.on("data", (chunk) => {
    process.stdout.write(`[backend:${label}] ${chunk}`);
  });
}

function backendCommand() {
  if (app.isPackaged) {
    const packagedExe = path.join(process.resourcesPath, "backend", "openresume-api.exe");
    if (fs.existsSync(packagedExe)) {
      return { command: packagedExe, args: [] };
    }
  }

  return {
    command: process.env.OPENRESUME_PYTHON || "python",
    args: ["-m", "openresume_api"]
  };
}

function backendCwd() {
  if (app.isPackaged) {
    return path.join(process.resourcesPath, "backend");
  }

  return path.join(__dirname, "..", "backend");
}

function startBackend() {
  if (backendProcess) {
    return;
  }

  const { command, args } = backendCommand();
  backendProcess = spawn(command, args, {
    cwd: backendCwd(),
    env: {
      ...process.env,
      OPENRESUME_API_PORT: API_PORT,
      OPENRESUME_STORAGE_DIR: path.join(app.getPath("userData"), "storage")
    },
    stdio: ["ignore", "pipe", "pipe"]
  });

  logBackend(backendProcess.stdout, "stdout");
  logBackend(backendProcess.stderr, "stderr");

  backendProcess.on("exit", (code) => {
    backendProcess = null;
    process.stdout.write(`[backend] exited with code ${code}\n`);
  });
}

async function waitForBackend() {
  const healthUrl = `http://127.0.0.1:${API_PORT}/health`;
  const startedAt = Date.now();

  while (Date.now() - startedAt < 15000) {
    try {
      const response = await fetch(healthUrl);
      if (response.ok) {
        return;
      }
    } catch (error) {
      // Backend is still starting.
    }

    await new Promise((resolve) => setTimeout(resolve, 500));
  }

  throw new Error("Backend did not become healthy in time.");
}

function createWindow() {
  const mainWindow = new BrowserWindow({
    width: 1480,
    height: 980,
    minWidth: 1180,
    minHeight: 760,
    backgroundColor: "#f5f0e8",
    autoHideMenuBar: true,
    webPreferences: {
      preload: path.join(__dirname, "preload.cjs"),
      contextIsolation: true,
      nodeIntegration: false
    }
  });

  mainWindow.webContents.setWindowOpenHandler(({ url }) => {
    shell.openExternal(url);
    return { action: "deny" };
  });

  if (app.isPackaged) {
    mainWindow.loadFile(path.join(__dirname, "..", "dist", "index.html"));
    return;
  }

  mainWindow.loadURL(RENDERER_URL);
}

app.whenReady().then(async () => {
  startBackend();
  await waitForBackend();
  createWindow();

  app.on("activate", () => {
    if (BrowserWindow.getAllWindows().length === 0) {
      createWindow();
    }
  });
});

app.on("window-all-closed", () => {
  if (process.platform !== "darwin") {
    app.quit();
  }
});

app.on("before-quit", () => {
  if (backendProcess) {
    backendProcess.kill();
  }
});

