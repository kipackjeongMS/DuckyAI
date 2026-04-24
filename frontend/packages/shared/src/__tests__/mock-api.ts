import type { DuckyAIApi } from "../types/duckyai";

/**
 * Creates a mock DuckyAIApi with all methods stubbed via vi.fn().
 * Can be overridden per-test by passing partial implementations.
 */
export function createMockApi(
  overrides?: Partial<{
    orchestrator: Partial<DuckyAIApi["orchestrator"]>;
    vault: Partial<DuckyAIApi["vault"]>;
    window: Partial<DuckyAIApi["window"]>;
    chat: Partial<DuckyAIApi["chat"]>;
    onNotification: DuckyAIApi["onNotification"];
  }>
): DuckyAIApi {
  return {
    orchestrator: {
      status: vi.fn().mockResolvedValue({ running: false }),
      listAgents: vi.fn().mockResolvedValue([]),
      triggerAgent: vi.fn().mockResolvedValue(undefined),
      start: vi.fn().mockResolvedValue({ status: "started" }),
      stop: vi.fn().mockResolvedValue({ status: "stopped" }),
      ...overrides?.orchestrator,
    },
    vault: {
      callTool: vi.fn().mockResolvedValue("{}"),
      ...overrides?.vault,
    },
    window: {
      minimize: vi.fn().mockResolvedValue(undefined),
      maximize: vi.fn().mockResolvedValue(undefined),
      close: vi.fn().mockResolvedValue(undefined),
      ...overrides?.window,
    },
    chat: {
      send: vi.fn().mockResolvedValue("mock response"),
      ...overrides?.chat,
    },
    terminal: {
      wsUrl: "ws://127.0.0.1:52847/ws/terminal",
    },
    onNotification: overrides?.onNotification ?? vi.fn().mockReturnValue(() => {}),
  };
}
