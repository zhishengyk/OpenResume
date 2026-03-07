const fs = require("fs");
const path = require("path");

const bundlePath = path.join(__dirname, "..", "backend", "dist", "openresume-api.exe");

if (!fs.existsSync(bundlePath)) {
  console.error(
    [
      "Missing backend executable bundle.",
      "Build it before packaging the desktop app.",
      "",
      "Suggested command:",
      "  cd backend",
      "  pip install -e .[packaging]",
      "  pyinstaller --onefile --name openresume-api openresume_api/__main__.py",
    ].join("\n"),
  );
  process.exit(1);
}

