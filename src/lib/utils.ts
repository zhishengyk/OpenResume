import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

export function splitCommaValues(input: string) {
  return input
    .split(/[,\n]/)
    .map((value) => value.trim())
    .filter(Boolean);
}

export function modeLabel(mode: string) {
  if (mode === "guided_apply") {
    return "\u5f15\u5bfc\u6295\u9012";
  }

  if (mode === "semi_auto") {
    return "\u534a\u81ea\u52a8\u6295\u9012";
  }

  if (mode === "auto_submit") {
    return "\u5168\u81ea\u52a8\u63d0\u4ea4";
  }

  if (mode === "review_in_browser") {
    return "\u6253\u5f00\u804c\u4f4d\u9875";
  }

  return "\u4ec5\u63a8\u8350";
}

export function pillLabel(label: string) {
  const lowered = label.toLowerCase();
  const mapping: Record<string, string> = {
    armed: "\u5df2\u542f\u7528",
    blocked: "\u5df2\u963b\u585e",
    ready: "\u5df2\u5b8c\u6210",
    running: "\u8fdb\u884c\u4e2d",
    pending: "\u7b49\u5f85\u4e2d",
    failed: "\u5931\u8d25",
    queued: "\u6392\u961f\u4e2d",
    prepared: "\u5df2\u51c6\u5907",
    submitted: "\u5df2\u63d0\u4ea4",
    cancelled: "\u5df2\u53d6\u6d88",
    active: "\u53ef\u7528",
    inactive: "\u505c\u7528",
    missing: "\u65e0\u7f13\u5b58",
    error: "\u7f13\u5b58\u5f02\u5e38",
    default: "\u9ed8\u8ba4",
    draft: "\u8349\u7a3f",
    official: "\u62db\u8058\u5b98\u7f51",
    experienced: "\u793e\u62db",
    campus: "\u6821\u62db",
    internship: "\u5b9e\u4e60",
    bytedance: "\u5b57\u8282\u8df3\u52a8",
    tencent: "\u817e\u8baf",
    taobao: "\u6dd8\u5929\u96c6\u56e2",
    alibaba_holding: "\u963f\u91cc\u63a7\u80a1",
    meituan: "\u7f8e\u56e2",
    pdd: "\u62fc\u591a\u591a",
    aliyun: "\u963f\u91cc\u4e91",
    kuaishou: "\u5feb\u624b",
    jd: "\u4eac\u4e1c",
    ant: "\u8682\u8681\u96c6\u56e2",
    amap: "\u9ad8\u5fb7\u5730\u56fe",
    eleme: "\u997f\u4e86\u4e48",
    aidc: "\u963f\u91cc\u56fd\u9645",
    xiaohongshu: "\u5c0f\u7ea2\u4e66",
    bilibili: "\u54d4\u54e9\u54d4\u54e9",
    dewu: "\u5f97\u7269",
    freshippo: "\u76d2\u9a6c",
    mihoyo: "\u7c73\u54c8\u6e38",
    boss: "Boss",
    fresh: "\u5b9e\u65f6",
    cached: "\u7f13\u5b58",
    heuristic: "\u542f\u53d1\u5f0f",
    openai_compatible: "OpenAI",
    "local api": "\u672c\u5730 API",
    "platform modules": "\u5e73\u53f0\u6a21\u5757",
    needs_verification: "\u7b49\u5f85\u9a8c\u8bc1",
  };

  return mapping[lowered] || label;
}

export function statusTone(status: string) {
  switch (status) {
    case "ready":
    case "prepared":
    case "submitted":
    case "active":
    case "default":
      return "bg-mint/20 text-ink";
    case "blocked":
    case "failed":
      return "bg-ember/15 text-ember";
    case "running":
    case "queued":
    case "needs_verification":
      return "bg-signal/20 text-ink";
    default:
      return "bg-ink/10 text-ink";
  }
}

/**
 * 格式化 UTC 时间字符串为本地时间显示
 * 后端返回的时间是 UTC 时间但不带时区标识，需要手动添加 'Z' 后缀
 */
export function formatDateTime(utcTimeString: string): string {
  if (!utcTimeString) return "";
  // 如果时间字符串不包含时区信息，添加 'Z' 表示 UTC
  const timeString = utcTimeString.endsWith("Z") ? utcTimeString : `${utcTimeString}Z`;
  const date = new Date(timeString);
  return date.toLocaleString("zh-CN", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hour12: false,
  });
}

/**
 * 格式化 UTC 时间字符串为本地时间（仅时分秒）
 */
export function formatTime(utcTimeString: string): string {
  if (!utcTimeString) return "";
  const timeString = utcTimeString.endsWith("Z") ? utcTimeString : `${utcTimeString}Z`;
  const date = new Date(timeString);
  return date.toLocaleTimeString("zh-CN", {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hour12: false,
  });
}
