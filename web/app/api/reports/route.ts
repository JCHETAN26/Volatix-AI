import { NextResponse } from "next/server";

import { safeQuery } from "@/lib/db";
import type { AgentReportRow } from "@/lib/types";

export const dynamic = "force-dynamic";

export async function GET(req: Request) {
  const url = new URL(req.url);
  const limit = clamp(parseInt(url.searchParams.get("limit") ?? "20", 10), 1, 100);

  const result = await safeQuery<AgentReportRow>(
    `SELECT id, case_id::text AS case_id, symbol, ts_ns::text AS ts_ns,
            anomaly_score, confidence, enforced, rationale_md,
            created_at, evidence
     FROM agent_report
     ORDER BY ts_ns DESC
     LIMIT $1`,
    [limit],
  );

  return NextResponse.json({ rows: result?.rows ?? [] });
}

function clamp(n: number, lo: number, hi: number): number {
  if (!Number.isFinite(n)) return lo;
  return Math.max(lo, Math.min(hi, Math.trunc(n)));
}
