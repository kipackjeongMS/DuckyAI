const { contextBridge, ipcRenderer } = require("electron");

contextBridge.exposeInMainWorld("duckyai", {
  orchestrator: {
    status: () => ipcRenderer.invoke("orch:status"),
    listAgents: () => ipcRenderer.invoke("orch:list-agents"),
    triggerAgent: (abbr, opts) => ipcRenderer.invoke("orch:trigger", abbr, opts),
    start: () => ipcRenderer.invoke("orch:start"),
    stop: () => ipcRenderer.invoke("orch:stop"),
    shutdown: () => ipcRenderer.invoke("orch:shutdown"),
    restart: () => ipcRenderer.invoke("orch:restart"),
    history: (opts) => ipcRenderer.invoke("orch:history", opts),
    executionLog: (executionId, date) => ipcRenderer.invoke("orch:log", executionId, date),
  },
  vault: {
    callTool: (name, args = {}) => ipcRenderer.invoke("vault:call-tool", name, args),
    listDir: (relativePath) => ipcRenderer.invoke("vault:list-dir", relativePath),
    readFile: (relativePath) => ipcRenderer.invoke("vault:read-file", relativePath),
    writeFile: (relativePath, content) =>
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
  onNotification: (callback) => {
    const handler = (_event, data) => callback(data);
    ipcRenderer.on("duckyai:notification", handler);
    return () => ipcRenderer.removeListener("duckyai:notification", handler);
  },
});
