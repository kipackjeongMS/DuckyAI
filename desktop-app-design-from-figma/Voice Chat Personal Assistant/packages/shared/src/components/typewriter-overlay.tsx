import { useEffect, useRef, useCallback, useState } from "react";
import { motion, AnimatePresence } from "motion/react";
import Markdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { Send } from "lucide-react";

export interface TypewriterEntry {
  id: string;
  role: "user" | "assistant";
  text: string;
}

interface TypewriterOverlayProps {
  entries: TypewriterEntry[];
  isProcessing?: boolean;
  onSendMessage?: (text: string) => void;
}

/** Shared markdown component config to avoid re-creating on every render. */
const markdownComponents = {
  p: ({ children }: { children?: React.ReactNode }) => <p className="mb-2 last:mb-0">{children}</p>,
  ul: ({ children }: { children?: React.ReactNode }) => <ul className="list-disc ml-4 mb-2">{children}</ul>,
  ol: ({ children }: { children?: React.ReactNode }) => <ol className="list-decimal ml-4 mb-2">{children}</ol>,
  li: ({ children }: { children?: React.ReactNode }) => <li className="mb-0.5">{children}</li>,
  h1: ({ children }: { children?: React.ReactNode }) => <h1 className="text-lg font-bold mb-2 text-[#00d4ff]">{children}</h1>,
  h2: ({ children }: { children?: React.ReactNode }) => <h2 className="text-base font-bold mb-1.5 text-[#00d4ff]">{children}</h2>,
  h3: ({ children }: { children?: React.ReactNode }) => <h3 className="text-sm font-semibold mb-1 text-[#00d4ff]">{children}</h3>,
  code: ({ children, className }: { children?: React.ReactNode; className?: string }) => {
    const isBlock = className?.includes("language-");
    return isBlock ? (
      <pre className="bg-[#0d1220] rounded-lg p-3 my-2 overflow-x-auto border border-[rgba(0,212,255,0.1)]">
        <code className="text-[0.85rem] text-[#a0b4d0]">{children}</code>
      </pre>
    ) : (
      <code className="bg-[#131b2e] text-[#00d4ff] px-1.5 py-0.5 rounded text-[0.85rem]">{children}</code>
    );
  },
  strong: ({ children }: { children?: React.ReactNode }) => <strong className="text-[#00d4ff] font-semibold">{children}</strong>,
  blockquote: ({ children }: { children?: React.ReactNode }) => (
    <blockquote className="border-l-2 border-[#00d4ff] pl-3 my-2 text-[#6b7fa3] italic">{children}</blockquote>
  ),
  a: ({ href, children }: { href?: string; children?: React.ReactNode }) => (
    <a href={href} className="text-[#00d4ff] underline hover:text-[#00ffa3]" target="_blank" rel="noopener noreferrer">{children}</a>
  ),
  table: ({ children }: { children?: React.ReactNode }) => (
    <div className="overflow-x-auto my-2">
      <table className="border-collapse text-[0.85rem]">{children}</table>
    </div>
  ),
  th: ({ children }: { children?: React.ReactNode }) => <th className="border border-[rgba(0,212,255,0.15)] px-2 py-1 text-[#00d4ff] text-left">{children}</th>,
  td: ({ children }: { children?: React.ReactNode }) => <td className="border border-[rgba(0,212,255,0.1)] px-2 py-1">{children}</td>,
};

/** A single chat bubble — renders markdown for assistant messages always. */
function ChatBubble({ entry }: { entry: TypewriterEntry }) {
  const isAssistant = entry.role === "assistant";

  return (
    <motion.div
      className={`flex flex-col ${isAssistant ? "items-start" : "items-end"} w-full`}
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3 }}
    >
      {/* Role label */}
      <span
        className={`mb-1.5 ${isAssistant ? "text-[#00d4ff]" : "text-[#6b7fa3]"}`}
        style={{
          fontSize: "0.6rem",
          letterSpacing: "0.15em",
          textTransform: "uppercase",
        }}
      >
        {isAssistant ? "DuckyAI" : "You"}
      </span>

      {/* Message content */}
      <div
        className={`leading-relaxed max-w-[90%] md:max-w-[80%] ${
          isAssistant ? "text-foreground" : "text-[#a0b4d0]"
        }`}
        style={{ fontSize: "0.95rem" }}
      >
        {isAssistant ? (
          <Markdown remarkPlugins={[remarkGfm]} components={markdownComponents}>
            {entry.text}
          </Markdown>
        ) : (
          <p style={{ fontSize: "0.95rem" }}>{entry.text}</p>
        )}
      </div>
    </motion.div>
  );
}

/** Animated thinking indicator (three bouncing dots). */
function ThinkingIndicator() {
  return (
    <motion.div
      className="flex flex-col items-start w-full"
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: -8 }}
      transition={{ duration: 0.25 }}
    >
      <span
        className="mb-1.5 text-[#00d4ff]"
        style={{
          fontSize: "0.6rem",
          letterSpacing: "0.15em",
          textTransform: "uppercase",
        }}
      >
        DuckyAI
      </span>
      <div className="flex items-center gap-1.5 py-1">
        {[0, 1, 2].map((i) => (
          <motion.span
            key={i}
            className="w-2 h-2 rounded-full bg-[#00d4ff]"
            animate={{
              opacity: [0.3, 1, 0.3],
              scale: [0.8, 1.1, 0.8],
            }}
            transition={{
              duration: 1.2,
              repeat: Infinity,
              delay: i * 0.2,
              ease: "easeInOut",
            }}
          />
        ))}
      </div>
    </motion.div>
  );
}

export function TypewriterOverlay({ entries, isProcessing, onSendMessage }: TypewriterOverlayProps) {
  const scrollRef = useRef<HTMLDivElement>(null);
  const bottomRef = useRef<HTMLDivElement>(null);
  const [inputText, setInputText] = useState("");
  const inputRef = useRef<HTMLInputElement>(null);

  // Auto-scroll to bottom on new entries or when processing state changes
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [entries, isProcessing]);

  // Focus input when overlay appears
  useEffect(() => {
    const t = setTimeout(() => inputRef.current?.focus(), 300);
    return () => clearTimeout(t);
  }, []);

  const handleSubmit = useCallback(
    (e: React.FormEvent) => {
      e.preventDefault();
      e.stopPropagation();
      const trimmed = inputText.trim();
      if (!trimmed || isProcessing) return;
      onSendMessage?.(trimmed);
      setInputText("");
    },
    [inputText, isProcessing, onSendMessage],
  );

  return (
    <div
      className="absolute inset-0 z-20 flex flex-col pointer-events-auto"
      onClick={(e) => e.stopPropagation()}
    >
      {/* Scrollable messages area */}
      <div
        ref={scrollRef}
        className="flex-1 overflow-y-auto px-6 md:px-16 lg:px-24 pt-6 pb-4 max-w-3xl mx-auto w-full"
        style={{ scrollbarWidth: "thin", scrollbarColor: "rgba(0,212,255,0.2) transparent" }}
      >
        <div className="flex flex-col gap-5 md:gap-6">
          <AnimatePresence mode="popLayout">
            {entries.map((entry) => (
              <ChatBubble key={entry.id} entry={entry} />
            ))}
          </AnimatePresence>

          {/* Thinking indicator */}
          <AnimatePresence>
            {isProcessing && <ThinkingIndicator />}
          </AnimatePresence>

          {/* Scroll anchor */}
          <div ref={bottomRef} />
        </div>
      </div>

      {/* Input bar */}
      <div className="px-6 md:px-16 lg:px-24 pb-5 pt-2 max-w-3xl mx-auto w-full">
        <form
          onSubmit={handleSubmit}
          className="flex items-center gap-3 bg-[#0d1220] border border-[rgba(0,212,255,0.12)] rounded-xl px-4 py-2.5 focus-within:border-[rgba(0,212,255,0.3)] transition-colors"
        >
          <input
            ref={inputRef}
            type="text"
            value={inputText}
            onChange={(e) => setInputText(e.target.value)}
            placeholder={isProcessing ? "DuckyAI is thinking..." : "Type a message..."}
            disabled={isProcessing}
            className="flex-1 bg-transparent text-foreground placeholder:text-[#3a4d6b] outline-none text-sm"
            style={{ fontSize: "0.9rem" }}
          />
          <button
            type="submit"
            disabled={!inputText.trim() || isProcessing}
            className="p-1.5 rounded-lg text-[#00d4ff] hover:bg-[rgba(0,212,255,0.1)] disabled:opacity-30 disabled:cursor-not-allowed transition-all"
          >
            <Send size={16} />
          </button>
        </form>
      </div>
    </div>
  );
}