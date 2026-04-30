import { useState, useEffect, useCallback, useRef } from "react";
import { useDuckyAI } from "../context/duckyai-provider";

interface AgentInfoRaw {
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

function toAgent(info: AgentInfoRaw): Agent {
  return {
    id: info.abbreviation,
    name: info.name,
    category: info.category,
    cron: info.cron,
    status: info.running && info.running > 0 ? "running" : "idle",
  };
}

const POLL_ACTIVE_MS = 5_000;
const POLL_HIDDEN_MS = 30_000;
const STARTUP_MAX_ATTEMPTS = 10;
const STARTUP_BASE_DELAY_MS = 300;

export function useOrchestrator() {
  const api = useDuckyAI();
  const [running, setRunning] = useState(false);
  const [agents, setAgents] = useState<Agent[]>([]);
  const [triggeringId, setTriggeringId] = useState<string | null>(null);
  const [toggling, setToggling] = useState(false);
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const togglingRef = useRef(false);
  const lastHashRef = useRef("");

  const refresh = useCallback(async () => {
    try {
      const status = await api.orchestrator.status();
      if (!status.running) {
        const hash = "stopped";
        if (lastHashRef.current !== hash) {
          lastHashRef.current = hash;
          setRunning(false);
          setAgents([]);
        }
        return;
      }

      const agentList = await api.orchestrator.listAgents();
      const hash = JSON.stringify({ running: true, agents: agentList });
      if (hash === lastHashRef.current) return;
      lastHashRef.current = hash;
      setRunning(true);
      setAgents((agentList as unknown as AgentInfoRaw[]).map(toAgent));
    } catch {
      // Ignore errors during polling
    }
  }, [api]);

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
        refresh();
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
    if (togglingRef.current) return;
    togglingRef.current = true;
    setToggling(true);
    try {
      if (running) {
        const result = await api.orchestrator.stop();
        console.log("[orchestrator] stop result:", result);
        setRunning(false);
        setAgents([]);
      } else {
        const result = await api.orchestrator.start();
        console.log("[orchestrator] start result:", result);
        // Poll with exponential backoff until daemon responds
        for (let i = 0; i < STARTUP_MAX_ATTEMPTS; i++) {
          await new Promise((r) => setTimeout(r, STARTUP_BASE_DELAY_MS * Math.pow(1.4, i)));
          try {
            const status = await api.orchestrator.status();
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
      setToggling(false);
    }
  }, [running, refresh, api]);

  const triggerAgent = useCallback(async (abbr: string) => {
    setTriggeringId(abbr);
    try {
      await api.orchestrator.triggerAgent(abbr);
    } catch (err) {
      console.error(`Trigger agent ${abbr} failed:`, err);
    } finally {
      setTriggeringId(null);
    }
  }, [api]);

  const [restarting, setRestarting] = useState(false);

  const restartDaemon = useCallback(async () => {
    if (restarting) return;
    setRestarting(true);
    try {
      await api.orchestrator.restart();
      // Poll until orchestrator is back
      for (let i = 0; i < 10; i++) {
        await new Promise((r) => setTimeout(r, 1000));
        try {
          const status = await api.orchestrator.status();
          if (status.running) break;
        } catch { /* retry */ }
      }
      await refresh();
    } catch (err) {
      console.error("Failed to restart daemon:", err);
      await refresh();
    } finally {
      setRestarting(false);
    }
  }, [restarting, refresh, api]);

  return {
    running,
    agents,
    triggeringId,
    toggling,
    restarting,
    toggleOrchestrator,
    triggerAgent,
    restartDaemon,
  };
}
