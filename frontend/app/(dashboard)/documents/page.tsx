"use client";

/**
 * Documents page — AI-generated documents from chat.
 *
 * PolicyAgent  → generate_policy_document()  → saved + indexed automatically
 * UWAgent      → generate_underwriting_memo() → saved + indexed automatically
 *
 * Layout: split panel
 *   Left  (35%) — document list with filter pills
 *   Right (65%) — full document viewer with Download PDF + Delete
 *
 * Download: uses window.print() with a print stylesheet — browser-native PDF,
 *           zero dependencies, professional output.
 *
 * RAG badge: "In RAG ✓" when indexed_at is set, "Indexing…" spinner otherwise.
 *            List refetches every 3s until all docs are indexed.
 */

import { useState } from "react";
import { useSession } from "next-auth/react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useAppStore } from "@/store";
import { api } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { ScrollArea } from "@/components/ui/scroll-area";
import { toast } from "sonner";
import {
  FileText, ShieldCheck, Loader2, Trash2, Download,
  CheckCircle, Clock, Bot,
} from "lucide-react";
import { formatDate } from "@/lib/utils";
import type { GeneratedDocSummary, GeneratedDoc, GeneratedDocType } from "@/lib/types";

// ── Type helpers ─────────────────────────────────────────────────────────────

const DOC_META: Record<GeneratedDocType | "all", { label: string; icon: React.ElementType; color: string }> = {
  all:                { label: "All",          icon: Bot,        color: "text-muted-foreground" },
  policy_document:    { label: "Policy Doc",   icon: FileText,   color: "text-blue-400"  },
  underwriting_memo:  { label: "UW Memo",      icon: ShieldCheck, color: "text-purple-400" },
};

function DocTypeBadge({ type }: { type: GeneratedDocType }) {
  const m    = DOC_META[type];
  const Icon = m.icon;
  return (
    <span className={`inline-flex items-center gap-1 text-[10px] font-medium ${m.color}`}>
      <Icon className="h-3 w-3" />
      {m.label}
    </span>
  );
}

function IndexedBadge({ indexedAt }: { indexedAt: string | null }) {
  if (indexedAt) {
    return (
      <span className="inline-flex items-center gap-1 text-[10px] text-green-400 font-medium">
        <CheckCircle className="h-3 w-3" /> In RAG
      </span>
    );
  }
  return (
    <span className="inline-flex items-center gap-1 text-[10px] text-muted-foreground">
      <Loader2 className="h-3 w-3 animate-spin" /> Indexing…
    </span>
  );
}

// ── PDF download via window.print() ─────────────────────────────────────────

function downloadAsPdf(title: string, content: string) {
  const win = window.open("", "_blank");
  if (!win) return;
  win.document.write(`
    <!DOCTYPE html>
    <html>
    <head>
      <meta charset="utf-8">
      <title>${title}</title>
      <style>
        body {
          font-family: "Courier New", monospace;
          font-size: 11px;
          line-height: 1.6;
          margin: 40px;
          color: #000;
          white-space: pre-wrap;
          word-break: break-word;
        }
        h1 { font-size: 14px; border-bottom: 1px solid #000; padding-bottom: 6px; margin-bottom: 16px; }
        @media print {
          body { margin: 20mm; }
        }
      </style>
    </head>
    <body>
      <h1>${title}</h1>
      ${content.replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;")}
    </body>
    </html>
  `);
  win.document.close();
  setTimeout(() => { win.print(); }, 400);
}

// ── Main page ────────────────────────────────────────────────────────────────

export default function DocumentsPage() {
  const { data: session }     = useSession();
  const token                 = (session as any)?.access_token as string | undefined;
  const { activeWorkspaceId } = useAppStore();
  const qc                    = useQueryClient();

  const [filter,      setFilter]      = useState<"all" | GeneratedDocType>("all");
  const [selectedId,  setSelectedId]  = useState<string | null>(null);

  // ── List query — refetch every 3s until everything is indexed ──────────────
  const { data: docs = [], isLoading } = useQuery<GeneratedDocSummary[]>({
    queryKey: ["gen-docs", activeWorkspaceId, filter, token],
    queryFn:  () =>
      api.generatedDocs.list(
        activeWorkspaceId!,
        token!,
        filter === "all" ? undefined : filter,
      ),
    enabled:  !!(activeWorkspaceId && token),
    refetchInterval: (query) => {
      const list = query.state.data as GeneratedDocSummary[] | undefined;
      return list?.some((d) => !d.indexed_at) ? 3000 : false;
    },
  });

  // ── Full doc fetch — only when user selects a doc ─────────────────────────
  const { data: selected, isFetching: loadingDoc } = useQuery<GeneratedDoc>({
    queryKey: ["gen-doc", selectedId, token],
    queryFn:  () => api.generatedDocs.get(selectedId!, activeWorkspaceId!, token!),
    enabled:  !!(selectedId && activeWorkspaceId && token),
  });

  // ── Delete ────────────────────────────────────────────────────────────────
  const deleteMutation = useMutation({
    mutationFn: (id: string) => api.generatedDocs.delete(id, activeWorkspaceId!, token!),
    onSuccess: (_d, id) => {
      toast.success("Document deleted");
      qc.invalidateQueries({ queryKey: ["gen-docs"] });
      if (selectedId === id) setSelectedId(null);
    },
    onError: (e: any) => toast.error(e.message ?? "Delete failed"),
  });

  return (
    <div className="flex h-full overflow-hidden">
      {/* ── LEFT: list panel ───────────────────────────────────────────────── */}
      <div className="w-[35%] min-w-[260px] border-r border-border flex flex-col h-full">
        {/* Header */}
        <div className="px-4 pt-4 pb-3 border-b border-border shrink-0">
          <h1 className="text-xl font-bold">Documents</h1>
          <p className="text-xs text-muted-foreground mt-0.5">
            AI-generated policy docs &amp; underwriting memos
          </p>
          {/* Filter pills */}
          <div className="flex gap-1.5 mt-3">
            {(["all", "policy_document", "underwriting_memo"] as const).map((f) => (
              <button
                key={f}
                type="button"
                onClick={() => setFilter(f)}
                className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full border text-[11px] font-medium transition-all ${
                  filter === f
                    ? "bg-primary/10 border-primary/30 text-primary"
                    : "bg-muted/30 border-border/40 text-muted-foreground hover:bg-muted/60"
                }`}
              >
                {(() => { const m = DOC_META[f]; const I = m.icon; return <I className="h-2.5 w-2.5" />; })()}
                {DOC_META[f].label}
              </button>
            ))}
          </div>
        </div>

        {/* Doc list */}
        <ScrollArea className="flex-1">
          {isLoading ? (
            <div className="flex justify-center py-12">
              <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
            </div>
          ) : docs.length === 0 ? (
            <div className="px-4 py-12 text-center text-muted-foreground">
              <Bot className="h-10 w-10 mx-auto mb-3 opacity-30" />
              <p className="text-sm font-medium">No documents yet</p>
              <p className="text-xs mt-1 leading-relaxed">
                Ask the AI to draft a policy or underwriting memo in chat — it will appear here automatically.
              </p>
            </div>
          ) : (
            <div className="p-2 space-y-1">
              {docs.map((d) => (
                <button
                  key={d.id}
                  type="button"
                  onClick={() => setSelectedId(d.id)}
                  className={`w-full text-left px-3 py-2.5 rounded-lg border transition-all group ${
                    selectedId === d.id
                      ? "bg-primary/10 border-primary/30"
                      : "bg-card border-border/50 hover:bg-accent hover:border-border"
                  }`}
                >
                  <div className="flex items-start justify-between gap-2">
                    <p className="text-sm font-medium truncate flex-1">{d.title}</p>
                    <button
                      type="button"
                      onClick={(e) => { e.stopPropagation(); deleteMutation.mutate(d.id); }}
                      disabled={deleteMutation.isPending}
                      className="shrink-0 opacity-0 group-hover:opacity-100 text-destructive hover:text-destructive p-0.5 rounded transition-opacity"
                      aria-label="Delete document"
                    >
                      <Trash2 className="h-3.5 w-3.5" />
                    </button>
                  </div>
                  <div className="flex items-center gap-2 mt-1 flex-wrap">
                    <DocTypeBadge type={d.doc_type} />
                    <span className="text-[10px] text-muted-foreground">
                      {(d.word_count ?? 0).toLocaleString()} words
                    </span>
                    <span className="text-[10px] text-muted-foreground">
                      {formatDate(d.created_at)}
                    </span>
                  </div>
                  <div className="mt-1">
                    <IndexedBadge indexedAt={d.indexed_at} />
                  </div>
                </button>
              ))}
            </div>
          )}
        </ScrollArea>
      </div>

      {/* ── RIGHT: content panel ───────────────────────────────────────────── */}
      <div className="flex-1 flex flex-col h-full overflow-hidden">
        {!selectedId ? (
          <div className="flex flex-col items-center justify-center h-full text-muted-foreground">
            <FileText className="h-12 w-12 mb-4 opacity-20" />
            <p className="text-sm">Select a document to view</p>
          </div>
        ) : loadingDoc ? (
          <div className="flex items-center justify-center h-full">
            <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
          </div>
        ) : selected ? (
          <>
            {/* Document toolbar */}
            <div className="flex items-center justify-between px-5 py-3 border-b border-border shrink-0 gap-4">
              <div className="flex-1 min-w-0">
                <h2 className="font-semibold text-base truncate">{selected.title}</h2>
                <div className="flex items-center gap-3 mt-0.5 flex-wrap">
                  <DocTypeBadge type={selected.doc_type} />
                  <span className="text-xs text-muted-foreground">
                    {(selected.word_count ?? 0).toLocaleString()} words
                  </span>
                  <span className="text-xs text-muted-foreground">
                    {formatDate(selected.created_at)}
                  </span>
                  <IndexedBadge indexedAt={selected.indexed_at} />
                </div>
              </div>
              <div className="flex items-center gap-2 shrink-0">
                <Button
                  size="sm"
                  variant="outline"
                  className="gap-2 text-xs"
                  onClick={() => downloadAsPdf(selected.title, selected.content)}
                >
                  <Download className="h-3.5 w-3.5" />
                  Download PDF
                </Button>
                <Button
                  size="sm"
                  variant="ghost"
                  className="text-destructive hover:text-destructive gap-2 text-xs"
                  onClick={() => deleteMutation.mutate(selected.id)}
                  disabled={deleteMutation.isPending}
                >
                  <Trash2 className="h-3.5 w-3.5" />
                  Delete
                </Button>
              </div>
            </div>

            {/* Document content */}
            <ScrollArea className="flex-1 px-5 py-4">
              <pre className="font-mono text-xs leading-relaxed whitespace-pre-wrap text-foreground/90">
                {selected.content}
              </pre>
            </ScrollArea>
          </>
        ) : null}
      </div>
    </div>
  );
}
