"use client";

import * as React from "react";

import { Badge } from "@/components/ui/badge";
import { Card, CardBody, CardHeader, CardTitle } from "@/components/ui/card";
import { EmptyState } from "@/components/ui/empty-state";
import { fmtNumber, fmtPct, ago } from "@/lib/format";
import type { AnomalyScoreRow } from "@/lib/types";
import { usePoll } from "@/lib/use-poll";

interface ScoreFeedProps {
  initial: AnomalyScoreRow[];
  /** REST endpoint to poll. */
  apiPath?: string;
  /** Cap on rows displayed in the live feed. */
  capacity?: number;
  /** Poll interval in ms. */
  intervalMs?: number;
}

export function ScoreFeed({
  initial,
  apiPath = "/api/scores?limit=50",
  capacity = 50,
  intervalMs = 1_500,
}: ScoreFeedProps) {
  const [rows, setRows] = React.useState<AnomalyScoreRow[]>(initial);

  const handle = React.useCallback(
    (data: { rows?: AnomalyScoreRow[] }) => {
      const next = data?.rows ?? [];
      if (next.length === 0) return;
      setRows((prev) => {
        // Merge by id, keep DESC ts ordering, cap at capacity.
        const seen = new Set(prev.map((r) => r.id));
        const merged = [...next.filter((r) => !seen.has(r.id)), ...prev];
        merged.sort((a, b) => Number(b.ts_ns) - Number(a.ts_ns));
        return merged.slice(0, capacity);
      });
    },
    [capacity],
  );

  usePoll<{ rows?: AnomalyScoreRow[] }>(apiPath, intervalMs, handle);

  return (
    <Card>
      <CardHeader>
        <CardTitle>Live anomaly scores</CardTitle>
      </CardHeader>
      <CardBody>
        {rows.length === 0 ? (
          <EmptyState
            title="Waiting for scores…"
            description="The classifier publishes a row per scored frame onto anomaly_score_log."
          />
        ) : (
          <ul className="divide-y divide-white/5 text-sm">
            {rows.map((row) => {
              const highRisk = row.score >= 0.85;
              return (
                <li
                  key={row.id}
                  className="py-2 flex items-center justify-between gap-3"
                >
                  <span className="font-mono text-white/80 w-16">
                    {row.symbol}
                  </span>
                  <span className="font-mono text-white/60 flex-1">
                    {fmtPct(row.score)}{" "}
                    <span className="text-white/30">({fmtNumber(row.score, 3)})</span>
                  </span>
                  <Badge tone={highRisk ? "red" : "blue"}>
                    {highRisk ? "high risk" : "ok"}
                  </Badge>
                  <span className="text-xs text-white/40 w-16 text-right">
                    {ago(row.inserted_at)}
                  </span>
                </li>
              );
            })}
          </ul>
        )}
      </CardBody>
    </Card>
  );
}
