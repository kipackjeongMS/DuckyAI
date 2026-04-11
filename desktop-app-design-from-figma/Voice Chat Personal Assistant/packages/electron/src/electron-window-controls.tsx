import { Minus, Square, X } from "lucide-react";
import type { DuckyAIApi } from "@duckyai/shared";

interface ElectronWindowControlsProps {
  api: DuckyAIApi;
}

export function ElectronWindowControls({ api }: ElectronWindowControlsProps) {
  return (
    <div
      className="flex items-center gap-1 ml-2"
      style={{ WebkitAppRegion: "no-drag" } as React.CSSProperties}
    >
      <button
        onClick={() => api.window.minimize()}
        className="p-1.5 rounded hover:bg-white/10 text-muted-foreground hover:text-foreground transition-colors"
        title="Minimize"
      >
        <Minus size={14} />
      </button>
      <button
        onClick={() => api.window.maximize()}
        className="p-1.5 rounded hover:bg-white/10 text-muted-foreground hover:text-foreground transition-colors"
        title="Maximize"
      >
        <Square size={12} />
      </button>
      <button
        onClick={() => api.window.close()}
        className="p-1.5 rounded hover:bg-red-500/20 text-muted-foreground hover:text-red-400 transition-colors"
        title="Close"
      >
        <X size={14} />
      </button>
    </div>
  );
}
