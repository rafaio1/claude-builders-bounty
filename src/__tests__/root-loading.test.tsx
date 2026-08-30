import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import RootLoading from "@/app/loading";

describe("RootLoading", () => {
  it("renders loading text", () => {
    render(<RootLoading />);
    expect(screen.getByText(/carregando/i)).toBeInTheDocument();
  });

  it("renders spinner element", () => {
    const { container } = render(<RootLoading />);
    const spinner = container.querySelector(".animate-spin");
    expect(spinner).toBeInTheDocument();
  });
});
