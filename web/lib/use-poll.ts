"use client";

import * as React from "react";

/**
 * Polls `url` every `intervalMs`, calls `onData` with the parsed JSON.
 * - Pauses while the tab is hidden (saves Supabase round-trips when the
 *   dashboard is left open on an inactive tab).
 * - Aborts in-flight fetches on unmount.
 * - Silently swallows errors so a transient 5xx doesn't break the UI;
 *   the next interval simply retries.
 *
 * Replaces the EventSource path we used to have at /api/stream — Vercel
 * serverless functions can't hold long-lived streams open without
 * hitting the per-function execution-time ceiling.
 */
export function usePoll<T>(
  url: string,
  intervalMs: number,
  onData: (data: T) => void,
): void {
  // Stable callback ref so we can re-fetch without re-creating the
  // interval on every render-induced identity change of onData.
  const cb = React.useRef(onData);
  React.useEffect(() => {
    cb.current = onData;
  }, [onData]);

  React.useEffect(() => {
    let cancelled = false;
    let controller: AbortController | null = null;

    const tick = async () => {
      if (typeof document !== "undefined" && document.hidden) return;
      controller?.abort();
      controller = new AbortController();
      try {
        const res = await fetch(url, {
          cache: "no-store",
          signal: controller.signal,
        });
        if (!res.ok) return;
        const data = (await res.json()) as T;
        if (!cancelled) cb.current(data);
      } catch {
        // Network blips / aborts / JSON errors — try again next tick.
      }
    };

    tick();
    const id = window.setInterval(tick, intervalMs);
    return () => {
      cancelled = true;
      controller?.abort();
      window.clearInterval(id);
    };
  }, [url, intervalMs]);
}
