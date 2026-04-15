import { contextBridge, ipcRenderer } from "electron";

contextBridge.exposeInMainWorld("duckyai", {
  orchestrator: {
    status: () => ipcRenderer.invoke("orch:status"),
    listAgents: () => ipcRenderer.invoke("orch:list-agents"),
    triggerAgent: (abbr: string, opts?: Record<string, unknown>) =>
      ipcRenderer.invoke("orch:trigger", abbr, opts),
    start: () => ipcRenderer.invoke("orch:start"),
    stop: () => ipcRenderer.invoke("orch:stop"),
  },
  vault: {
    callTool: (name: string, args: Record<string, unknown> = {}) =>
      ipcRenderer.invoke("vault:call-tool", name, args),
    listDir: (relativePath: string) =>
      ipcRenderer.invoke("vault:list-dir", relativePath),
    readFile: (relativePath: string) =>
      ipcRenderer.invoke("vault:read-file", relativePath),
  },
});
