// Receipt timeline derivation. Pulls the BIGINT ns timestamps off an
// AgentReportRow and turns them into ordered stages with the deltas the
// UI wants. Tolerant of missing stages (returns a partial chain) and
// clock skew (clamps negative deltas to zero).

import type { AgentReportRow } from "./types";

export type StageKey =
  | "wire"
  | "compute"
  | "score"
  | "verdict"
  | "enforced";

export interface Stage {
  key: StageKey;
  label: string;
  /** ns since epoch, or null if not captured. */
  ts_ns: bigint | null;
  /** ns since the wire stage. 0 for the wire stage itself; null when missing. */
  offset_ns: bigint | null;
  /** ns since the previous captured stage; null for wire / when missing. */
  delta_ns: bigint | null;
}

export interface Timeline {
  stages: Stage[];
  /** ns from wire → last captured stage. null if wire missing. */
  total_ns: bigint | null;
  /** true when every stage from wire→enforced has a value. */
  complete: boolean;
}

const STAGE_DEFS: ReadonlyArray<{ key: StageKey; label: string; field: keyof AgentReportRow }> = [
  { key: "wire", label: "wire", field: "wire_ts_ns" },
  { key: "compute", label: "compute", field: "compute_ts_ns" },
  { key: "score", label: "score", field: "score_ts_ns" },
  { key: "verdict", label: "verdict", field: "verdict_ts_ns" },
  { key: "enforced", label: "frozen", field: "enforced_ts_ns" },
];

function toBigint(v: unknown): bigint | null {
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

export function computeTimeline(row: AgentReportRow): Timeline {
  const raw = STAGE_DEFS.map(({ key, label, field }) => ({
    key,
    label,
    ts_ns: toBigint(row[field]),
  }));

  const wire = raw[0].ts_ns;
  let prev: bigint | null = null;
  let last_captured: bigint | null = null;
  let allPresent = true;

  const stages: Stage[] = raw.map((r, idx) => {
    const ts = r.ts_ns;
    if (ts === null) {
      allPresent = false;
      return { ...r, offset_ns: null, delta_ns: null };
    }
    last_captured = ts;
    const offset = idx === 0 ? 0n : wire !== null ? clampPos(ts - wire) : null;
    const delta = idx === 0 ? null : prev !== null ? clampPos(ts - prev) : null;
    prev = ts;
    return { ...r, offset_ns: offset, delta_ns: delta };
  });

  const total_ns =
    wire !== null && last_captured !== null ? clampPos(last_captured - wire) : null;

  return { stages, total_ns, complete: allPresent };
}

// ---------------------------------------------------------------------------
// Formatting
// ---------------------------------------------------------------------------

const NS_PER_MS = 1_000_000n;
const NS_PER_S = 1_000_000_000n;

export function fmtDuration(ns: bigint | null): string {
  if (ns === null) return "—";
  if (ns < 1_000n) return `${ns} ns`;
  if (ns < NS_PER_MS) return `${(Number(ns) / 1_000).toFixed(1)} µs`;
  if (ns < NS_PER_S) return `${(Number(ns) / 1_000_000).toFixed(1)} ms`;
  return `${(Number(ns) / 1_000_000_000).toFixed(3)} s`;
}

export function fmtOffsetLabel(ns: bigint | null): string {
  if (ns === null) return "—";
  if (ns === 0n) return "T+0";
  return `T+${fmtDuration(ns)}`;
}
