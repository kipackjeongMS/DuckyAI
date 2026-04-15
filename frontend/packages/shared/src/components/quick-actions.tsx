import { motion } from "motion/react";
import { Calendar, CheckSquare, Inbox, Zap } from "lucide-react";

interface QuickAction {
  icon: React.ReactNode;
  label: string;
  id: string;
}

const actions: QuickAction[] = [
  { id: "daily-note", icon: <Calendar size={18} />, label: "Daily Note" },
  { id: "tasks", icon: <CheckSquare size={18} />, label: "Tasks" },
  { id: "triage", icon: <Inbox size={18} />, label: "Triage" },
  { id: "status", icon: <Zap size={18} />, label: "Status" },
];

interface QuickActionsProps {
  onAction: (id: string) => void;
  layout?: "horizontal" | "compact";
}

export function QuickActions({
  onAction,
  layout = "compact",
}: QuickActionsProps) {
  return (
    <div
      className={`flex gap-3 ${layout === "compact" ? "px-6" : "px-0 justify-center"}`}
    >
      {actions.map((action, i) => (
        <motion.button
          key={action.id}
          className={`flex flex-col items-center gap-1.5 py-3 rounded-xl bg-[#131b2e] border border-[rgba(0,212,255,0.08)] hover:border-[rgba(0,212,255,0.2)] active:bg-[#1a2332] transition-colors cursor-pointer ${
            layout === "compact" ? "flex-1" : "w-24 md:w-28"
          }`}
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: i * 0.08 }}
          onClick={() => onAction(action.id)}
          whileTap={{ scale: 0.95 }}
          whileHover={{ y: -2 }}
        >
          <span className="text-[#00d4ff] opacity-70">{action.icon}</span>
          <span
            className="text-muted-foreground"
            style={{ fontSize: "0.65rem", letterSpacing: "0.05em" }}
          >
            {action.label}
          </span>
        </motion.button>
      ))}
    </div>
  );
}