import { useState } from "react";
import { motion, AnimatePresence } from "motion/react";
import {
  CheckCircle2,
  XCircle,
  Clock,
  Loader2,
  ChevronDown,
  ChevronRight,
  RefreshCw,
  Filter,
} from "lucide-react";
import type { ExecutionEntry, ExecutionLogDetail } from "../types/duckyai";

const statusConfig: Record<
  string,
  { color: string; icon: typeof CheckCircle2; label: string }
> = {
  PROCESSED: { color: "#00ffa3", icon: CheckCircle2, label: "Completed" },
  completed: { color: "#00ffa3", icon: CheckCircle2, label: "Completed" },
  IN_PROGRESS: { color: "#ffbe0b", icon: Loader2, label: "Running" },
  QUEUED: { color: "#00d4ff", icon: Clock, label: "Queued" },
  FAILED: { color: "#ff4466", icon: XCircle, label: "Failed" },
  failed: { color: "#ff4466", icon: XCircle, label: "Failed" },
  IGNORE: { color: "#666", icon: Clock, label: "Skipped" },
  IGNORED: { color: "#666", icon: Clock, label: "Skipped" },
  timeout: { color: "#ff8844", icon: XCircle, label: "Timeout" },
};

function getStatusInfo(status: string) {
  return (
    statusConfig[status] ?? {
      color: "#888",
      icon: Clock,
      label: status,
    }
  );
}

function formatDuration(created: string, updated: string): string {
  try {
    const t0 = new Date(created).getTime();
    const t1 = new Date(updated).getTime();
    const secs = (t1 - t0) / 1000;
    if (secs < 0 || isNaN(secs)) return "";
    if (secs < 120) return `${secs.toFixed(1)}s`;
    return `${(secs / 60).toFixed(1)}m`;
  } catch {
    return "";
  }
}

function formatTime(isoString: string): string {
  try {
    const dt = new Date(isoString);
    return dt.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
  } catch {
    return "";
  }
}

interface EntryRowProps {
  entry: ExecutionEntry;
  onFetchLog: (id: string, date?: string) => Promise<ExecutionLogDetail>;
}

function EntryRow({ entry, onFetchLog }: EntryRowProps) {
  const [expanded, setExpanded] = useState(false);
  const [logContent, setLogContent] = useState<string | null>(null);
  const [logLoading, setLogLoading] = useState(false);
  const [logError, setLogError] = useState<string | null>(null);

  const info = getStatusInfo(entry.status);
  const StatusIcon = info.icon;
  const duration = formatDuration(entry.created, entry.updated);
  const time = formatTime(entry.created);

  const handleExpand = async () => {
    if (!expanded && logContent === null) {
      setLogLoading(true);
      setLogError(null);
      try {
        // Extract YYYY-MM-DD from entry.created for cross-day robustness
        let dateStr: string | undefined;
        try {
          const d = new Date(entry.created);
          if (!isNaN(d.getTime())) {
            dateStr = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
          }
        } catch { /* fallback: let backend use today */ }
        const detail = await onFetchLog(entry.id, dateStr);
        setLogContent(detail.response || detail.content || "(empty)");
      } catch (err: unknown) {
        const message =
          err instanceof Error ? err.message : "Failed to load log";
        setLogError(message);
      } finally {
        setLogLoading(false);
      }
    }
    setExpanded(!expanded);
  };

  return (
    <div className="w-full min-w-0">
      <motion.button
        className="w-full text-left px-3 py-2 rounded-lg transition-colors overflow-hidden"
        style={{
          background: expanded
            ? "rgba(13,18,32,0.9)"
            : "rgba(13,18,32,0.6)",
          border: `1px solid ${expanded ? `${info.color}20` : "rgba(0,212,255,0.04)"}`,
        }}
        onClick={handleExpand}
        whileHover={{ background: "rgba(13,18,32,0.8)" }}
      >
        {/* Row 1: fixed-width columns */}
        <div className="flex items-center w-full min-w-0" style={{ gap: "6px" }}>
          {/* Chevron — fixed 14px */}
          <span className="shrink-0" style={{ color: "#666", width: 14 }}>
            {expanded ? <ChevronDown size={12} /> : <ChevronRight size={12} />}
          </span>

          {/* Status icon — fixed 14px */}
          <span className="shrink-0" style={{ color: info.color, width: 14 }}>
            {entry.status === "IN_PROGRESS" ? (
              <motion.span
                animate={{ rotate: 360 }}
                transition={{ duration: 1, repeat: Infinity, ease: "linear" }}
                style={{ display: "inline-block" }}
              >
                <StatusIcon size={13} />
              </motion.span>
            ) : (
              <StatusIcon size={13} />
            )}
          </span>

          {/* Agent name — fixed 36px */}
          <span
            className="shrink-0 text-foreground font-medium"
            style={{ fontSize: "0.74rem", width: 36 }}
          >
            {entry.agent}
          </span>

          {/* Time — fixed 62px */}
          <span
            className="shrink-0 text-muted-foreground"
            style={{ fontSize: "0.62rem", width: 62 }}
          >
            {time}
          </span>

          {/* Duration — fixed 40px */}
          <span
            className="shrink-0 text-muted-foreground"
            style={{ fontSize: "0.6rem", width: 40, opacity: 0.7 }}
          >
            {duration || ""}
          </span>

          {/* Status label — fixed 72px */}
          <span
            className="shrink-0"
            style={{
              fontSize: "0.58rem",
              width: 72,
              color: info.color,
              opacity: 0.8,
              textTransform: "uppercase",
              letterSpacing: "0.05em",
            }}
          >
            {info.label}
          </span>

          {/* Output/input — fills remaining space, single line truncated */}
          <span
            className="truncate min-w-0 flex-1"
            style={{ fontSize: "0.58rem", color: "#00d4ff", opacity: 0.7 }}
          >
            {entry.output || entry.input_path || entry.error || ""}
          </span>
        </div>
      </motion.button>

      {/* Expanded log detail */}
      <AnimatePresence>
        {expanded && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.2 }}
            className="overflow-hidden"
          >
            <div
              className="mx-3 mb-2 px-3 py-2 rounded-b-lg"
              style={{
                background: "rgba(0,0,0,0.3)",
                borderLeft: `2px solid ${info.color}30`,
                fontSize: "0.62rem",
              }}
            >
              {logLoading && (
                <div className="flex items-center gap-2 text-muted-foreground py-2">
                  <Loader2 size={12} className="animate-spin" />
                  Loading log...
                </div>
              )}
              {logError && (
                <div style={{ color: "#ff4466" }}>{logError}</div>
              )}
              {logContent && (
                <pre
                  className="whitespace-pre-wrap text-muted-foreground overflow-x-auto max-h-60 overflow-y-auto"
                  style={{ fontSize: "0.58rem", lineHeight: 1.5 }}
                >
                  {logContent}
                </pre>
              )}
              {!logLoading && !logError && !logContent && (
                <div className="text-muted-foreground py-1">
                  No log file for this execution.
                </div>
              )}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

export interface AgentActivityLogProps {
  entries: ExecutionEntry[];
  loading: boolean;
  agentFilter: string | null;
  agents: string[];
  onSetAgentFilter: (agent: string | null) => void;
  onRefresh: () => void;
  onFetchLog: (id: string, date?: string) => Promise<ExecutionLogDetail>;
}

export function AgentActivityLog({
  entries,
  loading,
  agentFilter,
  agents,
  onSetAgentFilter,
  onRefresh,
  onFetchLog,
}: AgentActivityLogProps) {
  // Sort entries: newest first
  const sorted = [...entries].sort((a, b) => {
    const ta = new Date(a.created).getTime();
    const tb = new Date(b.created).getTime();
    return tb - ta;
  });

  return (
    <div className="flex flex-col gap-3 w-full">
      {/* Header with filter and refresh */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Filter size={11} style={{ color: "#666" }} />
          <select
            className="bg-transparent text-muted-foreground border-none outline-none cursor-pointer"
            style={{
              fontSize: "0.65rem",
              background: "rgba(13,18,32,0.6)",
              padding: "2px 6px",
              borderRadius: "4px",
              border: "1px solid rgba(0,212,255,0.1)",
            }}
            value={agentFilter ?? ""}
            onChange={(e) =>
              onSetAgentFilter(e.target.value || null)
            }
          >
            <option value="">All agents</option>
            {agents.map((a) => (
              <option key={a} value={a}>
                {a}
              </option>
            ))}
          </select>
        </div>
        <motion.button
          className="p-1 rounded-md"
          style={{
            background: "rgba(0,212,255,0.06)",
            border: "1px solid rgba(0,212,255,0.1)",
          }}
          whileHover={{ background: "rgba(0,212,255,0.12)" }}
          whileTap={{ scale: 0.9 }}
          onClick={onRefresh}
          title="Refresh"
        >
          <RefreshCw size={11} style={{ color: "#00d4ff" }} />
        </motion.button>
      </div>

      {/* Entries */}
      {loading && entries.length === 0 ? (
        <div className="flex items-center justify-center py-8 text-muted-foreground gap-2">
          <Loader2 size={14} className="animate-spin" />
          <span style={{ fontSize: "0.7rem" }}>Loading history...</span>
        </div>
      ) : sorted.length === 0 ? (
        <div
          className="text-center text-muted-foreground py-8"
          style={{ fontSize: "0.7rem" }}
        >
          No executions today
        </div>
      ) : (
        <div className="space-y-1 w-full">
          {sorted.map((entry, i) => (
            <motion.div
              key={entry.id}
              className="w-full"
              initial={{ opacity: 0, y: 4 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: i * 0.02 }}
            >
              <EntryRow entry={entry} onFetchLog={onFetchLog} />
            </motion.div>
          ))}
        </div>
      )}
    </div>
  );
}
