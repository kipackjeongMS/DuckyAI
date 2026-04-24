import { describe, it, expect } from "vitest";
import type {
  DuckyAIApi,
  OrchestratorStatus,
  AgentInfo,
  NotificationData,
} from "../../types/duckyai";

/**
 * These tests validate the DuckyAIApi type contract at compile time.
 * If these compile, the interface agrees with what all consumers expect.
 */
describe("DuckyAIApi type contract", () => {
  it("has all required top-level keys", () => {
    // Compile-time check: if any key is missing, TypeScript errors
    const keys: (keyof DuckyAIApi)[] = [
      "orchestrator",
      "vault",
      "window",
      "chat",
      "terminal",
      "onNotification",
    ];
    expect(keys).toHaveLength(6);
  });

  it("orchestrator methods return correct types", () => {
    // Verify shapes exist (compile-time guard)
    type StatusReturn = ReturnType<DuckyAIApi["orchestrator"]["status"]>;
    type AgentsReturn = ReturnType<DuckyAIApi["orchestrator"]["listAgents"]>;
    type TriggerReturn = ReturnType<DuckyAIApi["orchestrator"]["triggerAgent"]>;
    type StartReturn = ReturnType<DuckyAIApi["orchestrator"]["start"]>;
    type StopReturn = ReturnType<DuckyAIApi["orchestrator"]["stop"]>;

    // Runtime: just assert the type names resolve
    const statusSatisfies: StatusReturn extends Promise<OrchestratorStatus>
      ? true
      : false = true;
    const agentsSatisfies: AgentsReturn extends Promise<AgentInfo[]>
      ? true
      : false = true;
    const triggerSatisfies: TriggerReturn extends Promise<void>
      ? true
      : false = true;
    const startSatisfies: StartReturn extends Promise<Record<string, unknown>>
      ? true
      : false = true;
    const stopSatisfies: StopReturn extends Promise<Record<string, unknown>>
      ? true
      : false = true;

    expect(statusSatisfies).toBe(true);
    expect(agentsSatisfies).toBe(true);
    expect(triggerSatisfies).toBe(true);
    expect(startSatisfies).toBe(true);
    expect(stopSatisfies).toBe(true);
  });

  it("vault.callTool accepts name and optional args", () => {
    type CallToolReturn = ReturnType<DuckyAIApi["vault"]["callTool"]>;
    const satisfies: CallToolReturn extends Promise<string> ? true : false =
      true;
    expect(satisfies).toBe(true);
  });

  it("NotificationData has correct type union", () => {
    const valid: NotificationData = {
      type: "success",
      title: "test",
      body: "optional",
    };
    expect(valid.type).toBe("success");

    // body is optional
    const noBody: NotificationData = { type: "error", title: "test" };
    expect(noBody.body).toBeUndefined();
  });

  it("OrchestratorStatus has running and optional fields", () => {
    const minimal: OrchestratorStatus = { running: false };
    expect(minimal.running).toBe(false);

    const full: OrchestratorStatus = {
      running: true,
      pid: 1234,
      agents_loaded: 5,
      status: "healthy",
    };
    expect(full.pid).toBe(1234);
  });

  it("onNotification returns an unsubscribe function", () => {
    type OnNotReturn = ReturnType<DuckyAIApi["onNotification"]>;
    const satisfies: OnNotReturn extends () => void ? true : false = true;
    expect(satisfies).toBe(true);
  });
});
