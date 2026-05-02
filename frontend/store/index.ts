"use client";

import { create } from "zustand";
import { persist } from "zustand/middleware";

export type SourceKey = "rag" | "workspace" | "web" | "regulations" | "huggingface";

export const ALL_SOURCES: SourceKey[] = ["rag", "workspace", "web", "regulations", "huggingface"];

export const AGENT_OPTIONS = [
  "auto",
  "RAGAgent",
  "ResearchAgent",
  "PricingAgent",
  "PolicyAgent",
  "UnderwritingAgent",
] as const;

export type AgentOption = (typeof AGENT_OPTIONS)[number];

export interface TokenUsage {
  inputTokens:  number;
  outputTokens: number;
  sessions:     number;
}

const ZERO_USAGE: TokenUsage = { inputTokens: 0, outputTokens: 0, sessions: 0 };

interface AppStore {
  // Workspace / session state
  activeWorkspaceId: string | null;
  activeSessions:    Record<string, string>; // workspaceId → sessionId

  // Chat preferences (persisted so they survive refreshes)
  sourcesEnabled: Record<SourceKey, boolean>;
  preferredAgent: AgentOption;

  // Token usage per user — keyed by userId so each user sees their own stats
  tokenUsageByUser: Record<string, TokenUsage>;

  // Actions
  setActiveWorkspace:  (id: string) => void;
  setActiveSession:    (workspaceId: string, sessionId: string) => void;
  getActiveSession:    (workspaceId: string) => string | null;
  clearSession:        (workspaceId: string) => void;

  setSourceEnabled:    (source: SourceKey, enabled: boolean) => void;
  setPreferredAgent:   (agent: AgentOption) => void;

  addTokenUsage:       (userId: string, input: number, output: number) => void;
  getTokenUsage:       (userId: string) => TokenUsage;
}

const DEFAULT_SOURCES: Record<SourceKey, boolean> = {
  rag:          true,
  workspace:    true,
  web:          true,
  regulations:  true,
  huggingface:  true,
};

export const useAppStore = create<AppStore>()(
  persist(
    (set, get) => ({
      activeWorkspaceId: null,
      activeSessions:    {},
      sourcesEnabled:    DEFAULT_SOURCES,
      preferredAgent:    "auto",
      tokenUsageByUser:  {},

      setActiveWorkspace: (id) => set({ activeWorkspaceId: id }),

      setActiveSession: (workspaceId, sessionId) =>
        set((s) => ({ activeSessions: { ...s.activeSessions, [workspaceId]: sessionId } })),

      getActiveSession: (workspaceId) => get().activeSessions[workspaceId] ?? null,

      clearSession: (workspaceId) =>
        set((s) => {
          const { [workspaceId]: _, ...rest } = s.activeSessions;
          return { activeSessions: rest };
        }),

      setSourceEnabled: (source, enabled) =>
        set((s) => ({
          sourcesEnabled: { ...s.sourcesEnabled, [source]: enabled },
        })),

      setPreferredAgent: (agent) => set({ preferredAgent: agent }),

      addTokenUsage: (userId, input, output) =>
        set((s) => {
          const prev = s.tokenUsageByUser[userId] ?? ZERO_USAGE;
          return {
            tokenUsageByUser: {
              ...s.tokenUsageByUser,
              [userId]: {
                inputTokens:  prev.inputTokens  + input,
                outputTokens: prev.outputTokens + output,
                sessions:     prev.sessions     + 1,
              },
            },
          };
        }),

      getTokenUsage: (userId) => get().tokenUsageByUser[userId] ?? ZERO_USAGE,
    }),
    { name: "insureiq-store" },
  ),
);
