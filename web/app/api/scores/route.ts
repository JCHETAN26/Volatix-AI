import { NextResponse } from "next/server";

import { safeQuery } from "@/lib/db";
import type { AnomalyScoreRow } from "@/lib/types";

export const dynamic = "force-dynamic";

export async function GET(req: Request) {
  const url = new URL(req.url);
  const limit = clamp(parseInt(url.searchParams.get("limit") ?? "50", 10), 1, 500);

  const result = await safeQuery<AnomalyScoreRow>(
    `SELECT id, ts_ns::text AS ts_ns, symbol, score, model_id, inserted_at
     FROM anomaly_score_log
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
