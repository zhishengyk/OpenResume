const { spawnSync } = require("child_process");

const API_PORT = 38417;

function listListeningPids(port) {
  const result = spawnSync("netstat", ["-ano", "-p", "tcp"], {
    encoding: "utf8",
  });
  if (result.status !== 0) {
    throw new Error(result.stderr || "failed to run netstat");
  }

  const lines = result.stdout.split(/\r?\n/);
  const pids = new Set();

  for (const line of lines) {
    const trimmed = line.trim();
    if (!trimmed.startsWith("TCP")) {
      continue;
    }
    if (!trimmed.includes(`:${port}`)) {
      continue;
    }
    if (!trimmed.includes("LISTENING")) {
      continue;
    }
    const parts = trimmed.split(/\s+/);
    const pid = Number(parts[parts.length - 1]);
    if (Number.isInteger(pid) && pid > 0 && pid !== process.pid) {
      pids.add(pid);
    }
  }

  return [...pids];
}

function killPid(pid) {
  const result = spawnSync("taskkill", ["/PID", String(pid), "/F"], {
    encoding: "utf8",
  });
  return result.status === 0;
}

try {
  const pids = listListeningPids(API_PORT);
  if (pids.length === 0) {
    process.stdout.write(`port ${API_PORT} is already free\n`);
    process.exit(0);
  }

  const failed = [];
  for (const pid of pids) {
    const ok = killPid(pid);
    if (ok) {
      process.stdout.write(`killed pid ${pid} on port ${API_PORT}\n`);
    } else {
      failed.push(pid);
    }
  }

  if (failed.length > 0) {
    process.stderr.write(
      `failed to kill processes on port ${API_PORT}: ${failed.join(", ")}\n`,
    );
    process.exit(1);
  }

  process.exit(0);
} catch (error) {
  process.stderr.write(`${error?.stack || String(error)}\n`);
  process.exit(1);
}
