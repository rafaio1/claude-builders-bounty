import { describe, it, expect } from "vitest";
import {
  emailSchema,
  passwordSchema,
  requiredTextSchema,
  urlSchema,
  parseOrThrow,
} from "../schemas";

describe("validation schemas", () => {
  it("validates email correctly", () => {
    expect(emailSchema.parse("test@example.com")).toBe("test@example.com");
    expect(() => emailSchema.parse("")).toThrow("Email is required");
    expect(() => emailSchema.parse("invalid")).toThrow("Invalid email address");
  });

  it("validates password correctly", () => {
    expect(passwordSchema.parse("Password1")).toBe("Password1");
    expect(() => passwordSchema.parse("short1A")).toThrow(
      "Password must be at least 8 characters"
    );
    expect(() => passwordSchema.parse("nouppercase1")).toThrow(
      "Password must contain at least one uppercase letter"
    );
    expect(() => passwordSchema.parse("NoNumberHere")).toThrow(
      "Password must contain at least one number"
    );
  });

  it("validates required text correctly", () => {
    expect(requiredTextSchema.parse("hello")).toBe("hello");
    expect(() => requiredTextSchema.parse("")).toThrow(
      "This field is required"
    );
  });

  it("validates url correctly", () => {
    expect(urlSchema.parse("https://example.com")).toBe("https://example.com");
    expect(() => urlSchema.parse("")).toThrow("URL is required");
    expect(() => urlSchema.parse("not-a-url")).toThrow("Invalid URL");
  });

  it("parseOrThrow returns parsed value or throws", () => {
    expect(parseOrThrow(emailSchema, "a@b.com")).toBe("a@b.com");
    expect(() => parseOrThrow(emailSchema, "bad")).toThrow();
  });
});
