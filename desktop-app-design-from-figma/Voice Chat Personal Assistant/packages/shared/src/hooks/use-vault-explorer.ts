import { useState, useCallback, useEffect, useRef } from "react";
import type { VaultEntry } from "../types/duckyai";
import { useDuckyAI } from "../context/duckyai-provider";

export interface FileTreeNode extends VaultEntry {
  children?: FileTreeNode[];
  loading?: boolean;
}

export interface VaultExplorerState {
  roots: FileTreeNode[];
  loading: boolean;
  selectedFile: string | null;
  fileContent: string | null;
  expandedPaths: Set<string>;
}

export function useVaultExplorer() {
  const api = useDuckyAI();
  const [roots, setRoots] = useState<FileTreeNode[]>([]);
  const [loading, setLoading] = useState(true);
  const [selectedFile, setSelectedFile] = useState<string | null>(null);
  const [fileContent, setFileContent] = useState<string | null>(null);
  const [expandedPaths, setExpandedPaths] = useState<Set<string>>(new Set());
  const loadingPaths = useRef(new Set<string>());

  // Load root directory on mount
  useEffect(() => {
    if (!api?.vault?.listDir) return;
    let cancelled = false;
    setLoading(true);
    api.vault.listDir("").then((entries) => {
      if (cancelled) return;
      setRoots(entries.map((e) => ({ ...e })));
      setLoading(false);
    }).catch(() => {
      if (!cancelled) setLoading(false);
    });
    return () => { cancelled = true; };
  }, [api]);

  const toggleDirectory = useCallback(async (dirPath: string) => {
    if (!api?.vault?.listDir) return;

    setExpandedPaths((prev) => {
      const next = new Set(prev);
      if (next.has(dirPath)) {
        next.delete(dirPath);
        return next;
      }
      next.add(dirPath);
      return next;
    });

    // If already loaded children, just toggle
    const findNode = (nodes: FileTreeNode[], target: string): FileTreeNode | null => {
      for (const node of nodes) {
        if (node.relativePath === target) return node;
        if (node.children) {
          const found = findNode(node.children, target);
          if (found) return found;
        }
      }
      return null;
    };

    const existingNode = findNode(roots, dirPath);
    if (existingNode?.children) return;
    if (loadingPaths.current.has(dirPath)) return;

    loadingPaths.current.add(dirPath);

    // Mark node as loading
    const updateNodeChildren = (
      nodes: FileTreeNode[],
      target: string,
      children: FileTreeNode[] | undefined,
      isLoading: boolean,
    ): FileTreeNode[] =>
      nodes.map((node) => {
        if (node.relativePath === target) {
          return { ...node, children, loading: isLoading };
        }
        if (node.children) {
          return { ...node, children: updateNodeChildren(node.children, target, children, isLoading) };
        }
        return node;
      });

    setRoots((prev) => updateNodeChildren(prev, dirPath, undefined, true));

    try {
      const entries = await api.vault.listDir(dirPath);
      const children: FileTreeNode[] = entries.map((e) => ({ ...e }));
      setRoots((prev) => updateNodeChildren(prev, dirPath, children, false));
    } catch {
      setRoots((prev) => updateNodeChildren(prev, dirPath, [], false));
    } finally {
      loadingPaths.current.delete(dirPath);
    }
  }, [api, roots]);

  const openFile = useCallback(async (filePath: string) => {
    if (!api?.vault?.readFile) return;
    setSelectedFile(filePath);
    setFileContent(null);
    try {
      const content = await api.vault.readFile(filePath);
      setFileContent(content);
    } catch {
      setFileContent("Error: Could not read file.");
    }
  }, [api]);

  const closeFile = useCallback(() => {
    setSelectedFile(null);
    setFileContent(null);
  }, []);

  return {
    roots,
    loading,
    selectedFile,
    fileContent,
    expandedPaths,
    toggleDirectory,
    openFile,
    closeFile,
  };
}
