// Replay derivation. Turns a single AgentReportRow into the ordered
// sequence of events the Replay modal animates over.
//
// Source data:
//   - wire / compute / score / verdict / enforced timestamps (PR A)
//   - evidence.stages.{forensic,auditor,enforcer}.{prompt,rationale} (PR C)
//   - evidence.rag_matches + evidence.features (PR C / earlier)
//
// The C++ engine + classifier give us precise timestamps for the first
// three events. The agent stages all happen between `score_ts_ns` and
// `verdict_ts_ns` — we don't capture per-node finish times — so we
// interpolate evenly across that span and mark those events as
// `approximate` so the UI can soften the timing label.

import type { AgentEvidence, AgentReportRow } from "./types";

export type ReplayStageKey =
  | "wire"
  | "compute"
  | "score"
  | "forensic"
  | "auditor"
  | "enforcer";

export interface ReplayEvent {
  key: ReplayStageKey;
  label: string;
  /** ns since epoch. */
  ts_ns: bigint;
  /** ns since the wire event (0 for wire). */
  offset_ns: bigint;
  /** ns since the previous captured event. */
  delta_ns: bigint;
  /** True when this timestamp was synthesized via interpolation. */
  approximate: boolean;
  /** Stage-specific content the modal renders. */
  payload: ReplayPayload;
}

export type ReplayPayload =
  | { kind: "wire"; symbol: string }
  | {
      kind: "compute";
      features: Record<string, number>;
    }
  | {
      kind: "score";
      score: number;
      threshold: number;
      high_risk: boolean;
    }
  | {
      kind: "forensic";
      prompt: string;
      rationale: string;
      matches: NonNullable<AgentEvidence["rag_matches"]>;
    }
  | {
      kind: "auditor";
      prompt: string;
      rationale: string;
      confidence: number;
    }
  | {
      kind: "enforcer";
      prompt: string;
      rationale: string;
      action: NonNullable<AgentEvidence["enforcement_action"]>;
    };

const FORENSIC_THRESHOLD = 0.85; // mirrors classifier default; used for the score event label

function tsToBig(v: unknown): bigint | null {
  if (v === null || v === undefined || v === "") return null;
  try {
    return BigInt(v as string | number | bigint);
  } catch {
    return null;
  }
}

function clampPos(n: bigint): bigint {
  return n < 0n ? 0n : n;
}

/**
 * Build the event stream for a single case. Returns an empty array when
 * the row is missing both wire_ts_ns and any agent stage data — there's
 * nothing meaningful to replay then.
 */
export function buildReplay(row: AgentReportRow): ReplayEvent[] {
  const ev = row.evidence ?? {};
  const stages = ev.stages ?? {};

  const wire = tsToBig(row.wire_ts_ns);
  const compute = tsToBig(row.compute_ts_ns);
  const score = tsToBig(row.score_ts_ns);
  const verdict = tsToBig(row.verdict_ts_ns);
  const enforced = tsToBig(row.enforced_ts_ns);
  if (wire === null) return [];

  const events: Array<Omit<ReplayEvent, "offset_ns" | "delta_ns">> = [];

  // T+0
  events.push({
    key: "wire",
    label: "Tick received",
    ts_ns: wire,
    approximate: false,
    payload: { kind: "wire", symbol: row.symbol },
  });

  // T+compute
  if (compute !== null) {
    events.push({
      key: "compute",
      label: "Feature computed",
      ts_ns: compute,
      approximate: false,
      payload: { kind: "compute", features: ev.features ?? {} },
    });
  }

  // T+score
  if (score !== null) {
    events.push({
      key: "score",
      label: "Anomaly scored",
      ts_ns: score,
      approximate: false,
      payload: {
        kind: "score",
        score: row.anomaly_score,
        threshold: FORENSIC_THRESHOLD,
        high_risk: row.anomaly_score >= FORENSIC_THRESHOLD,
      },
    });
  }

  // The forensic + auditor stages happen inside graph.invoke(); we don't
  // have per-node finish times. Place them between score and verdict by
  // even interpolation (or between score and enforced when present).
  const agentSpanStart = score ?? wire;
  const agentSpanEnd = enforced ?? verdict ?? agentSpanStart;
  const agentSpan = agentSpanEnd - agentSpanStart;
  const forensicStage = stages.forensic;
  const auditorStage = stages.auditor;
  const enforcerStage = stages.enforcer;

  const agentNodes: ReplayStageKey[] = [];
  if (forensicStage?.rationale) agentNodes.push("forensic");
  if (auditorStage?.rationale) agentNodes.push("auditor");
  if (enforcerStage?.rationale) agentNodes.push("enforcer");

  // Interpolate timestamps; the last node lands on agentSpanEnd so the
  // total still matches the real wire→enforced delta.
  agentNodes.forEach((nodeKey, idx) => {
    const denom = BigInt(agentNodes.length);
    const t =
      agentNodes.length === 1
        ? agentSpanEnd
        : agentSpanStart + ((agentSpan * BigInt(idx + 1)) / denom);
    if (nodeKey === "forensic") {
      events.push({
        key: "forensic",
        label: "Forensic Investigator",
        ts_ns: t,
        approximate: true,
        payload: {
          kind: "forensic",
          prompt: forensicStage?.prompt ?? "",
          rationale: forensicStage?.rationale ?? "",
          matches: ev.rag_matches ?? [],
        },
      });
    } else if (nodeKey === "auditor") {
      events.push({
        key: "auditor",
        label: "Risk & Compliance Auditor",
        ts_ns: t,
        approximate: true,
        payload: {
          kind: "auditor",
          prompt: auditorStage?.prompt ?? "",
          rationale: auditorStage?.rationale ?? "",
          confidence: row.confidence ?? auditorStage?.confidence ?? 0,
        },
      });
    } else {
      const action =
        enforcerStage?.action ??
        ev.enforcement_action ??
        ({
          action: "HALT_SYMBOL",
          target: row.symbol,
          reason_code: "HIGH_CONFIDENCE_ANOMALY",
        } as NonNullable<AgentEvidence["enforcement_action"]>);
      events.push({
        key: "enforcer",
        label: "Settlement & Enforcer",
        ts_ns: enforced ?? t,
        approximate: enforced === null,
        payload: {
          kind: "enforcer",
          prompt: enforcerStage?.prompt ?? "",
          rationale: enforcerStage?.rationale ?? "",
          action: action!,
        },
      });
    }
  });

  // Compute offsets + deltas in a second pass.
  let prev: bigint | null = null;
  return events.map((ev) => {
    const offset = clampPos(ev.ts_ns - wire);
    const delta = prev === null ? 0n : clampPos(ev.ts_ns - prev);
    prev = ev.ts_ns;
    return { ...ev, offset_ns: offset, delta_ns: delta };
  });
}
