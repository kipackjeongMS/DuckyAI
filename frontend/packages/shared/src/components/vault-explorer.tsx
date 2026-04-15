import { motion, AnimatePresence } from "motion/react";
import {
  ChevronRight,
  ChevronDown,
  Folder,
  FolderOpen,
  FileText,
  FileCode,
  File,
  Loader2,
} from "lucide-react";
import type { FileTreeNode } from "../hooks/use-vault-explorer";

/* ── Icon mapping ─────────────────────────────── */
const mdExtensions = new Set(["md", "mdx", "markdown"]);
const codeExtensions = new Set(["ts", "tsx", "js", "jsx", "py", "json", "yml", "yaml", "css", "html"]);

function getFileIcon(name: string) {
  const ext = name.split(".").pop()?.toLowerCase() ?? "";
  if (mdExtensions.has(ext)) return <FileText size={14} style={{ color: "#00d4ff", opacity: 0.7 }} />;
  if (codeExtensions.has(ext)) return <FileCode size={14} style={{ color: "#00ffa3", opacity: 0.7 }} />;
  return <File size={14} style={{ color: "#8892a4", opacity: 0.7 }} />;
}

/* ── Tree node ────────────────────────────────── */
interface TreeNodeProps {
  node: FileTreeNode;
  depth: number;
  expanded: boolean;
  selected: boolean;
  onToggle: (path: string) => void;
  onSelect: (path: string) => void;
  expandedPaths: Set<string>;
  selectedFile: string | null;
}

function TreeNode({ node, depth, expanded, selected, onToggle, onSelect, expandedPaths, selectedFile }: TreeNodeProps) {
  const isDir = node.type === "directory";
  const paddingLeft = 12 + depth * 16;

  return (
    <>
      <motion.button
        className="w-full flex items-center gap-1.5 py-[3px] pr-2 rounded-[4px] text-left group transition-colors"
        style={{
          paddingLeft,
          background: selected ? "rgba(0,212,255,0.1)" : "transparent",
          color: selected ? "#e2e8f0" : "#94a3b8",
        }}
        onClick={() => (isDir ? onToggle(node.relativePath) : onSelect(node.relativePath))}
        whileHover={{ background: selected ? "rgba(0,212,255,0.1)" : "rgba(255,255,255,0.03)" }}
        initial={false}
      >
        {isDir ? (
          <>
            <span className="shrink-0 w-4 flex items-center justify-center">
              {node.loading ? (
                <Loader2 size={12} className="animate-spin" style={{ color: "#00d4ff" }} />
              ) : expanded ? (
                <ChevronDown size={12} />
              ) : (
                <ChevronRight size={12} />
              )}
            </span>
            <span className="shrink-0">
              {expanded
                ? <FolderOpen size={14} style={{ color: "#00d4ff", opacity: 0.8 }} />
                : <Folder size={14} style={{ color: "#00d4ff", opacity: 0.6 }} />
              }
            </span>
          </>
        ) : (
          <>
            <span className="shrink-0 w-4" />
            <span className="shrink-0">{getFileIcon(node.name)}</span>
          </>
        )}
        <span
          className="truncate flex-1"
          style={{ fontSize: "0.76rem" }}
        >
          {node.name}
        </span>
      </motion.button>

      {/* Children */}
      <AnimatePresence initial={false}>
        {isDir && expanded && node.children && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.15, ease: "easeInOut" }}
            style={{ overflow: "hidden" }}
          >
            {node.children.map((child) => (
              <TreeNode
                key={child.relativePath}
                node={child}
                depth={depth + 1}
                expanded={expandedPaths.has(child.relativePath)}
                selected={selectedFile === child.relativePath}
                onToggle={onToggle}
                onSelect={onSelect}
                expandedPaths={expandedPaths}
                selectedFile={selectedFile}
              />
            ))}
          </motion.div>
        )}
      </AnimatePresence>
    </>
  );
}

/* ── Main VaultExplorer ───────────────────────── */

export interface VaultExplorerProps {
  roots: FileTreeNode[];
  loading: boolean;
  expandedPaths: Set<string>;
  selectedFile: string | null;
  onToggleDirectory: (path: string) => void;
  onOpenFile: (path: string) => void;
}

export function VaultExplorer({
  roots,
  loading,
  expandedPaths,
  selectedFile,
  onToggleDirectory,
  onOpenFile,
}: VaultExplorerProps) {
  if (loading) {
    return (
      <div className="flex items-center justify-center py-8">
        <Loader2 size={18} className="animate-spin" style={{ color: "#00d4ff" }} />
        <span className="ml-2 text-muted-foreground" style={{ fontSize: "0.75rem" }}>
          Loading vault...
        </span>
      </div>
    );
  }

  if (roots.length === 0) {
    return (
      <div className="px-4 py-6 text-center">
        <p className="text-muted-foreground" style={{ fontSize: "0.75rem" }}>
          No files found
        </p>
      </div>
    );
  }

  return (
    <div className="py-1">
      {roots.map((node) => (
        <TreeNode
          key={node.relativePath}
          node={node}
          depth={0}
          expanded={expandedPaths.has(node.relativePath)}
          selected={selectedFile === node.relativePath}
          onToggle={onToggleDirectory}
          onSelect={onOpenFile}
          expandedPaths={expandedPaths}
          selectedFile={selectedFile}
        />
      ))}
    </div>
  );
}
