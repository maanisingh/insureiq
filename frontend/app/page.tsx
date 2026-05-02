import Link from "next/link";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";
import {
  BookOpen, Search, TrendingUp, FileText, ShieldCheck,
  Globe, Zap, Lock, ArrowRight, CheckCircle, BarChart3,
  Users, Clock,
} from "lucide-react";

const AGENTS = [
  { name: "RAGAgent",          icon: Search,      color: "text-indigo-400",  border: "border-indigo-500/20", glow: "from-indigo-500/10",  desc: "Insurance knowledge base + your uploaded documents" },
  { name: "ResearchAgent",     icon: Globe,       color: "text-amber-400",   border: "border-amber-500/20",  glow: "from-amber-500/10",   desc: "Web search, HuggingFace datasets, regulatory updates" },
  { name: "PricingAgent",      icon: TrendingUp,  color: "text-emerald-400", border: "border-emerald-500/20",glow: "from-emerald-500/10", desc: "ISO auto, NCCI workers comp, SOA life — cited sources" },
  { name: "PolicyAgent",       icon: FileText,    color: "text-sky-400",     border: "border-sky-500/20",    glow: "from-sky-500/10",     desc: "40-page ISO standard policy document generation" },
  { name: "UnderwritingAgent", icon: ShieldCheck, color: "text-violet-400",  border: "border-violet-500/20", glow: "from-violet-500/10",  desc: "Risk scoring 0-100, appetite checks, UW memos" },
];

const FEATURES = [
  { icon: Zap,         title: "Zero Hallucination",     desc: "Every premium cites ISO, NCCI, or SOA. Policy language uses ISO standard forms only." },
  { icon: Lock,        title: "Your Documents, Private", desc: "Upload policies and contracts. Your RAG stays isolated to your workspace." },
  { icon: BookOpen,    title: "547K Knowledge Records",  desc: "Pre-indexed actuarial, underwriting, claims, and fraud datasets." },
  { icon: CheckCircle, title: "API Keys for Teams",      desc: "Programmatic access for integrations, automations, and custom workflows." },
];

const STATS = [
  { value: "547K",    label: "Knowledge records",   icon: BarChart3 },
  { value: "5",       label: "Specialist agents",   icon: Users },
  { value: "<2s",     label: "First token latency", icon: Clock },
  { value: "99.9%",   label: "Uptime SLA",          icon: Zap },
];

export default function LandingPage() {
  return (
    <div className="min-h-screen bg-background text-foreground">
      {/* Nav */}
      <nav className="fixed top-0 w-full z-50 border-b border-border/40 bg-background/80 backdrop-blur-xl">
        <div className="max-w-7xl mx-auto px-6 h-14 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <div className="h-7 w-7 rounded-lg bg-gradient-to-br from-indigo-500 to-violet-600 flex items-center justify-center">
              <ShieldCheck className="h-4 w-4 text-white" />
            </div>
            <span className="font-bold text-lg tracking-tight">InsureIQ</span>
          </div>
          <div className="flex gap-3">
            <Link href="/login">
              <Button variant="ghost" size="sm">Login</Button>
            </Link>
            <Link href="/register">
              <Button size="sm" className="bg-gradient-to-r from-indigo-500 to-violet-600 text-white border-0 hover:from-indigo-600 hover:to-violet-700">
                Get Started <ArrowRight className="ml-1 h-4 w-4" />
              </Button>
            </Link>
          </div>
        </div>
      </nav>

      {/* Hero */}
      <section className="relative pt-32 pb-24 px-6 text-center overflow-hidden">
        {/* Background glow */}
        <div className="absolute inset-0 -z-10">
          <div className="absolute top-1/4 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[800px] h-[600px] bg-gradient-to-r from-indigo-500/8 via-violet-500/8 to-sky-500/8 rounded-full blur-3xl" />
          <div className="absolute top-2/3 left-1/3 w-[400px] h-[400px] bg-gradient-to-r from-emerald-500/5 to-indigo-500/5 rounded-full blur-3xl" />
        </div>

        <div className="max-w-4xl mx-auto">
          <Badge variant="secondary" className="mb-6 text-xs px-4 py-1.5 bg-indigo-500/10 text-indigo-400 border-indigo-500/20 hover:bg-indigo-500/15">
            5 Specialist AI Agents  ·  Streaming  ·  Zero Hallucination
          </Badge>
          <h1 className="text-5xl md:text-7xl font-bold tracking-tight mb-6 bg-gradient-to-b from-foreground via-foreground/90 to-foreground/50 bg-clip-text text-transparent leading-[1.1]">
            AI-Powered Intelligence
            <br />
            <span className="bg-gradient-to-r from-indigo-400 via-violet-400 to-sky-400 bg-clip-text text-transparent">
              for Insurance
            </span>
          </h1>
          <p className="text-lg md:text-xl text-muted-foreground mb-10 max-w-2xl mx-auto leading-relaxed">
            Price risks accurately. Draft 40-page policies. Assess underwriting decisions.
            All in one conversation — with every source cited.
          </p>
          <div className="flex gap-4 justify-center">
            <Link href="/register">
              <Button size="lg" className="gap-2 bg-gradient-to-r from-indigo-500 to-violet-600 text-white border-0 hover:from-indigo-600 hover:to-violet-700 shadow-lg shadow-indigo-500/25 hover:shadow-indigo-500/40 transition-all">
                Start Free <ArrowRight className="h-4 w-4" />
              </Button>
            </Link>
            <Link href="/login">
              <Button size="lg" variant="outline" className="border-border/60">
                Sign In
              </Button>
            </Link>
          </div>
        </div>

        {/* Demo card */}
        <div className="max-w-3xl mx-auto mt-20 rounded-xl border border-border/60 bg-card/80 backdrop-blur p-6 text-left shadow-2xl shadow-black/10">
          <div className="flex items-center gap-2 mb-4 text-sm text-muted-foreground">
            <div className="h-3 w-3 rounded-full bg-emerald-500 animate-pulse" />
            <span className="text-emerald-400 font-semibold">PricingAgent</span>
            <span className="text-muted-foreground/60">·</span>
            <span>NCCI Loss Cost Method</span>
          </div>
          <div className="space-y-3 text-sm font-mono">
            <div className="text-muted-foreground">
              <span className="text-indigo-400 font-medium">You:</span> Calculate WC premium — roofing contractor, $2M payroll, NCCI 5403
            </div>
            <div className="text-foreground/90 pl-4 border-l-2 border-emerald-500/40 space-y-1">
              <p className="text-emerald-400 font-bold text-base">Annual WC Premium: $104,960</p>
              <p className="text-muted-foreground text-xs">+/- 15% uncertainty range · NCCI Voluntary Loss Costs · Class 5403 · $2.85 per $100 payroll</p>
              <p className="text-muted-foreground/60 text-xs mt-1">Sources: NCCI Basic Manual 2024, Rule 1-E-2 · ISO General Liability Rating Manual</p>
            </div>
          </div>
        </div>
      </section>

      {/* Stats */}
      <section className="py-8 px-6 border-y border-border/40 bg-muted/30">
        <div className="max-w-5xl mx-auto grid grid-cols-2 md:grid-cols-4 gap-8">
          {STATS.map((s) => (
            <div key={s.label} className="text-center">
              <p className="text-3xl font-bold tracking-tight bg-gradient-to-r from-indigo-400 to-violet-400 bg-clip-text text-transparent">{s.value}</p>
              <p className="text-sm text-muted-foreground mt-1">{s.label}</p>
            </div>
          ))}
        </div>
      </section>

      {/* Agents */}
      <section className="py-24 px-6 max-w-6xl mx-auto">
        <div className="text-center mb-16">
          <Badge variant="secondary" className="mb-4 text-xs bg-violet-500/10 text-violet-400 border-violet-500/20">Multi-Agent Architecture</Badge>
          <h2 className="text-3xl md:text-4xl font-bold mb-4">5 Specialist Agents</h2>
          <p className="text-muted-foreground max-w-lg mx-auto">
            Each query is routed to the right expert automatically by the orchestrator
          </p>
        </div>
        <div className="grid md:grid-cols-5 gap-4">
          {AGENTS.map((a) => (
            <Card key={a.name} className={`border ${a.border} bg-gradient-to-b ${a.glow} to-transparent hover:scale-[1.02] transition-all duration-200 cursor-default`}>
              <CardContent className="pt-6 pb-5">
                <div className={`h-10 w-10 rounded-lg bg-gradient-to-br ${a.glow} to-transparent flex items-center justify-center mb-4 border ${a.border}`}>
                  <a.icon className={`h-5 w-5 ${a.color}`} />
                </div>
                <p className={`font-semibold text-sm mb-2 ${a.color}`}>{a.name}</p>
                <p className="text-xs text-muted-foreground leading-relaxed">{a.desc}</p>
              </CardContent>
            </Card>
          ))}
        </div>
      </section>

      {/* Features */}
      <section className="py-24 px-6 bg-muted/20">
        <div className="max-w-5xl mx-auto">
          <div className="text-center mb-16">
            <h2 className="text-3xl md:text-4xl font-bold mb-4">Built for Professionals</h2>
            <p className="text-muted-foreground">Enterprise-grade AI designed specifically for insurance workflows</p>
          </div>
          <div className="grid md:grid-cols-2 gap-10">
            {FEATURES.map((f) => (
              <div key={f.title} className="flex gap-5">
                <div className="h-12 w-12 rounded-xl bg-gradient-to-br from-indigo-500/10 to-violet-500/10 border border-indigo-500/20 flex items-center justify-center shrink-0">
                  <f.icon className="h-6 w-6 text-indigo-400" />
                </div>
                <div>
                  <h3 className="font-semibold text-lg mb-1.5">{f.title}</h3>
                  <p className="text-sm text-muted-foreground leading-relaxed">{f.desc}</p>
                </div>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* CTA */}
      <section className="py-24 px-6 text-center relative overflow-hidden">
        <div className="absolute inset-0 -z-10">
          <div className="absolute bottom-0 left-1/2 -translate-x-1/2 w-[600px] h-[400px] bg-gradient-to-t from-indigo-500/5 to-transparent rounded-full blur-3xl" />
        </div>
        <div className="max-w-2xl mx-auto">
          <h2 className="text-3xl md:text-4xl font-bold mb-4">Ready to transform your workflow?</h2>
          <p className="text-muted-foreground mb-8">Start using InsureIQ in under 60 seconds. No credit card required.</p>
          <Link href="/register">
            <Button size="lg" className="gap-2 bg-gradient-to-r from-indigo-500 to-violet-600 text-white border-0 hover:from-indigo-600 hover:to-violet-700 shadow-lg shadow-indigo-500/25 hover:shadow-indigo-500/40 transition-all">
              Get Started Free <ArrowRight className="h-4 w-4" />
            </Button>
          </Link>
        </div>
      </section>

      {/* Footer */}
      <footer className="border-t border-border/40 py-8 px-6">
        <div className="max-w-7xl mx-auto flex flex-col md:flex-row items-center justify-between gap-4">
          <div className="flex items-center gap-2">
            <div className="h-6 w-6 rounded-md bg-gradient-to-br from-indigo-500 to-violet-600 flex items-center justify-center">
              <ShieldCheck className="h-3.5 w-3.5 text-white" />
            </div>
            <span className="font-semibold text-sm">InsureIQ</span>
            <span className="text-muted-foreground text-xs ml-2">&copy; {new Date().getFullYear()}</span>
          </div>
          <div className="flex gap-6 text-sm text-muted-foreground">
            <Link href="/login" className="hover:text-foreground transition-colors">Login</Link>
            <Link href="/register" className="hover:text-foreground transition-colors">Register</Link>
            <Link href="/docs" className="hover:text-foreground transition-colors">API Docs</Link>
          </div>
        </div>
      </footer>
    </div>
  );
}
