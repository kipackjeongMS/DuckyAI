const { contextBridge, ipcRenderer } = require("electron");

contextBridge.exposeInMainWorld("duckyai", {
  orchestrator: {
    status: () => ipcRenderer.invoke("orch:status"),
    listAgents: () => ipcRenderer.invoke("orch:list-agents"),
    triggerAgent: (abbr, opts) => ipcRenderer.invoke("orch:trigger", abbr, opts),
    start: () => ipcRenderer.invoke("orch:start"),
    stop: () => ipcRenderer.invoke("orch:stop"),
  },
  vault: {
    callTool: (name, args = {}) => ipcRenderer.invoke("vault:call-tool", name, args),
    listDir: (relativePath) => ipcRenderer.invoke("vault:list-dir", relativePath),
    readFile: (relativePath) => ipcRenderer.invoke("vault:read-file", relativePath),
  },
  window: {
    minimize: () => ipcRenderer.invoke("win:minimize"),
    maximize: () => ipcRenderer.invoke("win:maximize"),
    close: () => ipcRenderer.invoke("win:close"),
  },
  chat: {
    send: (text) => ipcRenderer.invoke("chat:send", text),
  },
  onNotification: (callback) => {
    const handler = (_event, data) => callback(data);
    ipcRenderer.on("duckyai:notification", handler);
    return () => ipcRenderer.removeListener("duckyai:notification", handler);
  },
});
