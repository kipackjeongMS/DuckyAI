import { useState, useRef, useEffect, useCallback } from "react";
import { motion, AnimatePresence } from "motion/react";
import { Send, Loader2, Bot, User, Trash2 } from "lucide-react";

interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  text: string;
  timestamp: number;
}

export interface ChatPanelProps {
  onSend: (text: string) => Promise<string>;
}

export function ChatPanel({ onSend }: ChatPanelProps) {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [sending, setSending] = useState(false);
  const scrollRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [messages]);

  const handleSend = useCallback(async () => {
    const text = input.trim();
    if (!text || sending) return;

    const userMsg: ChatMessage = {
      id: `user-${Date.now()}`,
      role: "user",
      text,
      timestamp: Date.now(),
    };
    setMessages((prev) => [...prev, userMsg]);
    setInput("");
    setSending(true);

    try {
      const response = await onSend(text);
      const assistantMsg: ChatMessage = {
        id: `assistant-${Date.now()}`,
        role: "assistant",
        text: response,
        timestamp: Date.now(),
      };
      setMessages((prev) => [...prev, assistantMsg]);
    } catch (err) {
      const errMsg: ChatMessage = {
        id: `error-${Date.now()}`,
        role: "assistant",
        text: `Error: ${err instanceof Error ? err.message : String(err)}`,
        timestamp: Date.now(),
      };
      setMessages((prev) => [...prev, errMsg]);
    } finally {
      setSending(false);
      inputRef.current?.focus();
    }
  }, [input, sending, onSend]);

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault();
        handleSend();
      }
    },
    [handleSend],
  );

  const clearChat = useCallback(() => {
    setMessages([]);
  }, []);

  return (
    <div className="flex flex-col" style={{ height: "320px" }}>
      {/* Header */}
      <div className="flex items-center justify-between mb-2">
        <h3
          className="text-muted-foreground"
          style={{
            fontSize: "0.65rem",
            letterSpacing: "0.2em",
            textTransform: "uppercase",
          }}
        >
          Chat
        </h3>
        {messages.length > 0 && (
          <motion.button
            className="p-1 rounded-md transition-colors"
            style={{
              background: "rgba(255,68,102,0.06)",
              border: "1px solid rgba(255,68,102,0.12)",
              color: "#ff4466",
            }}
            whileHover={{ background: "rgba(255,68,102,0.14)" }}
            whileTap={{ scale: 0.9 }}
            onClick={clearChat}
            title="Clear chat"
          >
            <Trash2 size={10} />
          </motion.button>
        )}
      </div>

      {/* Messages area */}
      <div
        ref={scrollRef}
        className="flex-1 overflow-y-auto space-y-2 mb-2"
        style={{
          minHeight: 0,
          scrollbarWidth: "thin",
          scrollbarColor: "rgba(0,212,255,0.15) transparent",
        }}
      >
        {messages.length === 0 && (
          <div
            className="flex items-center justify-center h-full text-muted-foreground"
            style={{ fontSize: "0.68rem", opacity: 0.5 }}
          >
            Ask DuckyAI anything...
          </div>
        )}
        <AnimatePresence initial={false}>
          {messages.map((msg) => (
            <motion.div
              key={msg.id}
              className="flex gap-2"
              initial={{ opacity: 0, y: 6 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.2 }}
            >
              <div className="shrink-0 mt-0.5">
                {msg.role === "user" ? (
                  <User size={12} style={{ color: "#64748b" }} />
                ) : (
                  <Bot size={12} style={{ color: "#00d4ff" }} />
                )}
              </div>
              <div
                className="flex-1 rounded-lg px-2.5 py-1.5"
                style={{
                  background:
                    msg.role === "user"
                      ? "rgba(100,116,139,0.1)"
                      : "rgba(0,212,255,0.06)",
                  border: `1px solid ${msg.role === "user" ? "rgba(100,116,139,0.12)" : "rgba(0,212,255,0.08)"}`,
                  fontSize: "0.72rem",
                  lineHeight: 1.5,
                  color: msg.role === "user" ? "#cbd5e1" : "#e2e8f0",
                  whiteSpace: "pre-wrap",
                  wordBreak: "break-word",
                }}
              >
                {msg.text}
              </div>
            </motion.div>
          ))}
        </AnimatePresence>
        {sending && (
          <motion.div
            className="flex gap-2 items-center"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
          >
            <Bot size={12} style={{ color: "#00d4ff" }} />
            <div className="flex items-center gap-1.5" style={{ fontSize: "0.68rem", color: "#64748b" }}>
              <Loader2 size={10} className="animate-spin" />
              Thinking...
            </div>
          </motion.div>
        )}
      </div>

      {/* Input area */}
      <div
        className="flex items-end gap-1.5 rounded-lg"
        style={{
          background: "rgba(13,18,32,0.8)",
          border: "1px solid rgba(0,212,255,0.08)",
          padding: "6px",
        }}
      >
        <textarea
          ref={inputRef}
          className="flex-1 bg-transparent text-foreground resize-none outline-none placeholder:text-muted-foreground"
          style={{
            fontSize: "0.72rem",
            lineHeight: 1.5,
            minHeight: "1.5rem",
            maxHeight: "4.5rem",
            padding: "2px 4px",
          }}
          rows={1}
          placeholder="Message DuckyAI..."
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={handleKeyDown}
          disabled={sending}
        />
        <motion.button
          className="shrink-0 p-1.5 rounded-md transition-colors"
          style={{
            background: input.trim()
              ? "rgba(0,212,255,0.15)"
              : "rgba(0,212,255,0.04)",
            border: `1px solid ${input.trim() ? "rgba(0,212,255,0.3)" : "rgba(0,212,255,0.08)"}`,
            color: input.trim() ? "#00d4ff" : "#334155",
          }}
          whileHover={input.trim() ? { background: "rgba(0,212,255,0.25)" } : {}}
          whileTap={input.trim() ? { scale: 0.9 } : {}}
          onClick={handleSend}
          disabled={!input.trim() || sending}
        >
          {sending ? (
            <Loader2 size={12} className="animate-spin" />
          ) : (
            <Send size={12} />
          )}
        </motion.button>
      </div>
    </div>
  );
}
