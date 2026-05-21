import "server-only";
import { Pool, type QueryResult, type QueryResultRow } from "pg";

import { env, isDbConfigured } from "./env";

// Single shared pool per server process. On Vercel each function instance
// is its own process; Supabase's session pooler caps at ~15 simultaneous
// clients per project, so we keep max=1 and lean on Supabase's pooler to
// absorb concurrency. For burstier traffic switch the DATABASE_URL to the
// transaction pooler endpoint (port 6543) — Supabase's recommended setup
// for serverless. Our queries are all simple parameterized SELECT/INSERTs
// so transaction-mode is fine (we don't use prepared statements, LISTEN,
// or session-scoped state).
let pool: Pool | null = null;

function getPool(): Pool {
  if (pool) return pool;
  const url = env.databaseUrl;
  // Supabase (and most managed Postgres) require TLS. node-postgres auto-
  // negotiates when the URL contains sslmode=require, but Supabase's pooler
  // is sometimes served behind an intermediate cert that node's default CA
  // set doesn't recognize on Vercel — flip rejectUnauthorized off so the
  // handshake succeeds. Connection is still encrypted.
  const needsSsl = /supabase\.(com|co)/i.test(url) || /sslmode=require/i.test(url);
  pool = new Pool({
    connectionString: url,
    max: 1,
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
