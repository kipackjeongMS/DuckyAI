import { createContext, useContext, type ReactNode } from "react";
import type { DuckyAIApi } from "../types/duckyai";

const DuckyAIContext = createContext<DuckyAIApi | null>(null);

export interface DuckyAIProviderProps {
  api: DuckyAIApi;
  children?: ReactNode;
}

export function DuckyAIProvider({ api, children }: DuckyAIProviderProps) {
  return (
    <DuckyAIContext.Provider value={api}>{children}</DuckyAIContext.Provider>
  );
}

export function useDuckyAI(): DuckyAIApi {
  const ctx = useContext(DuckyAIContext);
  if (!ctx) {
    throw new Error("useDuckyAI must be used within a <DuckyAIProvider>");
  }
  return ctx;
}
