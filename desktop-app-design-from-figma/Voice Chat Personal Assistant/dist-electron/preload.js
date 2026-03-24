import { contextBridge, ipcRenderer } from "electron";
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
});
