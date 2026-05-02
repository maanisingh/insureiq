"use client";

import { createContext, useCallback, useContext, useMemo, useRef, useState } from "react";
import { useSession } from "next-auth/react";
import {
  AssistantRuntimeProvider,
  useLocalRuntime,
} from "@assistant-ui/react";
import { createInsureIQAdapter } from "@/lib/insureiq-adapter";
import { useAppStore } from "@/store";

// ── Agent status context ────────────────────────────────────────────────────

interface AgentStatus {
  routing: string | null;  // agent currently being routed to
  used:    string | null;  // agent(s) that handled the last response
}

interface AgentStatusCtx {
  agentStatus: AgentStatus;
}

const AgentStatusContext = createContext<AgentStatusCtx>({
  agentStatus: { routing: null, used: null },
});

export function useAgentStatus() {
  return useContext(AgentStatusContext);
}

// ── Provider ────────────────────────────────────────────────────────────────

export function InsureIQRuntimeProvider({ children }: { children: React.ReactNode }) {
  const { data: session } = useSession();
  const token             = (session as any)?.access_token as string | undefined;

  const {
    activeWorkspaceId,
    getActiveSession,
    setActiveSession,
    sourcesEnabled,
    preferredAgent,
    addTokenUsage,
  } = useAppStore();

  const userId = (session as any)?.user_id as string | undefined;

  // Stable session ID for current workspace
  const workspaceId = activeWorkspaceId ?? "default";
  let sessionId     = getActiveSession(workspaceId);
  if (!sessionId) {
    sessionId = Math.random().toString(36).slice(2, 10);
    setActiveSession(workspaceId, sessionId);
  }

  // Agent status state (ephemeral — resets each response)
  const [agentStatus, setAgentStatus] = useState<AgentStatus>({ routing: null, used: null });

  // Use a ref so the callback always closes over the latest setState
  const agentCallbackRef = useRef<(type: "routing" | "done", agent: string) => void>(() => {});
  agentCallbackRef.current = (type, agent) => {
    if (type === "routing") setAgentStatus({ routing: agent, used: null });
    if (type === "done")    setAgentStatus({ routing: null,  used: agent });
  };

  const getToken = useCallback(() => token, [token]);

  // Stable snapshot of preferences for the adapter
  const getPrefs = useCallback(
    () => ({ preferredAgent, sourcesEnabled }),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [preferredAgent, sourcesEnabled],
  );

  const onAgentEvent = useCallback(
    (type: "routing" | "done", agent: string) => agentCallbackRef.current(type, agent),
    [],
  );

  const onTokenUsage = useCallback(
    (input: number, output: number) => {
      if (userId) addTokenUsage(userId, input, output);
    },
    [addTokenUsage, userId],
  );

  const adapter = useMemo(
    () => createInsureIQAdapter(workspaceId, sessionId, getToken, getPrefs, onAgentEvent, onTokenUsage),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [workspaceId, sessionId, token, preferredAgent, sourcesEnabled],
  );

  const runtime = useLocalRuntime(adapter);

  return (
    <AgentStatusContext.Provider value={{ agentStatus }}>
      <AssistantRuntimeProvider runtime={runtime}>
        {children}
      </AssistantRuntimeProvider>
    </AgentStatusContext.Provider>
  );
}
