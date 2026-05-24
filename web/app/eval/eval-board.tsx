"use client";

import * as React from "react";

import { Badge } from "@/components/ui/badge";
import { Card, CardBody, CardHeader, CardTitle } from "@/components/ui/card";
import { EmptyState } from "@/components/ui/empty-state";
import { fmtNumber } from "@/lib/format";
import type { EvalCaseResultRow, EvalRunRow } from "@/lib/types";

const REGRESSION_THRESHOLD = 0.05; // 5% drop counts as regression
const METRIC_KEYS = [
  "freeze_correctness",
  "faithfulness",
  "answer_relevancy",
] as const;
type MetricKey = (typeof METRIC_KEYS)[number];

const METRIC_LABELS: Record<MetricKey, string> = {
  freeze_correctness: "Freeze correctness",
  faithfulness: "Faithfulness",
  answer_relevancy: "Answer relevancy",
};

export function EvalBoard({ initialRuns }: { initialRuns: EvalRunRow[] }) {
  const [runs] = React.useState(initialRuns);
  const [selectedId, setSelectedId] = React.useState<number>(initialRuns[0]?.id ?? 0);
  const selectedRun = runs.find((r) => r.id === selectedId) ?? runs[0];
  const versions = React.useMemo(
    () => Array.from(new Set(runs.map((r) => r.prompt_version))),
    [runs],
  );
  const regressions = React.useMemo(() => detectRegressions(runs), [runs]);

  return (
    <div className="space-y-6">
      {regressions.length > 0 ? (
        <RegressionBanner regressions={regressions} />
      ) : null}

      <section className="grid grid-cols-1 lg:grid-cols-[minmax(0,3fr),minmax(0,2fr)] gap-6">
        <MetricsPanel runs={runs} versions={versions} />
        <RunListPanel
          runs={runs}
          selectedId={selectedId}
          onSelect={setSelectedId}
        />
      </section>

      {selectedRun ? <RunDrilldown run={selectedRun} /> : null}
    </div>
  );
}

// ---------------------------------------------------------------------------

function RegressionBanner({ regressions }: { regressions: Regression[] }) {
  return (
    <section className="rounded-md border border-accent-red/30 bg-accent-red/10 px-4 py-3">
      <header className="text-xs font-semibold uppercase tracking-[0.16em] text-accent-red">
        Regression detected
      </header>
      <ul className="mt-2 space-y-1 text-sm text-white/80">
        {regressions.map((r) => (
          <li key={`${r.promptVersion}-${r.metric}`}>
            <span className="font-mono text-white">{r.promptVersion}</span> ·{" "}
            <span>{METRIC_LABELS[r.metric]}</span> dropped{" "}
            <span className="font-mono text-accent-red">
              {fmtNumber(r.prev, 3)} → {fmtNumber(r.curr, 3)}
            </span>{" "}
            <span className="text-white/50">
              (Δ {fmtNumber(r.curr - r.prev, 3)})
            </span>
          </li>
        ))}
      </ul>
    </section>
  );
}

interface Regression {
  promptVersion: string;
  metric: MetricKey;
  prev: number;
  curr: number;
}

function detectRegressions(runs: EvalRunRow[]): Regression[] {
  const byVersion = new Map<string, EvalRunRow[]>();
  for (const r of runs) {
    const arr = byVersion.get(r.prompt_version) ?? [];
    arr.push(r);
    byVersion.set(r.prompt_version, arr);
  }
  const out: Regression[] = [];
  for (const [version, vRuns] of byVersion) {
    if (vRuns.length < 2) continue;
    const sorted = [...vRuns].sort(
      (a, b) => Date.parse(b.created_at) - Date.parse(a.created_at),
    );
    const curr = sorted[0];
    const prev = sorted[1];
    for (const k of METRIC_KEYS) {
      const c = curr[k];
      const p = prev[k];
      if (c === null || p === null) continue;
      if (p > 0 && (p - c) / p >= REGRESSION_THRESHOLD) {
        out.push({ promptVersion: version, metric: k, prev: p, curr: c });
      }
    }
  }
  return out;
}

// ---------------------------------------------------------------------------

function MetricsPanel({
  runs,
  versions,
}: {
  runs: EvalRunRow[];
  versions: string[];
}) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>Metric trends</CardTitle>
      </CardHeader>
      <CardBody className="space-y-6">
        {METRIC_KEYS.map((k) => (
          <MetricChart key={k} runs={runs} versions={versions} metric={k} />
        ))}
        <LatencyChart runs={runs} versions={versions} />
      </CardBody>
    </Card>
  );
}

function MetricChart({
  runs,
  versions,
  metric,
}: {
  runs: EvalRunRow[];
  versions: string[];
  metric: MetricKey;
}) {
  return (
    <div>
      <header className="mb-2 flex items-baseline justify-between gap-2">
        <h3 className="text-xs font-medium uppercase tracking-[0.16em] text-white/50">
          {METRIC_LABELS[metric]}
        </h3>
        <span className="text-[10px] text-white/30">0 → 1</span>
      </header>
      {versions.map((v) => (
        <Sparkline
          key={v}
          label={v}
          series={runs
            .filter((r) => r.prompt_version === v && r[metric] !== null)
            .sort(
              (a, b) => Date.parse(a.created_at) - Date.parse(b.created_at),
            )
            .map((r) => ({
              x: Date.parse(r.created_at),
              y: r[metric] as number,
            }))}
          domain={[0, 1]}
        />
      ))}
    </div>
  );
}

function LatencyChart({
  runs,
  versions,
}: {
  runs: EvalRunRow[];
  versions: string[];
}) {
  const maxLat = Math.max(
    1,
    ...runs.map((r) => r.p95_latency_ms ?? 0),
  );
  return (
    <div>
      <header className="mb-2 flex items-baseline justify-between gap-2">
        <h3 className="text-xs font-medium uppercase tracking-[0.16em] text-white/50">
          p95 stage latency
        </h3>
        <span className="text-[10px] text-white/30">0 → {fmtNumber(maxLat, 0)} ms</span>
      </header>
      {versions.map((v) => (
        <Sparkline
          key={v}
          label={v}
          series={runs
            .filter((r) => r.prompt_version === v && r.p95_latency_ms !== null)
            .sort(
              (a, b) => Date.parse(a.created_at) - Date.parse(b.created_at),
            )
            .map((r) => ({
              x: Date.parse(r.created_at),
              y: r.p95_latency_ms as number,
            }))}
          domain={[0, maxLat]}
        />
      ))}
    </div>
  );
}

function Sparkline({
  label,
  series,
  domain,
}: {
  label: string;
  series: Array<{ x: number; y: number }>;
  domain: [number, number];
}) {
  const W = 420;
  const H = 36;
  if (series.length === 0) {
    return (
      <div className="flex items-center gap-3 py-1 text-xs">
        <span className="w-12 font-mono text-white/40">{label}</span>
        <span className="text-white/30">no data</span>
      </div>
    );
  }
  const xMin = series[0].x;
  const xMax = series[series.length - 1].x;
  const xRange = Math.max(1, xMax - xMin);
  const [yMin, yMax] = domain;
  const yRange = Math.max(1e-9, yMax - yMin);
  const pts = series.map((p) => {
    const x = ((p.x - xMin) / xRange) * (W - 4) + 2;
    const y = H - 2 - ((p.y - yMin) / yRange) * (H - 4);
    return `${x.toFixed(1)},${y.toFixed(1)}`;
  });
  const latest = series[series.length - 1].y;
  return (
    <div className="flex items-center gap-3 py-1 text-xs">
      <span className="w-12 truncate font-mono text-white/60">{label}</span>
      <svg width={W} height={H} className="overflow-visible">
        <polyline
          fill="none"
          stroke="rgba(74,222,128,0.7)"
          strokeWidth="1.5"
          points={pts.join(" ")}
        />
        {series.map((p, i) => {
          const [x, y] = pts[i].split(",").map(parseFloat);
          return <circle key={i} cx={x} cy={y} r={2} fill="rgba(74,222,128,0.9)" />;
        })}
      </svg>
      <span className="w-16 text-right font-mono text-white/80">
        {fmtNumber(latest, 3)}
      </span>
    </div>
  );
}

// ---------------------------------------------------------------------------

function RunListPanel({
  runs,
  selectedId,
  onSelect,
}: {
  runs: EvalRunRow[];
  selectedId: number;
  onSelect: (id: number) => void;
}) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>Runs ({runs.length})</CardTitle>
      </CardHeader>
      <CardBody>
        <ol className="max-h-[24rem] divide-y divide-white/5 overflow-auto text-sm">
          {runs.map((r) => (
            <li key={r.id}>
              <button
                onClick={() => onSelect(r.id)}
                className={`w-full rounded px-2 py-2 text-left transition ${
                  r.id === selectedId
                    ? "bg-white/5 text-white"
                    : "text-white/70 hover:bg-white/5"
                }`}
              >
                <div className="flex items-center justify-between gap-2">
                  <span className="font-mono text-xs">#{r.id} · {r.prompt_version}</span>
                  <Badge tone={(r.freeze_correctness ?? 0) >= 0.9 ? "blue" : "red"}>
                    {fmtNumber(r.freeze_correctness ?? 0, 2)}
                  </Badge>
                </div>
                <div className="mt-0.5 text-[10px] text-white/40">
                  {r.llm_model} · {r.n_cases} cases ·{" "}
                  {new Date(r.created_at).toISOString().slice(0, 16).replace("T", " ")}
                </div>
              </button>
            </li>
          ))}
        </ol>
      </CardBody>
    </Card>
  );
}

// ---------------------------------------------------------------------------

function RunDrilldown({ run }: { run: EvalRunRow }) {
  const [cases, setCases] = React.useState<EvalCaseResultRow[] | null>(null);
  const [loading, setLoading] = React.useState(false);

  React.useEffect(() => {
    let cancelled = false;
    setLoading(true);
    fetch(`/api/eval/cases?run_id=${run.id}`)
      .then((r) => r.json())
      .then((d) => {
        if (cancelled) return;
        setCases(d?.rows ?? []);
        setLoading(false);
      })
      .catch(() => {
        if (cancelled) return;
        setCases([]);
        setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [run.id]);

  return (
    <Card>
      <CardHeader>
        <CardTitle>
          Run #{run.id} — {run.prompt_version} · {run.llm_model}
        </CardTitle>
      </CardHeader>
      <CardBody className="space-y-4">
        <dl className="grid grid-cols-2 gap-x-6 gap-y-1 text-xs sm:grid-cols-4">
          <Stat label="freeze_correctness" value={fmtNumber(run.freeze_correctness ?? null, 3)} />
          <Stat label="faithfulness" value={fmtNumber(run.faithfulness ?? null, 3)} />
          <Stat label="answer_relevancy" value={fmtNumber(run.answer_relevancy ?? null, 3)} />
          <Stat label="p95 latency (ms)" value={fmtNumber(run.p95_latency_ms ?? null, 0)} />
          <Stat label="cases" value={String(run.n_cases)} />
          <Stat label="fixture" value={run.fixture_revision.slice(0, 12)} mono />
          <Stat label="provider" value={`${run.llm_provider}`} />
          <Stat label="notes" value={run.notes ?? "—"} />
        </dl>

        {loading ? (
          <p className="text-xs text-white/40">loading cases…</p>
        ) : !cases || cases.length === 0 ? (
          <EmptyState title="No case rows for this run" />
        ) : (
          <CaseTable cases={cases} />
        )}
      </CardBody>
    </Card>
  );
}

function Stat({
  label,
  value,
  mono,
}: {
  label: string;
  value: string;
  mono?: boolean;
}) {
  return (
    <div className="min-w-0">
      <dt className="text-[10px] uppercase tracking-[0.16em] text-white/40">
        {label}
      </dt>
      <dd
        className={`mt-0.5 truncate text-white/85 ${mono ? "font-mono text-[11px]" : ""}`}
      >
        {value}
      </dd>
    </div>
  );
}

function CaseTable({ cases }: { cases: EvalCaseResultRow[] }) {
  return (
    <div className="overflow-x-auto rounded-md border border-white/5">
      <table className="w-full text-xs">
        <thead className="bg-bg-subtle/40 text-white/50">
          <tr className="text-left">
            <Th>case</Th>
            <Th>expected</Th>
            <Th>actual</Th>
            <Th>✓</Th>
            <Th>faith</Th>
            <Th>relev</Th>
            <Th className="text-right">ms</Th>
          </tr>
        </thead>
        <tbody>
          {cases.map((c) => (
            <tr key={c.id} className="border-t border-white/5 align-top">
              <Td mono>{c.case_id}</Td>
              <Td>{c.expected_action}</Td>
              <Td>{c.actual_action ?? "—"}</Td>
              <Td>
                <Badge tone={c.correct ? "blue" : "red"}>
                  {c.correct ? "ok" : "miss"}
                </Badge>
              </Td>
              <Td mono>{fmtNumber(c.faithfulness ?? null, 2)}</Td>
              <Td mono>{fmtNumber(c.answer_relevancy ?? null, 2)}</Td>
              <Td mono className="text-right">
                {fmtNumber(c.latency_ms ?? null, 0)}
              </Td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function Th({
  children,
  className,
}: {
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <th
      className={`px-2 py-2 text-[10px] font-medium uppercase tracking-[0.14em] ${className ?? ""}`}
    >
      {children}
    </th>
  );
}

function Td({
  children,
  mono,
  className,
}: {
  children: React.ReactNode;
  mono?: boolean;
  className?: string;
}) {
  return (
    <td
      className={`px-2 py-1.5 text-white/80 ${mono ? "font-mono text-[11px]" : ""} ${className ?? ""}`}
    >
      {children}
    </td>
  );
}
