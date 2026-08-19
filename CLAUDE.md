# CLAUDE.md - Next.js + SQLite SaaS Project Guide

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview
This is a B2B SaaS application built with Next.js (App Router) and SQLite (via Drizzle ORM or better-sqlite3). It focuses on rapid local development, edge-compatible deployments, and type-safe database interactions.

## Common Development Commands

### Local Development
```bash
# Install dependencies
pnpm install

# Run development server (starts on http://localhost:3000)
pnpm dev

# Run database migrations
pnpm db:migrate

# Seed database with test data
pnpm db:seed

# Open database GUI (Drizzle Studio or SQLite browser)
pnpm db:studio
```

### Testing & Quality
```bash
# Run unit and integration tests (Vitest)
pnpm test

# Run E2E tests (Playwright)
pnpm test:e2e

# Lint codebase
pnpm lint

# Type-check without building
pnpm typecheck
```

### Build & Production
```bash
# Create production build
pnpm build

# Start production server
pnpm start
```

## Architecture & Codebase Structure

### Next.js App Router
- **`src/app/`**: File-based routing. Use Server Components by default.
  - `layout.tsx`: Root layouts, providers, and global UI (navbars, footers).
  - `page.tsx`: Route entry points.
  - `loading.tsx` / `error.tsx`: Streaming UI and error boundaries.
- **`src/components/`**: Reusable React components.
  - `ui/`: Base UI primitives (buttons, inputs, modals).
  - `features/`: Feature-specific composite components.
- **`src/lib/`**: Shared utilities, API clients, and business logic.
- **`src/actions/`**: Next.js Server Actions for form submissions and mutations.

### SQLite Database Layer
- **`src/db/`**: Database schema, migrations, and connection logic.
  - `schema.ts`: Drizzle ORM table definitions and relations.
  - `index.ts`: Database client initialization. Uses `better-sqlite3` for local and `@libsql/client` for edge/production.
- **Migrations**: Managed via `drizzle-kit`. Never edit existing migration files; always generate new ones (`pnpm db:generate`).
- **Queries**: Keep raw SQL out of components. Use Drizzle's query builder or encapsulate complex queries in `src/db/queries/`.

### Authentication & Multi-tenancy
- **Auth**: Handled by NextAuth.js (Auth.js) or Clerk. Session data is available in Server Components via `auth()`.
- **Tenancy**: Row-Level Security (RLS) is simulated at the query layer. Always filter queries by `tenantId` or `userId` derived from the active session.

## Coding Standards
- **TypeScript**: Strict mode enabled. Avoid `any`; use `zod` for runtime validation of environment variables and API inputs.
- **Styling**: Tailwind CSS. Use utility classes; avoid custom CSS files unless defining complex animations.
- **State Management**: Prefer React Server Components and Server Actions over client-side state (Zustand/Redux) unless building highly interactive widgets.
