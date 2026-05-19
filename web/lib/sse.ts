// SSE encoder used by app/api/stream/route.ts. Kept tiny so we don't pull
// in a wire-format dep just for "data: ...\n\n".

export function sseEvent(data: unknown, event?: string): Uint8Array {
  const lines: string[] = [];
  if (event) lines.push(`event: ${event}`);
  lines.push(`data: ${JSON.stringify(data)}`);
  lines.push("", "");
  return new TextEncoder().encode(lines.join("\n"));
}

export function sseComment(text: string): Uint8Array {
  return new TextEncoder().encode(`: ${text}\n\n`);
}
