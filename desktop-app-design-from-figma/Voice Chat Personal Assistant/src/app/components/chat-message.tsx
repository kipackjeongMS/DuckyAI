import { motion } from "motion/react";
import Markdown from "react-markdown";
import remarkGfm from "remark-gfm";

export interface Message {
  id: string;
  role: "user" | "assistant";
  text: string;
  timestamp: Date;
}

interface ChatMessageProps {
  message: Message;
  index: number;
}

export function ChatMessage({ message, index }: ChatMessageProps) {
  const isAssistant = message.role === "assistant";

  return (
    <motion.div
      className={`flex ${isAssistant ? "justify-start" : "justify-end"} mb-3`}
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3, delay: index * 0.05 }}
    >
      <div
        className={`max-w-[85%] px-4 py-2.5 rounded-2xl ${
          isAssistant
            ? "bg-[#131b2e] border border-[rgba(0,212,255,0.08)] text-foreground"
            : "bg-[#00d4ff15] border border-[rgba(0,212,255,0.15)] text-foreground"
        }`}
      >
        {isAssistant && (
          <span className="text-[#00d4ff] opacity-60 block mb-0.5" style={{ fontSize: "0.65rem", letterSpacing: "0.1em", textTransform: "uppercase" }}>
            DuckyAI
          </span>
        )}
        {isAssistant ? (
          <div className="leading-relaxed prose-sm" style={{ fontSize: "0.9rem" }}>
            <Markdown remarkPlugins={[remarkGfm]}>{message.text}</Markdown>
          </div>
        ) : (
          <p className="leading-relaxed" style={{ fontSize: "0.9rem" }}>{message.text}</p>
        )}
        <span className="text-muted-foreground block mt-1" style={{ fontSize: "0.65rem" }}>
          {message.timestamp.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}
        </span>
      </div>
    </motion.div>
  );
}
