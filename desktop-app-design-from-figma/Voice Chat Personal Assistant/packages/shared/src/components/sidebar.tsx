import { motion, AnimatePresence } from "motion/react";
import {
  Clock,
  ChevronRight,
  Play,
  Pause,
  Zap,
  FileText,
  Loader2,
  Code2,
} from "lucide-react";
import type { Agent } from "../hooks/use-orchestrator";

type AgentStatus = "idle" | "running" | "offline" | "queued";

interface ConversationItem {
  id: string;
  title: string;
  time: string;
  preview: string;
}

// Placeholder until chat persistence is implemented
const recentConversations: ConversationItem[] = [];

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
  onToggleOrchestrator: () => void;
  onTriggerAgent: (abbreviation: string) => void;
  onOpenWorkspace?: () => void;
}

export function Sidebar({
  orchestratorRunning,
  agents,
  triggeringId,
  onToggleOrchestrator,
  onTriggerAgent,
  onOpenWorkspace,
}: SidebarProps) {

  const runningCount = agents.filter((a) => a.status === "running").length;
  const queuedCount = agents.filter((a) => a.status === "queued").length;

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
          <motion.button
            className="flex items-center gap-1.5 px-2.5 py-1 rounded-md transition-colors"
            style={{
              fontSize: "0.65rem",
              letterSpacing: "0.05em",
              background: orchestratorRunning
                ? "rgba(0,255,163,0.08)"
                : "rgba(255,68,102,0.08)",
              border: `1px solid ${orchestratorRunning ? "rgba(0,255,163,0.2)" : "rgba(255,68,102,0.2)"}`,
              color: orchestratorRunning ? "#00ffa3" : "#ff4466",
            }}
            whileTap={{ scale: 0.95 }}
            onClick={onToggleOrchestrator}
          >
            {orchestratorRunning ? <Pause size={10} /> : <Play size={10} />}
            {orchestratorRunning ? "Running" : "Stopped"}
          </motion.button>
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
        </div>

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

      {/* Recent Conversations */}
      <div className="flex-1">
        <h3
          className="text-muted-foreground mb-4"
          style={{
            fontSize: "0.65rem",
            letterSpacing: "0.2em",
            textTransform: "uppercase",
          }}
        >
          Recent Conversations
        </h3>
        <div className="space-y-2">
          {recentConversations.map((conv, i) => (
            <motion.button
              key={conv.id}
              className="w-full text-left p-3 rounded-lg bg-[#0d1220] border border-[rgba(0,212,255,0.05)] hover:border-[rgba(0,212,255,0.15)] transition-colors group"
              initial={{ opacity: 0, x: -10 }}
              animate={{ opacity: 1, x: 0 }}
              transition={{ delay: i * 0.06 }}
              whileHover={{ x: 2 }}
            >
              <div className="flex items-center justify-between mb-1">
                <span
                  className="text-foreground"
                  style={{ fontSize: "0.8rem" }}
                >
                  {conv.title}
                </span>
                <ChevronRight
                  size={12}
                  className="text-muted-foreground opacity-0 group-hover:opacity-100 transition-opacity"
                />
              </div>
              <div className="flex items-center gap-2 mb-1.5">
                <Clock size={10} className="text-muted-foreground" />
                <span
                  className="text-muted-foreground"
                  style={{ fontSize: "0.65rem" }}
                >
                  {conv.time}
                </span>
              </div>
              <p
                className="text-muted-foreground truncate"
                style={{ fontSize: "0.72rem" }}
              >
                {conv.preview}
              </p>
            </motion.button>
          ))}
        </div>
      </div>

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
    </div>
  );
}
