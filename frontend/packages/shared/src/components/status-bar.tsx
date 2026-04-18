import { motion } from "motion/react";
import { Wifi, Battery, Signal } from "lucide-react";

export function StatusBar() {
  return (
    <div className="flex items-center justify-between px-5 py-2 md:hidden">
      <span
        className="text-muted-foreground"
        style={{ fontSize: "0.75rem" }}
      >
        {new Date().toLocaleTimeString([], {
          hour: "2-digit",
          minute: "2-digit",
        })}
      </span>
      <div className="flex items-center gap-1.5 text-muted-foreground">
        <Signal size={12} />
        <Wifi size={12} />
        <Battery size={12} />
      </div>
    </div>
  );
}

interface StatusIndicatorProps {
  status: "idle" | "listening" | "processing" | "speaking";
}

export function StatusIndicator({ status }: StatusIndicatorProps) {
  const labels: Record<string, string> = {
    idle: "Standing by",
    listening: "Listening...",
    processing: "Processing...",
    speaking: "Speaking...",
  };

  const colors: Record<string, string> = {
    idle: "#6b7fa3",
    listening: "#00d4ff",
    processing: "#7b61ff",
    speaking: "#00ffa3",
  };

  return (
    <motion.div
      className="flex items-center gap-2"
      animate={{ opacity: [0.7, 1, 0.7] }}
      transition={{ duration: 2, repeat: Infinity }}
    >
      <div
        className="w-1.5 h-1.5 rounded-full"
        style={{
          backgroundColor: colors[status],
          boxShadow: `0 0 6px ${colors[status]}`,
        }}
      />
      <span
        style={{
          fontSize: "0.75rem",
          letterSpacing: "0.15em",
          textTransform: "uppercase",
          color: colors[status],
        }}
      >
        {labels[status]}
      </span>
    </motion.div>
  );
}
