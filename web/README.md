# Volatix-AI Web — Analytical Control Board

Next.js 15 (App Router) dashboard for the Volatix-AI engine. Reads
directly from PostgreSQL (`agent_report`, `anomaly_score_log`,
`model_registry`) and streams live updates via Server-Sent Events.

## Local dev

```bash
pnpm install
cp .env.example .env.local        # set DATABASE_URL to your forwarded chain-db
pnpm dev                          # http://localhost:3000
```

For a real DB, run from the repo root:
```bash
make port-forward-pg              # exposes chain-db on localhost:5432
# Then point DATABASE_URL=postgres://postgres:PASSWORD@localhost:5432/postgres
```

## Build

```bash
pnpm typecheck && pnpm lint && pnpm build
```

`frontend-ci` in the repo's GitHub Actions workflow runs all three on every
PR.

## Deploy

The repo is wired to Vercel:
- Root directory: `web/`
- Framework preset: Next.js (auto-detected)
- Install: `pnpm install`
- Build: `pnpm build`
- Required env: `DATABASE_URL`
- The app gracefully renders an "OFFLINE" ledger state when the DB is
  unreachable, so Preview deploys without a DB still render.
