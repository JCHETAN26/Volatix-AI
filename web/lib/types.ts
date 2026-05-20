// Shared types — kept narrow so server components and client components
// can both import without dragging in DB or React types.

export interface AnomalyScoreRow {
  id: number;
  ts_ns: string;        // BIGINT comes back as string from node-postgres
  symbol: string;
  score: number;
  model_id: number | null;
  inserted_at: string;  // ISO timestamp
  // Receipt-timeline anchors (added post-1.0; nullable for old rows).
  case_id?: string | null;
  wire_ts_ns?: string | null;
  compute_ts_ns?: string | null;
  score_ts_ns?: string | null;
}

export interface AgentReportRow {
  id: number;
  case_id: string;      // UUID — agent-internal id
  symbol: string;
  ts_ns: string;
  anomaly_score: number;
  confidence: number | null;
  enforced: boolean;
  rationale_md: string;
  created_at: string;
  // JSONB column — varies by case; rendered as raw JSON in the inspector.
  evidence: unknown;
  // Receipt-timeline join key + stage stamps.
  pipeline_case_id?: string | null;
  wire_ts_ns?: string | null;
  compute_ts_ns?: string | null;
  score_ts_ns?: string | null;
  verdict_ts_ns?: string | null;
  enforced_ts_ns?: string | null;
}

export interface FeatureLogRow {
  id: number;
  ts_ns: string;
  symbol: string;
  ofi: number;
  realized_vol: number;
  mid_price: number;
  total_volume: number;
  window_count: number;
  case_id?: string | null;
  wire_ts_ns?: string | null;
  compute_ts_ns?: string | null;
}

export type LedgerStatus = "SECURED" | "MONITORING" | "OFFLINE";
