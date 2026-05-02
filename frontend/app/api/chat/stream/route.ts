import { auth } from "@/auth";
import { NextRequest } from "next/server";

const API_URL = process.env.API_URL ?? process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export async function POST(req: NextRequest) {
  const session = await auth();
  const token   = (session as any)?.access_token;
  if (!token) return new Response("Unauthorized", { status: 401 });

  const body = await req.json();

  const upstream = await fetch(`${API_URL}/chat/stream`, {
    method:  "POST",
    headers: {
      "Content-Type":  "application/json",
      "Authorization": `Bearer ${token}`,
    },
    body: JSON.stringify(body),
  });

  if (!upstream.ok) {
    return new Response(await upstream.text(), { status: upstream.status });
  }

  return new Response(upstream.body, {
    headers: {
      "Content-Type":   "text/event-stream",
      "Cache-Control":  "no-cache",
      "Connection":     "keep-alive",
      "X-Accel-Buffering": "no",
    },
  });
}
