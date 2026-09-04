# Bounty #92: Unit Tests for sendMail and validateEmailConfig

## Deliverable

File: `tests/lib/sendmail.test.ts`

```ts
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";

// Mock @emailjs/browser before importing the module under test
vi.mock("@emailjs/browser", () => ({
  default: {
    send: vi.fn(),
  },
}));

import emailjs from "@emailjs/browser";
import sendMail from "@/lib/sendmail";

const mockedSend = vi.mocked(emailjs.send);

describe("sendmail", () => {
  const originalEnv = { ...process.env };

  beforeEach(() => {
    vi.resetModules();
    vi.clearAllMocks();

    // Set valid defaults for every test
    process.env.NEXT_PUBLIC_EMAILJS_SERVICE_ID = "test_service_id";
    process.env.NEXT_PUBLIC_EMAILJS_TEMPLATE_ID = "test_template_id";
    process.env.NEXT_PUBLIC_EMAILJS_PUBLIC_KEY = "test_public_key";
    process.env.NEXT_PUBLIC_DEFAULT_RECIPIENT_EMAIL = "default@test.com";
  });

  afterEach(() => {
    process.env = { ...originalEnv };
  });

  describe("validateEmailConfig", () => {
    it("throws an error naming all missing NEXT_PUBLIC_EMAILJS_* variables when unset", async () => {
      delete process.env.NEXT_PUBLIC_EMAILJS_SERVICE_ID;
      delete process.env.NEXT_PUBLIC_EMAILJS_TEMPLATE_ID;
      delete process.env.NEXT_PUBLIC_EMAILJS_PUBLIC_KEY;

      // Re-import to pick up cleared env vars (module reads env at top level)
      vi.resetModules();
      const freshSendMail = (await import("@/lib/sendmail")).default;

      await expect(
        freshSendMail({ name: "A", email: "a@b.com", message: "hi", subject: "s" })
      ).rejects.toThrow(/NEXT_PUBLIC_EMAILJS_SERVICE_ID/);

      await expect(
        freshSendMail({ name: "A", email: "a@b.com", message: "hi", subject: "s" })
      ).rejects.toThrow(/NEXT_PUBLIC_EMAILJS_TEMPLATE_ID/);

      await expect(
        freshSendMail({ name: "A", email: "a@b.com", message: "hi", subject: "s" })
      ).rejects.toThrow(/NEXT_PUBLIC_EMAILJS_PUBLIC_KEY/);
    });
  });

  describe("sendMail", () => {
    it("calls emailjs.send with serviceId, templateId, templateParams, and publicKey", async () => {
      mockedSend.mockResolvedValue({ status: 200, text: "OK" } as never);

      await sendMail({
        name: "Jane",
        email: "jane@example.com",
        message: "Hello",
        subject: "Test Subject",
      });

      expect(mockedSend).toHaveBeenCalledWith(
        "test_service_id",
        "test_template_id",
        expect.objectContaining({
          name: "Jane",
          email: "jane@example.com",
          message: "Hello",
          subject: "Test Subject",
        }),
        "test_public_key"
      );
    });

    it("defaults recipient_email to NEXT_PUBLIC_DEFAULT_RECIPIENT_EMAIL when not provided", async () => {
      mockedSend.mockResolvedValue({ status: 200, text: "OK" } as never);

      await sendMail({
        name: "Jane",
        email: "jane@example.com",
        message: "Hello",
        subject: "Test",
      });

      expect(mockedSend).toHaveBeenCalledWith(
        expect.any(String),
        expect.any(String),
        expect.objectContaining({ recipient_email: "default@test.com" }),
        expect.any(String)
      );
    });

    it("resolves successfully with the emailjs response", async () => {
      mockedSend.mockResolvedValue({ status: 200, text: "OK" } as never);

      const result = await sendMail({
        name: "Jane",
        email: "jane@example.com",
        message: "Hello",
        subject: "Test",
      });

      expect(result).toEqual({ status: 200, text: "OK" });
    });

    it("rejects and rethrows errors when emailjs.send fails", async () => {
      const sendError = new Error("Network failure");
      mockedSend.mockRejectedValue(sendError);

      await expect(
        sendMail({
          name: "Jane",
          email: "jane@example.com",
          message: "Hello",
          subject: "Test",
        })
      ).rejects.toThrow("Network failure");
    });
  });
});
```

## Notes

- The source module (`lib/sendmail.js`) reads environment variables at **module scope**, so tests that validate missing-config behaviour must use `vi.resetModules()` + dynamic `import()` to force re-evaluation after deleting env vars.
- All other tests set valid env vars in `beforeEach` and import once at the top of the file; this keeps the happy-path tests fast and avoids repeated re-imports.
- The mock for `@emailjs/browser` uses `vi.mock` with a factory so the default export's `send` method is replaced before the module under test is loaded.
- Test file path matches the issue requirement: `tests/lib/sendmail.test.ts`.