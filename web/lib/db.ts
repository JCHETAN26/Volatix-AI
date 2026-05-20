import "server-only";
import { Pool, type QueryResult, type QueryResultRow } from "pg";

import { env, isDbConfigured } from "./env";

// Single shared pool. Module scope is per-server-process so this respects
// Next.js' Node.js runtime caching (the dev server hot-reload still keeps
// the same module instance unless it explicitly reloads).
let pool: Pool | null = null;

function getPool(): Pool {
  if (pool) return pool;
  // Supabase (and most managed Postgres) require TLS. node-postgres will
  // auto-negotiate when the URL contains `sslmode=require`, but Supabase's
  // pooler endpoint is sometimes served behind an intermediate cert that
  // node's default CA set doesn't recognize on Vercel — flip rejectUnauthorized
  // off so the handshake succeeds. Connection itself is still encrypted.
  const url = env.databaseUrl;
  const needsSsl = /supabase\.(com|co)/i.test(url) || /sslmode=require/i.test(url);
  pool = new Pool({
    connectionString: url,
    max: 5,
    idleTimeoutMillis: 10_000,
    connectionTimeoutMillis: env.dbConnectTimeoutMs,
    ssl: needsSsl ? { rejectUnauthorized: false } : undefined,
  });
  pool.on("error", (err) => {
    // Pool emits errors when idle clients drop; log and continue.
    console.error("[db] pool error:", err.message);
  });
  return pool;
}

// Defensive wrapper. Returns null when the DB isn't configured (Vercel
// preview deploys, first-boot dev) or when a query times out — so the
// UI can render an empty state instead of crashing the request.
export async function safeQuery<T extends QueryResultRow = QueryResultRow>(
  text: string,
  params: readonly unknown[] = [],
): Promise<QueryResult<T> | null> {
  if (!isDbConfigured()) return null;
  try {
    return await getPool().query<T>(text, params as unknown[]);
  } catch (err) {
    console.error("[db] query failed:", (err as Error).message);
    return null;
  }
}

export async function pingDb(): Promise<boolean> {
  const r = await safeQuery<{ ok: number }>("SELECT 1 AS ok");
  return r?.rows[0]?.ok === 1;
}
