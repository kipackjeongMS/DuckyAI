import { contextBridge, ipcRenderer } from "electron";

contextBridge.exposeInMainWorld("duckyai", {
  orchestrator: {
    status: () => ipcRenderer.invoke("orch:status"),
    listAgents: () => ipcRenderer.invoke("orch:list-agents"),
    triggerAgent: (abbr: string, opts?: Record<string, unknown>) =>
      ipcRenderer.invoke("orch:trigger", abbr, opts),
    start: () => ipcRenderer.invoke("orch:start"),
    stop: () => ipcRenderer.invoke("orch:stop"),
    shutdown: () => ipcRenderer.invoke("orch:shutdown"),
    restart: () => ipcRenderer.invoke("orch:restart"),
    history: (opts?: { date?: string; agent?: string; status?: string }) =>
      ipcRenderer.invoke("orch:history", opts),
    executionLog: (executionId: string, date?: string) =>
      ipcRenderer.invoke("orch:log", executionId, date),
  },
  vault: {
    callTool: (name: string, args: Record<string, unknown> = {}) =>
      ipcRenderer.invoke("vault:call-tool", name, args),
    listDir: (relativePath: string) =>
      ipcRenderer.invoke("vault:list-dir", relativePath),
    readFile: (relativePath: string) =>
      ipcRenderer.invoke("vault:read-file", relativePath),
    writeFile: (relativePath: string, content: string) =>
      ipcRenderer.invoke("vault:write-file", relativePath, content),
  },
  window: {
    minimize: () => ipcRenderer.invoke("win:minimize"),
    maximize: () => ipcRenderer.invoke("win:maximize"),
    close: () => ipcRenderer.invoke("win:close"),
  },
  terminal: {
    wsUrl: "ws://127.0.0.1:52847/ws/terminal",
    start: () => ipcRenderer.invoke("terminal:start"),
    stop: () => ipcRenderer.invoke("terminal:stop"),
  },
  onNotification: (callback: (data: unknown) => void) => {
    const handler = (_event: unknown, data: unknown) => callback(data);
    ipcRenderer.on("duckyai:notification", handler as never);
    return () => ipcRenderer.removeListener("duckyai:notification", handler as never);
  },
});
