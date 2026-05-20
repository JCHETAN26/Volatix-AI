import { NextResponse } from "next/server";

import { safeQuery } from "@/lib/db";
import type { AgentReportRow } from "@/lib/types";

export const dynamic = "force-dynamic";

/**
 * Returns the most recent enforced agent_report with a complete
 * receipt timeline. Used as the seed value for the dashboard's
 * top-of-page Microsecond Receipt card.
 */
export async function GET() {
  const result = await safeQuery<AgentReportRow>(`
    SELECT id,
           case_id::text                AS case_id,
           symbol,
           ts_ns::text                  AS ts_ns,
           anomaly_score,
           confidence,
           enforced,
           rationale_md,
           created_at,
           evidence,
           pipeline_case_id::text       AS pipeline_case_id,
           wire_ts_ns::text             AS wire_ts_ns,
           compute_ts_ns::text          AS compute_ts_ns,
           score_ts_ns::text            AS score_ts_ns,
           verdict_ts_ns::text          AS verdict_ts_ns,
           enforced_ts_ns::text         AS enforced_ts_ns
    FROM agent_report
    WHERE enforced = TRUE
      AND wire_ts_ns IS NOT NULL
      AND enforced_ts_ns IS NOT NULL
    ORDER BY wire_ts_ns DESC NULLS LAST, id DESC
    LIMIT 1
  `);

  return NextResponse.json({ row: result?.rows[0] ?? null });
}
