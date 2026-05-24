import { safeQuery } from "@/lib/db";
import { isDbConfigured } from "@/lib/env";
import type { EvalRunRow } from "@/lib/types";

import { EvalBoard } from "./eval-board";

export const dynamic = "force-dynamic";
export const revalidate = 0;

async function loadRuns(): Promise<EvalRunRow[]> {
  const r = await safeQuery<EvalRunRow>(
    `SELECT id, created_at, prompt_version, fixture_revision,
            llm_provider, llm_model, n_cases,
            freeze_correctness, faithfulness, answer_relevancy,
            p50_latency_ms, p95_latency_ms, notes
     FROM eval_run
     ORDER BY created_at DESC
     LIMIT 100`,
  );
  return r?.rows ?? [];
}

export default async function EvalPage() {
  const runs = await loadRuns();
  return (
    <main className="mx-auto max-w-7xl px-6 py-8 space-y-6">
      <header>
        <h1 className="text-3xl font-semibold tracking-tight">
          LLM evaluation
        </h1>
        <p className="mt-1 max-w-2xl text-sm text-white/50">
          Ragas + binary-correctness scoring of the LangGraph agent cluster.
          Each run replays the 200-case fixture through the live graph and
          records per-prompt-version metrics so regressions are visible
          before they reach production.
        </p>
      </header>

      {!isDbConfigured() ? (
        <EmptyMsg
          title="DATABASE_URL not set"
          body="The eval dashboard pulls from the eval_run and eval_case_result tables in Supabase Postgres. Configure DATABASE_URL in this environment to populate it."
        />
      ) : runs.length === 0 ? (
        <EmptyMsg
          title="No eval runs yet"
          body="Trigger the chainguard_eval Airflow DAG (or run python -m agents.eval.runner inside a pod with DATABASE_URL set) to populate this page."
        />
      ) : (
        <EvalBoard initialRuns={runs} />
      )}
    </main>
  );
}

function EmptyMsg({ title, body }: { title: string; body: string }) {
  return (
    <section className="rounded-lg border border-white/10 bg-bg-panel/80 p-8 text-center">
      <h2 className="text-sm font-medium uppercase tracking-[0.14em] text-white/60">
        {title}
      </h2>
      <p className="mt-2 text-sm text-white/50">{body}</p>
    </section>
  );
}
