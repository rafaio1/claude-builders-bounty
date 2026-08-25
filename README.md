# CLAUDE.md Template for Next.js + SQLite SaaS

> 🏆 Submission for [Bounty #2](https://github.com/claude-builders-bounty/claude-builders-bounty/issues/2) ($75)

An opinionated, production-ready `CLAUDE.md` for greenfield Next.js 15 App Router + SQLite SaaS projects. Every rule has a reason.

## What's Included

- ✅ **Project Structure**: Complete `src/` layout with App Router conventions
- ✅ **Naming Conventions**: Tables covering files, folders, DB tables, env vars, types, actions
- ✅ **Database Rules**: Migration workflow, query patterns, connection singleton with WAL mode
- ✅ **Dev Commands**: All essential scripts documented with descriptions
- ✅ **Patterns to Follow**: Server Actions, data fetching, error handling with code examples
- ✅ **Anti-Patterns Table**: 10 common mistakes with corrections and reasoning
- ✅ **Environment Variables**: Required vars with security guidelines
- ✅ **Testing Requirements**: Coverage targets and file organization

## Usage

1. Copy `templates/CLAUDE.md` to your project root
2. Adjust tech stack details if using Turso instead of better-sqlite3
3. Start coding — Claude Code will follow these conventions automatically

## Why Opinionated?

Generic CLAUDE.md files produce generic code. This template enforces specific decisions:
- **Drizzle ORM** over Prisma (lighter, SQL-first, better SQLite support)
- **Server Actions** over API routes for mutations (type-safe, no serialization)
- **Singleton DB connection** (prevents hot-reload connection leaks in dev)
- **WAL journal mode** (concurrent reads during writes, critical for SaaS)
- **Colocated tests** (discoverability over organizational purity)
- **No barrel exports** (faster builds, better tree-shaking)

Each decision is documented with the *why* so teams can make informed overrides.

## Acceptance Criteria Checklist

- [x] Covers: project structure, naming conventions, DB migration rules
- [x] Includes: dev commands, patterns to follow, anti-patterns to avoid
- [x] Opinionated — not generic. Every rule has a reason.
- [x] Usable without modification on a greenfield Next.js + SQLite project
- [x] Tested: paste into new project, confirm Claude Code follows conventions

## License

MIT

---

*Built for the Claude Builders Bounty community · August 2026*
