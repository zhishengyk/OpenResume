const net = require("net");
const { spawn } = require("child_process");

const RENDERER_PORT = 4173;
const WAIT_TIMEOUT_MS = 15000;
const electronBinary = require("electron");

function waitForPort(port, timeoutMs) {
  const startedAt = Date.now();

  return new Promise((resolve, reject) => {
    const tryConnect = () => {
      const socket = new net.Socket();

      socket.setTimeout(800);
      socket.once("connect", () => {
        socket.destroy();
        resolve();
      });
      socket.once("timeout", () => {
        socket.destroy();
        retryOrFail();
      });
      socket.once("error", () => {
        socket.destroy();
        retryOrFail();
      });

      socket.connect(port, "127.0.0.1");
    };

    const retryOrFail = () => {
      if (Date.now() - startedAt >= timeoutMs) {
        reject(new Error(`renderer port ${port} did not become ready in time`));
        return;
      }
      setTimeout(tryConnect, 300);
    };

    tryConnect();
  });
}

async function main() {
  await waitForPort(RENDERER_PORT, WAIT_TIMEOUT_MS);

  const childEnv = { ...process.env };
  delete childEnv.ELECTRON_RUN_AS_NODE;

  const child = spawn(electronBinary, ["."], {
    stdio: "inherit",
    env: childEnv,
  });

  child.on("exit", (code) => {
    process.exit(code ?? 0);
  });
}

main().catch((error) => {
  process.stderr.write(`${error?.stack || String(error)}\n`);
  process.exit(1);
});
