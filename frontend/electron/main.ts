import { app, BrowserWindow, ipcMain } from "electron";
import path from "node:path";
import { fileURLToPath } from "node:url";
import fs from "node:fs";
import { DuckyAIClient } from "./bridge/duckyai-client.js";
import { resolveVaultPath } from "./bridge/config.js";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

let mainWindow: BrowserWindow | null = null;
let apiClient: DuckyAIClient | null = null;
let lastRecoveryAttemptAt = 0;
let userStoppedDaemon = false;

const isDev = process.env.ELECTRON_IS_DEV === "1";
const CHAT_URL = "http://127.0.0.1:52846";
const DAEMON_RECOVERY_COOLDOWN_MS = 15_000;
const DAEMON_RECOVERY_POLL_MS = 750;
const DAEMON_RECOVERY_ATTEMPTS = 8;

interface TriggerOptions {
  file?: string;
  lookback?: number;
  sinceLastSync?: boolean;
}

interface CliCandidate {
  command: string;
  baseArgs: string[];
  cwd: string;
}

function notify(
  msg: { type: "success" | "error" | "info"; title: string; body?: string },
): void {
  mainWindow?.webContents.send("duckyai:notification", msg);
}

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

async function chatHealthCheck(): Promise<boolean> {
  try {
    const resp = await fetch(`${CHAT_URL}/api/chat/health`, { signal: AbortSignal.timeout(2000) });
    return resp.ok;
  } catch {
    return false;
  }
}

async function ensureChatServer(vaultPath: string): Promise<void> {
  if (await chatHealthCheck()) return;
  console.log("[main] Chat server not running — starting on demand...");
  const { spawn } = await import("node:child_process");
  for (const candidate of getCliCandidates(vaultPath)) {
    try {
      const args = [...candidate.baseArgs, "chat", "start"];
      const spawnOpts: Record<string, unknown> = { cwd: candidate.cwd, stdio: "ignore", detached: true };
      if (process.platform === "win32") {
        spawnOpts.windowsHide = true;
        (spawnOpts as any).creationflags = 0x00000200 | 0x08000000;
      }
      const child = spawn(candidate.command, args, spawnOpts as any);
      child.unref();
      console.log(`[main] Spawned chat server: ${candidate.command} ${args.join(" ")}`);
      break;
    } catch { continue; }
  }
  const deadline = Date.now() + 15_000;
  while (Date.now() < deadline) {
    await sleep(500);
    if (await chatHealthCheck()) { console.log("[main] Chat server is ready"); return; }
  }
  throw new Error("Chat server failed to start within timeout");
}

async function spawnDaemon(vaultPath: string): Promise<void> {
  const { spawn } = await import("node:child_process");

  for (const candidate of getCliCandidates(vaultPath)) {
    try {
      const args = [...candidate.baseArgs, "-o"];
      const spawnOpts: Record<string, unknown> = {
        cwd: candidate.cwd,
        stdio: "ignore",
        detached: true,
      };

      if (process.platform === "win32") {
        const CREATE_NEW_PROCESS_GROUP = 0x00000200;
        const CREATE_NO_WINDOW = 0x08000000;
        spawnOpts.windowsHide = true;
        (spawnOpts as any).creationflags = CREATE_NEW_PROCESS_GROUP | CREATE_NO_WINDOW;
      }

      const child = spawn(candidate.command, args, spawnOpts as any);
      child.unref();
      console.log(`[main] Spawned daemon: ${candidate.command} ${args.join(" ")} (cwd: ${candidate.cwd})`);
      return;
    } catch (err) {
      console.warn(`[main] Failed to spawn daemon with ${candidate.command}:`, err);
    }
  }

  throw new Error("Could not spawn DuckyAI daemon — no working Python found");
}

function getCliCandidates(vaultPath: string): CliCandidate[] {
  const candidates: CliCandidate[] = [];
  const repoCliDir = path.join(vaultPath, "cli");
  const hasRepoCli = fs.existsSync(path.join(repoCliDir, "pyproject.toml"))
    && fs.existsSync(path.join(repoCliDir, "duckyai_cli"));

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

async function ensureDaemonReachable(api: DuckyAIClient, vaultPath: string): Promise<boolean> {
  // Quick probe — 3s timeout instead of 30s to avoid hanging on dead daemons
  if (await api.quickHealth()) {
    return true;
  }

  api.refreshDiscovery();
  if (await api.quickHealth()) {
    return true;
  }

  // Skip auto-recovery if user explicitly stopped the daemon
  if (userStoppedDaemon) {
    return false;
  }

  const now = Date.now();
  if (now - lastRecoveryAttemptAt < DAEMON_RECOVERY_COOLDOWN_MS) {
    return false;
  }
  lastRecoveryAttemptAt = now;

  // Clear stale discovery before spawning so new daemon's file is picked up
  api.clearDiscovery();

  try {
    await spawnDaemon(vaultPath);
    console.log("[main] Auto-started DuckyAI daemon");
    notify({
      type: "info",
      title: "DuckyAI Daemon Started",
      body: "Desktop reconnected to the local orchestrator daemon.",
    });
  } catch (err) {
    console.warn("[main] Failed to auto-start DuckyAI daemon:", err);
    return false;
  }

  for (let attempt = 0; attempt < DAEMON_RECOVERY_ATTEMPTS; attempt += 1) {
    await sleep(DAEMON_RECOVERY_POLL_MS);
    api.refreshDiscovery();
    if (await api.quickHealth()) {
      return true;
    }
  }

  return false;
}

async function getOrchestratorStatus(api: DuckyAIClient, vaultPath: string) {
  if (await ensureDaemonReachable(api, vaultPath)) {
    return api.status();
  }
  return { running: false, agents_loaded: 0 };
}

async function listOrchestratorAgents(api: DuckyAIClient, vaultPath: string): Promise<unknown[]> {
  if (!(await ensureDaemonReachable(api, vaultPath))) {
    return [];
  }
  return api.listAgents();
}

async function triggerOrchestratorAgent(
  api: DuckyAIClient,
  vaultPath: string,
  abbr: string,
  opts?: TriggerOptions,
) {
  if (!(await ensureDaemonReachable(api, vaultPath))) {
    throw new Error("DuckyAI daemon is not running. Start it first.");
  }
  return api.triggerAgent(abbr, opts);
}

function createWindow(): void {
  const preloadPath = path.join(__dirname, "..", "electron", "preload.cjs");
  const preloadExists = fs.existsSync(preloadPath);
  console.log(`[main] preload path: ${preloadPath}`);
  console.log(`[main] preload exists: ${preloadExists}`);

  const iconPath = path.join(__dirname, "..", "electron", "icon.png");

  mainWindow = new BrowserWindow({
    width: 1200,
    height: 800,
    minWidth: 400,
    minHeight: 600,
    frame: false,
    titleBarStyle: "hiddenInset",
    backgroundColor: "#0a0e1a",
    icon: iconPath,
    webPreferences: {
      preload: preloadPath,
      contextIsolation: true,
      nodeIntegration: false,
    },
  });

  if (isDev) {
    mainWindow.loadURL("http://localhost:5174");
  } else {
    mainWindow.loadFile(path.join(__dirname, "../dist/index.html"));
  }

  mainWindow.on("closed", () => {
    mainWindow = null;
  });
}

function registerIpcHandlers(api: DuckyAIClient, vaultPath: string): void {
  // --- Vault filesystem ---
  ipcMain.handle("vault:list-dir", async (_, relativePath: string) => {
    const dirPath = path.join(vaultPath, relativePath);
    // Prevent directory traversal outside vault
    const resolved = path.resolve(dirPath);
    if (!resolved.startsWith(path.resolve(vaultPath))) {
      throw new Error("Path outside vault");
    }
    const entries = await fs.promises.readdir(resolved, { withFileTypes: true });
    return entries
      .filter((e) => !e.name.startsWith("."))
      .sort((a, b) => {
        // Directories first, then alphabetical
        if (a.isDirectory() && !b.isDirectory()) return -1;
        if (!a.isDirectory() && b.isDirectory()) return 1;
        return a.name.localeCompare(b.name);
      })
      .map((e) => ({
        name: e.name,
        type: e.isDirectory() ? "directory" : "file",
        relativePath: path.join(relativePath, e.name).replace(/\\/g, "/"),
      }));
  });

  ipcMain.handle("vault:read-file", async (_, relativePath: string) => {
    const filePath = path.join(vaultPath, relativePath);
    const resolved = path.resolve(filePath);
    if (!resolved.startsWith(path.resolve(vaultPath))) {
      throw new Error("Path outside vault");
    }
    return fs.promises.readFile(resolved, "utf-8");
  });

  // --- Orchestrator (HTTP API) ---
  ipcMain.handle("orch:status", () => getOrchestratorStatus(api, vaultPath));
  ipcMain.handle("orch:list-agents", () => listOrchestratorAgents(api, vaultPath));
  ipcMain.handle("orch:trigger", (_, abbr: string, opts?: Record<string, unknown>) =>
    triggerOrchestratorAgent(api, vaultPath, abbr, opts as TriggerOptions),
  );
  ipcMain.handle("orch:history", (_, opts?: { date?: string; agent?: string; status?: string }) =>
    api.history(opts),
  );
  ipcMain.handle("orch:log", (_, executionId: string, date?: string) =>
    api.executionLog(executionId, date),
  );
  ipcMain.handle("orch:start", async () => {
    userStoppedDaemon = false;

    // Quick health check to see if the daemon is alive before trying to resume
    const alive = await api.quickHealth();
    if (alive) {
      // Daemon is running — just resume the event loop
      try {
        await api.post("/api/orchestrator/start", {}, 10_000);
        return { status: "started" };
      } catch (err) {
        console.warn("[main] POST /api/orchestrator/start failed on alive daemon:", err);
      }
    }

    // Daemon not reachable — clear stale discovery and spawn fresh
    api.clearDiscovery();
    await spawnDaemon(vaultPath);

    // Wait for daemon to become reachable
    for (let attempt = 0; attempt < DAEMON_RECOVERY_ATTEMPTS; attempt += 1) {
      await sleep(DAEMON_RECOVERY_POLL_MS);
      api.refreshDiscovery();
      try {
        await api.health();
        return { status: "started" };
      } catch {
        // Retry
      }
    }

    throw new Error("Failed to start daemon — it did not become reachable");
  });
  ipcMain.handle("orch:stop", async () => {
    userStoppedDaemon = true;
    try {
      // Pause event loop — daemon stays alive for quick resume
      await api.post("/api/orchestrator/stop");
      return { status: "stopped" };
    } catch (err) {
      userStoppedDaemon = false;
      throw err;
    }
  });
  ipcMain.handle("orch:shutdown", async () => {
    userStoppedDaemon = true;
    try {
      // Kill daemon process entirely
      await api.post("/api/orchestrator/shutdown");
      api.refreshDiscovery();
      return { status: "shutdown" };
    } catch {
      api.refreshDiscovery();
      return { status: "shutdown" };
    }
  });

  // --- Vault tools (via HTTP API) ---
  ipcMain.handle("vault:call-tool", (_, name: string, args: Record<string, unknown>) =>
    api.callTool(name, args),
  );

  // --- Chat (via dedicated chat runtime server) ---
  ipcMain.handle("chat:send", async (_, text: string) => {
    try {
      await ensureChatServer(vaultPath);
      const resp = await fetch(`${CHAT_URL}/api/chat/send`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: text }),
      });
      if (!resp.ok) {
        const err = await resp.json().catch(() => ({ error: `HTTP ${resp.status}` }));
        return `Error: ${(err as any).error ?? resp.statusText}`;
      }
      const data = await resp.json() as { response?: string };
      return data.response ?? "No response.";
    } catch (err) {
      const msg = err instanceof Error ? err.message : String(err);
      console.error("[chat] error:", msg);
      return `Error: ${msg}`;
    }
  });

  // --- Window controls ---
  ipcMain.handle("win:minimize", () => mainWindow?.minimize());
  ipcMain.handle("win:maximize", () => {
    if (mainWindow?.isMaximized()) {
      mainWindow.unmaximize();
    } else {
      mainWindow?.maximize();
    }
  });
  ipcMain.handle("win:close", () => mainWindow?.close());
}

app.whenReady().then(async () => {
  const vaultPath = resolveVaultPath();
  console.log(`[main] vault path: ${vaultPath}`);
  apiClient = new DuckyAIClient(vaultPath);

  // Verify the daemon is running, or recover it when possible.
  try {
    const reachable = await ensureDaemonReachable(apiClient, vaultPath);
    if (!reachable) {
      throw new Error("daemon unavailable");
    }
    const h = await apiClient.health();
    console.log(`[main] DuckyAI daemon healthy (pid ${h.pid})`);
  } catch (err) {
    console.warn("[main] DuckyAI daemon not reachable after recovery attempt:", err);
  }

  registerIpcHandlers(apiClient, vaultPath);
  createWindow();
});

app.on("window-all-closed", () => {
  apiClient?.close();
  app.quit();
});
