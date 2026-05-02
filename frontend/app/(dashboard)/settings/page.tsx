"use client";

import { useSession } from "next-auth/react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { api } from "@/lib/api";
import { useAppStore } from "@/store";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Collapsible, CollapsibleTrigger, CollapsibleContent } from "@/components/ui/collapsible";
import { toast } from "sonner";
import {
  Loader2, Plus, Trash2, Copy, Check, Key, Moon, Sun,
  ChevronRight, Terminal, Code2, Upload, Search, Shield, Zap,
  Activity,
} from "lucide-react";
import { useTheme } from "next-themes";
import { formatDate } from "@/lib/utils";
import type { ApiKey, ApiKeyCreated } from "@/lib/types";

/* ── Token Usage Card ───────────────────────────────────────────────────── */

function TokenUsageCard() {
  const { data: session } = useSession();
  const userId            = (session as any)?.user_id as string | undefined;
  const { getTokenUsage } = useAppStore();

  const usage        = getTokenUsage(userId ?? "");
  const totalTokens  = usage.inputTokens + usage.outputTokens;

  // Rough Bedrock Claude cost estimate (~$0.006 / 1K tokens blended average)
  const estimatedCost = ((totalTokens / 1000) * 0.006).toFixed(4);

  const fmt = (n: number) =>
    n >= 1_000_000 ? `${(n / 1_000_000).toFixed(2)}M`
    : n >= 1_000   ? `${(n / 1_000).toFixed(1)}K`
    : n.toString();

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <Activity className="h-5 w-5" /> Token Usage
        </CardTitle>
        <CardDescription>
          Your estimated token consumption across all chat sessions (4 chars ≈ 1 token).
          Actual Bedrock billing may differ.
        </CardDescription>
      </CardHeader>
      <CardContent>
        <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
          {[
            { label: "Input tokens",  value: fmt(usage.inputTokens),  sub: "prompt"     },
            { label: "Output tokens", value: fmt(usage.outputTokens), sub: "completion" },
            { label: "Total tokens",  value: fmt(totalTokens),        sub: "combined"   },
            { label: "Est. cost",     value: `$${estimatedCost}`,     sub: "~$0.006/1K" },
          ].map(({ label, value, sub }) => (
            <div key={label} className="rounded-lg border bg-muted/30 p-3 text-center">
              <p className="text-2xl font-bold tabular-nums">{value}</p>
              <p className="text-xs font-medium mt-0.5">{label}</p>
              <p className="text-[10px] text-muted-foreground">{sub}</p>
            </div>
          ))}
        </div>
        <p className="text-xs text-muted-foreground mt-3">
          {usage.sessions} chat {usage.sessions === 1 ? "request" : "requests"} tracked.
          Stats are stored locally in your browser and tied to your account.
        </p>
      </CardContent>
    </Card>
  );
}

/* ── Expandable doc section ─────────────────────────────────────────────── */

function DocSection({ icon: Icon, title, children }: {
  icon: React.ElementType;
  title: string;
  children: React.ReactNode;
}) {
  const [open, setOpen] = useState(false);
  return (
    <Collapsible open={open} onOpenChange={setOpen}>
      <CollapsibleTrigger className="w-full flex items-center gap-3 px-4 py-3 rounded-lg border border-border/50 bg-card hover:bg-accent/50 transition-all cursor-pointer group">
        <div className="h-8 w-8 rounded-lg bg-primary/10 flex items-center justify-center shrink-0">
          <Icon className="h-4 w-4 text-primary" />
        </div>
        <span className="text-sm font-medium flex-1 text-left">{title}</span>
        <ChevronRight className={`h-4 w-4 text-muted-foreground transition-transform duration-200 ${open ? "rotate-90" : ""}`} />
      </CollapsibleTrigger>
      <CollapsibleContent>
        <div className="mt-2 ml-11 space-y-3 text-sm text-muted-foreground pb-2">
          {children}
        </div>
      </CollapsibleContent>
    </Collapsible>
  );
}

function CodeBlock({ label, code }: { label: string; code: string }) {
  const [copied, setCopied] = useState(false);
  const copy = () => {
    navigator.clipboard.writeText(code);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };
  return (
    <div>
      {label && <p className="text-xs font-medium text-foreground mb-1.5">{label}</p>}
      <div className="relative rounded-lg bg-muted/80 border border-border/50 p-3 font-mono text-xs leading-relaxed overflow-x-auto">
        <button onClick={copy} className="absolute top-2 right-2 p-1 rounded hover:bg-accent transition-colors">
          {copied ? <Check className="h-3 w-3 text-green-400" /> : <Copy className="h-3 w-3 text-muted-foreground" />}
        </button>
        <pre className="whitespace-pre-wrap pr-8">{code}</pre>
      </div>
    </div>
  );
}

/* ── API Keys Section ───────────────────────────────────────────────────── */

function ApiKeysSection({ token }: { token: string }) {
  const qc = useQueryClient();
  const [name, setName] = useState("");
  const [newKey, setNewKey] = useState<ApiKeyCreated | null>(null);
  const [copied, setCopied] = useState(false);

  const { data: keys = [] } = useQuery<ApiKey[]>({
    queryKey: ["api-keys", token],
    queryFn: () => api.apiKeys.list(token),
    enabled: !!token,
  });

  const createMutation = useMutation({
    mutationFn: () => api.apiKeys.create(name, token),
    onSuccess: (data) => { setNewKey(data); setName(""); qc.invalidateQueries({ queryKey: ["api-keys"] }); },
    onError: (e: any) => toast.error(e.message ?? "Failed to create key"),
  });

  const revokeMutation = useMutation({
    mutationFn: (id: string) => api.apiKeys.revoke(id, token),
    onSuccess: () => { toast.success("Key revoked"); qc.invalidateQueries({ queryKey: ["api-keys"] }); },
    onError: (e: any) => toast.error(e.message ?? "Failed to revoke key"),
  });

  const copy = (text: string) => {
    navigator.clipboard.writeText(text);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2"><Key className="h-5 w-5" /> API Keys</CardTitle>
        <CardDescription>
          Use API keys to access InsureIQ programmatically.
          Keys are accepted as <code className="text-xs bg-muted px-1 py-0.5 rounded">Authorization: Bearer ak_...</code>
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        {/* Create */}
        <div className="flex gap-2">
          <Input
            placeholder="Key name (e.g. Production)"
            value={name}
            onChange={(e) => setName(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && name && createMutation.mutate()}
          />
          <Button onClick={() => createMutation.mutate()} disabled={!name || createMutation.isPending} size="sm">
            {createMutation.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : <Plus className="h-4 w-4" />}
          </Button>
        </div>

        {/* Newly created key */}
        {newKey && (
          <div className="p-3 rounded-lg border border-green-500/30 bg-green-500/5 space-y-2">
            <p className="text-xs font-medium text-green-400">Copy this key now — it won&apos;t be shown again</p>
            <div className="flex items-center gap-2 font-mono text-xs break-all bg-muted rounded p-2">
              <span className="flex-1">{newKey.raw_key}</span>
              <Button size="icon" variant="ghost" className="h-6 w-6" onClick={() => copy(newKey.raw_key)}>
                {copied ? <Check className="h-3 w-3 text-green-400" /> : <Copy className="h-3 w-3" />}
              </Button>
            </div>
            <Button size="sm" variant="outline" className="text-xs" onClick={() => setNewKey(null)}>
              I&apos;ve saved it
            </Button>
          </div>
        )}

        {/* Keys list */}
        {keys.length > 0 && (
          <div className="divide-y divide-border rounded-lg border overflow-hidden">
            {keys.map((k) => (
              <div key={k.id} className="flex items-center justify-between px-4 py-3 bg-card">
                <div>
                  <p className="text-sm font-medium">{k.name}</p>
                  <p className="text-xs text-muted-foreground font-mono mt-0.5">
                    {k.key_prefix} · Created {formatDate(k.created_at)}
                    {k.last_used_at && ` · Last used ${formatDate(k.last_used_at)}`}
                  </p>
                </div>
                <div className="flex items-center gap-2">
                  <Badge variant={k.is_active ? "default" : "secondary"} className="text-xs">
                    {k.is_active ? "Active" : "Revoked"}
                  </Badge>
                  {k.is_active && (
                    <Button
                      size="icon" variant="ghost"
                      className="text-destructive hover:text-destructive h-8 w-8"
                      onClick={() => revokeMutation.mutate(k.id)}
                      disabled={revokeMutation.isPending}
                    >
                      <Trash2 className="h-4 w-4" />
                    </Button>
                  )}
                </div>
              </div>
            ))}
          </div>
        )}

        {/* Expandable usage documentation */}
        <div className="space-y-2 pt-2">
          <p className="text-sm font-semibold">Usage Documentation</p>

          <DocSection icon={Shield} title="Authentication">
            <p>All API requests require a Bearer token in the <code className="text-xs bg-muted px-1 rounded">Authorization</code> header. You can use either a JWT token (from login) or an API key (prefixed with <code className="text-xs bg-muted px-1 rounded">ak_</code>).</p>
            <CodeBlock label="" code={`Authorization: Bearer ak_your_api_key_here`} />
            <p>API keys never expire but can be revoked at any time. Use separate keys for different integrations so you can revoke them independently.</p>
          </DocSection>

          <DocSection icon={Terminal} title="Chat Streaming (SSE)">
            <p>Send messages to the AI and receive real-time streaming responses via Server-Sent Events. The stream emits events: <code className="text-xs bg-muted px-1 rounded">routing</code>, <code className="text-xs bg-muted px-1 rounded">token</code>, <code className="text-xs bg-muted px-1 rounded">tool_call</code>, <code className="text-xs bg-muted px-1 rounded">done</code>.</p>
            <CodeBlock label="curl" code={`curl -N -X POST https://ai.cipherx.co.uk/api/chat/stream \\
  -H "Authorization: Bearer ak_your_key" \\
  -H "Content-Type: application/json" \\
  -d '{
    "workspace_id": "your-workspace-id",
    "message": "Calculate WC premium for a roofer, $2M payroll, NCCI 5403"
  }'`} />
            <CodeBlock label="Python" code={`import requests

resp = requests.post(
    "https://ai.cipherx.co.uk/api/chat/stream",
    headers={"Authorization": "Bearer ak_your_key"},
    json={
        "workspace_id": "your-workspace-id",
        "message": "What does my auto policy cover?"
    },
    stream=True,
)
for line in resp.iter_lines():
    if line.startswith(b"data: "):
        print(line.decode()[6:])`} />
            <CodeBlock label="Node.js" code={`const resp = await fetch("https://ai.cipherx.co.uk/api/chat/stream", {
  method: "POST",
  headers: {
    "Authorization": "Bearer ak_your_key",
    "Content-Type": "application/json",
  },
  body: JSON.stringify({
    workspace_id: "your-workspace-id",
    message: "Draft a commercial auto policy",
  }),
});

const reader = resp.body.getReader();
const decoder = new TextDecoder();
while (true) {
  const { done, value } = await reader.read();
  if (done) break;
  console.log(decoder.decode(value));
}`} />
          </DocSection>

          <DocSection icon={Code2} title="Policy Management">
            <p>Create, list, update, and delete insurance policies in your workspace.</p>
            <CodeBlock label="Create a policy" code={`curl -X POST https://ai.cipherx.co.uk/api/policies \\
  -H "Authorization: Bearer ak_your_key" \\
  -H "Content-Type: application/json" \\
  -d '{
    "workspace_id": "your-workspace-id",
    "policy_type": "auto",
    "policy_data": {
      "insured_name": "Acme Corp",
      "vehicles": 5,
      "coverage": {"liability": "1000000 CSL"}
    }
  }'`} />
            <CodeBlock label="List policies" code={`curl https://ai.cipherx.co.uk/api/policies?workspace_id=your-workspace-id \\
  -H "Authorization: Bearer ak_your_key"`} />
          </DocSection>

          <DocSection icon={Upload} title="Document Upload">
            <p>Upload documents (PDF, DOCX, TXT, CSV, Excel) to your workspace. They are automatically extracted, chunked, and indexed for AI search within seconds.</p>
            <CodeBlock label="Upload a file" code={`curl -X POST https://ai.cipherx.co.uk/api/uploads \\
  -H "Authorization: Bearer ak_your_key" \\
  -F "workspace_id=your-workspace-id" \\
  -F "file=@/path/to/policy-document.pdf"`} />
            <CodeBlock label="Check extraction status" code={`curl https://ai.cipherx.co.uk/api/uploads?workspace_id=your-workspace-id \\
  -H "Authorization: Bearer ak_your_key"

# Response includes extraction_status: "pending" | "processing" | "done" | "failed"`} />
          </DocSection>

          <DocSection icon={Search} title="Semantic Search">
            <p>Search across the global insurance knowledge base (547K records) and/or your workspace documents using natural language queries.</p>
            <CodeBlock label="Global search" code={`curl "https://ai.cipherx.co.uk/api/search/global?query=auto+insurance+deductibles&limit=5" \\
  -H "Authorization: Bearer ak_your_key"`} />
            <CodeBlock label="Workspace search" code={`curl "https://ai.cipherx.co.uk/api/search/workspace/your-workspace-id?query=coverage+limits&limit=5" \\
  -H "Authorization: Bearer ak_your_key"`} />
            <CodeBlock label="Combined search (both)" code={`curl -X POST https://ai.cipherx.co.uk/api/search \\
  -H "Authorization: Bearer ak_your_key" \\
  -H "Content-Type: application/json" \\
  -d '{"query": "loss ratio benchmarks", "workspace_id": "your-workspace-id", "limit": 10}'`} />
          </DocSection>

          <DocSection icon={Zap} title="Rate Limits & Best Practices">
            <p><strong>Rate limits:</strong> 60 requests/minute per API key for standard endpoints. Chat streaming is limited to 10 concurrent connections per user.</p>
            <p><strong>Best practices:</strong></p>
            <ul className="list-disc list-inside space-y-1 ml-2">
              <li>Use separate API keys per integration (production, staging, CI/CD)</li>
              <li>Rotate keys periodically — revoke and create new ones</li>
              <li>Never embed keys in client-side code or commit to version control</li>
              <li>Use environment variables: <code className="text-xs bg-muted px-1 rounded">INSUREIQ_API_KEY</code></li>
              <li>Handle SSE reconnection gracefully for chat streaming</li>
              <li>Cache search results client-side when appropriate (results are stable for ~30s)</li>
            </ul>
          </DocSection>
        </div>
      </CardContent>
    </Card>
  );
}

/* ── Main Settings Page ─────────────────────────────────────────────────── */

export default function SettingsPage() {
  const { data: session } = useSession();
  const token = (session as any)?.access_token as string | undefined;
  const { setTheme, theme } = useTheme();

  return (
    <div className="p-6 max-w-3xl mx-auto space-y-6">
      <h1 className="text-2xl font-bold">Settings</h1>

      {/* Theme */}
      <Card>
        <CardHeader>
          <CardTitle>Appearance</CardTitle>
          <CardDescription>Choose your preferred theme</CardDescription>
        </CardHeader>
        <CardContent className="flex gap-3">
          <Button variant={theme === "light" ? "default" : "outline"} size="sm" onClick={() => setTheme("light")}>
            <Sun className="h-4 w-4 mr-2" /> Light
          </Button>
          <Button variant={theme === "dark" ? "default" : "outline"} size="sm" onClick={() => setTheme("dark")}>
            <Moon className="h-4 w-4 mr-2" /> Dark
          </Button>
          <Button variant={theme === "system" ? "default" : "outline"} size="sm" onClick={() => setTheme("system")}>
            System
          </Button>
        </CardContent>
      </Card>

      {/* Account info */}
      <Card>
        <CardHeader>
          <CardTitle>Account</CardTitle>
          <CardDescription>Your InsureIQ account details</CardDescription>
        </CardHeader>
        <CardContent className="space-y-3 text-sm">
          <div className="flex justify-between py-2 border-b border-border">
            <span className="text-muted-foreground">Email</span>
            <span>{session?.user?.email ?? "—"}</span>
          </div>
          <div className="flex justify-between py-2 border-b border-border">
            <span className="text-muted-foreground">Name</span>
            <span>{session?.user?.name ?? "—"}</span>
          </div>
        </CardContent>
      </Card>

      {/* Token usage */}
      <TokenUsageCard />

      {/* API Keys */}
      {token && <ApiKeysSection token={token} />}
    </div>
  );
}
