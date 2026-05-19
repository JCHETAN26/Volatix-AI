"use client";

import * as React from "react";

import { Badge } from "@/components/ui/badge";
import { Card, CardBody, CardHeader, CardTitle } from "@/components/ui/card";
import { EmptyState } from "@/components/ui/empty-state";
import { fmtNumber, fmtPct, ago } from "@/lib/format";
import type { AnomalyScoreRow } from "@/lib/types";

interface ScoreFeedProps {
  initial: AnomalyScoreRow[];
  /** Polling URL for SSE; defaults to /api/stream. */
  streamPath?: string;
  /** Cap on rows displayed in the live feed. */
  capacity?: number;
}

export function ScoreFeed({
  initial,
  streamPath = "/api/stream",
  capacity = 50,
}: ScoreFeedProps) {
  const [rows, setRows] = React.useState<AnomalyScoreRow[]>(initial);

  React.useEffect(() => {
    const src = new EventSource(streamPath);
    src.addEventListener("score", (e) => {
      try {
        const row = JSON.parse((e as MessageEvent).data) as AnomalyScoreRow;
        setRows((prev) => {
          if (prev.some((r) => r.id === row.id)) return prev;
          return [row, ...prev].slice(0, capacity);
        });
      } catch {
        /* drop malformed message */
      }
    });
    return () => src.close();
  }, [streamPath, capacity]);

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
