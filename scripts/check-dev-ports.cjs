const net = require("net");

const ports = [
  { port: 4173, name: "Vite dev server" },
  { port: 38417, name: "FastAPI local API" },
];

function isPortBusy(port) {
  return new Promise((resolve) => {
    const socket = new net.Socket();

    socket.setTimeout(800);
    socket.once("connect", () => {
      socket.destroy();
      resolve(true);
    });
    socket.once("timeout", () => {
      socket.destroy();
      resolve(false);
    });
    socket.once("error", () => {
      socket.destroy();
      resolve(false);
    });

    socket.connect(port, "127.0.0.1");
  });
}

(async () => {
  const busy = [];

  for (const item of ports) {
    if (await isPortBusy(item.port)) {
      busy.push(item);
    }
  }

  if (busy.length === 0) {
    process.exit(0);
  }

  const details = busy
    .map((item) => `- port ${item.port} is already in use: ${item.name}`)
    .join("\n");

  process.stderr.write(
    [
      "Detected existing dev processes on required ports. Aborting new dev startup.",
      details,
      "Stop the old OpenResume / Vite / Python processes, then run npm.cmd run dev again.",
    ].join("\n") + "\n",
  );
  process.exit(1);
})().catch((error) => {
  process.stderr.write(`${error?.stack || String(error)}\n`);
  process.exit(1);
});
