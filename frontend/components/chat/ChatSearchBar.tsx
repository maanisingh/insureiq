"use client";

/**
 * ChatSearchBar — persistent semantic-search strip that lives between the
 * quick-action top bar and the Thread in the chat page.
 *
 * Always visible as a compact bar.  When the user submits a query, results
 * appear in a scrollable panel below (max-h-56).  A × button clears results
 * and collapses the panel.
 *
 * Calls the real backend search endpoints via lib/api.ts — no stubs.
 *   POST /search          → both sources
 *   GET  /search/global   → global KB only
 *   GET  /search/workspace/{id} → workspace docs only
 */

import { useState, useRef } from "react";
import { useSession } from "next-auth/react";
import { useAppStore } from "@/store";
import { api } from "@/lib/api";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Loader2, Search, Globe, Lock, X } from "lucide-react";
import { truncate } from "@/lib/utils";
import type { SearchResult } from "@/lib/types";

type SearchMode = "both" | "global" | "workspace";

export function ChatSearchBar() {
  const { data: session }     = useSession();
  const token                 = (session as any)?.access_token as string | undefined;
  const { activeWorkspaceId } = useAppStore();

  const [query,            setQuery]            = useState("");
  const [mode,             setMode]             = useState<SearchMode>("both");
  const [loading,          setLoading]          = useState(false);
  const [globalResults,    setGlobalResults]    = useState<SearchResult[]>([]);
  const [workspaceResults, setWorkspaceResults] = useState<SearchResult[]>([]);
  const [searched,         setSearched]         = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  const allResults: (SearchResult & { layer: "global" | "workspace" })[] = [
    ...globalResults.map((r) => ({ ...r, layer: "global"    as const })),
    ...workspaceResults.map((r) => ({ ...r, layer: "workspace" as const })),
  ].sort((a, b) => (b.score ?? 0) - (a.score ?? 0));

  const runSearch = async () => {
    const q = query.trim();
    if (!q || !token) return;
    setLoading(true);
    setSearched(false);
    try {
      if (mode === "both" && activeWorkspaceId) {
        const res = await api.search.both(q, activeWorkspaceId, 8, token) as any;
        setGlobalResults(res.global_results    ?? []);
        setWorkspaceResults(res.workspace_results ?? []);
      } else if (mode === "global") {
        const res = await api.search.global(q, 8, token) as any;
        setGlobalResults(res.results ?? []);
        setWorkspaceResults([]);
      } else if (mode === "workspace" && activeWorkspaceId) {
        const res = await api.search.workspace(activeWorkspaceId, q, 8, token) as any;
        setGlobalResults([]);
        setWorkspaceResults(res.results ?? []);
      }
    } catch (_) {
      /* silent — network errors shouldn't crash the chat page */
    } finally {
      setLoading(false);
      setSearched(true);
    }
  };

  const clearResults = () => {
    setSearched(false);
    setGlobalResults([]);
    setWorkspaceResults([]);
    setQuery("");
    inputRef.current?.focus();
  };

  const hasResults = searched && allResults.length > 0;
  const noResults  = searched && !loading && allResults.length === 0;

  return (
    <div className="border-b border-border shrink-0">
      {/* ── Search bar ─────────────────────────────────────────────────── */}
      <div className="flex items-center gap-2 px-3 py-2">
        {/* Mode tabs — compact pill toggles */}
        <div className="flex items-center gap-1 shrink-0">
          {(["both", "global", "workspace"] as SearchMode[]).map((m) => (
            <button
              key={m}
              type="button"
              onClick={() => setMode(m)}
              className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full border text-[11px] font-medium transition-all select-none ${
                mode === m
                  ? "bg-primary/10 border-primary/30 text-primary"
                  : "bg-muted/30 border-border/40 text-muted-foreground hover:bg-muted/60"
              }`}
            >
              {m === "global"    && <Globe    className="h-2.5 w-2.5" />}
              {m === "workspace" && <Lock     className="h-2.5 w-2.5" />}
              {m === "both"      && <Search   className="h-2.5 w-2.5" />}
              {m === "both" ? "Both" : m === "global" ? "Global KB" : "My Docs"}
            </button>
          ))}
        </div>

        {/* Input */}
        <div className="relative flex-1 min-w-0">
          <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-muted-foreground pointer-events-none" />
          <Input
            ref={inputRef}
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && runSearch()}
            placeholder="Semantic search — flood zone pricing, NCCI class codes, fraud patterns…"
            className="pl-8 h-8 text-sm"
          />
        </div>

        {/* Search button */}
        <Button
          size="sm"
          variant="outline"
          className="h-8 px-3 text-xs shrink-0"
          onClick={runSearch}
          disabled={loading || !query.trim()}
        >
          {loading
            ? <Loader2 className="h-3.5 w-3.5 animate-spin" />
            : <Search className="h-3.5 w-3.5" />}
        </Button>

        {/* Clear button — only shown when there are results */}
        {(hasResults || noResults) && (
          <button
            type="button"
            onClick={clearResults}
            className="shrink-0 h-8 w-8 flex items-center justify-center rounded-md text-muted-foreground hover:text-foreground hover:bg-muted/60 transition-colors"
            aria-label="Clear search results"
          >
            <X className="h-3.5 w-3.5" />
          </button>
        )}
      </div>

      {/* ── Results panel ───────────────────────────────────────────────── */}
      {hasResults && (
        <ScrollArea className="max-h-56 border-t border-border/50">
          <div className="px-3 py-2 space-y-1.5">
            <p className="text-[11px] text-muted-foreground font-medium px-1">
              {allResults.length} result{allResults.length !== 1 ? "s" : ""}
            </p>
            {allResults.map((r, i) => (
              <div
                key={i}
                className="rounded-lg border border-border/50 bg-card px-3 py-2 hover:bg-accent/50 transition-colors"
              >
                <div className="flex items-center gap-2 mb-1 flex-wrap">
                  <Badge
                    variant="outline"
                    className={`text-[10px] px-1.5 py-0 ${
                      r.layer === "global"
                        ? "border-indigo-500/30 text-indigo-400"
                        : "border-teal-500/30 text-teal-400"
                    }`}
                  >
                    {r.layer === "global"
                      ? <><Globe className="h-2.5 w-2.5 mr-1 inline" />Global</>
                      : <><Lock  className="h-2.5 w-2.5 mr-1 inline" />My Docs</>}
                  </Badge>
                  {r.score !== undefined && (
                    <span className="text-[10px] text-muted-foreground tabular-nums">
                      {(r.score * 100).toFixed(0)}% match
                    </span>
                  )}
                  {r.source && (
                    <span className="text-[10px] text-muted-foreground truncate max-w-[200px]">
                      {r.source}
                    </span>
                  )}
                </div>
                <p className="text-xs text-foreground/80 leading-relaxed">
                  {truncate(r.text, 300)}
                </p>
              </div>
            ))}
          </div>
        </ScrollArea>
      )}

      {/* No results */}
      {noResults && (
        <div className="px-3 pb-2 text-xs text-muted-foreground border-t border-border/50 pt-2">
          No results for <span className="font-medium">&ldquo;{query}&rdquo;</span>. Try different terms.
        </div>
      )}
    </div>
  );
}
