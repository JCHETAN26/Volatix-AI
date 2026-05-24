import { NextResponse } from "next/server";

import { safeQuery } from "@/lib/db";
import type { EvalCaseResultRow } from "@/lib/types";

export const dynamic = "force-dynamic";

export async function GET(req: Request) {
  const url = new URL(req.url);
  const runId = parseInt(url.searchParams.get("run_id") ?? "", 10);
  if (!Number.isFinite(runId)) {
    return NextResponse.json(
      { error: "run_id query param required" },
      { status: 400 },
    );
  }

  const result = await safeQuery<EvalCaseResultRow>(
    `SELECT id, eval_run_id, case_id, expected_action, actual_action,
            correct, faithfulness, answer_relevancy, latency_ms, agent_output
     FROM eval_case_result
     WHERE eval_run_id = $1
     ORDER BY case_id ASC`,
    [runId],
  );

  return NextResponse.json({ rows: result?.rows ?? [] });
}
