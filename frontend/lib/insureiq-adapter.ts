"use client";

import type { ChatModelAdapter } from "@assistant-ui/react";
import type { SSEEvent } from "./types";
import type { SourceKey, AgentOption } from "@/store";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export interface ChatPreferences {
  preferredAgent:  AgentOption;
  sourcesEnabled:  Record<SourceKey, boolean>;
}

export type AgentEventCallback = (type: "routing" | "done", agent: string) => void;
export type TokenCallback       = (input: number, output: number) => void;

export function createInsureIQAdapter(
  workspaceId:   string,
  sessionId:     string,
  getToken:      () => string | undefined,
  getPrefs:      () => ChatPreferences,
  onAgentEvent:  AgentEventCallback,
  onTokenUsage:  TokenCallback,
): ChatModelAdapter {
  return {
    async *run({ messages, abortSignal }) {
      // Extract the last user message text
      const lastMsg  = messages.at(-1);
      const userText =
        lastMsg?.content
          .filter((c): c is { type: "text"; text: string } => c.type === "text")
          .map((c) => c.text)
          .join("") ?? "";

      const token = getToken();
      if (!token) throw new Error("Not authenticated");

      const prefs = getPrefs();

      // Build enabled_sources list from the preferences map
      const enabledSources = (Object.keys(prefs.sourcesEnabled) as SourceKey[]).filter(
        (k) => prefs.sourcesEnabled[k],
      );
      // If all sources are on, send null (backend treats null as "all enabled")
      const allEnabled = enabledSources.length === 5;

      const body = {
        workspace_id:    workspaceId,
        session_id:      sessionId,
        message:         userText,
        preferred_agent: prefs.preferredAgent !== "auto" ? prefs.preferredAgent : null,
        enabled_sources: allEnabled ? null : enabledSources,
      };

      const res = await fetch(`${API_URL}/chat/stream`, {
        method:  "POST",
        headers: {
          "Content-Type":  "application/json",
          "Authorization": `Bearer ${token}`,
        },
        body:   JSON.stringify(body),
        signal: abortSignal,
      });

      if (!res.ok) {
        const err = await res.text().catch(() => res.statusText);
        throw new Error(`Chat error ${res.status}: ${err}`);
      }

      const reader  = res.body!.getReader();
      const decoder = new TextDecoder();
      let   buffer  = "";
      let   text    = "";

      try {
        while (true) {
          const { done, value } = await reader.read();
          if (done) break;

          buffer += decoder.decode(value, { stream: true });
          const lines = buffer.split("\n");
          buffer = lines.pop() ?? "";

          for (const line of lines) {
            if (!line.startsWith("data: ")) continue;
            const raw = line.slice(6).trim();
            if (!raw) continue;

            let event: SSEEvent;
            try { event = JSON.parse(raw); } catch { continue; }

            if (event.type === "routing" && event.agent) {
              onAgentEvent("routing", event.agent);
            }

            if (event.type === "token" && event.content) {
              text = event.content;
              yield { content: [{ type: "text", text }] };
            }

            if (event.type === "done") {
              // Signal which agent(s) handled this
              if (event.agent_used) {
                onAgentEvent("done", event.agent_used);
              }

              // Estimate token usage (4 chars ≈ 1 token)
              const inputEst  = Math.ceil(userText.length / 4);
              const outputEst = Math.ceil(text.length    / 4);
              onTokenUsage(inputEst, outputEst);

              yield { content: [{ type: "text", text }] };
              return;
            }

            if (event.type === "error") {
              throw new Error(event.message ?? "Agent error");
            }
          }
        }
      } finally {
        reader.releaseLock();
      }

      // Fallback if stream ended without done event
      if (text) {
        yield { content: [{ type: "text", text }] };
      }
    },
  };
}
