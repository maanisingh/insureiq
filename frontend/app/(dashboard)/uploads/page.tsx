"use client";

import { useSession } from "next-auth/react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useCallback, useState } from "react";
import { useAppStore } from "@/store";
import { api } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { toast } from "sonner";
import { Upload, Trash2, Loader2, FileText, CheckCircle, XCircle, Clock } from "lucide-react";
import { formatBytes, formatDate } from "@/lib/utils";
import type { UploadListItem } from "@/lib/types";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

function StatusIcon({ status }: { status: string }) {
  if (status === "done")       return <CheckCircle className="h-4 w-4 text-green-400" />;
  if (status === "failed")     return <XCircle     className="h-4 w-4 text-red-400" />;
  if (status === "processing") return <Loader2     className="h-4 w-4 text-blue-400 animate-spin" />;
  return <Clock className="h-4 w-4 text-muted-foreground" />;
}

const STATUS_LABEL: Record<string, string> = {
  pending:    "Pending",
  processing: "Extracting…",
  done:       "Indexed",
  failed:     "Failed",
};

export default function DocumentsPage() {
  const { data: session }       = useSession();
  const token                   = (session as any)?.access_token as string | undefined;
  const { activeWorkspaceId }   = useAppStore();
  const qc                      = useQueryClient();
  const [dragging,  setDragging]  = useState(false);
  const [uploading, setUploading] = useState(false);

  const { data: uploads = [] } = useQuery<UploadListItem[]>({
    queryKey:        ["uploads", activeWorkspaceId, token],
    queryFn:         () => api.uploads.list(activeWorkspaceId!, token!),
    enabled:         !!(activeWorkspaceId && token),
    refetchInterval: (query) =>
      (query.state.data as UploadListItem[] | undefined)?.some(
        (u) => u.extraction_status === "pending" || u.extraction_status === "processing",
      ) ? 3000 : false,
  });

  const deleteMutation = useMutation({
    mutationFn: (id: string) => api.uploads.delete(id, activeWorkspaceId!, token!),
    onSuccess:  () => { toast.success("Document deleted"); qc.invalidateQueries({ queryKey: ["uploads"] }); },
    onError:    (e: any) => toast.error(e.message ?? "Delete failed"),
  });

  const uploadFile = useCallback(async (file: File) => {
    if (!activeWorkspaceId || !token) return;
    setUploading(true);
    try {
      const form = new FormData();
      form.append("workspace_id", activeWorkspaceId);
      form.append("file", file);
      const res = await fetch(`${API_URL}/uploads`, {
        method:  "POST",
        headers: { Authorization: `Bearer ${token}` },
        body:    form,
      });
      if (!res.ok) throw new Error(await res.text());
      toast.success(`${file.name} uploaded — extracting…`);
      qc.invalidateQueries({ queryKey: ["uploads"] });
    } catch (e: any) {
      toast.error(e.message ?? "Upload failed");
    } finally {
      setUploading(false);
    }
  }, [activeWorkspaceId, token, qc]);

  const handleDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setDragging(false);
    Array.from(e.dataTransfer.files).forEach(uploadFile);
  }, [uploadFile]);

  return (
    <div className="p-6 max-w-4xl mx-auto space-y-6">
      <div>
        <h1 className="text-2xl font-bold">Uploads</h1>
        <p className="text-sm text-muted-foreground mt-1">
          Upload files to your workspace knowledge base. The AI searches them automatically.
        </p>
      </div>

      {/* Drop zone */}
      <div
        onDragOver={(e) => { e.preventDefault(); setDragging(true); }}
        onDragLeave={() => setDragging(false)}
        onDrop={handleDrop}
        className={`border-2 border-dashed rounded-xl p-12 text-center transition-colors cursor-pointer ${
          dragging ? "border-primary bg-primary/5" : "border-border hover:border-primary/50 hover:bg-muted/30"
        }`}
        onClick={() => document.getElementById("file-input")?.click()}
      >
        <input
          id="file-input"
          type="file"
          multiple
          accept=".pdf,.docx,.txt,.csv,.xlsx,.xls"
          className="hidden"
          onChange={(e) => Array.from(e.target.files ?? []).forEach(uploadFile)}
        />
        {uploading ? (
          <Loader2 className="h-8 w-8 animate-spin text-muted-foreground mx-auto mb-3" />
        ) : (
          <Upload className="h-8 w-8 text-muted-foreground mx-auto mb-3" />
        )}
        <p className="font-medium">Drop files here or click to browse</p>
        <p className="text-sm text-muted-foreground mt-1">PDF · DOCX · TXT · CSV · Excel — max 50 MB</p>
        <p className="text-xs text-muted-foreground mt-2">Extracted by Bedrock Claude · Indexed instantly into your workspace</p>
      </div>

      {/* Document list */}
      {uploads.length > 0 && (
        <div className="space-y-2">
          <h2 className="text-sm font-semibold text-muted-foreground uppercase tracking-wider">
            Your documents ({uploads.length})
          </h2>
          {uploads.map((u) => (
            <div key={u.id} className="flex items-center gap-4 p-4 rounded-lg border bg-card hover:bg-card/80 transition-colors">
              <FileText className="h-8 w-8 text-muted-foreground shrink-0" />
              <div className="flex-1 min-w-0">
                <p className="font-medium text-sm truncate">{u.original_filename ?? u.filename}</p>
                <div className="flex items-center gap-3 mt-1">
                  <span className="text-xs text-muted-foreground uppercase">{u.file_type}</span>
                  <span className="text-xs text-muted-foreground">{formatBytes(u.file_size)}</span>
                  {u.extraction_status === "done" && (
                    <span className="text-xs text-muted-foreground">{u.chunk_count} chunks</span>
                  )}
                  <span className="text-xs text-muted-foreground">{formatDate(u.uploaded_at)}</span>
                </div>
                {u.extraction_status === "processing" && (
                  <div className="h-1 mt-2 w-full bg-muted rounded-full overflow-hidden">
                    <div className="h-full w-1/3 bg-blue-500 rounded-full animate-pulse" />
                  </div>
                )}
              </div>
              <div className="flex items-center gap-2 shrink-0">
                <div className="flex items-center gap-1.5 text-xs">
                  <StatusIcon status={u.extraction_status} />
                  <span className={u.extraction_status === "done" ? "text-green-400" : "text-muted-foreground"}>
                    {STATUS_LABEL[u.extraction_status] ?? u.extraction_status}
                  </span>
                </div>
                <Button
                  size="icon" variant="ghost"
                  className="text-destructive hover:text-destructive h-8 w-8"
                  onClick={() => deleteMutation.mutate(u.id)}
                  disabled={deleteMutation.isPending}
                >
                  <Trash2 className="h-4 w-4" />
                </Button>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
