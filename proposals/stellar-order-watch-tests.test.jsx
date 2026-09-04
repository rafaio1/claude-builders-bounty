import { render, screen, waitFor } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";

// ---------------------------------------------------------------------------
// Mocks — drive the component entirely through callbacks; no Stellar RPC.
// ---------------------------------------------------------------------------

const mockStart = vi.fn();
const mockStop = vi.fn();

vi.mock("../lib/stellar/indexer", () => ({
  PaymentEventIndexer: vi.fn().mockImplementation(() => ({
    start: mockStart,
    stop: mockStop,
  })),
}));

// crypto.subtle.digest is already mocked in tests/setup.ts to return a
// deterministic 32-byte buffer derived from the input string, so
// hashOrderId("order-1") always produces the same bytes and therefore the
// same hex topic we can assert against.

import StellarOrderWatch from "../components/StellarOrderWatch";

/**
 * Compute the expected topic4 hex for a given orderId using the same
 * deterministic digest the setup file provides.
 */
async function expectedTopic(orderId) {
  const data = new TextEncoder().encode(orderId);
  const buf = await crypto.subtle.digest("SHA-256", data);
  return Array.from(new Uint8Array(buf))
    .map((b) => b.toString(16).padStart(2, "0"))
    .join("");
}

describe("StellarOrderWatch", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  // -------------------------------------------------------------------------
  // Render states
  // -------------------------------------------------------------------------

  it("renders the starting state before the indexer reports running", () => {
    render(<StellarOrderWatch orderId="order-1" />);

    expect(screen.getByText(/starting/i)).toBeInTheDocument();
    expect(mockStart).toHaveBeenCalledTimes(1);
  });

  it("renders the listening state once onStatus reports running", async () => {
    render(<StellarOrderWatch orderId="order-1" />);

    // Simulate the indexer reporting a successful connection.
    const callbacks = mockStart.mock.calls[0][0];
    callbacks.onStatus({ running: true, eventsSeen: 0 });

    await waitFor(() => {
      expect(screen.getByText(/listening for on-chain events/i)).toBeInTheDocument();
    });
  });

  it("does not start the indexer when enabled is false", () => {
    render(<StellarOrderWatch orderId="order-1" enabled={false} />);

    expect(mockStart).not.toHaveBeenCalled();
    expect(screen.getByText(/starting/i)).toBeInTheDocument();
  });

  it("stops the indexer on unmount", () => {
    const { unmount } = render(<StellarOrderWatch orderId="order-1" />);
    unmount();

    expect(mockStop).toHaveBeenCalled();
  });

  // -------------------------------------------------------------------------
  // Matching logic
  // -------------------------------------------------------------------------

  it("ignores events whose symbol is not 'pay'", async () => {
    render(<StellarOrderWatch orderId="order-1" />);

    const callbacks = mockStart.mock.calls[0][0];
    callbacks.onEvent({
      symbol: "create_order",
      fields: { topic4: await expectedTopic("order-1") },
      ledger: 100,
      txHash: "tx1",
    });

    // Still in listening state — no match rendered.
    expect(screen.queryByText(/payment detected/i)).not.toBeInTheDocument();
    expect(mockStop).not.toHaveBeenCalled();
  });

  it("ignores pay events with a non-matching topic4", async () => {
    render(<StellarOrderWatch orderId="order-1" />);

    const callbacks = mockStart.mock.calls[0][0];
    callbacks.onEvent({
      symbol: "pay",
      fields: { topic4: "deadbeef".repeat(8) },
      ledger: 101,
      txHash: "tx2",
    });

    expect(screen.queryByText(/payment detected/i)).not.toBeInTheDocument();
    expect(mockStop).not.toHaveBeenCalled();
  });

  // -------------------------------------------------------------------------
  // Stop-on-match
  // -------------------------------------------------------------------------

  it("calls onEvent, stops the indexer and renders matched ledger/amount on correct topic4", async () => {
    const onEvent = vi.fn();
    render(<StellarOrderWatch orderId="order-1" onEvent={onEvent} />);

    const topic = await expectedTopic("order-1");
    const event = {
      symbol: "pay",
      fields: { topic4: topic, amount: "2500000", topic1: "USDC" },
      ledger: 42,
      txHash: "abc123def456",
    };

    const callbacks = mockStart.mock.calls[0][0];
    callbacks.onEvent(event);

    await waitFor(() => {
      expect(screen.getByText(/payment detected on-chain/i)).toBeInTheDocument();
    });

    // Matched details are visible.
    expect(screen.getByText("42")).toBeInTheDocument();
    expect(screen.getByText("2500000")).toBeInTheDocument();

    // Consumer callback fired exactly once.
    expect(onEvent).toHaveBeenCalledTimes(1);
    expect(onEvent).toHaveBeenCalledWith(event);

    // Indexer was stopped after the first match.
    expect(mockStop).toHaveBeenCalled();
  });

  it("matches case-insensitively on topic4 hex", async () => {
    render(<StellarOrderWatch orderId="order-1" />);

    const topic = (await expectedTopic("order-1")).toUpperCase();
    const callbacks = mockStart.mock.calls[0][0];
    callbacks.onEvent({
      symbol: "pay",
      fields: { topic4: topic, amount: "100" },
      ledger: 7,
      txHash: "tx-upper",
    });

    await waitFor(() => {
      expect(screen.getByText(/payment detected on-chain/i)).toBeInTheDocument();
    });
    expect(mockStop).toHaveBeenCalled();
  });
});