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
  },
  window: {
    minimize: () => ipcRenderer.invoke("win:minimize"),
    maximize: () => ipcRenderer.invoke("win:maximize"),
    close: () => ipcRenderer.invoke("win:close"),
  },
  chat: {
    send: (text: string) => ipcRenderer.invoke("chat:send", text),
  },
  onNotification: (callback: (data: { type: string; title: string; body?: string }) => void) => {
    const handler = (_event: Electron.IpcRendererEvent, data: { type: string; title: string; body?: string }) => {
      callback(data);
    };
    ipcRenderer.on("duckyai:notification", handler);
    return () => {
      ipcRenderer.removeListener("duckyai:notification", handler);
    };
  },
});
