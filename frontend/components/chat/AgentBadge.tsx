import type { AgentName } from "@/lib/types";
import { cn } from "@/lib/utils";
import { Search, Globe, TrendingUp, FileText, ShieldCheck, Bot } from "lucide-react";

const AGENT_CONFIG: Record<AgentName | string, { color: string; bg: string; icon: React.ElementType }> = {
  RAGAgent:          { color: "text-indigo-400",  bg: "bg-indigo-500/10 border-indigo-500/30",  icon: Search      },
  ResearchAgent:     { color: "text-amber-400",   bg: "bg-amber-500/10 border-amber-500/30",    icon: Globe       },
  PricingAgent:      { color: "text-green-400",   bg: "bg-green-500/10 border-green-500/30",    icon: TrendingUp  },
  PolicyAgent:       { color: "text-blue-400",    bg: "bg-blue-500/10 border-blue-500/30",      icon: FileText    },
  UnderwritingAgent: { color: "text-purple-400",  bg: "bg-purple-500/10 border-purple-500/30",  icon: ShieldCheck },
};

export function AgentBadge({ name, className }: { name: string; className?: string }) {
  const cfg  = AGENT_CONFIG[name] ?? { color: "text-muted-foreground", bg: "bg-muted border-border", icon: Bot };
  const Icon = cfg.icon;

  return (
    <span className={cn(
      "inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full border text-xs font-medium",
      cfg.color, cfg.bg, className,
    )}>
      <Icon className="h-3 w-3" />
      {name}
    </span>
  );
}
