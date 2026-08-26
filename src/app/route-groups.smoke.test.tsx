import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import LandingPage from "./(marketing)/page";
import SignInPage from "./(auth)/signin/page";
import DocsPage from "./(support)/docs/page";
import DashboardOverviewPage from "./app/page";

describe("Route group layout smoke tests", () => {
  it("renders marketing pages inside the marketing section layout", () => {
    render(<LandingPage />);

    expect(
      screen.getByRole("link", { name: /lily protocol/i }),
    ).toBeInTheDocument();
    expect(screen.getByText("Public marketing")).toBeInTheDocument();
    expect(
      screen.getByRole("link", { name: /landing page/i }),
    ).toHaveAttribute("href", "/");
  });

  it("renders auth pages inside the auth section layout", () => {
    render(<SignInPage />);

    expect(screen.getByText("Auth")).toBeInTheDocument();
    expect(
      screen.getByRole("link", { name: /sign in/i }),
    ).toHaveAttribute("href", "/signin");
  });

  it("renders support/docs pages inside the support section layout", () => {
    render(<DocsPage />);

    expect(screen.getByText(/docs, status, and legal/i)).toBeInTheDocument();
    expect(
      screen.getByRole("link", { name: /documentation/i }),
    ).toHaveAttribute("href", "/docs");
  });

  it("renders dashboard pages inside the dashboard section layout", () => {
    render(<DashboardOverviewPage />);

    expect(screen.getByText("Dashboard")).toBeInTheDocument();
    expect(
      screen.getByRole("link", { name: /dashboard overview/i }),
    ).toHaveAttribute("href", "/app");
  });
});
