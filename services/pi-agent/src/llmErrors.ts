const OVERFLOW_MARKERS = [
  "context length",
  "maximum context",
  "context_length",
  "too many tokens",
  "token limit",
  "max_tokens",
  "reduce the length",
  "prompt is too long",
  "request too large",
  "上下文过长",
  "上下文长度",
  "超出最大",
  "超过最大",
  "token 超限",
];

export function isContextOverflowError(message: string | undefined | null): boolean {
  const text = String(message || "").trim().toLowerCase();
  if (!text) return false;
  return OVERFLOW_MARKERS.some((marker) => text.includes(marker));
}
