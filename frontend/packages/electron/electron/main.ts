import { app, BrowserWindow, ipcMain } from "electron";
import path from "node:path";
import { fileURLToPath } from "node:url";
import fs from "node:fs";
import { DuckyAIClient } from "./bridge/duckyai-client.js";
import { resolveVaultPath } from "./bridge/config.js";
// ChatEngine is lazy-imported to avoid crashing if @github/copilot-sdk
// is incompatible with Electron's bundled Node.js version
type ChatEngineType = import("./bridge/chat-engine.js").ChatEngine;

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

let mainWindow: BrowserWindow | null = null;
let apiClient: DuckyAIClient | null = null;
let chatEngine: ChatEngineType | null = null;
let lastRecoveryAttemptAt = 0;
let userStoppedDaemon = false;

const isDev = process.env.ELECTRON_IS_DEV === "1";
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
  try {
    await api.health();
    return true;
  } catch {
    // Discovery may be stale after a restart.
  }

  api.refreshDiscovery();
  try {
    await api.health();
    return true;
  } catch {
    // Fall through to auto-start.
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
    api.refreshDiscovery();
    try {
      await api.health();
      return true;
    } catch {
      await sleep(DAEMON_RECOVERY_POLL_MS);
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
  // --- Orchestrator (HTTP API) ---
  ipcMain.handle("orch:status", () => getOrchestratorStatus(api, vaultPath));
  ipcMain.handle("orch:list-agents", () => listOrchestratorAgents(api, vaultPath));
  ipcMain.handle("orch:trigger", (_, abbr: string, opts?: Record<string, unknown>) =>
    triggerOrchestratorAgent(api, vaultPath, abbr, opts as TriggerOptions),
  );
  ipcMain.handle("orch:start", async () => {
    userStoppedDaemon = false;

    // Try starting the event loop on an already-running daemon
    try {
      await api.post("/api/orchestrator/start");
      return { status: "started" };
    } catch {
      // Daemon not running — spawn it
    }

    // Spawn daemon as a detached subprocess
    await spawnDaemon(vaultPath);

    // Wait for daemon to become reachable
    for (let attempt = 0; attempt < DAEMON_RECOVERY_ATTEMPTS; attempt += 1) {
      api.refreshDiscovery();
      try {
        await api.health();
        return { status: "started" };
      } catch {
        await sleep(DAEMON_RECOVERY_POLL_MS);
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

  // --- Chat (Copilot SDK) ---
  ipcMain.handle("chat:send", async (_, text: string) => {
    if (!chatEngine) return "Chat engine not initialized.";
    try {
      const response = await chatEngine.sendMessage(text);
      return response;
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

  // Lazy-import ChatEngine to avoid crash if Copilot SDK is incompatible
  try {
    const { ChatEngine } = await import("./bridge/chat-engine.js");
    chatEngine = new ChatEngine(apiClient, vaultPath, (msg) => {
      mainWindow?.webContents.send("duckyai:notification", msg);
    });
  } catch (err) {
    console.error("[main] ChatEngine import failed (Copilot SDK may need Node 22+):", err);
  }

  registerIpcHandlers(apiClient, vaultPath);
  createWindow();

  // Start chat engine in background (non-blocking)
  chatEngine?.start().catch((err) => {
    console.error("[main] Chat engine failed to start:", err);
  });
});

app.on("window-all-closed", () => {
  chatEngine?.stop();
  apiClient?.close();
  app.quit();
});
