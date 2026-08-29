# CLAUDE.md — Next.js 15 + SQLite SaaS

> Opinionated project conventions for AI-assisted development.
> Stack: Next.js 15 (App Router) · TypeScript · better-sqlite3 · Drizzle ORM · Tailwind CSS v4

## Project Structure

```
src/
├── app/                  # App Router pages & layouts
│   ├── (auth)/           # Route group: login, register, forgot-password
│   ├── (dashboard)/      # Route group: protected app pages
│   ├── api/              # API routes (never business logic here)
│   └── layout.tsx        # Root layout with providers
├── components/
│   ├── ui/               # Primitive UI atoms (Button, Input, Card)
│   ├── forms/            # Form components with validation
│   └── layout/           # Sidebar, Header, Nav
├── db/
│   ├── schema.ts         # Drizzle table definitions (single source of truth)
│   ├── migrate.ts        # Migration runner
│   └── queries/          # Typed query functions (one file per domain)
├── lib/
│   ├── auth.ts           # Session/JWT helpers
│   ├── validators.ts     # Zod schemas shared server/client
│   └── utils.ts          # Pure utility functions
└── types/                # Shared TypeScript interfaces
```

## Naming Conventions

| Element | Convention | Example |
|---------|-----------|---------|
| Files/folders | kebab-case | `user-profile.tsx`, `db/queries/` |
| Components | PascalCase export | `export function UserProfile()` |
| DB tables | snake_case plural | `users`, `subscription_tiers` |
| DB columns | snake_case | `created_at`, `email_verified` |
| API routes | kebab-case nouns | `/api/users`, `/api/billing/invoices` |
| Env vars | SCREAMING_SNAKE | `DATABASE_PATH`, `NEXT_PUBLIC_APP_URL` |
| Types | PascalCase + suffix | `UserRecord`, `CreateInvoiceInput` |

## Database Rules

1. **Schema is code**: All tables defined in `src/db/schema.ts` using Drizzle. Never write raw SQL for DDL.
2. **Migrations are sequential**: Files in `drizzle/migrations/` named `0001_initial.sql`. Never edit applied migrations.
3. **Queries are typed functions**: Each domain has `src/db/queries/<domain>.ts`. Export async functions that return typed results. No inline SQL in components or API routes.
4. **No ORM magic in components**: Components receive plain objects, never Drizzle query builders.
5. **Timestamps**: Every table has `created_at` and `updated_at` (auto-managed via triggers or defaults). Use ISO 8601 strings at the API boundary.
6. **IDs**: Use `text` primary keys with ULID (`ulid()` from `@paralleldrive/cuid2`). No auto-increment integers.
7. **Soft deletes**: Add `deleted_at text` nullable column. Filter in queries. Never hard-delete user data.

## Component Patterns

- **Server Components by default**. Only add `"use client"` when you need interactivity, hooks, or browser APIs.
- **Data fetching**: Server Components call query functions directly. No `fetch()` to your own API routes.
- **Forms**: Use `react-hook-form` + `zod` + server actions. Validate on both client and server.
- **Loading states**: Co-locate `loading.tsx` next to the page. Use Suspense boundaries for partial loading.
- **Error handling**: Co-locate `error.tsx`. Log errors server-side; show generic messages to users.

## Dev Commands

```bash
pnpm dev              # Start dev server (Turbopack)
pnpm build            # Production build
pnpm db:migrate       # Run pending migrations
pnpm db:generate      # Generate new migration from schema changes
pnpm db:studio        # Open Drizzle Studio
pnpm lint             # ESLint + typecheck
pnpm test             # Vitest (unit + integration)
```

## Anti-Patterns (Do NOT Do)

| ❌ Don't | ✅ Do Instead | Why |
|----------|--------------|-----|
| Raw SQL strings in API routes | Typed query functions in `db/queries/` | Type safety, testability, single place to optimize |
| `fetch('/api/...')` in Server Components | Direct query function calls | Avoids HTTP overhead, prevents waterfall |
| Business logic in API route handlers | Service functions in `lib/` or `db/queries/` | Routes are adapters, not controllers |
| `any` type anywhere | Explicit types or Zod inference | AI generates better code with strict types |
| Global state for server data | Server Components + cache tags | Next.js caching is superior to client state for DB data |
| Inline Tailwind classes > 5 | Extract to component or `cva()` variant | Readability, reusability |
| `process.env` outside `lib/env.ts` | Centralized env validation with Zod | Fail fast at startup, typed access |
| Prisma or other ORMs | Drizzle ORM | Lighter bundle, SQL-first, better SQLite support |

## Testing

- **Unit tests**: Vitest for pure functions in `lib/` and `db/queries/`.
- **Integration tests**: Test API routes with actual SQLite (in-memory or temp file). Mock nothing.
- **E2E**: Playwright only for critical user flows (signup → dashboard → billing).
- **Coverage threshold**: 80% for `db/queries/`, 60% overall.

## AI Assistant Notes

- Always read `src/db/schema.ts` before writing any database-related code.
- When creating a new feature: schema → migration → query functions → server component/API route → tests.
- Prefer existing patterns over novel solutions. Check similar files first.
- If unsure about a convention, follow the pattern in the closest existing file.
- Never modify `drizzle/migrations/` files that have already been applied.
