import type { Metadata } from 'next';

import { createScaffoldMetadata } from '@/features/scaffold/page-factory';

export const metadata: Metadata = createScaffoldMetadata('about');

const values = [
  {
    title: 'Open by default',
    description:
      'Every protocol decision, design artifact, and contribution workflow is public so the community can verify, fork, and improve the work.',
  },
  {
    title: 'Contributor-first tooling',
    description:
      'Scaffolds, tokens, and validation guardrails exist to make first-time contributors productive without memorizing internal conventions.',
  },
  {
    title: 'Trust through transparency',
    description:
      'Security posture, audit status, and operational metrics are published alongside the product so users can evaluate risk independently.',
  },
] as const;

export default function AboutPage() {
  return (
    <div className="surface rounded-[1.75rem] p-8 sm:p-10">
      <p className="eyebrow text-(--color-accent)">marketing</p>

      <div className="mt-4 max-w-3xl">
        <h1 className="text-4xl font-semibold tracking-tight">About</h1>
        <p className="mt-4 text-lg leading-8 text-(--color-muted)">
          Lily Protocol is an open-source contributor network building stable,
          issue-driven frontend foundations for Stellar ecosystem projects. We
          coordinate designers, engineers, and maintainers around shared bounties
          so critical surfaces stay accessible, tested, and aligned with the
          protocol’s roadmap.
        </p>
      </div>

      <section aria-labelledby="mission-heading" className="mt-12">
        <h2 id="mission-heading" className="text-2xl font-semibold tracking-tight">
          Mission
        </h2>
        <p className="mt-4 max-w-3xl text-base leading-7 text-(--color-muted)">
          Make high-quality, accessible frontend infrastructure a commons for
          Stellar builders. We reduce duplicated effort by maintaining shared
          components, design tokens, and validation patterns that any team can
          adopt, audit, and extend.
        </p>
      </section>

      <section aria-labelledby="values-heading" className="mt-12">
        <h2 id="values-heading" className="text-2xl font-semibold tracking-tight">
          Values
        </h2>
        <ul className="mt-6 grid gap-6 md:grid-cols-3">
          {values.map((value) => (
            <li
              key={value.title}
              className="rounded-3xl border border-(--color-line) bg-(--color-panel-muted) p-6"
            >
              <h3 className="text-lg font-semibold">{value.title}</h3>
              <p className="mt-3 text-sm leading-7 text-(--color-muted)">
                {value.description}
              </p>
            </li>
          ))}
        </ul>
      </section>

      <section aria-labelledby="ecosystem-heading" className="mt-12">
        <h2 id="ecosystem-heading" className="text-2xl font-semibold tracking-tight">
          Ecosystem credibility
        </h2>
        <p className="mt-4 max-w-3xl text-base leading-7 text-(--color-muted)">
          Lily Protocol coordinates with Stellar Foundation grant programs,
          Soroban tooling teams, and partner DAOs to keep the frontend stack in
          sync with runtime upgrades. Contributors ship against public bounties
          with automated CI, accessibility checks, and design review so merged
          work meets production standards on day one.
        </p>
      </section>
    </div>
  );
}