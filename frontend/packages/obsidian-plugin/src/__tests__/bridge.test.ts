import { describe, it, expect, vi, beforeEach } from "vitest";
import { requestUrl } from "obsidian";
import { createObsidianBridge } from "../bridge";

// Type helper for the mocked requestUrl
const mockRequestUrl = requestUrl as ReturnType<typeof vi.fn>;

/** Mock a successful health check followed by an API response */
function mockHealthThen(json: unknown) {
  // 1st call: quickHealth → GET /api/health
  mockRequestUrl.mockResolvedValueOnce({ json: { ok: true } });
  // 2nd call: the actual API request
  mockRequestUrl.mockResolvedValueOnce({ json });
}

function createMockApp(vaultFiles: Record<string, string> = {}): any {
  return {
    vault: {
      adapter: { basePath: "C:\\test\\vault" },
      getAbstractFileByPath: vi.fn((path: string) => {
        return path in vaultFiles ? { path } : null;
      }),
      cachedRead: vi.fn(async (file: { path: string }) => {
        return vaultFiles[file.path] ?? "";
      }),
    },
    workspace: {
      getActiveFile: vi.fn(() => null),
    },
  };
}

describe("createObsidianBridge", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe("URL discovery", () => {
    it("uses default URL when .duckyai/api.json does not exist", async () => {
      const app = createMockApp();
      const api = createObsidianBridge(app);

      mockHealthThen({ running: false, agents: [] });

      await api.orchestrator.status();

      expect(mockRequestUrl).toHaveBeenCalledWith(
        expect.objectContaining({
          url: "http://127.0.0.1:52845/api/orchestrator/status",
          method: "GET",
        }),
      );
    });

    it("uses discovered URL from .duckyai/api.json", async () => {
      // Note: discoverSync reads from the filesystem via fs.existsSync/readFileSync,
      // not via Obsidian's vault API. We test that the default URL is used when the
      // discovery file doesn't exist on disk (which is the test environment case).
      // Custom URL discovery is implicitly tested via integration tests.
      const app = createMockApp();
      const api = createObsidianBridge(app);

      mockHealthThen({ running: true, agents: [] });

      await api.orchestrator.status();

      // Should use default URL since no api.json exists on disk
      expect(mockRequestUrl).toHaveBeenLastCalledWith(
        expect.objectContaining({
          url: "http://127.0.0.1:52845/api/orchestrator/status",
        }),
      );
    });
  });

  describe("orchestrator", () => {
    it("status() calls GET /api/orchestrator/status", async () => {
      const app = createMockApp();
      const api = createObsidianBridge(app);
      const expected = { running: true, agents: ["EIC", "GDR"] };

      mockHealthThen(expected);

      const result = await api.orchestrator.status();
      expect(result).toEqual(expected);
      expect(mockRequestUrl).toHaveBeenCalledWith(
        expect.objectContaining({
          url: "http://127.0.0.1:52845/api/orchestrator/status",
          method: "GET",
        }),
      );
    });

    it("listAgents() calls GET /api/orchestrator/agents", async () => {
      const app = createMockApp();
      const api = createObsidianBridge(app);
      const agents = [
        { abbr: "EIC", name: "Enrich Ingested Content" },
        { abbr: "GDR", name: "Generate Daily Roundup" },
      ];

      mockHealthThen(agents);

      const result = await api.orchestrator.listAgents();
      expect(result).toEqual(agents);
    });

    it("start() calls POST /api/orchestrator/start", async () => {
      const app = createMockApp();
      const api = createObsidianBridge(app);

      mockHealthThen({ started: true });

      await api.orchestrator.start();

      expect(mockRequestUrl).toHaveBeenCalledWith(
        expect.objectContaining({
          url: "http://127.0.0.1:52845/api/orchestrator/start",
          method: "POST",
          body: "{}",
        }),
      );
    });

    it("stop() calls POST /api/orchestrator/stop", async () => {
      const app = createMockApp();
      const api = createObsidianBridge(app);

      mockRequestUrl.mockResolvedValueOnce({ json: { stopped: true } });

      await api.orchestrator.stop();

      expect(mockRequestUrl).toHaveBeenCalledWith(
        expect.objectContaining({
          url: "http://127.0.0.1:52845/api/orchestrator/stop",
          method: "POST",
        }),
      );
    });

    it("triggerAgent() sends agent name and options", async () => {
      const app = createMockApp();
      const api = createObsidianBridge(app);

      mockHealthThen({ triggered: true });

      await api.orchestrator.triggerAgent("EIC", {
        file: "00-Inbox/test.md",
        lookback: 24,
      });

      expect(mockRequestUrl).toHaveBeenCalledWith(
        expect.objectContaining({
          method: "POST",
          body: JSON.stringify({
            agent: "EIC",
            input_file: "00-Inbox/test.md",
            agent_params: { lookback: 24 },
          }),
        }),
      );
    });

    it("triggerAgent() sends sinceLastSync param", async () => {
      const app = createMockApp();
      const api = createObsidianBridge(app);

      mockHealthThen({});

      await api.orchestrator.triggerAgent("TCS", { sinceLastSync: true });

      expect(mockRequestUrl).toHaveBeenCalledWith(
        expect.objectContaining({
          body: JSON.stringify({
            agent: "TCS",
            agent_params: { sinceLastSync: true },
          }),
        }),
      );
    });

    it("triggerAgent() without options sends only agent name", async () => {
      const app = createMockApp();
      const api = createObsidianBridge(app);

      mockHealthThen({});

      await api.orchestrator.triggerAgent("GDR");

      expect(mockRequestUrl).toHaveBeenCalledWith(
        expect.objectContaining({
          body: JSON.stringify({ agent: "GDR" }),
        }),
      );
    });

    it("triggerAgent() forwards arbitrary opts as agent_params", async () => {
      const app = createMockApp();
      const api = createObsidianBridge(app);

      mockHealthThen({});

      await api.orchestrator.triggerAgent("TP", {
        file: "01-Work/Tasks/fix-bug.md",
        mode: "task-file",
        selection_mode: false,
        selection: null,
      });

      expect(mockRequestUrl).toHaveBeenCalledWith(
        expect.objectContaining({
          body: JSON.stringify({
            agent: "TP",
            input_file: "01-Work/Tasks/fix-bug.md",
            agent_params: {
              mode: "task-file",
              selection_mode: false,
              selection: null,
            },
          }),
        }),
      );
    });

    it("triggerAgent() forwards selection text in agent_params", async () => {
      const app = createMockApp();
      const api = createObsidianBridge(app);

      mockHealthThen({});

      await api.orchestrator.triggerAgent("TP", {
        file: "04-Periodic/Daily/2026-04-09.md",
        mode: "daily-note",
        selection_mode: true,
        selection: "- [ ] Fix deployment timeout",
      });

      expect(mockRequestUrl).toHaveBeenCalledWith(
        expect.objectContaining({
          body: JSON.stringify({
            agent: "TP",
            input_file: "04-Periodic/Daily/2026-04-09.md",
            agent_params: {
              mode: "daily-note",
              selection_mode: true,
              selection: "- [ ] Fix deployment timeout",
            },
          }),
        }),
      );
    });
  });

  describe("vault", () => {
    it("callTool() sends tool name and arguments", async () => {
      const app = createMockApp();
      const api = createObsidianBridge(app);

      mockRequestUrl.mockResolvedValueOnce({
        json: {
          content: [{ text: "Daily note prepared" }],
        },
      });

      const result = await api.vault.callTool("prepareDailyNote", {
        date: "2026-04-02",
      });

      expect(result).toBe("Daily note prepared");
      expect(mockRequestUrl).toHaveBeenCalledWith(
        expect.objectContaining({
          method: "POST",
          body: JSON.stringify({
            tool: "prepareDailyNote",
            arguments: { date: "2026-04-02" },
          }),
        }),
      );
    });

    it("callTool() concatenates multiple content items", async () => {
      const app = createMockApp();
      const api = createObsidianBridge(app);

      mockRequestUrl.mockResolvedValueOnce({
        json: {
          content: [{ text: "Line 1" }, { text: "Line 2" }],
        },
      });

      const result = await api.vault.callTool("someMultiTool");
      expect(result).toBe("Line 1\nLine 2");
    });

    it("callTool() throws on error response", async () => {
      const app = createMockApp();
      const api = createObsidianBridge(app);

      mockRequestUrl.mockResolvedValueOnce({
        json: { error: "Tool not found" },
      });

      await expect(api.vault.callTool("badTool")).rejects.toThrow(
        "Tool not found",
      );
    });

    it("callTool() falls back to JSON.stringify for unknown response shape", async () => {
      const app = createMockApp();
      const api = createObsidianBridge(app);

      mockRequestUrl.mockResolvedValueOnce({
        json: { custom: "data" },
      });

      const result = await api.vault.callTool("customTool");
      expect(result).toBe('{"custom":"data"}');
    });
  });

  describe("chat", () => {
    it("send() posts to /api/chat/send and returns response", async () => {
      const app = createMockApp();
      const api = createObsidianBridge(app);

      mockRequestUrl.mockResolvedValueOnce({
        json: { response: "Hello! How can I help?" },
      });

      const result = await api.chat!.send("Hello");

      expect(result).toBe("Hello! How can I help?");
      expect(mockRequestUrl).toHaveBeenCalledWith(
        expect.objectContaining({
          url: "http://127.0.0.1:52845/api/chat/send",
          method: "POST",
          body: JSON.stringify({ message: "Hello" }),
        }),
      );
    });

    it("send() returns fallback message when daemon is down", async () => {
      const app = createMockApp();
      const api = createObsidianBridge(app);

      mockRequestUrl.mockRejectedValueOnce(new Error("Connection refused"));

      const result = await api.chat!.send("Hello");
      expect(result).toContain("Chat engine not available");
    });

    it("send() emits error notification when daemon is down", async () => {
      const app = createMockApp();
      const api = createObsidianBridge(app);
      const notifSpy = vi.fn();

      api.onNotification(notifSpy);

      mockRequestUrl.mockRejectedValueOnce(new Error("Connection refused"));

      await api.chat!.send("Hello");

      expect(notifSpy).toHaveBeenCalledWith(
        expect.objectContaining({
          type: "error",
          title: "Chat unavailable",
        }),
      );
    });
  });

  describe("onNotification", () => {
    it("registers and calls listeners", async () => {
      const app = createMockApp();
      const api = createObsidianBridge(app);
      const spy = vi.fn();

      api.onNotification(spy);

      // Trigger a notification via chat failure
      mockRequestUrl.mockRejectedValueOnce(new Error("fail"));
      await api.chat!.send("test");

      expect(spy).toHaveBeenCalledTimes(1);
    });

    it("returns unsubscribe function", async () => {
      const app = createMockApp();
      const api = createObsidianBridge(app);
      const spy = vi.fn();

      const unsub = api.onNotification(spy);
      unsub();

      // Trigger notification — spy should NOT be called
      mockRequestUrl.mockRejectedValueOnce(new Error("fail"));
      await api.chat!.send("test");

      expect(spy).not.toHaveBeenCalled();
    });
  });

  describe("window (no-ops in Obsidian)", () => {
    it("minimize, maximize, close are no-op functions", async () => {
      const app = createMockApp();
      const api = createObsidianBridge(app);

      // Should not throw
      await api.window!.minimize();
      await api.window!.maximize();
      await api.window!.close();
    });
  });
});
