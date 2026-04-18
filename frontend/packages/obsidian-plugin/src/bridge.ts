import { requestUrl } from "obsidian";
import type { App } from "obsidian";
import type { DuckyAIApi, NotificationData } from "@duckyai/shared";
import * as fs from "fs";
import * as path from "path";
import { spawn } from "child_process";

const DEFAULT_URL = "http://127.0.0.1:52845";
const CHAT_URL = "http://127.0.0.1:52846";
const CHAT_HEALTH_TIMEOUT_MS = 2_000;
const CHAT_STARTUP_POLL_MS = 500;
const CHAT_STARTUP_MAX_WAIT_MS = 15_000;
const DAEMON_RECOVERY_POLL_MS = 750;
const DAEMON_RECOVERY_ATTEMPTS = 8;

// ── Daemon spawner (mirrors Electron's spawnDaemon) ────────────

interface CliCandidate {
  command: string;
  baseArgs: string[];
  cwd: string;
}

function getCliCandidates(vaultPath: string): CliCandidate[] {
  const candidates: CliCandidate[] = [];
  const repoCliDir = path.join(vaultPath, "cli");
  const hasRepoCli =
    fs.existsSync(path.join(repoCliDir, "pyproject.toml")) &&
    fs.existsSync(path.join(repoCliDir, "duckyai_cli"));

  const addCandidates = (cwd: string) => {
    if (process.platform === "win32") {
      candidates.push({ command: "py", baseArgs: ["-m", "duckyai_cli"], cwd });
    }
    candidates.push({ command: "python", baseArgs: ["-m", "duckyai_cli"], cwd });
    candidates.push({ command: "python3", baseArgs: ["-m", "duckyai_cli"], cwd });
  };

  if (hasRepoCli) {
    addCandidates(repoCliDir);
  }
  addCandidates(vaultPath);
  return candidates;
}

async function spawnDaemon(vaultPath: string): Promise<void> {
  for (const candidate of getCliCandidates(vaultPath)) {
    try {
      const args = [...candidate.baseArgs, "orchestrator", "start"];
      const spawnOpts: Record<string, unknown> = {
        cwd: candidate.cwd,
        stdio: "ignore",
        detached: true,
      };

      if (process.platform === "win32") {
        const CREATE_NEW_PROCESS_GROUP = 0x00000200;
        const CREATE_NO_WINDOW = 0x08000000;
        spawnOpts.windowsHide = true;
        (spawnOpts as any).creationflags =
          CREATE_NEW_PROCESS_GROUP | CREATE_NO_WINDOW;
      }

      const child = spawn(candidate.command, args, spawnOpts as any);
      child.unref();
      console.log(
        `[duckyai] Spawned daemon: ${candidate.command} ${args.join(" ")}`,
      );
      return;
    } catch (err) {
      console.warn(
        `[duckyai] Failed to spawn with ${candidate.command}:`,
        err,
      );
    }
  }

  throw new Error("Could not spawn DuckyAI daemon — no working Python found");
}

/** Spawn the chat server as a detached background process. */
async function spawnChatServer(vaultPath: string): Promise<void> {
  for (const candidate of getCliCandidates(vaultPath)) {
    try {
      const args = [...candidate.baseArgs, "chat", "start"];
      const spawnOpts: Record<string, unknown> = {
        cwd: candidate.cwd,
        stdio: "ignore",
        detached: true,
      };

      if (process.platform === "win32") {
        const CREATE_NEW_PROCESS_GROUP = 0x00000200;
        const CREATE_NO_WINDOW = 0x08000000;
        spawnOpts.windowsHide = true;
        (spawnOpts as any).creationflags =
          CREATE_NEW_PROCESS_GROUP | CREATE_NO_WINDOW;
      }

      const child = spawn(candidate.command, args, spawnOpts as any);
      child.unref();
      console.log(
        `[duckyai] Spawned chat server: ${candidate.command} ${args.join(" ")}`,
      );
      return;
    } catch (err) {
      console.warn(
        `[duckyai] Failed to spawn chat server with ${candidate.command}:`,
        err,
      );
    }
  }
  throw new Error("Could not spawn chat server — no working Python found");
}

/** Check if the chat server is reachable. */
async function chatHealthCheck(): Promise<boolean> {
  try {
    const res = await requestUrl({
      url: `${CHAT_URL}/api/chat/health`,
      method: "GET",
      headers: { Accept: "application/json" },
    });
    return res.status === 200;
  } catch {
    return false;
  }
}

/** Ensure the chat server is running, spawning it on demand if needed. */
async function ensureChatServer(vaultPath: string): Promise<void> {
  if (await chatHealthCheck()) return;

  console.log("[duckyai] Chat server not running — starting on demand...");
  await spawnChatServer(vaultPath);

  // Poll until healthy
  const deadline = Date.now() + CHAT_STARTUP_MAX_WAIT_MS;
  while (Date.now() < deadline) {
    await sleep(CHAT_STARTUP_POLL_MS);
    if (await chatHealthCheck()) {
      console.log("[duckyai] Chat server is ready");
      return;
    }
  }
  throw new Error("Chat server failed to start within timeout");
}

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

// ── Bridge ─────────────────────────────────────────────────────

/**
 * Obsidian-native DuckyAI API adapter.
 *
 * HTTP-only: uses requestUrl() for all daemon communication.
 * Spawns daemon as a detached subprocess when needed (same as Electron).
 */
export function createObsidianBridge(obsidianApp: App): DuckyAIApi {
  let baseUrl = DEFAULT_URL;

  // Resolve the vault's filesystem path
  const vaultPath = (obsidianApp.vault.adapter as any).basePath as string;

  // Notification listeners
  const listeners = new Set<(data: NotificationData) => void>();

  // Try to discover API URL from .duckyai/api.json in the vault
  function discoverSync(): string {
    try {
      const discoveryPath = path.join(vaultPath, ".duckyai", "api.json");
      if (fs.existsSync(discoveryPath)) {
        const data = JSON.parse(fs.readFileSync(discoveryPath, "utf-8"));
        if (data.url) {
          baseUrl = data.url;
          return baseUrl;
        }
      }
    } catch {
      // Fall through to default
    }
    return DEFAULT_URL;
  }

  /** Quick health probe with a short timeout. */
  async function quickHealth(): Promise<boolean> {
    try {
      discoverSync();
      await requestUrl({
        url: `${baseUrl}/api/health`,
        method: "GET",
        headers: { Accept: "application/json" },
        throw: true,
      });
      return true;
    } catch {
      return false;
    }
  }

  /** Clear stale discovery file so discoverSync picks up a fresh daemon. */
  function clearDiscovery(): void {
    try {
      const discoveryPath = path.join(vaultPath, ".duckyai", "api.json");
      if (fs.existsSync(discoveryPath)) {
        fs.unlinkSync(discoveryPath);
      }
    } catch {
      // ignore
    }
    baseUrl = DEFAULT_URL;
  }

  /** Check if the daemon HTTP API is reachable. */
  async function isDaemonReachable(): Promise<boolean> {
    return quickHealth();
  }

  async function get<T>(endpoint: string): Promise<T> {
    discoverSync();
    const resp = await requestUrl({
      url: `${baseUrl}${endpoint}`,
      method: "GET",
      headers: { Accept: "application/json" },
    });
    return resp.json as T;
  }

  async function post<T>(
    endpoint: string,
    body: Record<string, unknown>,
  ): Promise<T> {
    discoverSync();
    const resp = await requestUrl({
      url: `${baseUrl}${endpoint}`,
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Accept: "application/json",
      },
      body: JSON.stringify(body),
    });
    return resp.json as T;
  }

  function emitNotification(data: NotificationData) {
    for (const cb of listeners) {
      try {
        cb(data);
      } catch {
        // ignore listener errors
      }
    }
  }

  const api: DuckyAIApi = {
    orchestrator: {
      status: async () => {
        if (await isDaemonReachable()) {
          return get("/api/orchestrator/status");
        }
        return { running: false, agents_loaded: 0 };
      },
      listAgents: async () => {
        if (!(await isDaemonReachable())) {
          return [];
        }
        return get("/api/orchestrator/agents");
      },
      triggerAgent: async (abbr: string, opts?: Record<string, unknown>) => {
        if (!(await isDaemonReachable())) {
          throw new Error("DuckyAI daemon is not running. Start it first.");
        }
        const body: Record<string, unknown> = { agent: abbr };
        if (opts) {
          const { file, ...rest } = opts;
          if (file) body.input_file = file;
          if (Object.keys(rest).length > 0) {
            body.agent_params = rest;
          }
        }
        await post("/api/orchestrator/trigger", body);
      },
      start: async () => {
        // Quick check if daemon is actually alive before trying to POST
        if (await quickHealth()) {
          try {
            await post("/api/orchestrator/start", {});
            return { status: "started" };
          } catch {
            // POST failed on seemingly-alive daemon; fall through
          }
        }

        // Daemon not reachable — clear stale discovery and spawn fresh
        clearDiscovery();
        await spawnDaemon(vaultPath);

        // Wait for daemon to become reachable
        for (let attempt = 0; attempt < DAEMON_RECOVERY_ATTEMPTS; attempt++) {
          await sleep(DAEMON_RECOVERY_POLL_MS);
          discoverSync();
          if (await quickHealth()) {
            return { status: "started" };
          }
        }

        throw new Error(
          "Failed to start daemon — it did not become reachable",
        );
      },
      stop: async () => {
        // Pause event loop — daemon stays alive for quick resume
        await post("/api/orchestrator/stop", {});
        return { status: "stopped" };
      },
      shutdown: async () => {
        // Kill the daemon process entirely
        try {
          await post("/api/orchestrator/shutdown", {});
          return { status: "shutdown" };
        } catch {
          // Daemon may already be dead — that's fine
          return { status: "shutdown" };
        }
      },
      restart: async () => {
        // Kill daemon, clear stale discovery, spawn fresh
        try {
          await post("/api/orchestrator/shutdown", {});
        } catch {
          // Daemon may already be dead
        }
        clearDiscovery();
        await spawnDaemon(vaultPath);

        // Wait for it to become healthy
        for (let attempt = 0; attempt < 15; attempt++) {
          await sleep(1000);
          discoverSync();
          if (await quickHealth()) {
            return { status: "restarted" };
          }
        }
        throw new Error("Daemon did not become healthy after restart");
      },
      history: async (opts?: { date?: string; agent?: string; status?: string }) => {
        const params = new URLSearchParams();
        if (opts?.date) params.set("date", opts.date);
        if (opts?.agent) params.set("agent", opts.agent);
        if (opts?.status) params.set("status", opts.status);
        const qs = params.toString();
        return get(`/api/orchestrator/history${qs ? `?${qs}` : ""}`);
      },
      executionLog: async (executionId: string, date?: string) => {
        const params = new URLSearchParams();
        if (date) params.set("date", date);
        const qs = params.toString();
        return get(`/api/orchestrator/log/${encodeURIComponent(executionId)}${qs ? `?${qs}` : ""}`);
      },
    },

    vault: {
      callTool: async (name: string, args: Record<string, unknown> = {}) => {
        const resp: any = await post("/api/vault/tool", {
          tool: name,
          arguments: args,
        });
        if (resp.content && Array.isArray(resp.content)) {
          return resp.content
            .map((c: { text?: string }) => c.text ?? "")
            .join("\n");
        }
        if (resp.error) {
          throw new Error(resp.error);
        }
        return JSON.stringify(resp);
      },
    },

    window: {
      // No window controls in Obsidian — the host app owns the window
      minimize: async () => {},
      maximize: async () => {},
      close: async () => {},
    },

    chat: {
      send: async (text: string) => {
        try {
          // Lazy-start: spawn chat server on first message if not running
          await ensureChatServer(vaultPath);

          const res = await requestUrl({
            url: `${CHAT_URL}/api/chat/send`,
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ message: text }),
          });
          const data = JSON.parse(res.text);
          return data.response ?? JSON.stringify(data);
        } catch (err: any) {
          const msg = err instanceof Error ? err.message : String(err);
          emitNotification({
            type: "error",
            title: "Chat unavailable",
            body: msg,
          });
          return `Chat error: ${msg}`;
        }
      },
    },

    onNotification: (callback: (data: NotificationData) => void) => {
      listeners.add(callback);
      return () => {
        listeners.delete(callback);
      };
    },
  };

  return api;
}
