// Context & Provider
export { DuckyAIProvider, useDuckyAI } from "./context/duckyai-provider";
export type { DuckyAIProviderProps } from "./context/duckyai-provider";

// Types
export type {
  DuckyAIApi,
  NotificationData,
  OrchestratorStatus,
  AgentInfo,
  VaultEntry,
  ExecutionEntry,
  ExecutionLogDetail,
} from "./types/duckyai";

// Hooks
export { useOrchestrator } from "./hooks/use-orchestrator";
export type { Agent } from "./hooks/use-orchestrator";
export { useVaultExplorer } from "./hooks/use-vault-explorer";
export type { FileTreeNode } from "./hooks/use-vault-explorer";
export { useAgentHistory } from "./hooks/use-agent-history";

// App component
export { default as DuckyAIApp } from "./components/App";
export type { DuckyAIAppProps } from "./components/App";

// Components
export { VoiceOrb } from "./components/voice-orb";
export { StatusBar, StatusIndicator } from "./components/status-bar";
export { QuickActions } from "./components/quick-actions";
export { TypewriterOverlay } from "./components/typewriter-overlay";
export type { TypewriterEntry } from "./components/typewriter-overlay";
export { Sidebar } from "./components/sidebar";
export { VaultExplorer } from "./components/vault-explorer";
export { NoteViewer } from "./components/note-viewer";
export { LoginScreen } from "./components/login-screen";
export { ToastContainer, useToasts } from "./components/toast";
export { AgentActivityLog } from "./components/agent-activity-log";
export type { AgentActivityLogProps } from "./components/agent-activity-log";
export { TerminalPanel } from "./components/terminal-panel";
export type { TerminalPanelProps } from "./components/terminal-panel";
