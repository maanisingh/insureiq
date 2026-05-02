"use client";

/**
 * ComposerSources — compact toggle bar inside the chat composer, next to the +
 * attachment button.
 *
 * Left  : source toggle pills  (RAG / My Docs / Web / Regs / HuggingFace)
 * Middle: divider
 * Right : agent selector pill  (Auto | specific agent)
 *
 * Preferences are persisted in Zustand (localStorage) and read by the adapter
 * on every send.
 */

import {
  Brain, FolderOpen, Globe, Scale, Database,
  Search, TrendingUp, FileText, ShieldCheck, Zap, ChevronDown,
} from "lucide-react";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
  DropdownMenuSeparator,
} from "@/components/ui/dropdown-menu";
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { cn } from "@/lib/utils";
import { useAppStore, type SourceKey, type AgentOption, AGENT_OPTIONS } from "@/store";

// ── Source definitions ──────────────────────────────────────────────────────

const SOURCES: { key: SourceKey; label: string; icon: React.ElementType; tooltip: string }[] = [
  { key: "rag",         label: "RAG",     icon: Brain,      tooltip: "Global knowledge base (547K insurance records)" },
  { key: "workspace",   label: "My Docs", icon: FolderOpen, tooltip: "Your uploaded workspace documents" },
  { key: "web",         label: "Web",     icon: Globe,      tooltip: "Live internet search + industry news" },
  { key: "regulations", label: "Regs",    icon: Scale,      tooltip: "Insurance regulations & compliance (US)" },
  { key: "huggingface", label: "HF",      icon: Database,   tooltip: "HuggingFace insurance & actuarial datasets" },
];

// ── Agent definitions ───────────────────────────────────────────────────────

const AGENT_META: Record<AgentOption, { label: string; icon: React.ElementType; color: string }> = {
  auto:              { label: "Auto",         icon: Zap,         color: "text-muted-foreground" },
  RAGAgent:          { label: "RAG",          icon: Search,      color: "text-indigo-400"       },
  ResearchAgent:     { label: "Research",     icon: Globe,       color: "text-amber-400"        },
  PricingAgent:      { label: "Pricing",      icon: TrendingUp,  color: "text-green-400"        },
  PolicyAgent:       { label: "Policy",       icon: FileText,    color: "text-blue-400"         },
  UnderwritingAgent: { label: "Underwriting", icon: ShieldCheck, color: "text-purple-400"       },
};

// ── Source toggle pill ──────────────────────────────────────────────────────

function SourcePill({ sourceKey }: { sourceKey: SourceKey }) {
  const { sourcesEnabled, setSourceEnabled } = useAppStore();
  const cfg     = SOURCES.find((s) => s.key === sourceKey)!;
  const Icon    = cfg.icon;
  const enabled = sourcesEnabled[sourceKey];

  return (
    <Tooltip>
      <TooltipTrigger
        render={
          <button
            type="button"
            onClick={() => setSourceEnabled(sourceKey, !enabled)}
            className={cn(
              "inline-flex items-center gap-1 px-2 py-0.5 rounded-full border text-[11px] font-medium transition-all select-none",
              enabled
                ? "bg-primary/10 border-primary/30 text-primary hover:bg-primary/20"
                : "bg-muted/40 border-border/40 text-muted-foreground/50 hover:bg-muted/60",
            )}
          >
            <Icon className="h-2.5 w-2.5 shrink-0" />
            {cfg.label}
          </button>
        }
      />
      <TooltipContent side="top" className="text-xs max-w-[180px]">
        {cfg.tooltip}
        <span className="block text-muted-foreground mt-0.5">
          {enabled ? "Click to disable" : "Click to enable"}
        </span>
      </TooltipContent>
    </Tooltip>
  );
}

// ── Agent selector pill ─────────────────────────────────────────────────────

function AgentSelector() {
  const { preferredAgent, setPreferredAgent } = useAppStore();
  const meta = AGENT_META[preferredAgent];
  const Icon = meta.icon;

  return (
    <DropdownMenu>
      {/* base-ui MenuPrimitive.Trigger uses render prop, not asChild */}
      <DropdownMenuTrigger
        render={
          <button
            type="button"
            className={cn(
              "inline-flex items-center gap-1 px-2 py-0.5 rounded-full border text-[11px] font-medium transition-all select-none",
              preferredAgent === "auto"
                ? "bg-muted/40 border-border/40 text-muted-foreground hover:bg-muted/60"
                : "bg-primary/10 border-primary/30 text-primary hover:bg-primary/20",
            )}
          />
        }
      >
        <Icon className={cn("h-2.5 w-2.5 shrink-0", meta.color)} />
        {meta.label}
        <ChevronDown className="h-2.5 w-2.5 shrink-0 opacity-60" />
      </DropdownMenuTrigger>

      <DropdownMenuContent align="end" side="top" className="w-44">
        <div className="px-2 py-1 text-[10px] text-muted-foreground font-medium uppercase tracking-wider">
          Route to agent
        </div>
        <DropdownMenuSeparator />
        {AGENT_OPTIONS.map((opt) => {
          const m     = AGENT_META[opt];
          const MIcon = m.icon;
          return (
            <DropdownMenuItem
              key={opt}
              onClick={() => setPreferredAgent(opt)}
              className={cn(
                "flex items-center gap-2 text-sm cursor-pointer",
                preferredAgent === opt && "bg-primary/10",
              )}
            >
              <MIcon className={cn("h-3.5 w-3.5", m.color)} />
              {m.label}
              {opt === "auto" && (
                <span className="ml-auto text-[10px] text-muted-foreground">default</span>
              )}
              {preferredAgent === opt && opt !== "auto" && (
                <span className="ml-auto text-[10px] text-primary">active</span>
              )}
            </DropdownMenuItem>
          );
        })}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

// ── Main bar ────────────────────────────────────────────────────────────────

export function ComposerSources() {
  return (
    <div className="flex items-center gap-1 flex-wrap">
      {SOURCES.map((s) => (
        <SourcePill key={s.key} sourceKey={s.key} />
      ))}
      <div className="w-px h-3 bg-border/60 mx-0.5 shrink-0" />
      <AgentSelector />
    </div>
  );
}
