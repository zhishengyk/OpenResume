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

  if (mode === "review_in_browser") {
    return "\u6d4f\u89c8\u804c\u4f4d";
  }

  return "\u4ec5\u63a8\u8350";
}

export function pillLabel(label: string) {
  const lowered = label.toLowerCase();
  const mapping: Record<string, string> = {
    armed: "\u5df2\u5c31\u7eea",
    blocked: "\u5df2\u963b\u585e",
    ready: "\u5df2\u5b8c\u6210",
    running: "\u8fdb\u884c\u4e2d",
    failed: "\u5931\u8d25",
    queued: "\u6392\u961f\u4e2d",
    prepared: "\u5df2\u51c6\u5907",
    cancelled: "\u5df2\u53d6\u6d88",
    draft: "\u8349\u7a3f",
    boss: "Boss\u76f4\u8058",
    liepin: "\u730e\u8058",
    fresh: "\u65b0\u5206\u6790",
    cached: "\u7f13\u5b58",
    "local api": "\u672c\u5730\u63a5\u53e3",
    "boss adapter": "Boss\u9002\u914d\u5668",
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
      return "bg-signal/20 text-ink";
    default:
      return "bg-ink/10 text-ink";
  }
}

