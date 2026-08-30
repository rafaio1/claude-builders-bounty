/**
 * src/api/grants-bounties.ts
 *
 * [ECO08] Grants & Bounties Activity Explorer
 * Issue #1019 — Surface on-chain and program activity (proposals, contributions,
 * reward streams) relevant to grant/bounty programs into a dashboard API.
 *
 * Endpoints:
 *   GET /api/v1/grants-bounties/overview      — aggregate stats for dashboard
 *   GET /api/v1/grants-bounties/proposals     — grant-related proposals (paginated)
 *   GET /api/v1/grants-bounties/streams       — active reward/payout streams
 *   GET /api/v1/grants-bounties/leaderboard   — top contributors by payout/reputation
 *   GET /api/v1/grants-bounties/milestones    — proposal milestones & execution status
 *
 * All reads are public. Data sourced from existing GovernanceProposal,
 * TreasuryPayoutStream, TreasuryTransaction, and GovernanceVote tables.
 */
import { Router, Request, Response } from 'express';
import { z } from 'zod';
import { prismaRead } from '../db';
import { asyncHandler } from '../middleware/asyncHandler';

export const grantsBountiesRouter = Router();

// ─── Schemas ──────────────────────────────────────────────────────────────────

const paginationSchema = z.object({
  page: z.coerce.number().int().min(1).default(1),
  limit: z.coerce.number().int().min(1).max(100).default(20),
});

const proposalFilterSchema = paginationSchema.extend({
  status: z.string().optional(),
  template: z.string().optional(),
  proposer: z.string().optional(),
  search: z.string().optional(),
});

const leaderboardSchema = z.object({
  limit: z.coerce.number().int().min(1).max(100).default(20),
  orderBy: z.enum(['totalPaid', 'streamCount', 'voteCount']).default('totalPaid'),
});

// ─── Helpers ──────────────────────────────────────────────────────────────────

function grantProposalWhere() {
  // Heuristic: grant/bounty proposals are fund_transfer templates or contain
  // grant/bounty keywords in title/description. This avoids schema changes
  // while surfacing the relevant subset of governance proposals.
  return {
    OR: [
      { template: 'fund_transfer' },
      { title: { contains: 'grant', mode: 'insensitive' as const } },
      { title: { contains: 'bounty', mode: 'insensitive' as const } },
      { description: { contains: 'grant', mode: 'insensitive' as const } },
      { description: { contains: 'bounty', mode: 'insensitive' as const } },
    ],
  };
}

// ─── GET /overview ────────────────────────────────────────────────────────────

grantsBountiesRouter.get(
  '/overview',
  asyncHandler(async (_req: Request, res: Response) => {
    const where = grantProposalWhere();

    const [
      totalProposals,
      activeProposals,
      executedProposals,
      totalStreams,
      activeStreams,
      totalPayouts,
      uniqueRecipients,
    ] = await Promise.all([
      prismaRead.governanceProposal.count({ where }),
      prismaRead.governanceProposal.count({ where: { ...where, status: 'active' } }),
      prismaRead.governanceProposal.count({ where: { ...where, status: 'executed' } }),
      prismaRead.treasuryPayoutStream.count(),
      prismaRead.treasuryPayoutStream.count({ where: { status: 'active' } }),
      prismaRead.treasuryTransaction.aggregate({
        _sum: { amount: true },
        where: { direction: 'outflow', category: 'grants' },
      }),
      prismaRead.treasuryPayoutStream.groupBy({
        by: ['recipient'],
        _count: true,
      }),
    ]);

    res.json({
      proposals: {
        total: totalProposals,
        active: activeProposals,
        executed: executedProposals,
      },
      streams: {
        total: totalStreams,
        active: activeStreams,
      },
      payouts: {
        totalOutflow: totalPayouts._sum.amount ?? '0',
        uniqueRecipients: uniqueRecipients.length,
      },
      updatedAt: new Date().toISOString(),
    });
  }),
);

// ─── GET /proposals ───────────────────────────────────────────────────────────

grantsBountiesRouter.get(
  '/proposals',
  asyncHandler(async (req: Request, res: Response) => {
    const parsed = proposalFilterSchema.safeParse(req.query);
    if (!parsed.success) return res.status(400).json({ error: parsed.error.flatten() });

    const { page, limit, status, template, proposer, search } = parsed.data;
    const base = grantProposalWhere();

    const where: Record<string, unknown> = { ...base };
    if (status) where.status = status;
    if (template) where.template = template;
    if (proposer) where.proposer = proposer;
    if (search) {
      where.AND = [
        ...(Array.isArray(where.OR) ? [{ OR: where.OR }] : []),
        {
          OR: [
            { title: { contains: search, mode: 'insensitive' } },
            { description: { contains: search, mode: 'insensitive' } },
          ],
        },
      ];
    }

    const [proposals, total] = await Promise.all([
      prismaRead.governanceProposal.findMany({
        where,
        select: {
          id: true,
          proposalId: true,
          contractAddress: true,
          proposer: true,
          title: true,
          description: true,
          template: true,
          status: true,
          startBlock: true,
          endBlock: true,
          votesFor: true,
          votesAgainst: true,
          executedAt: true,
          createdAt: true,
        },
        orderBy: { createdAt: 'desc' },
        skip: (page - 1) * limit,
        take: limit,
      }),
      prismaRead.governanceProposal.count({ where }),
    ]);

    res.json({ data: proposals, total, page, pages: Math.ceil(total / limit) });
  }),
);

// ─── GET /streams ─────────────────────────────────────────────────────────────

grantsBountiesRouter.get(
  '/streams',
  asyncHandler(async (req: Request, res: Response) => {
    const parsed = paginationSchema.safeParse(req.query);
    if (!parsed.success) return res.status(400).json({ error: parsed.error.flatten() });

    const { page, limit } = parsed.data;
    const status = req.query.status as string | undefined;

    const where: Record<string, unknown> = {};
    if (status) where.status = status;

    const [streams, total] = await Promise.all([
      prismaRead.treasuryPayoutStream.findMany({
        where,
        include: {
          treasury: { select: { accountAddress: true, name: true, contractAddress: true } },
        },
        orderBy: { createdAt: 'desc' },
        skip: (page - 1) * limit,
        take: limit,
      }),
      prismaRead.treasuryPayoutStream.count({ where }),
    ]);

    res.json({ data: streams, total, page, pages: Math.ceil(total / limit) });
  }),
);

// ─── GET /leaderboard ─────────────────────────────────────────────────────────

grantsBountiesRouter.get(
  '/leaderboard',
  asyncHandler(async (req: Request, res: Response) => {
    const parsed = leaderboardSchema.safeParse(req.query);
    if (!parsed.success) return res.status(400).json({ error: parsed.error.flatten() });

    const { limit, orderBy } = parsed.data;

    if (orderBy === 'totalPaid') {
      const rows = await prismaRead.treasuryTransaction.groupBy({
        by: ['counterparty'],
        _sum: { amount: true },
        _count: true,
        where: { direction: 'outflow', counterparty: { not: null } },
        orderBy: { _sum: { amount: 'desc' } },
        take: limit,
      });

      const leaderboard = rows.map((r, i) => ({
        rank: i + 1,
        address: r.counterparty,
        totalPaid: r._sum.amount ?? '0',
        transactionCount: r._count,
      }));

      return res.json({ data: leaderboard, orderBy });
    }

    if (orderBy === 'streamCount') {
      const rows = await prismaRead.treasuryPayoutStream.groupBy({
        by: ['recipient'],
        _count: true,
        orderBy: { _count: { recipient: 'desc' } },
        take: limit,
      });

      const leaderboard = rows.map((r, i) => ({
        rank: i + 1,
        address: r.recipient,
        streamCount: r._count,
      }));

      return res.json({ data: leaderboard, orderBy });
    }

    // voteCount — top voters across grant-related proposals
    const grantProposals = await prismaRead.governanceProposal.findMany({
      where: grantProposalWhere(),
      select: { contractAddress: true, proposalId: true },
    });

    const proposalKeys = grantProposals.map((p) => ({
      contractAddress: p.contractAddress,
      proposalId: p.proposalId,
    }));

    if (proposalKeys.length === 0) {
      return res.json({ data: [], orderBy });
    }

    const rows = await prismaRead.governanceVote.groupBy({
      by: ['voter'],
      _count: true,
      where: {
        OR: proposalKeys,
      },
      orderBy: { _count: { voter: 'desc' } },
      take: limit,
    });

    const leaderboard = rows.map((r, i) => ({
      rank: i + 1,
      address: r.voter,
      voteCount: r._count,
    }));

    res.json({ data: leaderboard, orderBy });
  }),
);

// ─── GET /milestones ──────────────────────────────────────────────────────────

grantsBountiesRouter.get(
  '/milestones',
  asyncHandler(async (req: Request, res: Response) => {
    const parsed = paginationSchema.safeParse(req.query);
    if (!parsed.success) return res.status(400).json({ error: parsed.error.flatten() });

    const { page, limit } = parsed.data;
    const where = grantProposalWhere();

    const [proposals, total] = await Promise.all([
      prismaRead.governanceProposal.findMany({
        where,
        select: {
          id: true,
          proposalId: true,
          contractAddress: true,
          title: true,
          status: true,
          startBlock: true,
          endBlock: true,
          queuedAt: true,
          eta: true,
          executedAt: true,
          executionTxHash: true,
          createdAt: true,
          updatedAt: true,
        },
        orderBy: { updatedAt: 'desc' },
        skip: (page - 1) * limit,
        take: limit,
      }),
      prismaRead.governanceProposal.count({ where }),
    ]);

    const milestones = proposals.map((p) => ({
      ...p,
      timeline: {
        created: p.createdAt,
        votingStart: p.startBlock,
        votingEnd: p.endBlock,
        queued: p.queuedAt,
        executableAfter: p.eta,
        executed: p.executedAt,
      },
      executionTx: p.executionTxHash,
    }));

    res.json({ data: milestones, total, page, pages: Math.ceil(total / limit) });
  }),
);
