import { createRoot } from "react-dom/client";
import { DuckyAIProvider, DuckyAIApp } from "@duckyai/shared";
import type { DuckyAIApi } from "@duckyai/shared";
import "@duckyai/shared/styles/index.css";
import { ElectronWindowControls } from "./electron-window-controls";

/**
 * In Electron, window.duckyai is injected by preload.ts via contextBridge.
 * We cast it to DuckyAIApi for the shared provider.
 */
declare global {
  interface Window {
    duckyai: DuckyAIApi;
  }
}

function ElectronApp() {
  const api = window.duckyai;

  return (
    <DuckyAIProvider api={api}>
      <DuckyAIApp
        draggableTitleBar={true}
        renderWindowControls={() => <ElectronWindowControls api={api} />}
      />
    </DuckyAIProvider>
  );
}

createRoot(document.getElementById("root")!).render(<ElectronApp />);
