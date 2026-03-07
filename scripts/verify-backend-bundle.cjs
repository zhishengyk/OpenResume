const fs = require("fs");
const path = require("path");

const bundlePath = path.join(__dirname, "..", "backend", "dist", "openresume-api.exe");

if (!fs.existsSync(bundlePath)) {
  console.error(
    [
      "缺少后端可执行文件。",
      "请先打包后端，再执行桌面端打包。",
      "",
      "建议执行：",
      "  cd backend",
      "  python -m pip install -e .[packaging]",
      "  pyinstaller --onefile --name openresume-api openresume_api/__main__.py",
    ].join("\n"),
  );
  process.exit(1);
}
