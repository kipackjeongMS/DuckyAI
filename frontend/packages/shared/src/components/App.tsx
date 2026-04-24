import { useState, useCallback, useRef, useEffect } from "react";
import { motion, AnimatePresence } from "motion/react";
import { Settings, X, Menu, FolderTree, Bot } from "lucide-react";
import { VoiceOrb } from "./voice-orb";
import { StatusBar, StatusIndicator } from "./status-bar";
import { QuickActions } from "./quick-actions";
import { TypewriterOverlay, type TypewriterEntry } from "./typewriter-overlay";
import { Sidebar } from "./sidebar";
import { LoginScreen } from "./login-screen";
import { VaultExplorer } from "./vault-explorer";
import { NoteViewer } from "./note-viewer";
import { useOrchestrator } from "../hooks/use-orchestrator";
import { useVaultExplorer } from "../hooks/use-vault-explorer";
import { useAgentHistory } from "../hooks/use-agent-history";
import { ToastContainer, useToasts } from "./toast";
import { useDuckyAI } from "../context/duckyai-provider";

type AppStatus = "idle" | "listening" | "processing" | "speaking";

/** Quick action labels shown in the typewriter overlay. */
const quickActionLabels: Record<string, string> = {
  "daily-note": "Prepare today's daily note",
  tasks: "Show current tasks",
  triage: "Triage my inbox",
  status: "Check system status",
};

export interface DuckyAIAppProps {
  /** Render window controls (minimize/maximize/close). Electron provides these; Obsidian does not. */
  renderWindowControls?: () => React.ReactNode;
  /** Whether the title bar should be draggable (Electron frameless window). */
  draggableTitleBar?: boolean;
  /** Use viewport sizing (h-screen/w-screen). True for standalone windows, false for embedded panels. */
  fullscreen?: boolean;
  /** Show only the sidebar (orchestrator + agents) without the main chat panel. */
  sidebarOnly?: boolean;
  /** Callback to open the code workspace (e.g. in VS Code). */
  onOpenWorkspace?: () => void;
}

export default function DuckyAIApp({
  renderWindowControls,
  draggableTitleBar = false,
  fullscreen = true,
  sidebarOnly = false,
  onOpenWorkspace,
}: DuckyAIAppProps) {
  const api = useDuckyAI();

  const [isAuthenticated, setIsAuthenticated] = useState(true);
  const [status, setStatus] = useState<AppStatus>("idle");
  const [overlayEntries, setOverlayEntries] = useState<TypewriterEntry[]>([]);
  const [showOverlay, setShowOverlay] = useState(false);
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const chatRequestIdRef = useRef(0);

  const orch = useOrchestrator();
  const { toasts, addToast, dismissToast } = useToasts();
  const vault = useVaultExplorer();
  const activity = useAgentHistory();
  const [sidebarTab, setSidebarTab] = useState<"files" | "agents">("files");

  // Listen for background notifications
  useEffect(() => {
    const unsubscribe = api.onNotification((data) => {
      addToast(data);
    });
    return unsubscribe;
  }, [api, addToast]);

  const dismissOverlay = useCallback(() => {
    chatRequestIdRef.current++;
    setStatus("idle");
    setShowOverlay(false);
    setOverlayEntries([]);
  }, []);

  const sendChat = useCallback(
    async (userText: string) => {
      const userEntry: TypewriterEntry = {
        id: `user-${Date.now()}`,
        role: "user",
        text: userText,
      };

      setOverlayEntries((prev) => [...prev, userEntry]);
      setShowOverlay(true);
      setStatus("processing");

      const requestId = ++chatRequestIdRef.current;

      try {
        const response = await api.chat.send(userText);
        if (chatRequestIdRef.current === requestId) {
          const assistantEntry: TypewriterEntry = {
            id: `assistant-${Date.now()}`,
            role: "assistant",
            text: response,
          };
          setOverlayEntries((prev) => [...prev, assistantEntry]);
          setStatus("idle");
        }
      } catch (err) {
        if (chatRequestIdRef.current === requestId) {
          const msg = err instanceof Error ? err.message : String(err);
          const errEntry: TypewriterEntry = {
            id: `assistant-${Date.now()}`,
            role: "assistant",
            text: `Error: ${msg}`,
          };
          setOverlayEntries((prev) => [...prev, errEntry]);
          setStatus("idle");
        }
      }
    },
    [api],
  );

  const executeVaultAction = useCallback(
    async (actionId: string) => {
      const userText = quickActionLabels[actionId] ?? actionId;
      await sendChat(userText);
    },
    [sendChat],
  );

  const handleDuckyPress = useCallback(() => {
    if (status !== "idle") return;
    setShowOverlay(true);
  }, [status]);

  const handleQuickAction = useCallback(
    (id: string) => {
      if (status !== "idle") return;
      executeVaultAction(id);
    },
    [status, executeVaultAction],
  );

  const titleBarStyle = draggableTitleBar
    ? ({ WebkitAppRegion: "drag" } as React.CSSProperties)
    : undefined;
  const noDragStyle = draggableTitleBar
    ? ({ WebkitAppRegion: "no-drag" } as React.CSSProperties)
    : undefined;

  return (
    <AnimatePresence mode="wait">
      {!isAuthenticated ? (
        <motion.div
          key="login"
          exit={{ opacity: 0, scale: 0.98 }}
          transition={{ duration: 0.4 }}
        >
          <LoginScreen onLogin={() => setIsAuthenticated(true)} />
        </motion.div>
      ) : (
        <>
          <ToastContainer toasts={toasts} onDismiss={dismissToast} />
          <motion.div
            key="app"
            className={`${fullscreen ? "h-screen w-screen" : "h-full w-full"} flex bg-background overflow-hidden`}
            style={{ fontFamily: "'Inter', system-ui, sans-serif" }}
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={{ duration: 0.6, delay: 0.2 }}
          >
            {sidebarOnly ? (
              /* Sidebar-only mode (Obsidian plugin) */
              <div className="w-full h-full flex flex-col bg-[#080c16]">
                <div className="px-5 pt-6 pb-4 border-b border-[rgba(0,212,255,0.06)]">
                  <h1
                    className="text-foreground tracking-wide"
                    style={{ fontSize: "1.2rem", letterSpacing: "0.25em" }}
                  >
                    DUCKAI
                  </h1>
                  <p
                    className="text-muted-foreground mt-1"
                    style={{ fontSize: "0.68rem", letterSpacing: "0.05em" }}
                  >
                    Your Intelligent Duck Assistant
                  </p>
                </div>
                <Sidebar
                  orchestratorRunning={orch.running}
                  agents={orch.agents}
                  triggeringId={orch.triggeringId}
                  onToggleOrchestrator={orch.toggleOrchestrator}
                  onTriggerAgent={orch.triggerAgent}
                  restarting={orch.restarting}
                  onRestartDaemon={orch.restartDaemon}
                  onOpenWorkspace={onOpenWorkspace}
                  onChatSend={api.chat.send}
                  activityEntries={activity.entries}
                  activityLoading={activity.loading}
                  activityAgentFilter={activity.agentFilter}
                  onActivityFilterChange={activity.setAgentFilter}
                  onActivityRefresh={activity.refresh}
                  onFetchLog={activity.fetchLog}
                />
              </div>
            ) : (
            <>
            {/* Desktop Sidebar */}
            <div className="hidden lg:flex w-72 xl:w-80 h-full flex-col border-r border-[rgba(0,212,255,0.06)] bg-[#080c16]">
              <div className="px-5 pt-6 pb-4 border-b border-[rgba(0,212,255,0.06)]">
                <h1
                  className="text-foreground tracking-wide"
                  style={{ fontSize: "1.2rem", letterSpacing: "0.25em" }}
                >
                  DUCKAI
                </h1>
                <p
                  className="text-muted-foreground mt-1"
                  style={{ fontSize: "0.68rem", letterSpacing: "0.05em" }}
                >
                  Your Intelligent Duck Assistant
                </p>
              </div>

              {/* Sidebar tabs */}
              <div className="flex border-b border-[rgba(0,212,255,0.06)]">
                <button
                  className="flex-1 flex items-center justify-center gap-1.5 py-2.5 transition-colors"
                  style={{
                    fontSize: "0.68rem",
                    letterSpacing: "0.1em",
                    color: sidebarTab === "files" ? "#00d4ff" : "#64748b",
                    borderBottom: sidebarTab === "files" ? "2px solid #00d4ff" : "2px solid transparent",
                  }}
                  onClick={() => setSidebarTab("files")}
                >
                  <FolderTree size={13} />
                  FILES
                </button>
                <button
                  className="flex-1 flex items-center justify-center gap-1.5 py-2.5 transition-colors"
                  style={{
                    fontSize: "0.68rem",
                    letterSpacing: "0.1em",
                    color: sidebarTab === "agents" ? "#00d4ff" : "#64748b",
                    borderBottom: sidebarTab === "agents" ? "2px solid #00d4ff" : "2px solid transparent",
                  }}
                  onClick={() => setSidebarTab("agents")}
                >
                  <Bot size={13} />
                  AGENTS
                </button>
              </div>

              {/* Tab content */}
              <div className="flex-1 overflow-y-auto">
                {sidebarTab === "files" ? (
                  <VaultExplorer
                    roots={vault.roots}
                    loading={vault.loading}
                    expandedPaths={vault.expandedPaths}
                    selectedFile={vault.selectedFile}
                    onToggleDirectory={vault.toggleDirectory}
                    onOpenFile={vault.openFile}
                  />
                ) : (
                  <Sidebar
                    orchestratorRunning={orch.running}
                    agents={orch.agents}
                    triggeringId={orch.triggeringId}
                    onToggleOrchestrator={orch.toggleOrchestrator}
                    onTriggerAgent={orch.triggerAgent}
                    restarting={orch.restarting}
                    onRestartDaemon={orch.restartDaemon}
                    onOpenWorkspace={onOpenWorkspace}
                    onChatSend={api.chat.send}
                    activityEntries={activity.entries}
                    activityLoading={activity.loading}
                    activityAgentFilter={activity.agentFilter}
                    onActivityFilterChange={activity.setAgentFilter}
                    onActivityRefresh={activity.refresh}
                    onFetchLog={activity.fetchLog}
                  />
                )}
              </div>
            </div>

            {/* Mobile sidebar overlay */}
            <AnimatePresence>
              {sidebarOpen && (
                <>
                  <motion.div
                    className="fixed inset-0 z-40 bg-black/60 lg:hidden"
                    initial={{ opacity: 0 }}
                    animate={{ opacity: 1 }}
                    exit={{ opacity: 0 }}
                    onClick={() => setSidebarOpen(false)}
                  />
                  <motion.div
                    className="fixed left-0 top-0 bottom-0 z-50 w-80 bg-[#080c16] border-r border-[rgba(0,212,255,0.06)] lg:hidden flex flex-col"
                    initial={{ x: -320 }}
                    animate={{ x: 0 }}
                    exit={{ x: -320 }}
                    transition={{ type: "spring", damping: 25, stiffness: 300 }}
                  >
                    <div className="px-5 pt-6 pb-4 border-b border-[rgba(0,212,255,0.06)] flex items-center justify-between">
                      <div>
                        <h1
                          className="text-foreground tracking-wide"
                          style={{ fontSize: "1.1rem", letterSpacing: "0.2em" }}
                        >
                          DUCKAI
                        </h1>
                        <p
                          className="text-muted-foreground mt-0.5"
                          style={{
                            fontSize: "0.68rem",
                            letterSpacing: "0.05em",
                          }}
                        >
                          Your Intelligent Duck Assistant
                        </p>
                      </div>
                      <button
                        onClick={() => setSidebarOpen(false)}
                        className="p-2 rounded-lg text-muted-foreground hover:text-foreground"
                      >
                        <X size={18} />
                      </button>
                    </div>
                    <Sidebar
                      orchestratorRunning={orch.running}
                      agents={orch.agents}
                      triggeringId={orch.triggeringId}
                      onToggleOrchestrator={orch.toggleOrchestrator}
                      onTriggerAgent={orch.triggerAgent}
                      restarting={orch.restarting}
                      onRestartDaemon={orch.restartDaemon}
                      onOpenWorkspace={onOpenWorkspace}
                      onChatSend={api.chat.send}
                      activityEntries={activity.entries}
                      activityLoading={activity.loading}
                      activityAgentFilter={activity.agentFilter}
                      onActivityFilterChange={activity.setAgentFilter}
                      onActivityRefresh={activity.refresh}
                      onFetchLog={activity.fetchLog}
                    />
                  </motion.div>
                </>
              )}
            </AnimatePresence>

            {/* Main content */}
            <div className="flex-1 h-full flex flex-col relative overflow-hidden">
              <div
                className="absolute inset-0 pointer-events-none"
                style={{
                  background:
                    "radial-gradient(ellipse at 50% 30%, rgba(0,212,255,0.03) 0%, transparent 60%)",
                }}
              />

              <StatusBar />

              {/* Header */}
              <div
                className="flex items-center justify-between px-5 md:px-8 py-3 md:py-5 relative z-30"
                style={titleBarStyle}
              >
                <div
                  className="flex items-center gap-4"
                  style={noDragStyle}
                >
                  <button
                    onClick={() => setSidebarOpen(true)}
                    className="p-2 -ml-2 rounded-lg text-muted-foreground hover:text-foreground transition-colors lg:hidden"
                  >
                    <Menu size={20} />
                  </button>
                  <div className="lg:hidden">
                    <h1
                      className="text-foreground tracking-wide"
                      style={{ fontSize: "1.1rem", letterSpacing: "0.2em" }}
                    >
                      DUCKAI
                    </h1>
                    <p
                      className="text-muted-foreground mt-0.5"
                      style={{ fontSize: "0.7rem", letterSpacing: "0.05em" }}
                    >
                      Your Intelligent Duck Assistant
                    </p>
                  </div>
                  <div className="hidden lg:block">
                    <p
                      className="text-muted-foreground"
                      style={{ fontSize: "0.78rem" }}
                    >
                      {new Date().toLocaleDateString("en-US", {
                        weekday: "long",
                        month: "long",
                        day: "numeric",
                        year: "numeric",
                      })}
                    </p>
                  </div>
                </div>
                <div
                  className="flex items-center gap-2 md:gap-3"
                  style={noDragStyle}
                >
                  {showOverlay && (
                    <motion.button
                      initial={{ opacity: 0, scale: 0.8 }}
                      animate={{ opacity: 1, scale: 1 }}
                      onClick={dismissOverlay}
                      className="p-2 rounded-lg text-muted-foreground hover:text-foreground transition-colors"
                      title="Close chat"
                    >
                      <X size={18} />
                    </motion.button>
                  )}
                  <button className="p-2 rounded-lg text-muted-foreground hover:text-foreground transition-colors">
                    <Settings size={18} />
                  </button>

                  {renderWindowControls?.()}
                </div>
              </div>

              <div className="h-px bg-[rgba(0,212,255,0.06)] mx-5 md:mx-8 relative z-30" />

              {/* Central content */}
              <div className="flex-1 flex flex-col overflow-hidden relative">
                {vault.selectedFile && vault.fileContent !== null ? (
                  /* Note viewer */
                  <NoteViewer
                    filePath={vault.selectedFile}
                    content={vault.fileContent}
                    onClose={vault.closeFile}
                  />
                ) : vault.selectedFile ? (
                  /* Loading file content */
                  <div className="flex-1 flex items-center justify-center">
                    <div className="flex items-center gap-2 text-muted-foreground" style={{ fontSize: "0.8rem" }}>
                      <div className="w-4 h-4 border-2 border-t-[#00d4ff] border-[rgba(0,212,255,0.2)] rounded-full animate-spin" />
                      Loading...
                    </div>
                  </div>
                ) : (
                  /* Default voice assistant view */
                  <>
                <div className="flex-1 flex flex-col items-center justify-center gap-4 md:gap-8 relative z-10">
                  <StatusIndicator status={status} />

                  <div className="md:hidden">
                    <VoiceOrb
                      isListening={status === "listening"}
                      isProcessing={status === "processing"}
                      isSpeaking={status === "speaking"}
                      size="sm"
                      onClick={handleDuckyPress}
                    />
                  </div>
                  <div className="hidden md:block">
                    <VoiceOrb
                      isListening={status === "listening"}
                      isProcessing={status === "processing"}
                      isSpeaking={status === "speaking"}
                      size="lg"
                      onClick={handleDuckyPress}
                    />
                  </div>

                  <AnimatePresence>
                    {!showOverlay && status === "idle" && (
                      <motion.p
                        className="text-muted-foreground text-center px-8 max-w-xs md:max-w-md"
                        style={{ fontSize: "0.75rem", letterSpacing: "0.1em" }}
                        initial={{ opacity: 0 }}
                        animate={{ opacity: 0.5 }}
                        exit={{ opacity: 0 }}
                      >
                        TAP THE DUCK TO SPEAK
                      </motion.p>
                    )}
                    {status !== "idle" && (
                      <motion.p
                        className="text-muted-foreground text-center px-8"
                        style={{ fontSize: "0.7rem", letterSpacing: "0.1em" }}
                        initial={{ opacity: 0 }}
                        animate={{ opacity: 0.6 }}
                        exit={{ opacity: 0 }}
                      >
                        {status === "listening"
                          ? "LISTENING"
                          : status === "processing"
                            ? "PROCESSING"
                            : "SPEAKING"}
                      </motion.p>
                    )}
                  </AnimatePresence>
                </div>

                <AnimatePresence>
                  {showOverlay && (
                    <motion.div
                      className="absolute inset-0 z-20"
                      initial={{ opacity: 0 }}
                      animate={{ opacity: 1 }}
                      exit={{ opacity: 0 }}
                      transition={{ duration: 0.4 }}
                      style={{
                        background:
                          "linear-gradient(to bottom, rgba(10,14,26,0.92) 0%, rgba(10,14,26,0.88) 40%, rgba(10,14,26,0.95) 100%)",
                        backdropFilter: "blur(8px)",
                      }}
                    >
                      <TypewriterOverlay
                        entries={overlayEntries}
                        isProcessing={status === "processing"}
                        onSendMessage={sendChat}
                      />
                    </motion.div>
                  )}
                </AnimatePresence>
                  </>
                )}
              </div>

              {/* Bottom controls */}
              <div className="relative z-30 pb-6 md:pb-10 pt-3">
                <div className="flex justify-center">
                  <div className="w-full md:w-auto">
                    <div className="md:hidden">
                      <QuickActions
                        onAction={handleQuickAction}
                        layout="compact"
                      />
                    </div>
                    <div className="hidden md:block">
                      <QuickActions
                        onAction={handleQuickAction}
                        layout="horizontal"
                      />
                    </div>
                  </div>
                </div>
              </div>
            </div>
            </>
            )}
          </motion.div>
        </>
      )}
    </AnimatePresence>
  );
}
