# CLAUDE.md — Next.js 15 App Router + SQLite SaaS

## Stack & Versions
- **Runtime**: Node.js 20 LTS (ESM only)
- **Framework**: Next.js 15.x (App Router, no Pages)
- **Database**: better-sqlite3 11.x (synchronous, zero-config) or Turso (libsql) for edge
- **ORM**: Drizzle ORM 0.36+ (schema-first, type-safe SQL)
- **Styling**: Tailwind CSS 4.x + shadcn/ui primitives
- **Validation**: Zod 3.23+ at every boundary (env, API input, form)
- **Auth**: Better Auth or Lucia v3 (no NextAuth — deprecated patterns)

## Folder Structure
```
src/
  app/              # Routes, layouts, loading.tsx, error.tsx
    (marketing)/    # Public pages (landing, pricing)
    (dashboard)/    # Protected app routes
    api/            # Route handlers only — no business logic here
  components/       # UI primitives (shadcn) + composite features
    ui/             # Atomic: Button, Input, Dialog
    features/       # Domain: BillingForm, TeamInviteModal
  db/
    schema.ts       # Single source of truth for all tables
    migrate.ts      # Migration runner (drizzle-kit generate/migrate)
    seed.ts         # Dev/test data seeder
  lib/
    auth.ts         # Session helpers, guards
    validators.ts   # Shared Zod schemas
    utils.ts        # Pure functions only
  hooks/            # Client-side React hooks
  types/            # Global TypeScript interfaces
```

## Naming Conventions
- **Files**: kebab-case (`user-profile.tsx`, `create-team.ts`)
- **Components**: PascalCase exports, default export for page components
- **DB columns**: snake_case in schema, camelCase in TS via Drizzle mapping
- **API routes**: RESTful nouns plural (`/api/teams/:id/members`)
- **Env vars**: `NEXT_PUBLIC_` prefix ONLY for client-exposed values; never secrets
- **Types**: Suffix with `T` for internal types (`UserT`), no suffix for DB entities

## Database & Migration Rules
1. **Never edit existing migrations**. Create new ones via `pnpm drizzle-kit generate`.
2. **All tables must have**: `id TEXT PRIMARY KEY DEFAULT (ulid())`, `created_at INTEGER NOT NULL`, `updated_at INTEGER NOT NULL`.
3. **Foreign keys**: Always `ON DELETE CASCADE` unless explicit business requirement states otherwise. Document exception in schema comment.
4. **No raw SQL in route handlers**. Use Drizzle query builder or prepared statements from `db/queries/`.
5. **Transactions**: Wrap multi-table writes in `db.transaction()`. Never rely on implicit commits.
6. **SQLite pragmas**: Set in `db/connection.ts`: `journal_mode=WAL`, `foreign_keys=ON`, `busy_timeout=5000`.
7. **Seed before test**: `pnpm db:seed` must be idempotent and safe to run repeatedly.

## Component Patterns
- **Server Components by default**. Add `"use client"` only when using hooks, event handlers, or browser APIs.
- **Data fetching**: Server Components fetch directly via Drizzle. No SWR/React Query for server data.
- **Forms**: Server Actions for mutations. Validate with Zod on server AND client. Show inline errors.
- **Loading states**: Co-locate `loading.tsx` next to the route it serves.
- **Error boundaries**: Every `(group)` folder must have an `error.tsx`. Log to `/api/errors` endpoint.
- **Props**: Define interface above component. No inline prop types. Export interface if reused.

## Anti-Patterns (Do Not Do)
- ❌ `getServerSideProps` / `getStaticProps` — App Router replaces these entirely.
- ❌ `next-auth` — Unmaintained; use Better Auth or Lucia.
- ❌ Prisma with SQLite — Overhead unjustified; Drizzle is lighter and sync-compatible.
- ❌ Barrel files (`index.ts`) in `components/` — Causes tree-shaking failures and slow IDE.
- ❌ `any` type — Configure `strict: true` in tsconfig. Fix the root cause.
- ❌ Environment variables without Zod validation — App crashes silently at runtime otherwise.
- ❌ Direct `fetch()` in Server Components without error handling — Wrap in try/catch or use Result pattern.
- ❌ Mutable global state — Use React Context or URL search params for shared client state.

## Dev Commands
```bash
pnpm dev              # Start dev server (Turbopack)
pnpm build            # Production build
pnpm lint             # ESLint + Prettier check
pnpm typecheck        # tsc --noEmit
pnpm db:generate      # Generate migration from schema changes
pnpm db:migrate       # Apply pending migrations
pnpm db:seed          # Seed development data
pnpm db:studio        # Open Drizzle Studio (visual DB explorer)
pnpm test             # Vitest (unit + integration)
pnpm test:e2e         # Playwright E2E suite
```

## Testing Strategy
- **Unit**: Vitest for pure functions in `lib/`. Mock DB layer.
- **Integration**: Test route handlers against real SQLite (in-memory). Reset between tests.
- **E2E**: Playwright covers critical paths: signup → onboarding → billing → team invite.
- **Coverage threshold**: 80% line coverage enforced in CI. Exclusions require `// istanbul ignore` + comment.

## Deployment Notes
- **Vercel**: Use `@vercel/postgres` adapter OR Turso. `better-sqlite3` requires custom server (not supported).
- **Docker/Fly.io**: `better-sqlite3` works natively. Mount volume for persistence.
- **Environment parity**: `.env.local` mirrors production keys (different values). Validate on startup.
- **Preview deployments**: Auto-seed with test data. Never connect to production DB.

## Code Review Checklist
- [ ] New DB column has migration + schema update
- [ ] Zod schema validates all external input
- [ ] Server Action includes authorization check
- [ ] No `"use client"` without justification comment
- [ ] Error boundary present for new route group
- [ ] Types exported if used across modules
- [ ] Test added for non-trivial logic
