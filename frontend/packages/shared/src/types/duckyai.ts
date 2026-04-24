export interface DuckyAIApi {
  orchestrator: {
    status: () => Promise<OrchestratorStatus>;
    listAgents: () => Promise<AgentInfo[]>;
    triggerAgent: (abbr: string, opts?: Record<string, unknown>) => Promise<void>;
    start: () => Promise<Record<string, unknown>>;
    stop: () => Promise<Record<string, unknown>>;
    shutdown?: () => Promise<Record<string, unknown>>;
    restart: () => Promise<Record<string, unknown>>;
    history: (opts?: { date?: string; agent?: string; status?: string }) => Promise<ExecutionEntry[]>;
    executionLog: (executionId: string, date?: string) => Promise<ExecutionLogDetail>;
  };
  vault: {
    callTool: (name: string, args?: Record<string, unknown>) => Promise<string>;
    listDir: (relativePath: string) => Promise<VaultEntry[]>;
    readFile: (relativePath: string) => Promise<string>;
  };
  window: {
    minimize: () => Promise<void>;
    maximize: () => Promise<void>;
    close: () => Promise<void>;
  };
  chat: {
    send: (text: string) => Promise<string>;
  };
  terminal: {
    /** WebSocket URL for the terminal server, e.g. ws://127.0.0.1:52847/ws/terminal */
    wsUrl: string;
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

export interface VaultEntry {
  name: string;
  type: "file" | "directory";
  relativePath: string;
}

export interface TokenUsage {
  input_tokens: number;
  output_tokens: number;
  cache_read_tokens: number;
  total_tokens: number;
  requests: number;
}

export interface ExecutionEntry {
  id: string;
  agent: string;
  status: string;
  trigger_type: string;
  input_path: string;
  output: string;
  error: string;
  log_path: string;
  created: string;
  updated: string;
  priority: string;
  token_usage?: TokenUsage;
}

export interface ExecutionLogDetail {
  execution_id: string;
  log_path: string;
  content: string;
  response: string;
}
