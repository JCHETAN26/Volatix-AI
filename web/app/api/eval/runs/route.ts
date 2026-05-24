import { NextResponse } from "next/server";

import { safeQuery } from "@/lib/db";
import type { EvalRunRow } from "@/lib/types";

export const dynamic = "force-dynamic";

export async function GET(req: Request) {
  const url = new URL(req.url);
  const limit = clamp(parseInt(url.searchParams.get("limit") ?? "50", 10), 1, 200);
  const promptVersion = url.searchParams.get("prompt_version");

  const params: unknown[] = [limit];
  let where = "";
  if (promptVersion) {
    where = "WHERE prompt_version = $2";
    params.push(promptVersion);
  }

  const result = await safeQuery<EvalRunRow>(
    `SELECT id, created_at, prompt_version, fixture_revision,
            llm_provider, llm_model, n_cases,
            freeze_correctness, faithfulness, answer_relevancy,
            p50_latency_ms, p95_latency_ms, notes
     FROM eval_run
     ${where}
     ORDER BY created_at DESC
     LIMIT $1`,
    params,
  );

  return NextResponse.json({ rows: result?.rows ?? [] });
}

function clamp(n: number, lo: number, hi: number): number {
  if (!Number.isFinite(n)) return lo;
  return Math.max(lo, Math.min(hi, Math.trunc(n)));
}
