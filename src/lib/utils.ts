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
    return "引导投递";
  }

  if (mode === "review_in_browser") {
    return "打开职位页";
  }

  return "仅推荐";
}

export function pillLabel(label: string) {
  const lowered = label.toLowerCase();
  const mapping: Record<string, string> = {
    armed: "已启用",
    blocked: "已阻塞",
    ready: "已完成",
    running: "进行中",
    pending: "等待中",
    failed: "失败",
    queued: "排队中",
    prepared: "已准备",
    cancelled: "已取消",
    draft: "草稿",
    official: "招聘官网",
    boss: "Boss",
    fresh: "实时",
    cached: "缓存",
    heuristic: "启发式",
    openai_compatible: "OpenAI",
    "local api": "本地 API",
    "platform modules": "平台模块",
    needs_verification: "等待验证",
  };

  return mapping[lowered] || label;
}

export function statusTone(status: string) {
  switch (status) {
    case "ready":
    case "prepared":
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
