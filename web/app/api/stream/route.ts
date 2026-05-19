import { safeQuery } from "@/lib/db";
import { env } from "@/lib/env";
import { sseComment, sseEvent } from "@/lib/sse";
import type { AgentReportRow, AnomalyScoreRow } from "@/lib/types";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

// Polls Postgres for new anomaly_score_log / agent_report rows since the
// last sample and streams them to the client as SSE events. Simpler than
// LISTEN/NOTIFY and works through Vercel's serverless functions.
export async function GET(req: Request) {
  let cancelled = false;
  let lastScoreTs = "0";
  let lastReportTs = "0";

  const stream = new ReadableStream<Uint8Array>({
    async start(controller) {
      controller.enqueue(sseComment("chainguard-stream connected"));

      const abort = () => {
        cancelled = true;
      };
      req.signal.addEventListener("abort", abort);

      // Heartbeat keeps proxies from closing the connection.
      const heartbeat = setInterval(() => {
        if (!cancelled) controller.enqueue(sseComment("ping"));
      }, 15_000);

      try {
        while (!cancelled) {
          const [scores, reports] = await Promise.all([
            safeQuery<AnomalyScoreRow>(
              `SELECT id, ts_ns::text AS ts_ns, symbol, score, model_id, inserted_at
               FROM anomaly_score_log
               WHERE ts_ns::text > $1
               ORDER BY ts_ns ASC
               LIMIT 50`,
              [lastScoreTs],
            ),
            safeQuery<AgentReportRow>(
              `SELECT id, case_id::text AS case_id, symbol, ts_ns::text AS ts_ns,
                      anomaly_score, confidence, enforced, rationale_md,
                      created_at, evidence
               FROM agent_report
               WHERE ts_ns::text > $1
               ORDER BY ts_ns ASC
               LIMIT 20`,
              [lastReportTs],
            ),
          ]);

          for (const row of scores?.rows ?? []) {
            controller.enqueue(sseEvent(row, "score"));
            lastScoreTs = row.ts_ns;
          }
          for (const row of reports?.rows ?? []) {
            controller.enqueue(sseEvent(row, "report"));
            lastReportTs = row.ts_ns;
          }

          await sleep(env.ssePollMs);
        }
      } catch (err) {
        controller.enqueue(
          sseEvent({ error: (err as Error).message }, "error"),
        );
      } finally {
        clearInterval(heartbeat);
        req.signal.removeEventListener("abort", abort);
        try {
          controller.close();
        } catch {
          /* already closed */
        }
      }
    },
  });

  return new Response(stream, {
    headers: {
      "Content-Type": "text/event-stream; charset=utf-8",
      "Cache-Control": "no-cache, no-transform",
      Connection: "keep-alive",
      "X-Accel-Buffering": "no",
    },
  });
}

function sleep(ms: number): Promise<void> {
  return new Promise((r) => setTimeout(r, ms));
}
