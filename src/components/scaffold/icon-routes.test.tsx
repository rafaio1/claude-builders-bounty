import { describe, it, expect } from "vitest";
import Icon from "@/app/icon";
import AppleIcon from "@/app/apple-icon";

describe("app icon routes", () => {
  it("exports correct metadata for favicon", () => {
    expect(Icon.size).toEqual({ width: 32, height: 32 });
    expect(Icon.contentType).toBe("image/png");
    expect(Icon.runtime).toBe("edge");
  });

  it("exports correct metadata for apple touch icon", () => {
    expect(AppleIcon.size).toEqual({ width: 180, height: 180 });
    expect(AppleIcon.contentType).toBe("image/png");
    expect(AppleIcon.runtime).toBe("edge");
  });
});
