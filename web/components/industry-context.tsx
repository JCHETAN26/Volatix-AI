import * as React from "react";

import { cn } from "@/lib/cn";

/**
 * Footnoted reference panel that lives under the Receipt. We deliberately
 * avoid a single "vs industry average" number — the comparable surfaces
 * aren't apples-to-apples — and instead list specific, citable regulatory
 * and industry benchmarks so the audience can draw their own contrast.
 *
 * Each entry's `source` is a primary regulation or published vendor
 * specification; nothing here is invented.
 */

interface Benchmark {
  label: string;
  detail: string;
  source: string;
}

const BENCHMARKS: ReadonlyArray<Benchmark> = [
  {
    label: "FinCEN Suspicious Activity Report",
    detail: "Banks must file within 30 days of initial detection.",
    source: "31 CFR § 1020.320",
  },
  {
    label: "US securities settlement (T+1)",
    detail: "Post-trade reconciliation runs one business day after execution.",
    source: "SEC Rule 15c6-1, effective May 2024",
  },
  {
    label: "Card-payment authorization",
    detail:
      "Real-time scoring at the network is sub-100 ms — narrower problem (auth-decision only).",
    source: "Visa Advanced Authorization & similar issuer-side stacks",
  },
  {
    label: "Trade surveillance at most sell-side banks",
    detail: "Anomaly review is batch, typically T+1 next-day reconciliation.",
    source: "Industry practice; see FCA MAR Thematic Reviews",
  },
];

export function IndustryContext({ className }: { className?: string }) {
  return (
    <section
      className={cn(
        "rounded-md border border-white/5 bg-bg-subtle/60 px-4 py-3",
        className,
      )}
      aria-label="Industry context"
    >
      <header className="text-[10px] font-medium uppercase tracking-[0.18em] text-white/40">
        Industry context — not a direct comparable
      </header>
      <ul className="mt-2 space-y-1.5 text-xs text-white/70">
        {BENCHMARKS.map((b) => (
          <li key={b.label} className="flex flex-col gap-0.5">
            <span>
              <span className="text-white">{b.label}.</span>{" "}
              {b.detail}
            </span>
            <span className="text-[10px] text-white/40">{b.source}</span>
          </li>
        ))}
      </ul>
    </section>
  );
}
