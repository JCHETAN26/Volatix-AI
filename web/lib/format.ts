// Human-friendly formatters used by the dashboard. Kept here so server +
// client components can both use them without re-implementing.

export function fmtNumber(n: number, digits = 2): string {
  if (!Number.isFinite(n)) return "—";
  return n.toLocaleString(undefined, {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  });
}

export function fmtCompact(n: number): string {
  if (!Number.isFinite(n)) return "—";
  return new Intl.NumberFormat(undefined, {
    notation: "compact",
    maximumFractionDigits: 1,
  }).format(n);
}

export function fmtPct(p: number): string {
  if (!Number.isFinite(p)) return "—";
  return `${(p * 100).toFixed(1)}%`;
}

// ns since epoch (BIGINT → string) → ISO-8601 UTC
export function fmtTsNs(tsNs: string | number | bigint): string {
  try {
    const ns = typeof tsNs === "bigint" ? tsNs : BigInt(String(tsNs));
    const ms = Number(ns / 1_000_000n);
    return new Date(ms).toISOString();
  } catch {
    return String(tsNs);
  }
}

export function ago(iso: string): string {
  const t = new Date(iso).getTime();
  if (!Number.isFinite(t)) return iso;
  const s = Math.max(0, Math.floor((Date.now() - t) / 1000));
  if (s < 60) return `${s}s ago`;
  if (s < 3_600) return `${Math.floor(s / 60)}m ago`;
  if (s < 86_400) return `${Math.floor(s / 3600)}h ago`;
  return `${Math.floor(s / 86_400)}d ago`;
}
