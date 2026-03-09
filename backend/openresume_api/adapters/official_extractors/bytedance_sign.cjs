const fs = require("fs");
const vm = require("vm");

function readInput() {
  const raw = fs.readFileSync(0, "utf8");
  return JSON.parse(raw || "{}");
}

function buildSandbox(input) {
  const href = input.href || "https://jobs.bytedance.com/campus/position";
  const url = new URL(href);
  const sandbox = {
    module: { exports: {} },
    exports: {},
    navigator: {
      userAgent: input.user_agent || "",
      appVersion: input.user_agent || "",
      language: "zh-CN",
    },
    location: {
      href,
      search: url.search,
      hash: url.hash,
      pathname: url.pathname,
      hostname: url.hostname,
    },
    document: {
      referrer: input.referrer || href,
      cookie: "",
    },
    screen: {
      width: 1920,
      height: 1080,
      colorDepth: 24,
    },
    setTimeout,
    clearTimeout,
    console,
    Math,
    Date,
    String,
    Number,
    Boolean,
    Array,
    Object,
    RegExp,
    JSON,
    encodeURIComponent,
    decodeURIComponent,
  };
  sandbox.window = sandbox;
  sandbox.globalThis = sandbox;
  sandbox.self = sandbox;
  sandbox.exports = sandbox.module.exports;
  return sandbox;
}

function main() {
  const input = readInput();
  const sandbox = buildSandbox(input);
  const fn = vm.runInNewContext(`(${input.module_source})`, sandbox, { timeout: 5000 });
  fn(sandbox.module, sandbox.module.exports);
  const sign = sandbox.module.exports.sign;
  const signatures = (input.requests || []).map((request) => sign(request));
  process.stdout.write(JSON.stringify({ signatures }));
}

main();
