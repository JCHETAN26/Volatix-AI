"use client";

import * as React from "react";

import { Badge } from "@/components/ui/badge";
import { Modal } from "@/components/ui/modal";
import { cn } from "@/lib/cn";
import { fmtNumber, fmtPct } from "@/lib/format";
import { buildReplay, type ReplayEvent } from "@/lib/replay";
import { fmtDuration, fmtOffsetLabel } from "@/lib/timeline";
import type { AgentReportRow } from "@/lib/types";

interface ReplayModalProps {
  row: AgentReportRow | null;
  open: boolean;
  onClose: () => void;
}

type Speed = 0.5 | 1 | 2 | 4;
const SPEEDS: Speed[] = [0.5, 1, 2, 4];

/** Total replay duration at speed=1, in ms. Demo-friendly slow motion. */
const BASE_DURATION_MS = 18_000;

export function ReplayModal({ row, open, onClose }: ReplayModalProps) {
  const events = React.useMemo<ReplayEvent[]>(
    () => (row ? buildReplay(row) : []),
    [row],
  );

  const [idx, setIdx] = React.useState(0);
  const [isPlaying, setIsPlaying] = React.useState(false);
  const [speed, setSpeed] = React.useState<Speed>(1);

  // Reset on row swap or modal open.
  React.useEffect(() => {
    setIdx(0);
    setIsPlaying(false);
  }, [row?.id, open]);

  // Auto-advance.
  React.useEffect(() => {
    if (!isPlaying || events.length === 0) return;
    const per = BASE_DURATION_MS / Math.max(events.length, 1) / speed;
    const t = setTimeout(() => {
      setIdx((curr) => {
        const next = curr + 1;
        if (next >= events.length) {
          setIsPlaying(false);
          return events.length - 1;
        }
        return next;
      });
    }, per);
    return () => clearTimeout(t);
  }, [isPlaying, idx, events.length, speed]);

  const current = events[idx];

  return (
    <Modal open={open} onClose={onClose} label="Case replay">
      <ReplayHeader row={row} onClose={onClose} eventsCount={events.length} />

      {events.length === 0 ? (
        <div className="px-6 py-10 text-center text-white/40 text-sm">
          No replay data for this case — wire timestamp missing.
        </div>
      ) : (
        <>
          <ReplayProgress events={events} idx={idx} onJump={setIdx} />
          <div className="grid grid-cols-1 md:grid-cols-[200px,1fr] divide-x divide-white/5 overflow-hidden flex-1 min-h-0">
            <StageRail events={events} idx={idx} onJump={setIdx} />
            <StageDetail event={current} />
          </div>
          <ReplayControls
            idx={idx}
            count={events.length}
            isPlaying={isPlaying}
            speed={speed}
            onPlayPause={() => setIsPlaying((p) => !p)}
            onRestart={() => {
              setIdx(0);
              setIsPlaying(true);
            }}
            onStep={(d) =>
              setIdx((c) => Math.max(0, Math.min(events.length - 1, c + d)))
            }
            onSpeed={setSpeed}
          />
        </>
      )}
    </Modal>
  );
}

// ---------------------------------------------------------------------------
// Pieces
// ---------------------------------------------------------------------------

function ReplayHeader({
  row,
  onClose,
  eventsCount,
}: {
  row: AgentReportRow | null;
  onClose: () => void;
  eventsCount: number;
}) {
  return (
    <header className="flex items-center justify-between px-5 py-4 border-b border-white/5">
      <div className="flex items-center gap-3">
        <span className="text-[10px] font-medium uppercase tracking-[0.18em] text-white/40">
          Case Replay
        </span>
        <span className="font-mono text-sm text-white/80">
          {row?.symbol ?? "—"}
        </span>
        {row?.enforced ? (
          <Badge tone="red">enforced</Badge>
        ) : (
          <Badge tone="blue">review</Badge>
        )}
        <span className="text-xs text-white/40">
          {eventsCount} stages
        </span>
      </div>
      <button
        onClick={onClose}
        aria-label="Close replay"
        className="rounded-md px-2 py-1 text-white/50 hover:text-white hover:bg-white/5 transition"
      >
        ✕
      </button>
    </header>
  );
}

function ReplayProgress({
  events,
  idx,
  onJump,
}: {
  events: ReplayEvent[];
  idx: number;
  onJump: (i: number) => void;
}) {
  return (
    <div className="px-5 pt-3 pb-2">
      <div className="flex h-1 gap-1">
        {events.map((_, i) => (
          <button
            key={i}
            onClick={() => onJump(i)}
            aria-label={`Jump to stage ${i + 1}`}
            className={cn(
              "flex-1 rounded-sm transition",
              i < idx
                ? "bg-accent-green/60"
                : i === idx
                  ? "bg-accent-green"
                  : "bg-white/10 hover:bg-white/20",
            )}
          />
        ))}
      </div>
    </div>
  );
}

function StageRail({
  events,
  idx,
  onJump,
}: {
  events: ReplayEvent[];
  idx: number;
  onJump: (i: number) => void;
}) {
  return (
    <ol className="overflow-auto max-h-[60vh] py-2">
      {events.map((ev, i) => (
        <li key={`${ev.key}-${i}`}>
          <button
            onClick={() => onJump(i)}
            className={cn(
              "w-full text-left px-4 py-2 transition border-l-2",
              i === idx
                ? "bg-white/5 border-accent-green"
                : "border-transparent hover:bg-white/5",
            )}
          >
            <div className="flex items-center justify-between gap-2">
              <span className="text-xs uppercase tracking-[0.12em] text-white/50">
                {ev.label}
              </span>
              {ev.approximate ? (
                <span className="text-[9px] text-white/30">~</span>
              ) : null}
            </div>
            <div className="font-mono text-xs text-white/70 mt-0.5">
              {fmtOffsetLabel(ev.offset_ns)}
            </div>
            {ev.delta_ns > 0n ? (
              <div className="text-[10px] text-white/30">
                +{fmtDuration(ev.delta_ns)}
              </div>
            ) : null}
          </button>
        </li>
      ))}
    </ol>
  );
}

function StageDetail({ event }: { event: ReplayEvent | undefined }) {
  if (!event) return null;
  const p = event.payload;
  return (
    <div className="p-5 overflow-auto max-h-[60vh]">
      <header className="flex items-baseline justify-between mb-3">
        <h3 className="text-sm font-semibold tracking-tight">
          {event.label}
        </h3>
        <span className="font-mono text-xs text-white/50">
          {fmtOffsetLabel(event.offset_ns)}
          {event.approximate ? " (approx)" : ""}
        </span>
      </header>

      {p.kind === "wire" ? (
        <div className="text-sm text-white/70">
          WebSocket message hit the engine.{" "}
          <span className="font-mono text-white">{p.symbol}</span> tick payload
          stamped before parsing.
        </div>
      ) : p.kind === "compute" ? (
        <FeatureTable features={p.features} />
      ) : p.kind === "score" ? (
        <ScorePanel score={p.score} threshold={p.threshold} highRisk={p.high_risk} />
      ) : p.kind === "forensic" ? (
        <ForensicPanel
          matches={p.matches}
          prompt={p.prompt}
          rationale={p.rationale}
        />
      ) : p.kind === "auditor" ? (
        <AuditorPanel
          confidence={p.confidence}
          prompt={p.prompt}
          rationale={p.rationale}
        />
      ) : (
        <EnforcerPanel
          action={p.action}
          prompt={p.prompt}
          rationale={p.rationale}
        />
      )}
    </div>
  );
}

function FeatureTable({ features }: { features: Record<string, number> }) {
  const entries = Object.entries(features);
  if (entries.length === 0)
    return <div className="text-sm text-white/40">No feature snapshot persisted.</div>;
  return (
    <table className="text-sm font-mono w-full">
      <tbody>
        {entries.map(([k, v]) => (
          <tr key={k} className="border-b border-white/5">
            <td className="py-1.5 pr-3 text-white/50">{k}</td>
            <td className="py-1.5 text-right text-white/90">
              {fmtNumber(Number(v), 4)}
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function ScorePanel({
  score,
  threshold,
  highRisk,
}: {
  score: number;
  threshold: number;
  highRisk: boolean;
}) {
  return (
    <div className="space-y-3">
      <div className="flex items-baseline gap-3">
        <span
          className={cn(
            "font-mono text-4xl font-semibold",
            highRisk ? "text-accent-red" : "text-accent-blue",
          )}
        >
          {fmtPct(score)}
        </span>
        <span className="text-xs text-white/40">
          threshold {fmtPct(threshold)}
        </span>
        <Badge tone={highRisk ? "red" : "blue"}>
          {highRisk ? "high risk" : "ok"}
        </Badge>
      </div>
      <p className="text-sm text-white/70">
        LightGBM scored the feature vector. Above-threshold scores forward
        onto the agent graph.
      </p>
    </div>
  );
}

function ForensicPanel({
  matches,
  prompt,
  rationale,
}: {
  matches: NonNullable<import("@/lib/types").AgentEvidence["rag_matches"]>;
  prompt: string;
  rationale: string;
}) {
  return (
    <div className="space-y-4">
      <section>
        <h4 className="text-[10px] uppercase tracking-[0.16em] text-white/40 mb-1">
          RAG matches
        </h4>
        {matches.length === 0 ? (
          <div className="text-sm text-white/40">(no matches)</div>
        ) : (
          <ul className="text-sm font-mono space-y-1">
            {matches.map((m) => (
              <li key={m.attack_id} className="flex justify-between gap-2">
                <span className="text-white/80">
                  [{m.attack_id}] {m.name}
                </span>
                <span className="text-white/50">
                  sim {fmtNumber(m.similarity, 3)} · sev{" "}
                  {fmtNumber(m.severity, 2)}
                </span>
              </li>
            ))}
          </ul>
        )}
      </section>
      <PromptRationale prompt={prompt} rationale={rationale} />
    </div>
  );
}

function AuditorPanel({
  confidence,
  prompt,
  rationale,
}: {
  confidence: number;
  prompt: string;
  rationale: string;
}) {
  return (
    <div className="space-y-4">
      <div className="flex items-baseline gap-3">
        <span
          className={cn(
            "font-mono text-3xl font-semibold",
            confidence >= 0.95 ? "text-accent-red" : "text-accent-amber",
          )}
        >
          {fmtPct(confidence)}
        </span>
        <span className="text-xs text-white/40">enforcement gate ≥ 95%</span>
      </div>
      <PromptRationale prompt={prompt} rationale={rationale} />
    </div>
  );
}

function EnforcerPanel({
  action,
  prompt,
  rationale,
}: {
  action: NonNullable<import("@/lib/types").AgentEvidence["enforcement_action"]>;
  prompt: string;
  rationale: string;
}) {
  return (
    <div className="space-y-4">
      <section className="rounded-md ring-1 ring-accent-red/30 bg-accent-red/10 px-3 py-2 text-sm font-mono">
        <div>
          <span className="text-white/50">action </span>
          <span className="text-accent-red">{action!.action}</span>
        </div>
        <div>
          <span className="text-white/50">target </span>
          <span className="text-white">{action!.target}</span>
        </div>
        <div>
          <span className="text-white/50">reason </span>
          <span className="text-white/80">{action!.reason_code}</span>
        </div>
        {action!.notes ? (
          <div className="text-white/60 mt-1">{action!.notes}</div>
        ) : null}
      </section>
      <PromptRationale prompt={prompt} rationale={rationale} />
    </div>
  );
}

function PromptRationale({
  prompt,
  rationale,
}: {
  prompt: string;
  rationale: string;
}) {
  return (
    <div className="grid grid-cols-1 lg:grid-cols-2 gap-3">
      <section>
        <h4 className="text-[10px] uppercase tracking-[0.16em] text-white/40 mb-1">
          Prompt sent
        </h4>
        <pre className="text-xs font-mono whitespace-pre-wrap rounded bg-bg-subtle/70 p-3 max-h-56 overflow-auto text-white/70">
          {prompt || "(not recorded)"}
        </pre>
      </section>
      <section>
        <h4 className="text-[10px] uppercase tracking-[0.16em] text-white/40 mb-1">
          LLM response
        </h4>
        <pre className="text-xs font-mono whitespace-pre-wrap rounded bg-bg-subtle/70 p-3 max-h-56 overflow-auto text-white/80">
          {rationale || "(not recorded)"}
        </pre>
      </section>
    </div>
  );
}

function ReplayControls({
  idx,
  count,
  isPlaying,
  speed,
  onPlayPause,
  onRestart,
  onStep,
  onSpeed,
}: {
  idx: number;
  count: number;
  isPlaying: boolean;
  speed: Speed;
  onPlayPause: () => void;
  onRestart: () => void;
  onStep: (delta: number) => void;
  onSpeed: (s: Speed) => void;
}) {
  return (
    <footer className="border-t border-white/5 px-5 py-3 flex items-center justify-between gap-3">
      <div className="flex items-center gap-2">
        <ControlButton onClick={() => onStep(-1)} disabled={idx === 0} label="◀">
          Prev
        </ControlButton>
        <ControlButton onClick={onPlayPause} label={isPlaying ? "❚❚" : "▶"}>
          {isPlaying ? "Pause" : idx === count - 1 ? "Replay" : "Play"}
        </ControlButton>
        <ControlButton onClick={() => onStep(1)} disabled={idx === count - 1} label="▶">
          Next
        </ControlButton>
        <ControlButton onClick={onRestart} label="⟲">
          Restart
        </ControlButton>
      </div>
      <div className="flex items-center gap-1 text-xs">
        <span className="text-white/40 mr-1">Speed</span>
        {SPEEDS.map((s) => (
          <button
            key={s}
            onClick={() => onSpeed(s)}
            className={cn(
              "px-2 py-0.5 rounded font-mono",
              s === speed
                ? "bg-white/10 text-white"
                : "text-white/40 hover:text-white/80",
            )}
          >
            {s}×
          </button>
        ))}
      </div>
      <div className="text-xs text-white/40 font-mono">
        {idx + 1} / {count}
      </div>
    </footer>
  );
}

function ControlButton({
  onClick,
  disabled,
  label,
  children,
}: {
  onClick: () => void;
  disabled?: boolean;
  label: string;
  children: React.ReactNode;
}) {
  return (
    <button
      onClick={onClick}
      disabled={disabled}
      aria-label={label}
      className={cn(
        "rounded-md px-2.5 py-1 text-xs font-medium transition",
        disabled
          ? "text-white/20 cursor-not-allowed"
          : "text-white/70 hover:text-white hover:bg-white/5",
      )}
    >
      {children}
    </button>
  );
}
