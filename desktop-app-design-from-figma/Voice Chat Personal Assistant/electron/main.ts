import { app, BrowserWindow, ipcMain } from "electron";
import path from "node:path";
import { fileURLToPath } from "node:url";
import fs from "node:fs";
import { OrchestratorBridge } from "./bridge/orchestrator.js";
import { McpClient } from "./bridge/mcp-client.js";
import { resolveVaultPath } from "./bridge/config.js";
import { ensureAzLogin } from "./bridge/auth.js";
// ChatEngine is lazy-imported to avoid crashing if @github/copilot-sdk
// is incompatible with Electron's bundled Node.js version
type ChatEngineType = import("./bridge/chat-engine.js").ChatEngine;

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

let mainWindow: BrowserWindow | null = null;
let orchestrator: OrchestratorBridge | null = null;
let mcpClient: McpClient | null = null;
let chatEngine: ChatEngineType | null = null;

const isDev = process.env.ELECTRON_IS_DEV === "1";

function createWindow(): void {
  const preloadPath = path.join(__dirname, "..", "electron", "preload.cjs");
  const preloadExists = fs.existsSync(preloadPath);
  console.log(`[main] preload path: ${preloadPath}`);
  console.log(`[main] preload exists: ${preloadExists}`);

  mainWindow = new BrowserWindow({
    width: 1200,
    height: 800,
    minWidth: 400,
    minHeight: 600,
    frame: false,
    titleBarStyle: "hiddenInset",
    backgroundColor: "#0a0e1a",
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

function registerIpcHandlers(
  orch: OrchestratorBridge,
  mcp: McpClient,
): void {
  // --- Orchestrator ---
  ipcMain.handle("orch:start", () => orch.start());
  ipcMain.handle("orch:stop", () => orch.stop());
  ipcMain.handle("orch:status", () => orch.status());
  ipcMain.handle("orch:list-agents", () => orch.listAgents());
  ipcMain.handle("orch:trigger", (_, abbr: string, opts?: Record<string, unknown>) =>
    orch.triggerAgent(abbr, opts),
  );

  // --- Vault (MCP tools) ---
  ipcMain.handle("vault:call-tool", (_, name: string, args: Record<string, unknown>) =>
    mcp.callTool(name, args),
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
  try {
    await ensureAzLogin();
  } catch (err) {
    console.error("Azure CLI login failed:", err);
    app.quit();
    return;
  }

  const vaultPath = resolveVaultPath();
  console.log(`[main] vault path: ${vaultPath}`);
  orchestrator = new OrchestratorBridge(vaultPath);
  mcpClient = new McpClient(vaultPath);

  // Lazy-import ChatEngine to avoid crash if Copilot SDK is incompatible
  try {
    const { ChatEngine } = await import("./bridge/chat-engine.js");
    chatEngine = new ChatEngine(mcpClient, orchestrator, vaultPath);
  } catch (err) {
    console.error("[main] ChatEngine import failed (Copilot SDK may need Node 22+):", err);
  }

  registerIpcHandlers(orchestrator, mcpClient);
  createWindow();

  // Start chat engine in background (non-blocking)
  chatEngine?.start().catch((err) => {
    console.error("[main] Chat engine failed to start:", err);
  });
});

app.on("window-all-closed", () => {
  chatEngine?.stop();
  mcpClient?.close();
  app.quit();
});
