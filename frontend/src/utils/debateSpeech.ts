import { DebateStage } from "../types";

const STAGE_KEY_ALIASES: Record<DebateStage, string[]> = {
  opening: ["opening_statement", "开场陈词"],
  free_debate: ["free_debate_speech", "自由辩论发言", "自由辩论"],
  closing: ["closing_speech", "closing_statement", "总结陈词", "总结陈词内容"],
  summary: ["summary", "总结"],
};

const JSON_STYLE_QUOTES = new Map<string, string>([
  ["“", '"'],
  ["”", '"'],
  ["‘", "'"],
  ["’", "'"],
  ["：", ":"],
]);

function normalizeJsonLikeText(input: string): string {
  let output = input.trim();
  for (const [from, to] of JSON_STYLE_QUOTES) {
    output = output.split(from).join(to);
  }
  if (output.includes("```")) {
    const parts = output.split("```");
    if (parts.length > 1) {
      output = parts[1];
    }
    output = output.trim();
    if (output.startsWith("json")) {
      output = output.slice(4).trim();
    }
  }
  return output.trim();
}

function extractFromParsedObject(value: unknown, stage?: DebateStage): string | null {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    return null;
  }

  const record = value as Record<string, unknown>;
  const keys = stage ? STAGE_KEY_ALIASES[stage] : [];

  for (const key of keys) {
    const candidate = record[key];
    if (typeof candidate === "string" && candidate.trim()) {
      return candidate.trim();
    }
  }

  if (Object.keys(record).length === 1) {
    const onlyValue = Object.values(record)[0];
    if (typeof onlyValue === "string" && onlyValue.trim()) {
      return onlyValue.trim();
    }
  }

  return null;
}

function extractByKeyPattern(input: string, keys: string[]): string | null {
  for (const key of keys) {
    const escapedKey = key.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
    const quotedPattern = new RegExp(
      `["']?${escapedKey}["']?\\s*:\\s*["']?([\\s\\S]*)$`,
      "i",
    );
    const match = input.match(quotedPattern);
    if (!match) {
      continue;
    }

    let extracted = match[1].trim();
    extracted = extracted.replace(/["']?\s*}\s*$/, "").trim();
    extracted = extracted.replace(/^[\s"']+/, "").trim();
    if (extracted) {
      return extracted;
    }
    return "";
  }
  return null;
}

export function extractDebateSpeechContent(raw: string, stage?: DebateStage): string {
  const normalized = normalizeJsonLikeText(raw);
  if (!normalized) {
    return "";
  }

  try {
    const parsed = JSON.parse(normalized);
    const extracted = extractFromParsedObject(parsed, stage);
    if (extracted !== null) {
      return extracted;
    }
  } catch {
    // Fall through to best-effort object extraction.
  }

  if (normalized.startsWith("{")) {
    const keys = stage ? STAGE_KEY_ALIASES[stage] : [];
    const extracted = extractByKeyPattern(normalized, keys);
    if (extracted !== null) {
      return extracted;
    }
  }

  return raw;
}
