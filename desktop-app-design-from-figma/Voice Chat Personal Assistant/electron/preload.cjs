const { contextBridge, ipcRenderer } = require("electron");

contextBridge.exposeInMainWorld("duckyai", {
  orchestrator: {
    start: () => ipcRenderer.invoke("orch:start"),
    stop: () => ipcRenderer.invoke("orch:stop"),
    status: () => ipcRenderer.invoke("orch:status"),
    listAgents: () => ipcRenderer.invoke("orch:list-agents"),
    triggerAgent: (abbr, opts) => ipcRenderer.invoke("orch:trigger", abbr, opts),
  },
  vault: {
    callTool: (name, args = {}) => ipcRenderer.invoke("vault:call-tool", name, args),
  },
  window: {
    minimize: () => ipcRenderer.invoke("win:minimize"),
    maximize: () => ipcRenderer.invoke("win:maximize"),
    close: () => ipcRenderer.invoke("win:close"),
  },
  chat: {
    send: (text) => ipcRenderer.invoke("chat:send", text),
  },
});
