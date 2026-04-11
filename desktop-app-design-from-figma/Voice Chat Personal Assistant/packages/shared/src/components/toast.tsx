import { useState, useEffect, useCallback } from "react";
import { motion, AnimatePresence } from "motion/react";
import { CheckCircle2, XCircle, Info, X } from "lucide-react";

export interface ToastItem {
  id: string;
  type: "success" | "error" | "info";
  title: string;
  body?: string;
}

const TOAST_DURATION = 5000;

const icons = {
  success: <CheckCircle2 size={16} className="text-[#00ffa3]" />,
  error: <XCircle size={16} className="text-[#ff4466]" />,
  info: <Info size={16} className="text-[#00d4ff]" />,
};

const borderColors = {
  success: "border-[rgba(0,255,163,0.3)]",
  error: "border-[rgba(255,68,102,0.3)]",
  info: "border-[rgba(0,212,255,0.3)]",
};

function Toast({ item, onDismiss }: { item: ToastItem; onDismiss: (id: string) => void }) {
  useEffect(() => {
    const t = setTimeout(() => onDismiss(item.id), TOAST_DURATION);
    return () => clearTimeout(t);
  }, [item.id, onDismiss]);

  return (
    <motion.div
      layout
      initial={{ opacity: 0, y: -20, scale: 0.95 }}
      animate={{ opacity: 1, y: 0, scale: 1 }}
      exit={{ opacity: 0, y: -10, scale: 0.95 }}
      transition={{ duration: 0.25 }}
      className={`flex items-start gap-3 bg-[#0d1220] border ${borderColors[item.type]} rounded-xl px-4 py-3 shadow-lg max-w-sm pointer-events-auto`}
    >
      <div className="mt-0.5 shrink-0">{icons[item.type]}</div>
      <div className="flex-1 min-w-0">
        <p className="text-foreground text-sm font-medium">{item.title}</p>
        {item.body && (
          <p className="text-muted-foreground text-xs mt-0.5 line-clamp-2">{item.body}</p>
        )}
      </div>
      <button
        onClick={() => onDismiss(item.id)}
        className="shrink-0 p-0.5 text-muted-foreground hover:text-foreground transition-colors"
      >
        <X size={14} />
      </button>
    </motion.div>
  );
}

export function useToasts() {
  const [toasts, setToasts] = useState<ToastItem[]>([]);

  const addToast = useCallback((toast: Omit<ToastItem, "id">) => {
    setToasts((prev) => [...prev, { ...toast, id: `toast-${Date.now()}` }]);
  }, []);

  const dismissToast = useCallback((id: string) => {
    setToasts((prev) => prev.filter((t) => t.id !== id));
  }, []);

  return { toasts, addToast, dismissToast };
}

export function ToastContainer({
  toasts,
  onDismiss,
}: {
  toasts: ToastItem[];
  onDismiss: (id: string) => void;
}) {
  return (
    <div className="fixed top-16 right-4 z-50 flex flex-col gap-2 pointer-events-none">
      <AnimatePresence mode="popLayout">
        {toasts.map((item) => (
          <Toast key={item.id} item={item} onDismiss={onDismiss} />
        ))}
      </AnimatePresence>
    </div>
  );
}
