"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { useSession } from "next-auth/react";
import { useQuery } from "@tanstack/react-query";
import { useAppStore } from "@/store";
import { api } from "@/lib/api";
import { InsureIQRuntimeProvider, useAgentStatus } from "@/components/chat/InsureIQRuntimeProvider";
import { Thread } from "@/components/assistant-ui/thread";
import { AgentBadge } from "@/components/chat/AgentBadge";
import { ChatSearchBar } from "@/components/chat/ChatSearchBar";
import { Button } from "@/components/ui/button";
import { ScrollArea } from "@/components/ui/scroll-area";
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger,
} from "@/components/ui/dialog";
import { Plus, MessageSquare, History, Clock, Loader2 } from "lucide-react";
import { useThreadRuntime } from "@assistant-ui/react";
import { formatDate } from "@/lib/utils";
import type { ChatSession } from "@/lib/types";

// ── Quick action prompts ────────────────────────────────────────────────────

const QUICK_ACTIONS = [
  { label: "Price a risk",       message: "Help me price a risk. What type of insurance and what are the key details?" },
  { label: "Draft a policy",     message: "I need to create a new insurance policy. Let's start with the basics." },
  { label: "Check appetite",     message: "Help me assess underwriting appetite for a risk I'm evaluating." },
  { label: "Find data",          message: "Search for insurance datasets or market data on HuggingFace." },
  { label: "Explain coverage",   message: "Explain the difference between claims-made and occurrence-based policies." },
];

function QuickActionBar() {
  const threadRuntime = useThreadRuntime();

  const send = (text: string) => {
    threadRuntime.append({
      role: "user",
      content: [{ type: "text", text }],
    });
  };

  return (
    <div className="flex gap-2 p-3 overflow-x-auto shrink-0">
      {QUICK_ACTIONS.map((a) => (
        <Button
          key={a.label}
          variant="outline"
          size="sm"
          className="text-xs shrink-0 whitespace-nowrap"
          onClick={() => send(a.message)}
        >
          {a.label}
        </Button>
      ))}
    </div>
  );
}

// ── Agent status display ────────────────────────────────────────────────────

function AgentStatusBadge() {
  const { agentStatus } = useAgentStatus();

  if (agentStatus.routing) {
    return (
      <div className="flex items-center gap-1.5 shrink-0 pl-2">
        <Loader2 className="h-3 w-3 animate-spin text-muted-foreground" />
        <AgentBadge name={agentStatus.routing} className="animate-pulse" />
      </div>
    );
  }

  if (agentStatus.used) {
    // Show individual badges when multiple agents responded
    const agents = agentStatus.used.split(", ").filter(Boolean);
    return (
      <div className="flex items-center gap-1 shrink-0 pl-2">
        {agents.map((a) => (
          <AgentBadge key={a} name={a} />
        ))}
      </div>
    );
  }

  return null;
}

// ── Chat history modal ──────────────────────────────────────────────────────

function ChatHistoryModal() {
  const router                  = useRouter();
  const { data: session }       = useSession();
  const token                   = (session as any)?.access_token as string | undefined;
  const { activeWorkspaceId, setActiveSession, clearSession } = useAppStore();
  const [open, setOpen]         = useState(false);

  const { data: history, isLoading } = useQuery({
    queryKey: ["chat-sessions", activeWorkspaceId, token],
    queryFn:  () => api.chat.history(activeWorkspaceId!, token!),
    enabled:  !!(activeWorkspaceId && token),
    refetchInterval: 10_000,
  });

  const sessions: ChatSession[] = (history as any)?.sessions ?? [];

  const newSession = () => {
    if (activeWorkspaceId) clearSession(activeWorkspaceId);
    setOpen(false);
    router.refresh();
  };

  const loadSession = (sessionId: string) => {
    if (activeWorkspaceId) {
      setActiveSession(activeWorkspaceId, sessionId);
      setOpen(false);
      router.refresh();
    }
  };

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger render={<Button variant="outline" size="sm" className="gap-2" />}>
        <History className="h-4 w-4" />
        Chats
        {sessions.length > 0 && (
          <span className="ml-1 bg-primary/10 text-primary px-1.5 py-0.5 rounded-full text-[10px] font-semibold">
            {sessions.length}
          </span>
        )}
      </DialogTrigger>

      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <History className="h-5 w-5" /> Chat History
          </DialogTitle>
        </DialogHeader>

        <div className="space-y-3">
          <Button size="sm" className="w-full gap-2" onClick={newSession}>
            <Plus className="h-4 w-4" /> New Chat
          </Button>

          {isLoading ? (
            <div className="flex items-center justify-center py-8">
              <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
            </div>
          ) : sessions.length === 0 ? (
            <div className="text-center py-8 text-muted-foreground text-sm">
              <MessageSquare className="h-8 w-8 mx-auto mb-3 opacity-40" />
              <p>No chat history yet.</p>
              <p className="text-xs mt-1">Start a conversation to see it here.</p>
            </div>
          ) : (
            <ScrollArea className="max-h-[400px]">
              <div className="space-y-1">
                {sessions.map((s) => (
                  <button
                    key={s.session_id}
                    onClick={() => loadSession(s.session_id)}
                    className="w-full text-left px-4 py-3 rounded-lg border border-border/50 bg-card hover:bg-accent hover:border-border transition-all flex items-center gap-3 group"
                  >
                    <div className="h-8 w-8 rounded-lg bg-primary/10 flex items-center justify-center shrink-0 group-hover:bg-primary/20 transition-colors">
                      <MessageSquare className="h-4 w-4 text-primary" />
                    </div>
                    <div className="flex-1 min-w-0">
                      {/* Show first message as title, fall back to friendly label */}
                      <p className="text-sm font-medium truncate">
                        {s.first_message
                          ? s.first_message.slice(0, 60) + (s.first_message.length > 60 ? "…" : "")
                          : "New conversation"}
                      </p>
                      <div className="flex items-center gap-2 text-xs text-muted-foreground mt-0.5">
                        <Clock className="h-3 w-3" />
                        <span>{formatDate(s.created_at)}</span>
                        <span>· {s.message_count} {s.message_count === 1 ? "message" : "messages"}</span>
                      </div>
                    </div>
                  </button>
                ))}
              </div>
            </ScrollArea>
          )}
        </div>
      </DialogContent>
    </Dialog>
  );
}

// ── Page ────────────────────────────────────────────────────────────────────

export default function ChatPage() {
  return (
    <InsureIQRuntimeProvider>
      <div className="flex flex-col h-full overflow-hidden">
        {/* Top bar: quick actions + agent status + history */}
        <div className="flex items-center border-b border-border px-3 py-2 shrink-0 gap-2">
          <div className="flex-1 min-w-0 overflow-x-auto">
            <QuickActionBar />
          </div>
          <AgentStatusBadge />
          <div className="shrink-0">
            <ChatHistoryModal />
          </div>
        </div>

        {/* Semantic search bar — always visible between top bar and thread */}
        <ChatSearchBar />

        {/* Thread — fills remaining height */}
        <div className="flex-1 overflow-hidden">
          <Thread />
        </div>
      </div>
    </InsureIQRuntimeProvider>
  );
}
