import { useState } from "react";
import { motion, AnimatePresence } from "motion/react";
import { X, Check, Settings } from "lucide-react";
import { AVAILABLE_MODELS } from "../utils/duckyai-yaml";

export interface DefaultModelModalProps {
  currentModel: string | null;
  onSave: (model: string | null) => void;
  onClose: () => void;
}

export function DefaultModelModal({
  currentModel,
  onSave,
  onClose,
}: DefaultModelModalProps) {
  const [selectedModel, setSelectedModel] = useState<string>(currentModel || "");
  const [saving, setSaving] = useState(false);

  const handleSave = async () => {
    setSaving(true);
    try {
      onSave(selectedModel || null);
    } finally {
      setSaving(false);
    }
  };

  return (
    <AnimatePresence>
      <motion.div
        className="fixed inset-0 z-50 flex items-center justify-center"
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        exit={{ opacity: 0 }}
      >
        <motion.div
          className="absolute inset-0"
          style={{ background: "rgba(0,0,0,0.6)", backdropFilter: "blur(4px)" }}
          onClick={onClose}
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
        />

        <motion.div
          className="relative rounded-xl p-5 w-[340px] max-w-[90vw]"
          style={{
            background: "rgba(13,18,32,0.95)",
            border: "1px solid rgba(0,212,255,0.12)",
            boxShadow: "0 20px 60px rgba(0,0,0,0.5)",
          }}
          initial={{ scale: 0.9, opacity: 0, y: 10 }}
          animate={{ scale: 1, opacity: 1, y: 0 }}
          exit={{ scale: 0.9, opacity: 0, y: 10 }}
          transition={{ type: "spring", damping: 25, stiffness: 300 }}
        >
          {/* Header */}
          <div className="flex items-center justify-between mb-4">
            <div className="flex items-center gap-2">
              <Settings size={14} style={{ color: "#00d4ff" }} />
              <span style={{ fontSize: "0.82rem", color: "#e0e0e0" }}>
                Default Model
              </span>
            </div>
            <button
              className="p-1 rounded-md transition-colors"
              style={{ color: "#666" }}
              onClick={onClose}
            >
              <X size={14} />
            </button>
          </div>

          <p
            className="mb-4"
            style={{ fontSize: "0.7rem", color: "#888" }}
          >
            Sets the default AI model for all agents without per-agent override.
          </p>

          {/* Model selection */}
          <div className="mb-5">
            <label
              className="block mb-2"
              style={{ fontSize: "0.68rem", color: "#aaa", letterSpacing: "0.05em" }}
            >
              AI Model
            </label>
            <div className="space-y-1.5">
              {AVAILABLE_MODELS.map((m) => (
                <ModelOption
                  key={m.id}
                  id={m.id}
                  label={m.label}
                  selected={selectedModel === m.id}
                  onClick={() => setSelectedModel(m.id)}
                />
              ))}
            </div>
          </div>

          {/* Actions */}
          <div className="flex justify-end gap-2">
            <button
              className="px-3 py-1.5 rounded-md text-xs transition-colors"
              style={{
                background: "rgba(255,255,255,0.04)",
                border: "1px solid rgba(255,255,255,0.08)",
                color: "#aaa",
              }}
              onClick={onClose}
            >
              Cancel
            </button>
            <button
              className="px-3 py-1.5 rounded-md text-xs transition-colors flex items-center gap-1.5"
              style={{
                background: "rgba(0,212,255,0.1)",
                border: "1px solid rgba(0,212,255,0.2)",
                color: "#00d4ff",
                opacity: saving ? 0.6 : 1,
              }}
              onClick={handleSave}
              disabled={saving}
            >
              <Check size={11} />
              Save
            </button>
          </div>
        </motion.div>
      </motion.div>
    </AnimatePresence>
  );
}

function ModelOption({
  id,
  label,
  selected,
  onClick,
}: {
  id: string;
  label: string;
  selected: boolean;
  onClick: () => void;
}) {
  return (
    <button
      className="w-full text-left px-3 py-2 rounded-md transition-all"
      style={{
        background: selected ? "rgba(0,212,255,0.08)" : "rgba(255,255,255,0.02)",
        border: `1px solid ${selected ? "rgba(0,212,255,0.25)" : "rgba(255,255,255,0.04)"}`,
        color: selected ? "#00d4ff" : "#ccc",
        fontSize: "0.72rem",
      }}
      onClick={onClick}
    >
      <div className="flex items-center justify-between">
        <span>{label}</span>
        {selected && (
          <motion.div
            initial={{ scale: 0 }}
            animate={{ scale: 1 }}
            transition={{ type: "spring", damping: 15 }}
          >
            <Check size={11} style={{ color: "#00d4ff" }} />
          </motion.div>
        )}
      </div>
      <span style={{ fontSize: "0.6rem", color: "#666", marginTop: "2px", display: "block" }}>
        {id}
      </span>
    </button>
  );
}
