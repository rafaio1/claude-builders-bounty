import { describe, expect, it, vi, beforeEach, afterEach } from "vitest";
import request from "supertest";
import express from "express";
import { errorHandler } from "../src/common/http/error.middleware";
import { AppError } from "../src/common/http/app-error";

describe("Error Message Redaction", () => {
  let app: express.Express;
  const originalEnv = process.env.NODE_ENV;

  beforeEach(() => {
    app = express();
    app.get("/test-generic", () => {
      throw new Error("Sensitive internal stack trace details");
    });
    app.get("/test-app-error", () => {
      throw new AppError(500, "User-facing business error message");
    });
    app.use(errorHandler);
  });

  afterEach(() => {
    process.env.NODE_ENV = originalEnv;
    vi.restoreAllMocks();
  });

  it("should redact generic Error messages in production", async () => {
    process.env.NODE_ENV = "production";
    const res = await request(app).get("/test-generic");
    
    expect(res.status).toBe(500);
    expect(res.body.success).toBe(false);
    expect(res.body.message).toBe("Internal server error");
    expect(res.body.message).not.toContain("Sensitive");
  });

  it("should expose generic Error messages in non-production environments", async () => {
    process.env.NODE_ENV = "test";
    const res = await request(app).get("/test-generic");
    
    expect(res.status).toBe(500);
    expect(res.body.success).toBe(false);
    expect(res.body.message).toBe("Sensitive internal stack trace details");
  });

  it("should always pass through AppError messages even in production", async () => {
    process.env.NODE_ENV = "production";
    const res = await request(app).get("/test-app-error");
    
    expect(res.status).toBe(500);
    expect(res.body.success).toBe(false);
    expect(res.body.message).toBe("User-facing business error message");
  });
});
