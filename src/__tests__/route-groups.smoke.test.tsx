import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

vi.mock("next/link", () => ({
  default: ({ children, href }: { children: React.ReactNode; href: string }) => (
    <a href={href}>{children}</a>
  ),
}));

vi.mock("@/config/site", () => ({
  routes: { home: "/", docs: "/docs", signin: "/signin", dashboard: "/app" },
  siteConfig: { name: "Lilly" },
}));

vi.mock("@/config/routes", () => ({
  sectionDefinitions: [
    { key: "marketing", label: "Marketing", description: "Public site" },
    { key: "auth", label: "Auth", description: "Authentication" },
    { key: "docs", label: "Docs", description: "Documentation" },
    { key: "legal", label: "Legal", description: "Legal pages" },
    { key: "dashboard", label: "Dashboard", description: "App dashboard" },
  ],
  getSectionRoutes: (section: string) => {
    const map: Record<string, Array<{ id: string; title: string; path: string }>> = {
      marketing: [{ id: "m1", title: "Home", path: "/" }],
      auth: [{ id: "a1", title: "Sign In", path: "/signin" }],
      docs: [{ id: "d1", title: "Docs", path: "/docs" }],
      legal: [{ id: "l1", title: "Privacy", path: "/privacy" }],
      dashboard: [{ id: "db1", title: "Dashboard", path: "/app" }],
    };
    return map[section] ?? [];
  },
}));

import MarketingLayout from "@/app/(marketing)/layout";
import AuthLayout from "@/app/(auth)/layout";
import SupportLayout from "@/app/(support)/layout";
import DashboardLayout from "@/app/app/layout";

describe("Route group layouts render expected landmarks", () => {
  it("renders SiteHeader and SectionNav in marketing layout", () => {
    render(<MarketingLayout><div>Marketing Page</div></MarketingLayout>);
    expect(screen.getByRole("banner")).toBeInTheDocument();
    expect(screen.getByLabelText("Section routes")).toBeInTheDocument();
    expect(screen.getByText("Marketing Page")).toBeInTheDocument();
  });

  it("renders SiteHeader and SectionNav in auth layout", () => {
    render(<AuthLayout><div>Auth Page</div></AuthLayout>);
    expect(screen.getByRole("banner")).toBeInTheDocument();
    expect(screen.getByLabelText("Section routes")).toBeInTheDocument();
    expect(screen.getByText("Auth Page")).toBeInTheDocument();
  });

  it("renders SiteHeader and SectionNav in support layout", () => {
    render(<SupportLayout><div>Support Page</div></SupportLayout>);
    expect(screen.getByRole("banner")).toBeInTheDocument();
    expect(screen.getByLabelText("Section routes")).toBeInTheDocument();
    expect(screen.getByText("Support Page")).toBeInTheDocument();
  });

  it("renders SiteHeader and SectionNav in dashboard layout", () => {
    render(<DashboardLayout><div>Dashboard Page</div></DashboardLayout>);
    expect(screen.getByRole("banner")).toBeInTheDocument();
    expect(screen.getByLabelText("Section routes")).toBeInTheDocument();
    expect(screen.getByText("Dashboard Page")).toBeInTheDocument();
  });
});
