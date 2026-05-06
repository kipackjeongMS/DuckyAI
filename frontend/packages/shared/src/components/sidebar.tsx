import { motion, AnimatePresence } from "motion/react";
import { useMemo, useState } from "react";
import {
  Play,
  Pause,
  Zap,
  FileText,
  Loader2,
  Code2,
  Activity,
  RotateCcw,
  Settings,
} from "lucide-react";
import type { Agent } from "../hooks/use-orchestrator";
import type { ExecutionEntry, ExecutionLogDetail, TokenUsage } from "../types/duckyai";
import { AgentActivityLog } from "./agent-activity-log";
import { AgentSettingsModal } from "./agent-settings-modal";
import { DefaultModelModal } from "./default-model-modal";

type AgentStatus = "idle" | "running" | "offline" | "queued";

const agentStatusColors: Record<AgentStatus, string> = {
  idle: "#00d4ff",
  running: "#00ffa3",
  offline: "#ff4466",
  queued: "#ffbe0b",
};

const agentStatusLabels: Record<AgentStatus, string> = {
  idle: "Idle",
  running: "Running",
  offline: "Offline",
  queued: "Queued",
};

export interface SidebarProps {
  orchestratorRunning: boolean;
  agents: Agent[];
  triggeringId: string | null;
  toggling?: boolean;
  restarting?: boolean;
  onToggleOrchestrator: () => void;
  onTriggerAgent: (abbreviation: string) => void;
  onRestartDaemon?: () => void;
  onOpenWorkspace?: () => void;
  // Talk with Ducky button (unused — kept for external consumers)
  onTalkWithDucky?: () => void;
  // Agent settings
  onGetAgentModel?: (abbreviation: string) => Promise<string | null>;
  onSaveAgentModel?: (abbreviation: string, model: string | null) => Promise<void>;
  // Default model settings
  onGetDefaultModel?: () => Promise<string | null>;
  onSaveDefaultModel?: (model: string | null) => Promise<void>;
  // Activity log
  activityEntries?: ExecutionEntry[];
  activityLoading?: boolean;
  activityAgentFilter?: string | null;
  onActivityFilterChange?: (agent: string | null) => void;
  onActivityRefresh?: () => void;
  onFetchLog?: (id: string, date?: string) => Promise<ExecutionLogDetail>;
}

export function Sidebar({
  orchestratorRunning,
  agents,
  triggeringId,
  toggling,
  restarting,
  onToggleOrchestrator,
  onTriggerAgent,
  onRestartDaemon,
  onOpenWorkspace,
  onTalkWithDucky,
  onGetAgentModel,
  onSaveAgentModel,
  onGetDefaultModel,
  onSaveDefaultModel,
  activityEntries,
  activityLoading,
  activityAgentFilter,
  onActivityFilterChange,
  onActivityRefresh,
  onFetchLog,
}: SidebarProps) {
  const [settingsAgent, setSettingsAgent] = useState<{ abbreviation: string; name: string } | null>(null);
  const [settingsCurrentModel, setSettingsCurrentModel] = useState<string | null>(null);
  const [defaultModelOpen, setDefaultModelOpen] = useState(false);
  const [defaultCurrentModel, setDefaultCurrentModel] = useState<string | null>(null);

  const runningCount = agents.filter((a) => a.status === "running").length;
  const queuedCount = agents.filter((a) => a.status === "queued").length;

  // Aggregate token usage from today's activity entries
  const tokenSummary = useMemo(() => {
    if (!activityEntries?.length) return null;
    const byAgent: Record<string, { input: number; output: number; requests: number }> = {};
    let totalIn = 0, totalOut = 0, totalReqs = 0;
    for (const entry of activityEntries) {
      const u = entry.token_usage;
      if (!u) continue;
      const inp = u.input_tokens || 0;
      const out = u.output_tokens || 0;
      totalIn += inp;
      totalOut += out;
      totalReqs += u.requests || 0;
      const agent = entry.agent || "?";
      if (!byAgent[agent]) byAgent[agent] = { input: 0, output: 0, requests: 0 };
      byAgent[agent].input += inp;
      byAgent[agent].output += out;
      byAgent[agent].requests += (u.requests || 0);
    }
    if (totalIn + totalOut === 0) return null;
    return { totalIn, totalOut, totalReqs, byAgent };
  }, [activityEntries]);

  return (
    <div className="h-full flex flex-col py-6 px-5 overflow-y-auto">
      {/* Orchestrator Status */}
      <div className="mb-6">
        <div className="flex items-center justify-between mb-4">
          <h3
            className="text-muted-foreground"
            style={{
              fontSize: "0.65rem",
              letterSpacing: "0.2em",
              textTransform: "uppercase",
            }}
          >
            Orchestrator
          </h3>
          <div className="flex items-center gap-1.5">
            <motion.button
              className="flex items-center gap-1.5 px-2.5 py-1 rounded-md transition-colors"
              style={{
                fontSize: "0.65rem",
                letterSpacing: "0.05em",
                background: orchestratorRunning
                  ? "rgba(0,255,163,0.08)"
                  : toggling
                    ? "rgba(255,190,11,0.08)"
                    : "rgba(255,68,102,0.08)",
                border: `1px solid ${orchestratorRunning ? "rgba(0,255,163,0.2)" : toggling ? "rgba(255,190,11,0.2)" : "rgba(255,68,102,0.2)"}`,
                color: orchestratorRunning ? "#00ffa3" : toggling ? "#ffbe0b" : "#ff4466",
              }}
              whileTap={{ scale: 0.95 }}
              onClick={onToggleOrchestrator}
              disabled={!!toggling}
            >
              {toggling && !orchestratorRunning ? (
                <Loader2 size={10} className="animate-spin" />
              ) : orchestratorRunning ? (
                <Pause size={10} />
              ) : (
                <Play size={10} />
              )}
              {toggling && !orchestratorRunning
                ? "Starting..."
                : toggling && orchestratorRunning
                  ? "Stopping..."
                  : orchestratorRunning
                    ? "Running"
                    : "Stopped"}
            </motion.button>
            {onRestartDaemon && (
              <motion.button
                className="p-1 rounded-md transition-colors"
                style={{
                  background: "rgba(0,212,255,0.06)",
                  border: "1px solid rgba(0,212,255,0.12)",
                  color: restarting ? "#ffbe0b" : "#00d4ff",
                }}
                whileHover={{ background: "rgba(0,212,255,0.14)" }}
                whileTap={{ scale: 0.9 }}
                onClick={onRestartDaemon}
                title="Restart daemon (picks up code changes)"
              >
                {restarting ? (
                  <Loader2 size={12} className="animate-spin" />
                ) : (
                  <RotateCcw size={12} />
                )}
              </motion.button>
            )}
          </div>
        </div>

        {/* Orchestrator summary bar */}
        <div
          className="flex items-center gap-3 px-3 py-2.5 rounded-lg mb-3"
          style={{
            background: "rgba(13,18,32,0.8)",
            border: "1px solid rgba(0,212,255,0.05)",
          }}
        >
          <div className="flex items-center gap-1.5">
            <motion.div
              className="w-2 h-2 rounded-full"
              style={{
                backgroundColor: orchestratorRunning ? "#00ffa3" : "#ff4466",
                boxShadow: `0 0 6px ${orchestratorRunning ? "#00ffa3" : "#ff4466"}`,
              }}
              animate={
                orchestratorRunning
                  ? { opacity: [1, 0.4, 1] }
                  : { opacity: 1 }
              }
              transition={{
                duration: 2,
                repeat: Infinity,
                ease: "easeInOut",
              }}
            />
            <span
              className="text-muted-foreground"
              style={{ fontSize: "0.7rem" }}
            >
              Core
            </span>
          </div>
          <div
            className="w-px h-3"
            style={{ background: "rgba(0,212,255,0.1)" }}
          />
          <div className="flex items-center gap-3">
            <span style={{ fontSize: "0.68rem", color: "#00ffa3" }}>
              {runningCount} active
            </span>
            {queuedCount > 0 && (
              <span style={{ fontSize: "0.68rem", color: "#ffbe0b" }}>
                {queuedCount} queued
              </span>
            )}
            <span style={{ fontSize: "0.68rem", color: "#00d4ff" }}>
              {agents.filter((a) => a.status === "idle").length} idle
            </span>
          </div>
          {/* Default model settings button */}
          <motion.button
            className="shrink-0 ml-auto p-1.5 rounded-md transition-colors"
            style={{
              background: "rgba(255,255,255,0.02)",
              border: "1px solid rgba(255,255,255,0.06)",
            }}
            whileHover={{
              background: "rgba(255,255,255,0.06)",
              borderColor: "rgba(255,255,255,0.12)",
            }}
            whileTap={{ scale: 0.9 }}
            title="Default model settings"
            onClick={async () => {
              if (onGetDefaultModel) {
                const model = await onGetDefaultModel();
                setDefaultCurrentModel(model);
              }
              setDefaultModelOpen(true);
            }}
          >
            <Settings size={10} style={{ color: "#888" }} />
          </motion.button>
        </div>

        {/* Token usage summary */}
        {tokenSummary && (
          <div
            className="flex flex-col gap-1.5 px-3 py-2 rounded-lg mb-3"
            style={{
              background: "rgba(13,18,32,0.6)",
              border: "1px solid rgba(0,212,255,0.05)",
            }}
          >
            <div className="flex items-center justify-between">
              <span className="text-muted-foreground" style={{ fontSize: "0.6rem", letterSpacing: "0.1em", textTransform: "uppercase" }}>
                Today&apos;s Tokens
              </span>
              <span style={{ fontSize: "0.65rem", color: "#00d4ff" }}>
                {((tokenSummary.totalIn + tokenSummary.totalOut) / 1000).toFixed(1)}K
                <span className="text-muted-foreground" style={{ fontSize: "0.58rem" }}> ({tokenSummary.totalReqs} calls)</span>
              </span>
            </div>
            {/* Stacked bar */}
            <div className="flex rounded-full overflow-hidden" style={{ height: 4 }}>
              {Object.entries(tokenSummary.byAgent).map(([agent, data], i) => {
                const total = tokenSummary.totalIn + tokenSummary.totalOut;
                const pct = total > 0 ? ((data.input + data.output) / total) * 100 : 0;
                const colors = ["#00d4ff", "#00ffa3", "#ffbe0b", "#ff4466", "#a78bfa", "#f472b6"];
                return (
                  <div
                    key={agent}
                    title={`${agent}: ${((data.input + data.output) / 1000).toFixed(1)}K tokens`}
                    style={{
                      width: `${pct}%`,
                      backgroundColor: colors[i % colors.length],
                      opacity: 0.7,
                      minWidth: pct > 0 ? 2 : 0,
                    }}
                  />
                );
              })}
            </div>
            {/* Agent breakdown */}
            <div className="flex flex-wrap gap-x-3 gap-y-0.5">
              {Object.entries(tokenSummary.byAgent).map(([agent, data], i) => {
                const colors = ["#00d4ff", "#00ffa3", "#ffbe0b", "#ff4466", "#a78bfa", "#f472b6"];
                return (
                  <span key={agent} style={{ fontSize: "0.58rem", color: colors[i % colors.length], opacity: 0.8 }}>
                    {agent} {((data.input + data.output) / 1000).toFixed(1)}K
                  </span>
                );
              })}
            </div>
          </div>
        )}

        {/* Agent list */}
        <div className="space-y-1.5">
          {agents.map((agent, i) => {
            const color = agentStatusColors[agent.status];
            const isTriggerable =
              orchestratorRunning &&
              agent.status !== "running" &&
              agent.status !== "offline" &&
              triggeringId !== agent.id;

            return (
              <motion.div
                key={agent.id}
                className="group relative px-3 py-2.5 rounded-lg"
                style={{
                  background: "rgba(13,18,32,0.6)",
                  border: `1px solid ${agent.status === "running" ? `${color}20` : "rgba(0,212,255,0.04)"}`,
                }}
                initial={{ opacity: 0, x: -8 }}
                animate={{ opacity: 1, x: 0 }}
                transition={{ delay: i * 0.04 }}
              >
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2 min-w-0 flex-1">
                    <span
                      className="shrink-0"
                      style={{ color: color, opacity: 0.8 }}
                    >
                      <FileText size={13} />
                    </span>
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center gap-2">
                        <span
                          className="text-foreground truncate"
                          style={{ fontSize: "0.76rem" }}
                        >
                          {agent.name}
                        </span>
                        <div className="flex items-center gap-1 shrink-0">
                          {agent.status === "running" ? (
                            <motion.div
                              className="w-1.5 h-1.5 rounded-full"
                              style={{
                                backgroundColor: color,
                                boxShadow: `0 0 4px ${color}`,
                              }}
                              animate={{ opacity: [1, 0.3, 1] }}
                              transition={{
                                duration: 1,
                                repeat: Infinity,
                                ease: "easeInOut",
                              }}
                            />
                          ) : (
                            <div
                              className="w-1.5 h-1.5 rounded-full"
                              style={{
                                backgroundColor: color,
                                boxShadow: `0 0 3px ${color}`,
                                opacity: 0.7,
                              }}
                            />
                          )}
                          <span
                            style={{
                              fontSize: "0.6rem",
                              color: color,
                              opacity: 0.8,
                            }}
                          >
                            {agentStatusLabels[agent.status]}
                          </span>
                        </div>
                      </div>
                      <p
                        className="text-muted-foreground truncate mt-0.5"
                        style={{ fontSize: "0.62rem", opacity: 0.6 }}
                      >
                        {agent.cron ? `Cron: ${agent.cron}` : "File trigger"}
                      </p>
                    </div>
                  </div>

                  {/* Trigger button */}
                  <AnimatePresence>
                    {isTriggerable && (
                      <motion.button
                        className="shrink-0 ml-2 p-1.5 rounded-md transition-colors"
                        style={{
                          background: "rgba(0,212,255,0.06)",
                          border: "1px solid rgba(0,212,255,0.12)",
                        }}
                        initial={{ opacity: 0, scale: 0.8 }}
                        animate={{ opacity: 1, scale: 1 }}
                        exit={{ opacity: 0, scale: 0.8 }}
                        whileHover={{
                          background: "rgba(0,212,255,0.14)",
                          borderColor: "rgba(0,212,255,0.3)",
                        }}
                        whileTap={{ scale: 0.9 }}
                        onClick={() => onTriggerAgent(agent.id)}
                        title={`Trigger ${agent.name}`}
                      >
                        <Zap size={11} style={{ color: "#00d4ff" }} />
                      </motion.button>
                    )}
                  </AnimatePresence>
                  {/* Settings gear */}
                  {onGetAgentModel && onSaveAgentModel && (
                    <motion.button
                      className="shrink-0 ml-1 p-1.5 rounded-md transition-colors"
                      style={{
                        background: "rgba(255,255,255,0.02)",
                        border: "1px solid rgba(255,255,255,0.06)",
                      }}
                      whileHover={{
                        background: "rgba(255,255,255,0.06)",
                        borderColor: "rgba(255,255,255,0.12)",
                      }}
                      whileTap={{ scale: 0.9 }}
                      onClick={async () => {
                        const model = await onGetAgentModel(agent.id);
                        setSettingsCurrentModel(model);
                        setSettingsAgent({ abbreviation: agent.id, name: agent.name });
                      }}
                      title={`${agent.name} settings`}
                    >
                      <Settings size={10} style={{ color: "#888" }} />
                    </motion.button>
                  )}
                  {triggeringId === agent.id && (
                    <motion.div
                      className="shrink-0 ml-2 p-1.5"
                      animate={{ rotate: 360 }}
                      transition={{
                        duration: 1,
                        repeat: Infinity,
                        ease: "linear",
                      }}
                    >
                      <Loader2 size={11} style={{ color: "#ffbe0b" }} />
                    </motion.div>
                  )}
                </div>
              </motion.div>
            );
          })}
        </div>
      </div>

      {/* Recent Activity */}
      {activityEntries !== undefined && onActivityRefresh && onFetchLog && (
        <div className="mb-6">
          <div className="flex items-center gap-1.5 mb-3">
            <Activity size={11} style={{ color: "#666" }} />
            <h3
              className="text-muted-foreground"
              style={{
                fontSize: "0.65rem",
                letterSpacing: "0.2em",
                textTransform: "uppercase",
              }}
            >
              Activity Log
            </h3>
          </div>
          <AgentActivityLog
            entries={activityEntries}
            loading={activityLoading ?? false}
            agentFilter={activityAgentFilter ?? null}
            agents={agents.map((a) => a.id)}
            onSetAgentFilter={onActivityFilterChange ?? (() => {})}
            onRefresh={onActivityRefresh}
            onFetchLog={onFetchLog}
          />
        </div>
      )}

      {/* Quick Actions */}
      {onOpenWorkspace && (
        <div className="mt-4 mb-2">
          <motion.button
            className="w-full flex items-center gap-2.5 px-3 py-2.5 rounded-lg transition-colors"
            style={{
              background: "rgba(0,212,255,0.06)",
              border: "1px solid rgba(0,212,255,0.1)",
            }}
            whileHover={{
              background: "rgba(0,212,255,0.12)",
              borderColor: "rgba(0,212,255,0.25)",
            }}
            whileTap={{ scale: 0.98 }}
            onClick={onOpenWorkspace}
          >
            <Code2 size={14} style={{ color: "#00d4ff" }} />
            <span
              className="text-foreground"
              style={{ fontSize: "0.76rem" }}
            >
              Open Code Workspace
            </span>
          </motion.button>
        </div>
      )}

      {/* Bottom status */}
      <div className="mt-6 pt-4 border-t border-[rgba(0,212,255,0.06)]">
        <div className="flex items-center gap-2">
          <div
            className="w-1.5 h-1.5 rounded-full"
            style={{
              backgroundColor: orchestratorRunning ? "#00ffa3" : "#ff4466",
              boxShadow: `0 0 4px ${orchestratorRunning ? "#00ffa3" : "#ff4466"}`,
            }}
          />
          <span
            className="text-muted-foreground"
            style={{ fontSize: "0.7rem" }}
          >
            {orchestratorRunning
              ? "All systems operational"
              : "Orchestrator paused"}
          </span>
        </div>
      </div>

      {/* Agent Settings Modal */}
      {settingsAgent && (
        <AgentSettingsModal
          agentName={settingsAgent.name}
          agentAbbreviation={settingsAgent.abbreviation}
          currentModel={settingsCurrentModel}
          onSave={async (model) => {
            if (onSaveAgentModel) {
              await onSaveAgentModel(settingsAgent.abbreviation, model);
            }
            setSettingsAgent(null);
          }}
          onClose={() => setSettingsAgent(null)}
        />
      )}

      {/* Default Model Settings Modal */}
      {defaultModelOpen && (
        <DefaultModelModal
          currentModel={defaultCurrentModel}
          onSave={async (model) => {
            if (onSaveDefaultModel) {
              await onSaveDefaultModel(model);
            }
            setDefaultModelOpen(false);
          }}
          onClose={() => setDefaultModelOpen(false)}
        />
      )}
    </div>
  );
}
