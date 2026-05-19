import * as React from "react";

import { cn } from "@/lib/cn";

interface MetricCardProps {
  label: string;
  value: React.ReactNode;
  hint?: React.ReactNode;
  tone?: "default" | "warn" | "danger";
}

const toneStyles = {
  default: "text-white",
  warn: "text-accent-amber",
  danger: "text-accent-red",
} as const;

export function MetricCard({ label, value, hint, tone = "default" }: MetricCardProps) {
  return (
    <div className="rounded-lg border border-white/10 bg-bg-panel/80 backdrop-blur px-4 py-3 flex flex-col gap-1">
      <span className="text-[10px] font-medium uppercase tracking-[0.18em] text-white/50">
        {label}
      </span>
      <span className={cn("text-2xl font-semibold font-mono", toneStyles[tone])}>
        {value}
      </span>
      {hint ? <span className="text-xs text-white/40">{hint}</span> : null}
    </div>
  );
}
