export interface DuckyAIApi {
  orchestrator: {
    status: () => Promise<OrchestratorStatus>;
    listAgents: () => Promise<AgentInfo[]>;
    triggerAgent: (abbr: string, opts?: Record<string, unknown>) => Promise<void>;
    start: () => Promise<Record<string, unknown>>;
    stop: () => Promise<Record<string, unknown>>;
  };
  vault: {
    callTool: (name: string, args?: Record<string, unknown>) => Promise<string>;
  };
  window: {
    minimize: () => Promise<void>;
    maximize: () => Promise<void>;
    close: () => Promise<void>;
  };
  chat: {
    send: (text: string) => Promise<string>;
  };
  onNotification: (callback: (data: NotificationData) => void) => () => void;
}

export interface NotificationData {
  type: "success" | "error" | "info";
  title: string;
  body?: string;
}

export interface OrchestratorStatus {
  running: boolean;
  pid?: number;
  agents_loaded?: number;
  status?: string;
}

export interface AgentInfo {
  abbreviation: string;
  name: string;
  category: string;
  cron: string | null;
  enabled: boolean;
}

declare global {
  interface Window {
    duckyai: DuckyAIApi;
  }
}
