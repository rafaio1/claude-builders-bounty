# CLAUDE.md — Next.js + SQLite SaaS Project

> Opinionated project instructions for Claude Code. Paste at repo root.

## Tech Stack

- **Framework**: Next.js 15 (App Router, `app/` directory)
- **Database**: SQLite via `better-sqlite3` (synchronous, zero-config) or Turso (libsql, edge-compatible)
- **ORM**: Drizzle ORM with `drizzle-kit` for migrations
- **Styling**: Tailwind CSS + shadcn/ui components
- **Auth**: NextAuth.js v5 (Auth.js) with SQLite adapter
- **Validation**: Zod schemas shared between server and client
- **Testing**: Vitest + React Testing Library + Playwright E2E

## Project Structure

```
src/
├── app/                    # Next.js App Router pages & layouts
│   ├── (auth)/             # Auth route group (login, register, reset)
│   ├── (dashboard)/        # Protected route group
│   │   ├── layout.tsx      # Dashboard shell with sidebar/nav
│   │   └── page.tsx        # Dashboard home
│   ├── api/                # API routes (server-only)
│   │   ├── auth/[...nextauth]/route.ts
│   │   └── trpc/[trpc]/route.ts
│   ├── layout.tsx          # Root layout (html, body, providers)
│   └── page.tsx            # Landing page
├── components/             # Shared UI components
│   ├── ui/                 # shadcn/ui primitives (button, input, etc.)
│   └── features/           # Feature-specific composite components
├── db/                     # Database layer
│   ├── schema.ts           # Drizzle table definitions
│   ├── migrate.ts          # Migration runner
│   └── connection.ts       # DB connection singleton
├── lib/                    # Shared utilities (non-React)
│   ├── auth.ts             # Auth helpers & session checks
│   ├── validators.ts       # Zod schemas
│   └── utils.ts            # cn(), formatDate(), etc.
├── server/                 # Server-only business logic
│   ├── actions.ts          # Server Actions (form mutations)
│   └── queries.ts          # Read operations (cached where possible)
└── types/                  # Shared TypeScript interfaces
```

## Naming Conventions

| Element | Convention | Example |
|---------|-----------|---------|
| Files (components) | PascalCase | `UserProfile.tsx` |
| Files (utils/hooks) | camelCase | `useDebounce.ts` |
| Folders | kebab-case | `user-settings/` |
| DB tables | snake_case plural | `user_accounts` |
| DB columns | snake_case | `created_at` |
| Env vars | SCREAMING_SNAKE | `DATABASE_URL` |
| Types/Interfaces | PascalCase + suffix | `UserAccount`, `CreateUserInput` |
| Server Actions | verb + noun | `createUser`, `deleteProject` |
| API routes | kebab-case nouns | `/api/user-accounts` |

## Database Rules

### Migrations
- **NEVER** edit existing migration files. Create new ones via `npx drizzle-kit generate`.
- **ALWAYS** run `npx drizzle-kit push` in dev to apply schema changes instantly.
- **ALWAYS** run `npx drizzle-kit migrate` in production/staging.
- Every table MUST have: `id` (text, primary key, cuid2), `created_at`, `updated_at`.
- Use `timestamp('created_at').defaultNow().notNull()` pattern consistently.

### Queries
- All reads go through `src/server/queries.ts` — never inline SQL in components.
- Use Drizzle's query builder, not raw SQL, unless performance-critical (document why).
- Add `.returning()` to all insert/update/delete operations.
- Wrap multi-step mutations in transactions: `db.transaction(async (tx) => { ... })`.

### Connection
```typescript
// src/db/connection.ts — singleton pattern prevents hot-reload leaks
import Database from 'better-sqlite3';
import { drizzle } from 'drizzle-orm/better-sqlite3';
import * as schema from './schema';

const globalForDb = globalThis as unknown as { db: ReturnType<typeof createDb> };

function createDb() {
  const sqlite = new Database(process.env.DATABASE_URL || 'file:local.db');
  sqlite.pragma('journal_mode = WAL');
  sqlite.pragma('foreign_keys = ON');
  return drizzle(sqlite, { schema });
}

export const db = globalForDb.db ?? createDb();
if (process.env.NODE_ENV !== 'production') globalForDb.db = db;
```

## Dev Commands

```bash
# Development
pnpm dev              # Start dev server (Turbopack)
pnpm db:push          # Push schema changes to dev DB
pnpm db:generate      # Generate new migration file
pnpm db:migrate       # Apply pending migrations
pnpm db:studio        # Open Drizzle Studio (DB GUI)

# Quality
pnpm lint             # ESLint + Prettier check
pnpm lint:fix         # Auto-fix lint issues
pnpm typecheck        # tsc --noEmit
pnpm test             # Vitest unit tests
pnpm test:e2e         # Playwright E2E tests
pnpm build            # Production build (validates everything)
```

## Patterns to Follow

### Server Actions
```typescript
// ✅ DO: Validate input, handle errors, revalidate paths
export async function createProject(input: CreateProjectInput) {
  const session = await requireSession(); // throws if unauthenticated
  const validated = createProjectSchema.parse(input);
  
  const [project] = await db.insert(projects)
    .values({ ...validated, ownerId: session.user.id })
    .returning();
    
  revalidatePath('/dashboard/projects');
  return project;
}
```

### Data Fetching
```typescript
// ✅ DO: Separate read logic, use unstable_cache for expensive queries
export async function getProjects(userId: string) {
  return db.select().from(projects).where(eq(projects.ownerId, userId));
}

// ✅ DO: Cache dashboard stats (revalidate every 60s)
export const getDashboardStats = unstable_cache(
  async (userId: string) => { /* ... */ },
  ['dashboard-stats'],
  { revalidate: 60 }
);
```

### Error Handling
```typescript
// ✅ DO: Use typed error boundaries, never expose stack traces
// In Server Actions: return structured errors, don't throw
// In API routes: use standardized error response format
// In components: <ErrorBoundary fallback={<ErrorMessage />}>
```

## Anti-Patterns to Avoid

| ❌ DON'T | ✅ DO INSTEAD | Why |
|----------|--------------|-----|
| `fetch()` in Server Components for DB queries | Drizzle query in `queries.ts` | No network overhead, type-safe |
| `useEffect` for data fetching | Server Components + Suspense | SSR, no waterfall |
| Raw SQL strings | Drizzle query builder | SQL injection safe, typed |
| `any` type | Define interface in `types/` | Catches bugs at compile time |
| Client-side auth checks only | `requireSession()` on server | Prevents unauthorized access |
| Inline styles / className strings | Tailwind + `cn()` utility | Consistent design system |
| Direct `process.env` in components | Pass via props or server action | Security, testability |
| Mutating state from child components | Server Actions or callbacks | Predictable data flow |
| `console.log` in production code | Structured logging lib | Observable, filterable |
| Barrel exports (`index.ts`) for large modules | Direct imports | Faster builds, tree-shaking |

## Environment Variables

Required variables (see `.env.example`):
- `DATABASE_URL` — SQLite file path or Turso connection string
- `NEXTAUTH_SECRET` — Auth encryption secret
- `NEXTAUTH_URL` — App base URL
- `NODE_ENV` — `development` | `production` | `test`

Never commit `.env`. Never log secrets. Never use env vars in client components without `NEXT_PUBLIC_` prefix (and understand the security implications).

## Testing Requirements

- Unit tests for all `lib/` and `server/` functions
- Component tests for interactive components (not static UI)
- E2E tests for critical user flows (auth, CRUD, payment)
- Minimum 80% line coverage on `server/` directory
- Test files colocated: `Component.test.tsx` next to `Component.tsx`

---

*Generated for Claude Builders Bounty #2 · August 2026*
