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
    return "Guided Apply";
  }

  if (mode === "review_in_browser") {
    return "Review";
  }

  return "Recommend";
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

