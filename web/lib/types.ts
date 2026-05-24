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

// Structured shape of the agent_report.evidence JSONB column. Schema
// tagged so future migrations can fan out; today only v1 exists.
export interface AgentEvidence {
  schema?: "chainguard.agent_evidence.v1" | string;
  features?: Record<string, number>;
  rag_matches?: Array<{
    attack_id: string;
    name: string;
    severity: number;
    similarity: number;
  }>;
  stages?: {
    forensic?: { prompt?: string; rationale?: string };
    auditor?: { prompt?: string; rationale?: string; confidence?: number };
    enforcer?: {
      prompt?: string;
      rationale?: string;
      action?: {
        action: string;
        target: string;
        reason_code: string;
        notes?: string;
      } | null;
    };
  };
  enforcement_action?: {
    action: string;
    target: string;
    reason_code: string;
    notes?: string;
  } | null;
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
  // Replay payload — narrowed from the JSONB column. May still be `null`
  // on legacy rows written before PR C.
  evidence: AgentEvidence | null;
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

// Phase 6 — LLM evaluation tables.

export interface EvalRunRow {
  id: number;
  created_at: string;
  prompt_version: string;
  fixture_revision: string;
  llm_provider: string;
  llm_model: string;
  n_cases: number;
  freeze_correctness: number | null;
  faithfulness: number | null;
  answer_relevancy: number | null;
  p50_latency_ms: number | null;
  p95_latency_ms: number | null;
  notes: string | null;
}

export interface EvalCaseResultRow {
  id: number;
  eval_run_id: number;
  case_id: string;            // fixture-local id, e.g. "av-001-03"
  expected_action: string;    // FREEZE | MONITOR | NO_ACTION
  actual_action: string | null;
  correct: boolean;
  faithfulness: number | null;
  answer_relevancy: number | null;
  latency_ms: number | null;
  agent_output: {
    rationale_md?: string;
    confidence?: number;
    enforcement_action?: {
      action: string;
      target: string;
      reason_code: string;
      notes?: string;
    } | null;
    rag_matches?: Array<{
      attack_id: string;
      name: string;
      severity: number;
      similarity: number;
    }>;
    error?: string;
  };
}
