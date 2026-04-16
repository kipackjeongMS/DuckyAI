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
  onFetchLog: (id: string) => Promise<ExecutionLogDetail>;
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
    if (!expanded && logContent === null && entry.log_path) {
      setLogLoading(true);
      setLogError(null);
      try {
        const detail = await onFetchLog(entry.id);
        setLogContent(detail.content);
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
    <div>
      <motion.button
        className="w-full text-left px-3 py-2.5 rounded-lg transition-colors"
        style={{
          background: expanded
            ? "rgba(13,18,32,0.9)"
            : "rgba(13,18,32,0.6)",
          border: `1px solid ${expanded ? `${info.color}20` : "rgba(0,212,255,0.04)"}`,
        }}
        onClick={handleExpand}
        whileHover={{ background: "rgba(13,18,32,0.8)" }}
      >
        <div className="flex items-center gap-2">
          {/* Expand chevron */}
          <span style={{ color: "#666" }}>
            {expanded ? (
              <ChevronDown size={12} />
            ) : (
              <ChevronRight size={12} />
            )}
          </span>

          {/* Status icon */}
          <span style={{ color: info.color }}>
            {entry.status === "IN_PROGRESS" ? (
              <motion.span
                animate={{ rotate: 360 }}
                transition={{
                  duration: 1,
                  repeat: Infinity,
                  ease: "linear",
                }}
                style={{ display: "inline-block" }}
              >
                <StatusIcon size={13} />
              </motion.span>
            ) : (
              <StatusIcon size={13} />
            )}
          </span>

          {/* Agent name */}
          <span
            className="text-foreground font-medium"
            style={{ fontSize: "0.74rem", minWidth: "2.5rem" }}
          >
            {entry.agent}
          </span>

          {/* Time */}
          <span
            className="text-muted-foreground"
            style={{ fontSize: "0.62rem" }}
          >
            {time}
          </span>

          {/* Duration */}
          {duration && (
            <span
              className="text-muted-foreground"
              style={{ fontSize: "0.6rem", opacity: 0.7 }}
            >
              {duration}
            </span>
          )}

          {/* Spacer */}
          <div className="flex-1" />

          {/* Status label */}
          <span
            style={{
              fontSize: "0.58rem",
              color: info.color,
              opacity: 0.8,
              textTransform: "uppercase",
              letterSpacing: "0.05em",
            }}
          >
            {info.label}
          </span>
        </div>

        {/* Input/output summary */}
        {(entry.input_path || entry.output || entry.error) && (
          <div
            className="mt-1 ml-7 flex flex-wrap gap-x-3"
            style={{ fontSize: "0.6rem" }}
          >
            {entry.input_path && (
              <span className="text-muted-foreground truncate max-w-[180px]">
                in: {entry.input_path.split("/").pop()}
              </span>
            )}
            {entry.output && (
              <span
                className="truncate max-w-[180px]"
                style={{ color: "#00d4ff", opacity: 0.7 }}
              >
                {entry.output}
              </span>
            )}
            {entry.error && (
              <span
                className="truncate max-w-[200px]"
                style={{ color: "#ff4466", opacity: 0.8 }}
              >
                {entry.error}
              </span>
            )}
          </div>
        )}
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
              {!logLoading && !logError && !logContent && !entry.log_path && (
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
  onFetchLog: (id: string) => Promise<ExecutionLogDetail>;
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
    <div className="flex flex-col gap-3">
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
        <div className="space-y-1">
          {sorted.map((entry, i) => (
            <motion.div
              key={entry.id}
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
