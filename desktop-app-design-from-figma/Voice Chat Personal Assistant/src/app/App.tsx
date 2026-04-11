import { useState, useCallback, useRef, useEffect } from "react";
import { motion, AnimatePresence } from "motion/react";
import { Settings, X, Menu, Minus, Square } from "lucide-react";
import { VoiceOrb } from "./components/voice-orb";
import { StatusBar, StatusIndicator } from "./components/status-bar";
import { QuickActions } from "./components/quick-actions";
import { TypewriterOverlay, type TypewriterEntry } from "./components/typewriter-overlay";
import { Sidebar } from "./components/sidebar";
import { LoginScreen } from "./components/login-screen";
import { useOrchestrator } from "./hooks/use-orchestrator";
import { ToastContainer, useToasts } from "./components/toast";

type AppStatus = "idle" | "listening" | "processing" | "speaking";

/** Check if window.duckyai is available (Electron context). */
function hasBridge(): boolean {
  return typeof window !== "undefined" && window.duckyai != null;
}

/** Quick action labels shown in the typewriter overlay. */
const quickActionLabels: Record<string, string> = {
  "daily-note": "Prepare today's daily note",
  tasks: "Show current tasks",
  triage: "Triage my inbox",
  status: "Check system status",
};

export default function App() {
  // Auth handled by `az login` in Electron main process before window loads.
  const [isAuthenticated, setIsAuthenticated] = useState(true);
  const [status, setStatus] = useState<AppStatus>("idle");
  const [overlayEntries, setOverlayEntries] = useState<TypewriterEntry[]>([]);
  const [showOverlay, setShowOverlay] = useState(false);
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const chatRequestIdRef = useRef(0);

  const orch = useOrchestrator();
  const { toasts, addToast, dismissToast } = useToasts();

  // Listen for background notifications from Electron main process
  useEffect(() => {
    if (!hasBridge()) return;
    const unsubscribe = window.duckyai.onNotification((data) => {
      addToast(data);
    });
    return unsubscribe;
  }, [addToast]);

  const dismissOverlay = useCallback(() => {
    chatRequestIdRef.current++; // invalidate any in-flight chat response
    setStatus("idle");
    setShowOverlay(false);
    setOverlayEntries([]);
  }, []);

  /** Send a message through the Copilot SDK chat engine. */
  const sendChat = useCallback(
    async (userText: string) => {
      const userEntry: TypewriterEntry = {
        id: `user-${Date.now()}`,
        role: "user",
        text: userText,
      };

      // Append user message and show overlay
      setOverlayEntries((prev) => [...prev, userEntry]);
      setShowOverlay(true);
      setStatus("processing");

      if (!hasBridge()) {
        const errEntry: TypewriterEntry = {
          id: `assistant-${Date.now()}`,
          role: "assistant",
          text: "Running in browser — no vault connection.",
        };
        setOverlayEntries((prev) => [...prev, errEntry]);
        setStatus("idle");
        return;
      }

      const requestId = ++chatRequestIdRef.current;

      try {
        const response = await window.duckyai.chat.send(userText);
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
    [],
  );

  /** Execute a vault MCP tool and display the result. */
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
          className="h-screen w-screen flex bg-background overflow-hidden"
          style={{ fontFamily: "'Inter', system-ui, sans-serif" }}
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ duration: 0.6, delay: 0.2 }}
        >
          {/* Desktop Sidebar — hidden on mobile */}
          <div className="hidden lg:flex w-72 xl:w-80 h-full flex-col border-r border-[rgba(0,212,255,0.06)] bg-[#080c16]">
            {/* Sidebar header */}
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
            />
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
                        style={{ fontSize: "0.68rem", letterSpacing: "0.05em" }}
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
                  />
                </motion.div>
              </>
            )}
          </AnimatePresence>

          {/* Main content */}
          <div className="flex-1 h-full flex flex-col relative overflow-hidden">
            {/* Background gradient */}
            <div
              className="absolute inset-0 pointer-events-none"
              style={{
                background:
                  "radial-gradient(ellipse at 50% 30%, rgba(0,212,255,0.03) 0%, transparent 60%)",
              }}
            />

            {/* Mobile status bar */}
            <StatusBar />

            {/* Header — draggable title bar region */}
            <div
              className="flex items-center justify-between px-5 md:px-8 py-3 md:py-5 relative z-30"
              style={{ WebkitAppRegion: "drag" } as React.CSSProperties}
            >
              <div className="flex items-center gap-4" style={{ WebkitAppRegion: "no-drag" } as React.CSSProperties}>
                {/* Mobile menu button */}
                <button
                  onClick={() => setSidebarOpen(true)}
                  className="p-2 -ml-2 rounded-lg text-muted-foreground hover:text-foreground transition-colors lg:hidden"
                >
                  <Menu size={20} />
                </button>
                {/* Title — mobile only (desktop has it in sidebar) */}
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
                {/* Desktop — date and greeting */}
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
              <div className="flex items-center gap-2 md:gap-3" style={{ WebkitAppRegion: "no-drag" } as React.CSSProperties}>
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

                {/* Window controls (frameless window) */}
                {hasBridge() && (
                  <div className="flex items-center ml-2 -mr-2">
                    <button
                      onClick={() => window.duckyai.window.minimize()}
                      className="p-2 hover:bg-[rgba(255,255,255,0.06)] rounded transition-colors text-muted-foreground hover:text-foreground"
                      title="Minimize"
                    >
                      <Minus size={14} />
                    </button>
                    <button
                      onClick={() => window.duckyai.window.maximize()}
                      className="p-2 hover:bg-[rgba(255,255,255,0.06)] rounded transition-colors text-muted-foreground hover:text-foreground"
                      title="Maximize"
                    >
                      <Square size={12} />
                    </button>
                    <button
                      onClick={() => window.duckyai.window.close()}
                      className="p-2 hover:bg-[rgba(255,68,102,0.2)] rounded transition-colors text-muted-foreground hover:text-[#ff4466]"
                      title="Close"
                    >
                      <X size={14} />
                    </button>
                  </div>
                )}
              </div>
            </div>

            {/* Divider */}
            <div className="h-px bg-[rgba(0,212,255,0.06)] mx-5 md:mx-8 relative z-30" />

            {/* Central content — orb + overlay */}
            <div className="flex-1 flex flex-col overflow-hidden relative">
              {/* Orb area */}
              <div className="flex-1 flex flex-col items-center justify-center gap-4 md:gap-8 relative z-10">
                <StatusIndicator status={status} />

                {/* Responsive orb: small on mobile, large on desktop */}
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

                {/* Idle hint */}
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

              {/* Chat overlay */}
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
            </div>

            {/* Bottom controls */}
            <div
              className="relative z-30 pb-6 md:pb-10 pt-3"
            >
              {/* Quick actions */}
              <div className="flex justify-center">
                <div className="w-full md:w-auto">
                  <div className="md:hidden">
                    <QuickActions onAction={handleQuickAction} layout="compact" />
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
        </motion.div>
        </>
      )}
    </AnimatePresence>
  );
}