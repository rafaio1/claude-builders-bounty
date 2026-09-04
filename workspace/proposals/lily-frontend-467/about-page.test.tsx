import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

vi.mock('next/link', () => ({
  default: ({ children, href }: { children: React.ReactNode; href: string }) => (
    <a href={href}>{children}</a>
  ),
}));

vi.mock('next/navigation', () => ({
  usePathname: () => '/about',
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
}));

import AboutPage from '../(marketing)/about/page';

describe('About page', () => {
  it('renders a single h1 and section headings in logical order', () => {
    render(<AboutPage />);

    const h1 = screen.getByRole('heading', { level: 1, name: /about/i });
    expect(h1).toBeInTheDocument();

    const headings = screen.getAllByRole('heading');
    const levels = headings.map((h) => Number(h.getAttribute('aria-level') ?? h.tagName.replace('H', '')));

    // First heading must be h1; subsequent headings must be h2 or lower
    expect(levels[0]).toBe(1);
    for (let i = 1; i < levels.length; i += 1) {
      expect(levels[i]).toBeGreaterThanOrEqual(2);
    }
  });

  it('renders mission section', () => {
    render(<AboutPage />);
    expect(
      screen.getByRole('heading', { level: 2, name: /mission/i }),
    ).toBeInTheDocument();
  });

  it('renders values section', () => {
    render(<AboutPage />);
    expect(
      screen.getByRole('heading', { level: 2, name: /values/i }),
    ).toBeInTheDocument();
  });

  it('renders ecosystem credibility section', () => {
    render(<AboutPage />);
    expect(
      screen.getByRole('heading', { level: 2, name: /ecosystem credibility/i }),
    ).toBeInTheDocument();
  });

  it('does not contain nested main landmarks', () => {
    const { container } = render(<AboutPage />);
    const mains = container.querySelectorAll('main');
    expect(mains).toHaveLength(0);
  });
});