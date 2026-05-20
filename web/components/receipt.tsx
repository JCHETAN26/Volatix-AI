"use client";

import * as React from "react";

import { Badge } from "@/components/ui/badge";
import { Card, CardBody, CardHeader, CardTitle } from "@/components/ui/card";
import { EmptyState } from "@/components/ui/empty-state";
import { IndustryContext } from "@/components/industry-context";
import { cn } from "@/lib/cn";
import {
  computeTimeline,
  fmtDuration,
  fmtOffsetLabel,
  type Stage,
  type Timeline,
} from "@/lib/timeline";
import type { AgentReportRow } from "@/lib/types";
import { usePoll } from "@/lib/use-poll";

interface ReceiptProps {
  /** Initial value from SSR. */
  initial: AgentReportRow | null;
  /** REST endpoint to poll for the latest enforced case. */
  apiPath?: string;
  className?: string;
  /** Hide the industry context block (used by the inspector embed). */
  hideContext?: boolean;
  intervalMs?: number;
}

export function Receipt({
  initial,
  apiPath = "/api/receipt",
  className,
  hideContext = false,
  intervalMs = 3_000,
}: ReceiptProps) {
  const [row, setRow] = React.useState<AgentReportRow | null>(initial);

  const handle = React.useCallback((data: { row?: AgentReportRow | null }) => {
    const next = data?.row;
    if (!next) return;
    setRow((curr) => {
      if (!next.enforced_ts_ns) return curr;
      if (!curr) return next;
      // Prefer newer wire_ts_ns, fall back to id ordering.
      const newer =
        (next.wire_ts_ns ?? "0") > (curr.wire_ts_ns ?? "0") ||
        next.id > curr.id;
      return newer ? next : curr;
    });
  }, []);

  usePoll<{ row?: AgentReportRow | null }>(apiPath, intervalMs, handle);

  if (!row) {
    return (
      <Card className={className}>
        <CardHeader>
          <CardTitle>Microsecond Receipt</CardTitle>
        </CardHeader>
        <CardBody>
          <EmptyState
            title="Standing by"
            description="Receipt populates when the agent cluster enforces its first case."
          />
        </CardBody>
      </Card>
    );
  }

  return <ReceiptCard row={row} className={className} hideContext={hideContext} />;
}

/**
 * Pure render of the timeline for a given row. Exported so the
 * ReportInspector can drop one in for the currently-selected case
 * without re-subscribing to SSE.
 */
export function ReceiptCard({
  row,
  className,
  hideContext = false,
}: {
  row: AgentReportRow;
  className?: string;
  hideContext?: boolean;
}) {
  const tl = React.useMemo(() => computeTimeline(row), [row]);

  return (
    <Card className={className}>
      <CardHeader className="flex flex-row items-center justify-between gap-2">
        <CardTitle>Microsecond Receipt — {row.symbol}</CardTitle>
        <Badge tone={row.enforced ? "red" : "blue"}>
          {row.enforced ? "enforced" : "review"}
        </Badge>
      </CardHeader>
      <CardBody className="space-y-4">
        <TimelineStrip timeline={tl} />
        <TotalLine total={tl.total_ns} complete={tl.complete} />
        {!hideContext ? <IndustryContext /> : null}
      </CardBody>
    </Card>
  );
}

function TimelineStrip({ timeline }: { timeline: Timeline }) {
  return (
    <ol className="grid grid-cols-5 gap-2" aria-label="Pipeline stages">
      {timeline.stages.map((stage, idx) => (
        <StageDot
          key={stage.key}
          stage={stage}
          isFirst={idx === 0}
          isLast={idx === timeline.stages.length - 1}
        />
      ))}
    </ol>
  );
}

function StageDot({
  stage,
  isFirst,
  isLast,
}: {
  stage: Stage;
  isFirst: boolean;
  isLast: boolean;
}) {
  const captured = stage.ts_ns !== null;
  return (
    <li className="relative flex flex-col items-center text-center">
      {/* connector line behind the dot */}
      {!isFirst ? (
        <span
          aria-hidden
          className={cn(
            "absolute top-2 right-1/2 h-0.5 w-full",
            captured ? "bg-accent-green/40" : "bg-white/10",
          )}
        />
      ) : null}
      {!isLast ? (
        <span
          aria-hidden
          className={cn(
            "absolute top-2 left-1/2 h-0.5 w-full",
            captured ? "bg-accent-green/40" : "bg-white/10",
          )}
        />
      ) : null}

      <span
        className={cn(
          "relative z-10 h-4 w-4 rounded-full ring-2",
          captured
            ? "bg-accent-green ring-accent-green/40 shadow-[0_0_10px_rgba(74,222,128,0.5)]"
            : "bg-bg-subtle ring-white/15",
        )}
        aria-hidden
      />

      <span className="mt-2 text-[10px] font-medium uppercase tracking-[0.16em] text-white/50">
        {stage.label}
      </span>
      <span className="font-mono text-sm text-white/80">
        {fmtOffsetLabel(stage.offset_ns)}
      </span>
      {stage.delta_ns !== null ? (
        <span className="text-[10px] text-white/30">
          +{fmtDuration(stage.delta_ns)}
        </span>
      ) : (
        <span className="text-[10px] text-white/30">&nbsp;</span>
      )}
    </li>
  );
}

function TotalLine({
  total,
  complete,
}: {
  total: bigint | null;
  complete: boolean;
}) {
  return (
    <div className="flex items-baseline justify-between border-t border-white/5 pt-3">
      <span className="text-[10px] font-medium uppercase tracking-[0.18em] text-white/50">
        Total — wire → frozen
      </span>
      <span className="flex items-baseline gap-2">
        <span className="font-mono text-2xl font-semibold tracking-tight text-accent-green">
          {fmtDuration(total)}
        </span>
        {!complete ? (
          <span className="text-[10px] text-white/40">(partial)</span>
        ) : null}
      </span>
    </div>
  );
}
