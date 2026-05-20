"use client";

import * as React from "react";
import ReactMarkdown from "react-markdown";

import { ReceiptCard } from "@/components/receipt";
import { ReplayModal } from "@/components/replay-modal";
import { Badge } from "@/components/ui/badge";
import { Card, CardBody, CardHeader, CardTitle } from "@/components/ui/card";
import { EmptyState } from "@/components/ui/empty-state";
import { fmtNumber, ago } from "@/lib/format";
import type { AgentReportRow } from "@/lib/types";
import { usePoll } from "@/lib/use-poll";

interface ReportInspectorProps {
  initial: AgentReportRow[];
  /** REST endpoint to poll. */
  apiPath?: string;
  capacity?: number;
  intervalMs?: number;
}

export function ReportInspector({
  initial,
  apiPath = "/api/reports?limit=20",
  capacity = 20,
  intervalMs = 3_000,
}: ReportInspectorProps) {
  const [rows, setRows] = React.useState<AgentReportRow[]>(initial);
  const [selectedId, setSelectedId] = React.useState<number | null>(
    initial[0]?.id ?? null,
  );
  const [replayRow, setReplayRow] = React.useState<AgentReportRow | null>(null);

  const handle = React.useCallback(
    (data: { rows?: AgentReportRow[] }) => {
      const next = data?.rows ?? [];
      if (next.length === 0) return;
      setRows((prev) => {
        const seen = new Set(prev.map((r) => r.id));
        const merged = [...next.filter((r) => !seen.has(r.id)), ...prev];
        merged.sort((a, b) => Number(b.ts_ns) - Number(a.ts_ns));
        return merged.slice(0, capacity);
      });
      setSelectedId((curr) => curr ?? next[0]?.id ?? null);
    },
    [capacity],
  );

  usePoll<{ rows?: AgentReportRow[] }>(apiPath, intervalMs, handle);

  const selected = rows.find((r) => r.id === selectedId) ?? rows[0];

  return (
    <Card>
      <CardHeader>
        <CardTitle>Agent reasoning log</CardTitle>
      </CardHeader>
      <CardBody>
        {rows.length === 0 ? (
          <EmptyState
            title="No agent reports yet"
            description="The Settlement & Enforcer writes one row per case into agent_report. Trigger a high-risk frame to populate."
          />
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-[200px,1fr] gap-4">
            <ol className="text-sm divide-y divide-white/5 max-h-80 overflow-auto pr-1">
              {rows.map((row) => (
                <li key={row.id}>
                  <button
                    onClick={() => setSelectedId(row.id)}
                    className={`w-full text-left py-2 px-2 rounded transition ${
                      row.id === selected?.id
                        ? "bg-white/5 text-white"
                        : "text-white/70 hover:bg-white/5"
                    }`}
                  >
                    <div className="flex items-center justify-between gap-2">
                      <span className="font-mono text-xs">{row.symbol}</span>
                      <Badge tone={row.enforced ? "red" : "blue"}>
                        {row.enforced ? "enforced" : "review"}
                      </Badge>
                    </div>
                    <div className="text-[10px] text-white/40 mt-0.5">
                      conf {fmtNumber(row.confidence ?? 0, 2)} · {ago(row.created_at)}
                    </div>
                  </button>
                </li>
              ))}
            </ol>
            <div className="space-y-3">
              {selected ? (
                <>
                  <div className="flex items-center justify-end">
                    <button
                      onClick={() => setReplayRow(selected)}
                      className="rounded-md bg-accent-green/15 hover:bg-accent-green/25 ring-1 ring-inset ring-accent-green/30 text-accent-green text-xs font-medium px-3 py-1.5 transition"
                    >
                      ▶ Replay this case
                    </button>
                  </div>
                  <ReceiptCard row={selected} hideContext />
                  <div className="rounded-md bg-bg-subtle/70 border border-white/5 p-4 overflow-auto max-h-[24rem]">
                    <article className="prose prose-invert prose-sm max-w-none prose-headings:font-semibold prose-headings:tracking-tight prose-h1:text-base prose-h2:text-sm prose-h2:uppercase prose-h2:tracking-[0.16em] prose-h2:text-white/60 prose-code:text-accent-amber">
                      <ReactMarkdown>{selected.rationale_md || "_(empty)_"}</ReactMarkdown>
                    </article>
                  </div>
                </>
              ) : (
                <EmptyState title="Select a case" />
              )}
            </div>
          </div>
        )}
      </CardBody>
      <ReplayModal
        row={replayRow}
        open={replayRow !== null}
        onClose={() => setReplayRow(null)}
      />
    </Card>
  );
}
