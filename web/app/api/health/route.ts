import { NextResponse } from "next/server";

import { pingDb } from "@/lib/db";
import { isDbConfigured } from "@/lib/env";

export const dynamic = "force-dynamic";

export async function GET() {
  const dbConfigured = isDbConfigured();
  const dbAlive = dbConfigured ? await pingDb() : false;
  return NextResponse.json({
    status: dbConfigured && dbAlive ? "ok" : "degraded",
    db: {
      configured: dbConfigured,
      reachable: dbAlive,
    },
    ts: new Date().toISOString(),
  });
}
