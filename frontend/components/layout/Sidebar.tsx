"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { usePathname, useRouter } from "next/navigation";
import { signOut, useSession } from "next-auth/react";
import {
  MessageSquare, FileText, Upload, Settings,
  LogOut, User, ChevronDown, Plus,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  DropdownMenu, DropdownMenuContent, DropdownMenuItem,
  DropdownMenuSeparator, DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger,
} from "@/components/ui/dialog";
import { cn } from "@/lib/utils";
import { useAppStore } from "@/store";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { toast } from "sonner";
import type { Workspace } from "@/lib/types";

const NAV = [
  { href: "/chat",      label: "Chat",      icon: MessageSquare },
  { href: "/documents", label: "Documents", icon: FileText      },
  { href: "/uploads",   label: "Uploads",   icon: Upload        },
  { href: "/settings",  label: "Settings",  icon: Settings      },
];

// ── New Workspace Dialog ──────────────────────────────────────────────────────

function NewWorkspaceDialog({ token }: { token: string }) {
  const [open, setOpen]   = useState(false);
  const [name, setName]   = useState("");
  const qc                = useQueryClient();
  const { setActiveWorkspace } = useAppStore();

  const createMutation = useMutation({
    mutationFn: () => api.workspaces.create({ name: name.trim() }, token),
    onSuccess: (ws) => {
      toast.success(`Workspace "${ws.name}" created`);
      qc.invalidateQueries({ queryKey: ["workspaces"] });
      setActiveWorkspace(ws.id);
      setName("");
      setOpen(false);
    },
    onError: (e: any) => toast.error(e.message ?? "Failed to create workspace"),
  });

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger render={
        <DropdownMenuItem
          onClick={(e) => { e.preventDefault(); setOpen(true); }}
          className="cursor-pointer"
        />
      }>
        <Plus className="h-4 w-4 mr-2" /> New workspace
      </DialogTrigger>
      <DialogContent className="max-w-sm">
        <DialogHeader>
          <DialogTitle>Create workspace</DialogTitle>
        </DialogHeader>
        <div className="space-y-4 pt-1">
          <Input
            placeholder="e.g. Commercial Lines, Personal Lines…"
            value={name}
            onChange={(e) => setName(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && name.trim() && createMutation.mutate()}
            autoFocus
          />
          <Button
            className="w-full"
            onClick={() => createMutation.mutate()}
            disabled={!name.trim() || createMutation.isPending}
          >
            {createMutation.isPending ? "Creating…" : "Create workspace"}
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}

// ── Sidebar ───────────────────────────────────────────────────────────────────

export function Sidebar() {
  const router                = useRouter();
  const pathname              = usePathname();
  const { data: session }     = useSession();
  const token                 = (session as any)?.access_token as string | undefined;
  const { activeWorkspaceId, setActiveWorkspace } = useAppStore();

  const { data: workspaces = [] } = useQuery<Workspace[]>({
    queryKey: ["workspaces", token],
    queryFn:  () => api.workspaces.list(token!),
    enabled:  !!token,
  });

  useEffect(() => {
    if (workspaces.length > 0 && !activeWorkspaceId) {
      setActiveWorkspace(workspaces[0].id);
    }
  }, [workspaces, activeWorkspaceId, setActiveWorkspace]);

  const activeWs = workspaces.find((w) => w.id === activeWorkspaceId) ?? workspaces[0];

  return (
    <aside className="flex flex-col h-full w-64 border-r border-border bg-card/50">
      {/* Logo */}
      <div className="px-4 py-4 border-b border-border">
        <span className="font-bold text-lg tracking-tight">InsureIQ</span>
      </div>

      {/* Workspace selector */}
      {workspaces.length > 0 && (
        <div className="px-3 py-3 border-b border-border">
          <DropdownMenu>
            <DropdownMenuTrigger className="w-full flex items-center justify-between gap-2 px-3 py-2 rounded-md border border-input bg-background text-xs hover:bg-accent transition-colors">
              <span className="truncate">{activeWs?.name ?? "Select workspace"}</span>
              <ChevronDown className="h-3 w-3 shrink-0" />
            </DropdownMenuTrigger>
            <DropdownMenuContent className="w-56">
              {workspaces.map((ws) => (
                <DropdownMenuItem
                  key={ws.id}
                  onClick={() => setActiveWorkspace(ws.id)}
                  className={cn(activeWorkspaceId === ws.id && "bg-primary/10 text-primary")}
                >
                  {ws.name}
                </DropdownMenuItem>
              ))}
              <DropdownMenuSeparator />
              {token && <NewWorkspaceDialog token={token} />}
            </DropdownMenuContent>
          </DropdownMenu>
        </div>
      )}

      {/* Nav */}
      <nav className="flex-1 px-3 py-3 space-y-1">
        {NAV.map(({ href, label, icon: Icon }) => (
          <Link
            key={href}
            href={href}
            className={cn(
              "flex items-center gap-3 px-3 py-2 rounded-lg text-sm transition-colors",
              pathname.startsWith(href)
                ? "bg-primary/10 text-primary font-medium"
                : "text-muted-foreground hover:text-foreground hover:bg-accent",
            )}
          >
            <Icon className="h-4 w-4" />
            {label}
          </Link>
        ))}
      </nav>

      {/* User */}
      <div className="px-3 py-3 border-t border-border">
        <DropdownMenu>
          <DropdownMenuTrigger className="w-full flex items-center gap-2 px-3 py-2 rounded-lg text-xs text-muted-foreground hover:text-foreground hover:bg-accent transition-colors">
            <div className="h-6 w-6 rounded-full bg-primary/20 flex items-center justify-center shrink-0">
              <User className="h-3 w-3" />
            </div>
            <span className="truncate">{session?.user?.email ?? "User"}</span>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="start">
            <DropdownMenuItem onClick={() => router.push("/settings")}>
              Profile &amp; Settings
            </DropdownMenuItem>
            <DropdownMenuSeparator />
            <DropdownMenuItem
              onClick={() => signOut({ callbackUrl: "/login" })}
              className="text-destructive"
            >
              <LogOut className="h-4 w-4 mr-2" /> Sign out
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      </div>
    </aside>
  );
}
