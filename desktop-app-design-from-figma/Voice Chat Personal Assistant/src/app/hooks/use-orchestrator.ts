import { useState, useEffect, useCallback, useRef } from "react";

interface OrchestratorStatus {
  running: boolean;
  pid?: number;
  agents_loaded?: number;
}

interface AgentInfo {
  abbreviation: string;
  name: string;
  category: string;
  cron: string | null;
  enabled: boolean;
  running?: number;
}

export interface Agent {
  id: string;
  name: string;
  category: string;
  cron: string | null;
  status: "idle" | "running" | "offline" | "queued";
}

function toAgent(info: AgentInfo): Agent {
  return {
    id: info.abbreviation,
    name: info.name,
    category: info.category,
    cron: info.cron,
    status: info.running && info.running > 0 ? "running" : "idle",
  };
}

function hasBridge(): boolean {
  return typeof window !== "undefined" && window.duckyai != null;
}

const POLL_ACTIVE_MS = 5_000;
const POLL_HIDDEN_MS = 30_000;
const STARTUP_MAX_ATTEMPTS = 10;
const STARTUP_BASE_DELAY_MS = 300;

export function useOrchestrator() {
  const [running, setRunning] = useState(false);
  const [agents, setAgents] = useState<Agent[]>([]);
  const [triggeringId, setTriggeringId] = useState<string | null>(null);
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const togglingRef = useRef(false);
  const lastHashRef = useRef("");

  const refresh = useCallback(async () => {
    if (!hasBridge()) return;
    try {
      const status = await window.duckyai.orchestrator.status();
      if (!status.running) {
        const hash = "stopped";
        if (lastHashRef.current !== hash) {
          lastHashRef.current = hash;
          setRunning(false);
          setAgents([]);
        }
        return;
      }

      const agentList = await window.duckyai.orchestrator.listAgents();
      const hash = JSON.stringify({ running: true, agents: agentList });
      if (hash === lastHashRef.current) return; // skip redundant updates
      lastHashRef.current = hash;
      setRunning(true);
      setAgents(agentList.map(toAgent));
    } catch {
      // Ignore errors during polling
    }
  }, []);

  // Visibility-aware polling: 5s when active, 30s when tab/window hidden
  useEffect(() => {
    const startPolling = (intervalMs: number) => {
      if (intervalRef.current) clearInterval(intervalRef.current);
      intervalRef.current = setInterval(refresh, intervalMs);
    };

    refresh();
    startPolling(document.hidden ? POLL_HIDDEN_MS : POLL_ACTIVE_MS);

    const onVisibilityChange = () => {
      if (document.hidden) {
        startPolling(POLL_HIDDEN_MS);
      } else {
        refresh(); // immediate refresh on focus
        startPolling(POLL_ACTIVE_MS);
      }
    };

    document.addEventListener("visibilitychange", onVisibilityChange);
    return () => {
      if (intervalRef.current) clearInterval(intervalRef.current);
      document.removeEventListener("visibilitychange", onVisibilityChange);
    };
  }, [refresh]);

  const toggleOrchestrator = useCallback(async () => {
    if (!hasBridge() || togglingRef.current) return;
    togglingRef.current = true;
    try {
      if (running) {
        const result = await window.duckyai.orchestrator.stop();
        console.log("[orchestrator] stop result:", result);
        setRunning(false);
        setAgents([]);
      } else {
        const result = await window.duckyai.orchestrator.start();
        console.log("[orchestrator] start result:", result);
        // Poll with exponential backoff until daemon responds
        for (let i = 0; i < STARTUP_MAX_ATTEMPTS; i++) {
          await new Promise((r) => setTimeout(r, STARTUP_BASE_DELAY_MS * Math.pow(1.4, i)));
          try {
            const status = await window.duckyai.orchestrator.status();
            if (status.running) break;
          } catch { /* retry */ }
        }
        await refresh();
      }
    } catch (err) {
      console.error("Failed to toggle orchestrator:", err);
      await refresh();
    } finally {
      togglingRef.current = false;
    }
  }, [running, refresh]);

  const triggerAgent = useCallback(async (abbr: string, opts?: Record<string, unknown>) => {
    if (!hasBridge()) return;
    setTriggeringId(abbr);
    try {
      await window.duckyai.orchestrator.triggerAgent(abbr, opts);
    } catch (err) {
      console.error(`Trigger agent ${abbr} failed:`, err);
    } finally {
      setTriggeringId(null);
    }
  }, []);

  return {
    running,
    agents,
    triggeringId,
    toggleOrchestrator,
    triggerAgent,
  };
}
