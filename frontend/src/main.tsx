import { createRoot } from "react-dom/client";
import type { CSSProperties } from "react";
import { Minus, Square, X } from "lucide-react";
import { DuckyAIApp, DuckyAIProvider, type DuckyAIApi } from "@duckyai/shared";
import "../packages/shared/src/styles/index.css";

// The Electron preload (preload.cjs) exposes the DuckyAIApi on window.duckyai.
const api = (window as unknown as { duckyai?: DuckyAIApi }).duckyai;

function WindowControls() {
  if (!api) return null;
  return (
    <div className="flex items-center" style={{ WebkitAppRegion: "no-drag" } as CSSProperties}>
      <button
        onClick={() => api.window.minimize()}
        className="h-8 w-11 inline-flex items-center justify-center text-muted-foreground hover:bg-white/10 transition-colors"
        aria-label="Minimize"
      >
        <Minus size={14} />
      </button>
      <button
        onClick={() => api.window.maximize()}
        className="h-8 w-11 inline-flex items-center justify-center text-muted-foreground hover:bg-white/10 transition-colors"
        aria-label="Maximize"
      >
        <Square size={12} />
      </button>
      <button
        onClick={() => api.window.close()}
        className="h-8 w-11 inline-flex items-center justify-center text-muted-foreground hover:bg-red-500/80 hover:text-white transition-colors"
        aria-label="Close"
      >
        <X size={15} />
      </button>
    </div>
  );
}

const root = createRoot(document.getElementById("root")!);

if (!api) {
  root.render(
    <div
      style={{
        height: "100vh",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        color: "#e2e8f0",
        background: "#0a0e1a",
        fontFamily: "system-ui, sans-serif",
        textAlign: "center",
        padding: "2rem",
      }}
    >
      <div>
        <h1 style={{ fontSize: "1.25rem", marginBottom: "0.5rem" }}>DuckyAI bridge unavailable</h1>
        <p style={{ color: "#94a3b8" }}>
          The desktop bridge (window.duckyai) was not injected. Ensure the app is launched via Electron
          with the preload script.
        </p>
      </div>
    </div>,
  );
} else {
  root.render(
    <DuckyAIProvider api={api}>
      <DuckyAIApp
        draggableTitleBar
        fullscreen
        renderWindowControls={() => <WindowControls />}
      />
    </DuckyAIProvider>,
  );
}