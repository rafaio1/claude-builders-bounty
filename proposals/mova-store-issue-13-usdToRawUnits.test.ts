import { describe, it, expect } from "vitest";
import { usdToRawUnits } from "../lib/stellar/checkout";
import { WalletError } from "../lib/stellar/freighter";

describe("usdToRawUnits", () => {
  it("converts 12.34 USD to 123400000n raw units", () => {
    expect(usdToRawUnits(12.34)).toBe(123400000n);
  });

  it("converts 0.29 USD to 2900000n raw units", () => {
    expect(usdToRawUnits(0.29)).toBe(2900000n);
  });

  it("converts smallest positive unit 0.0000001 to 1n", () => {
    expect(usdToRawUnits(0.0000001)).toBe(1n);
  });

  it("converts whole dollar 1 to 10000000n", () => {
    expect(usdToRawUnits(1)).toBe(10000000n);
  });

  it("throws WalletError with code INVALID_AMOUNT for zero", () => {
    expect(() => usdToRawUnits(0)).toThrow(WalletError);
    try {
      usdToRawUnits(0);
    } catch (e) {
      expect(e).toBeInstanceOf(WalletError);
      expect((e as WalletError).code).toBe("INVALID_AMOUNT");
    }
  });

  it("throws WalletError with code INVALID_AMOUNT for negative value", () => {
    expect(() => usdToRawUnits(-5)).toThrow(WalletError);
    try {
      usdToRawUnits(-5);
    } catch (e) {
      expect(e).toBeInstanceOf(WalletError);
      expect((e as WalletError).code).toBe("INVALID_AMOUNT");
    }
  });

  it("throws WalletError with code INVALID_AMOUNT for NaN", () => {
    expect(() => usdToRawUnits(NaN)).toThrow(WalletError);
    try {
      usdToRawUnits(NaN);
    } catch (e) {
      expect(e).toBeInstanceOf(WalletError);
      expect((e as WalletError).code).toBe("INVALID_AMOUNT");
    }
  });

  it("throws WalletError with code INVALID_AMOUNT for Infinity", () => {
    expect(() => usdToRawUnits(Infinity)).toThrow(WalletError);
    try {
      usdToRawUnits(Infinity);
    } catch (e) {
      expect(e).toBeInstanceOf(WalletError);
      expect((e as WalletError).code).toBe("INVALID_AMOUNT");
    }
  });
});