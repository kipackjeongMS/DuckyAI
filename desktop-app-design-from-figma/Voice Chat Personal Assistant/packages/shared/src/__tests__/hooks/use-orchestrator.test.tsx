import { describe, it, expect, vi, afterEach } from "vitest";
import { renderHook, act, waitFor } from "@testing-library/react";
import React from "react";
import { DuckyAIProvider } from "../../context/duckyai-provider";
import { useOrchestrator } from "../../hooks/use-orchestrator";
import { createMockApi } from "../mock-api";
import type { DuckyAIApi } from "../../types/duckyai";

function wrapper(api: DuckyAIApi) {
  return function Wrapper({ children }: { children: React.ReactNode }) {
    return <DuckyAIProvider api={api}>{children}</DuckyAIProvider>;
  };
}

describe("useOrchestrator", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("returns initial state with running=false and empty agents", () => {
    const api = createMockApi();
    const { result } = renderHook(() => useOrchestrator(), {
      wrapper: wrapper(api),
    });

    expect(result.current.running).toBe(false);
    expect(result.current.agents).toEqual([]);
    expect(result.current.triggeringId).toBeNull();
  });

  it("fetches status on mount", async () => {
    const api = createMockApi({
      orchestrator: {
        status: vi.fn().mockResolvedValue({ running: true, agents_loaded: 2 }),
        listAgents: vi.fn().mockResolvedValue([
          {
            abbreviation: "EIC",
            name: "Enrich Content",
            category: "ingest",
            cron: null,
            enabled: true,
          },
        ]),
      },
    });

    const { result } = renderHook(() => useOrchestrator(), {
      wrapper: wrapper(api),
    });

    await waitFor(() => {
      expect(result.current.running).toBe(true);
    });

    expect(result.current.agents).toHaveLength(1);
    expect(result.current.agents[0]).toEqual({
      id: "EIC",
      name: "Enrich Content",
      category: "ingest",
      cron: null,
      status: "idle",
    });
  });

  it("maps running agents to 'running' status", async () => {
    const api = createMockApi({
      orchestrator: {
        status: vi.fn().mockResolvedValue({ running: true }),
        listAgents: vi.fn().mockResolvedValue([
          {
            abbreviation: "GDR",
            name: "Generate Daily Roundup",
            category: "periodic",
            cron: "0 18 * * 1-5",
            enabled: true,
            running: 1,
          },
        ]),
      },
    });

    const { result } = renderHook(() => useOrchestrator(), {
      wrapper: wrapper(api),
    });

    await waitFor(() => {
      expect(result.current.agents).toHaveLength(1);
    });

    expect(result.current.agents[0].status).toBe("running");
  });

  it("toggleOrchestrator starts when stopped", async () => {
    const startMock = vi.fn().mockResolvedValue({ status: "started" });
    const statusMock = vi
      .fn()
      .mockResolvedValueOnce({ running: false })    // initial mount
      .mockResolvedValueOnce({ running: true });     // after start refresh

    const api = createMockApi({
      orchestrator: {
        start: startMock,
        status: statusMock,
        listAgents: vi.fn().mockResolvedValue([]),
      },
    });

    const { result } = renderHook(() => useOrchestrator(), {
      wrapper: wrapper(api),
    });

    // Wait for initial mount refresh
    await waitFor(() => {
      expect(statusMock).toHaveBeenCalledTimes(1);
    });

    // Toggle ON — the hook has a 2s setTimeout inside, so we need to mock it out
    vi.useFakeTimers({ shouldAdvanceTime: true });
    await act(async () => {
      result.current.toggleOrchestrator();
      // Advance past the 2-second internal setTimeout
      await vi.advanceTimersByTimeAsync(2500);
    });
    vi.useRealTimers();

    expect(startMock).toHaveBeenCalledTimes(1);
  });

  it("toggleOrchestrator stops when running", async () => {
    const stopMock = vi.fn().mockResolvedValue({ status: "stopped" });
    const api = createMockApi({
      orchestrator: {
        status: vi.fn().mockResolvedValue({ running: true }),
        listAgents: vi.fn().mockResolvedValue([]),
        stop: stopMock,
      },
    });

    const { result } = renderHook(() => useOrchestrator(), {
      wrapper: wrapper(api),
    });

    await waitFor(() => {
      expect(result.current.running).toBe(true);
    });

    await act(async () => {
      await result.current.toggleOrchestrator();
    });

    expect(stopMock).toHaveBeenCalledTimes(1);
    expect(result.current.running).toBe(false);
  });

  it("triggerAgent calls api and sets triggeringId", async () => {
    const triggerMock = vi.fn().mockResolvedValue(undefined);
    const api = createMockApi({
      orchestrator: {
        triggerAgent: triggerMock,
      },
    });

    const { result } = renderHook(() => useOrchestrator(), {
      wrapper: wrapper(api),
    });

    await act(async () => {
      await result.current.triggerAgent("EIC");
    });

    expect(triggerMock).toHaveBeenCalledWith("EIC");
    expect(result.current.triggeringId).toBeNull();
  });

  it("polls status at regular intervals", async () => {
    const statusMock = vi.fn().mockResolvedValue({ running: false });
    const api = createMockApi({
      orchestrator: {
        status: statusMock,
      },
    });

    vi.useFakeTimers({ shouldAdvanceTime: true });

    renderHook(() => useOrchestrator(), {
      wrapper: wrapper(api),
    });

    // Initial call
    await vi.advanceTimersByTimeAsync(100);
    expect(statusMock).toHaveBeenCalledTimes(1);

    // After 5 seconds — second call
    await vi.advanceTimersByTimeAsync(5000);
    expect(statusMock).toHaveBeenCalledTimes(2);

    // After another 5 seconds — third call
    await vi.advanceTimersByTimeAsync(5000);
    expect(statusMock).toHaveBeenCalledTimes(3);

    vi.useRealTimers();
  });

  it("clears agents when orchestrator is not running", async () => {
    const api = createMockApi({
      orchestrator: {
        status: vi.fn().mockResolvedValue({ running: false }),
      },
    });

    const { result } = renderHook(() => useOrchestrator(), {
      wrapper: wrapper(api),
    });

    await waitFor(() => {
      expect(api.orchestrator.status).toHaveBeenCalled();
    });

    expect(result.current.agents).toEqual([]);
    expect(api.orchestrator.listAgents).not.toHaveBeenCalled();
  });
});
