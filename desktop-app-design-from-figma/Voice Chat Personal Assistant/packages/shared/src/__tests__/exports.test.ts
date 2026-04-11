import { describe, it, expect } from "vitest";
import * as shared from "../index";

describe("@duckyai/shared barrel export", () => {
  it("exports DuckyAIProvider", () => {
    expect(shared.DuckyAIProvider).toBeDefined();
    expect(typeof shared.DuckyAIProvider).toBe("function");
  });

  it("exports useDuckyAI", () => {
    expect(shared.useDuckyAI).toBeDefined();
    expect(typeof shared.useDuckyAI).toBe("function");
  });

  it("exports useOrchestrator", () => {
    expect(shared.useOrchestrator).toBeDefined();
    expect(typeof shared.useOrchestrator).toBe("function");
  });

  it("exports DuckyAIApp", () => {
    expect(shared.DuckyAIApp).toBeDefined();
  });

  it("exports UI components", () => {
    expect(shared.VoiceOrb).toBeDefined();
    expect(shared.StatusBar).toBeDefined();
    expect(shared.StatusIndicator).toBeDefined();
    expect(shared.QuickActions).toBeDefined();
    expect(shared.TypewriterOverlay).toBeDefined();
    expect(shared.Sidebar).toBeDefined();
    expect(shared.LoginScreen).toBeDefined();
    expect(shared.ToastContainer).toBeDefined();
    expect(shared.useToasts).toBeDefined();
  });
});
