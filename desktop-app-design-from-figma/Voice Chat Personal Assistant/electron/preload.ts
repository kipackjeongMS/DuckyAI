import { contextBridge, ipcRenderer } from "electron";

contextBridge.exposeInMainWorld("duckyai", {
  orchestrator: {
    start: () => ipcRenderer.invoke("orch:start"),
    stop: () => ipcRenderer.invoke("orch:stop"),
    status: () => ipcRenderer.invoke("orch:status"),
    listAgents: () => ipcRenderer.invoke("orch:list-agents"),
    triggerAgent: (abbr: string, opts?: Record<string, unknown>) =>
      ipcRenderer.invoke("orch:trigger", abbr, opts),
  },
  vault: {
    callTool: (name: string, args: Record<string, unknown> = {}) =>
      ipcRenderer.invoke("vault:call-tool", name, args),
  },
});
