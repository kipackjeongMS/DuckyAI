import { useState, useEffect, useCallback, useRef } from "react";
import { useDuckyAI } from "../context/duckyai-provider";
import type { ExecutionEntry, ExecutionLogDetail } from "../types/duckyai";

const POLL_ACTIVE_MS = 10_000;
const POLL_HIDDEN_MS = 60_000;

export function useAgentHistory() {
  const api = useDuckyAI();
  const [entries, setEntries] = useState<ExecutionEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [agentFilter, setAgentFilter] = useState<string | null>(null);
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const lastHashRef = useRef("");

  const refresh = useCallback(async () => {
    try {
      const opts: { agent?: string } = {};
      if (agentFilter) opts.agent = agentFilter;
      const result = await api.orchestrator.history(opts);
      const hash = JSON.stringify(result);
      if (hash === lastHashRef.current) return;
      lastHashRef.current = hash;
      setEntries(result);
    } catch {
      // Ignore polling errors
    } finally {
      setLoading(false);
    }
  }, [api, agentFilter]);

  useEffect(() => {
    const startPolling = (ms: number) => {
      if (intervalRef.current) clearInterval(intervalRef.current);
      intervalRef.current = setInterval(refresh, ms);
    };

    setLoading(true);
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

  const fetchLog = useCallback(
    async (executionId: string, date?: string): Promise<ExecutionLogDetail> => {
      return api.orchestrator.executionLog(executionId, date);
    },
    [api],
  );

  return {
    entries,
    loading,
    agentFilter,
    setAgentFilter,
    refresh,
    fetchLog,
  };
}
