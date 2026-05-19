import * as React from "react";

import { cn } from "@/lib/cn";
import type { LedgerStatus } from "@/lib/types";

interface LedgerStatusProps {
  status: LedgerStatus;
  description?: string;
}

const styles: Record<LedgerStatus, { ring: string; dot: string; label: string }> = {
  SECURED: {
    ring: "ring-accent-green/40 bg-accent-green/10",
    dot: "bg-accent-green shadow-[0_0_18px_var(--tw-shadow-color)] shadow-accent-green/60",
    label: "text-accent-green",
  },
  MONITORING: {
    ring: "ring-accent-blue/40 bg-accent-blue/10",
    dot: "bg-accent-blue shadow-[0_0_18px_var(--tw-shadow-color)] shadow-accent-blue/60",
    label: "text-accent-blue",
  },
  OFFLINE: {
    ring: "ring-accent-red/40 bg-accent-red/10",
    dot: "bg-accent-red shadow-[0_0_14px_var(--tw-shadow-color)] shadow-accent-red/60",
    label: "text-accent-red",
  },
};

export function LedgerStatusCard({ status, description }: LedgerStatusProps) {
  const s = styles[status];
  return (
    <div
      className={cn(
        "rounded-xl ring-1 ring-inset px-5 py-4 flex items-center gap-4",
        s.ring,
      )}
    >
      <span className={cn("h-3 w-3 rounded-full", s.dot)} aria-hidden />
      <div className="flex flex-col">
        <span className="text-[10px] font-medium uppercase tracking-[0.18em] text-white/50">
          Ledger Status
        </span>
        <span className={cn("text-2xl font-semibold tracking-tight", s.label)}>
          {status}
        </span>
        {description ? (
          <span className="text-xs text-white/50 mt-0.5">{description}</span>
        ) : null}
      </div>
    </div>
  );
}
