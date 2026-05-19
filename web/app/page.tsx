import { LedgerStatusCard } from "@/components/ledger-status";
import { MetricCard } from "@/components/metric-card";
import { ReportInspector } from "@/components/report-inspector";
import { ScoreFeed } from "@/components/score-feed";
import { safeQuery } from "@/lib/db";
import { isDbConfigured } from "@/lib/env";
import { fmtCompact, fmtNumber, fmtPct } from "@/lib/format";
import type {
  AgentReportRow,
  AnomalyScoreRow,
  LedgerStatus,
} from "@/lib/types";

export const dynamic = "force-dynamic";
export const revalidate = 0;

interface KpiSnapshot {
  scoresLastMinute: number;
  highRiskLastMinute: number;
  enforcedLastDay: number;
  meanScoreLastMinute: number;
  latestModelId: number | null;
}

async function loadKpis(): Promise<KpiSnapshot> {
  const empty: KpiSnapshot = {
    scoresLastMinute: 0,
    highRiskLastMinute: 0,
    enforcedLastDay: 0,
    meanScoreLastMinute: 0,
    latestModelId: null,
  };

  const r = await safeQuery<{
    scores_last_minute: string;
    high_risk_last_minute: string;
    enforced_last_day: string;
    mean_score: string | null;
    latest_model_id: number | null;
  }>(`
    SELECT
      (SELECT COUNT(*) FROM anomaly_score_log
        WHERE inserted_at > NOW() - INTERVAL '1 minute') AS scores_last_minute,
      (SELECT COUNT(*) FROM anomaly_score_log
        WHERE inserted_at > NOW() - INTERVAL '1 minute' AND score >= 0.85)
        AS high_risk_last_minute,
      (SELECT COUNT(*) FROM agent_report
        WHERE enforced = TRUE AND created_at > NOW() - INTERVAL '1 day')
        AS enforced_last_day,
      (SELECT AVG(score)::text FROM anomaly_score_log
        WHERE inserted_at > NOW() - INTERVAL '1 minute') AS mean_score,
      (SELECT MAX(id) FROM model_registry) AS latest_model_id
  `);

  if (!r) return empty;
  const row = r.rows[0];
  return {
    scoresLastMinute: Number(row?.scores_last_minute ?? 0),
    highRiskLastMinute: Number(row?.high_risk_last_minute ?? 0),
    enforcedLastDay: Number(row?.enforced_last_day ?? 0),
    meanScoreLastMinute: Number(row?.mean_score ?? 0),
    latestModelId: row?.latest_model_id ?? null,
  };
}

async function loadInitialScores(): Promise<AnomalyScoreRow[]> {
  const r = await safeQuery<AnomalyScoreRow>(
    `SELECT id, ts_ns::text AS ts_ns, symbol, score, model_id, inserted_at
     FROM anomaly_score_log
     ORDER BY ts_ns DESC
     LIMIT 50`,
  );
  return r?.rows ?? [];
}

async function loadInitialReports(): Promise<AgentReportRow[]> {
  const r = await safeQuery<AgentReportRow>(
    `SELECT id, case_id::text AS case_id, symbol, ts_ns::text AS ts_ns,
            anomaly_score, confidence, enforced, rationale_md,
            created_at, evidence
     FROM agent_report
     ORDER BY ts_ns DESC
     LIMIT 20`,
  );
  return r?.rows ?? [];
}

function ledgerFor(kpis: KpiSnapshot, dbAlive: boolean): {
  status: LedgerStatus;
  description: string;
} {
  if (!dbAlive) {
    return {
      status: "OFFLINE",
      description: isDbConfigured()
        ? "Postgres unreachable. Check chain-db rollout + port-forward."
        : "DATABASE_URL is not set in this environment.",
    };
  }
  if (kpis.highRiskLastMinute > 0) {
    return {
      status: "MONITORING",
      description: `${kpis.highRiskLastMinute} high-risk frame(s) in the last minute.`,
    };
  }
  return {
    status: "SECURED",
    description: "No high-risk anomalies in the last minute.",
  };
}

export default async function DashboardPage() {
  const [kpis, scores, reports] = await Promise.all([
    loadKpis(),
    loadInitialScores(),
    loadInitialReports(),
  ]);
  const dbAlive = isDbConfigured() && scores.length + reports.length > 0;
  const ledger = ledgerFor(kpis, dbAlive);

  return (
    <main className="mx-auto max-w-7xl px-6 py-8 space-y-6">
      <header className="flex flex-wrap items-end gap-4 justify-between">
        <div>
          <h1 className="text-3xl font-semibold tracking-tight">
            ChainGuard Control Board
          </h1>
          <p className="text-sm text-white/50 mt-1 max-w-2xl">
            Live telemetry from the C++ ingestion engine, the LightGBM
            classifier and the 3-tier LangGraph agent cluster.
          </p>
        </div>
        <LedgerStatusCard status={ledger.status} description={ledger.description} />
      </header>

      <section className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <MetricCard
          label="Scores / min"
          value={fmtCompact(kpis.scoresLastMinute)}
          hint="anomaly_score_log inserts (last minute)"
        />
        <MetricCard
          label="High-risk / min"
          value={fmtCompact(kpis.highRiskLastMinute)}
          tone={kpis.highRiskLastMinute > 0 ? "warn" : "default"}
          hint="score ≥ 0.85"
        />
        <MetricCard
          label="Enforced / 24h"
          value={fmtCompact(kpis.enforcedLastDay)}
          tone={kpis.enforcedLastDay > 0 ? "danger" : "default"}
          hint="agent_report.enforced=TRUE"
        />
        <MetricCard
          label="Mean score / min"
          value={fmtPct(kpis.meanScoreLastMinute)}
          hint={
            kpis.latestModelId !== null
              ? `model #${fmtNumber(kpis.latestModelId, 0)}`
              : "baseline model"
          }
        />
      </section>

      <section className="grid grid-cols-1 lg:grid-cols-[3fr,5fr] gap-6">
        <ScoreFeed initial={scores} />
        <ReportInspector initial={reports} />
      </section>

      <footer className="text-xs text-white/30 pt-6">
        Updates stream from <code>/api/stream</code> (Server-Sent Events).
        Initial load fetched on the server.
      </footer>
    </main>
  );
}
