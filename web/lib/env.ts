// Server-only env access. Imported from server components and API routes
// so we never accidentally leak DATABASE_URL into the client bundle.

const num = (raw: string | undefined, fallback: number) => {
  if (!raw) return fallback;
  const v = Number(raw);
  return Number.isFinite(v) && v >= 0 ? v : fallback;
};

export const env = {
  databaseUrl: process.env.DATABASE_URL ?? "",
  dbConnectTimeoutMs: num(process.env.DB_CONNECT_TIMEOUT_MS, 2000),
  ssePollMs: num(process.env.SSE_POLL_MS, 500),
};

export function isDbConfigured(): boolean {
  return env.databaseUrl.length > 0;
}
