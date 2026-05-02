"""
Chat router — send messages, get history, manage sessions.
"""

import os
import uuid
import json
import asyncio

from fastapi import APIRouter, Depends, HTTPException, status, Request
from fastapi.responses import StreamingResponse

from app.routers.auth import get_current_user
from app.database import get_db_connection
from app.schemas.chat import ChatMessage, ChatResponse

router = APIRouter()


def _redis():
    import redis
    return redis.Redis(
        host=os.getenv("REDIS_HOST", "localhost"),
        port=int(os.getenv("REDIS_PORT", "6379")),
        db=int(os.getenv("REDIS_DB", "0")),
        decode_responses=True,
    )


def _sse(data: dict) -> str:
    """Format a dict as an SSE data line."""
    return f"data: {json.dumps(data)}\n\n"


@router.post("", response_model=ChatResponse)
def chat(message: ChatMessage, current_user: dict = Depends(get_current_user)):
    """Send a message and receive an AI-generated response with RAG sources."""
    conn = get_db_connection()
    cur  = conn.cursor()
    try:
        cur.execute(
            "SELECT id FROM workspaces WHERE id = %s AND user_id = %s",
            (message.workspace_id, current_user["id"]),
        )
        if not cur.fetchone():
            raise HTTPException(status_code=404, detail="Workspace not found")
    finally:
        cur.close()
        conn.close()

    if not message.session_id:
        message.session_id = str(uuid.uuid4())[:8]

    from agents.insurance_agent import agent
    result = agent.chat(
        message=message.message,
        workspace_id=message.workspace_id,
        session_id=message.session_id,
        user_id=current_user["id"],
    )

    return ChatResponse(
        session_id=result["session_id"],
        response=result["response"],
        sources=result.get("sources", []),
        agent_used=result.get("agent_used"),
    )


@router.post("/stream")
async def chat_stream(message: ChatMessage, current_user: dict = Depends(get_current_user)):
    """Stream chat response as Server-Sent Events.

    SSE event types:
      routing    — {"type":"routing",    "agent":"PricingAgent"}
      tool_call  — {"type":"tool_call",  "tool":"calculate_auto_premium", "agent":"..."}
      tool_result— {"type":"tool_result","tool":"...", "preview":"..."}
      token      — {"type":"token",      "content":"partial text"}
      done       — {"type":"done",       "sources":[...], "agent_used":"...", "session_id":"..."}
      error      — {"type":"error",      "message":"..."}
    """
    # Validate workspace
    conn = get_db_connection()
    cur  = conn.cursor()
    try:
        cur.execute(
            "SELECT id FROM workspaces WHERE id = %s AND user_id = %s",
            (message.workspace_id, current_user["id"]),
        )
        if not cur.fetchone():
            raise HTTPException(status_code=404, detail="Workspace not found")
    finally:
        cur.close()
        conn.close()

    if not message.session_id:
        message.session_id = str(uuid.uuid4())[:8]

    session_id      = message.session_id
    workspace_id    = message.workspace_id
    user_id         = current_user["id"]
    preferred_agent = message.preferred_agent
    enabled_sources = message.enabled_sources  # list[str] | None

    async def generate():
        try:
            from agents.multi_agent import build_insurance_team
            from agents.insurance_agent import _load_history, _save_messages

            history = _load_history(workspace_id, session_id)
            team    = build_insurance_team(workspace_id, enabled_sources=enabled_sources)

            # Build task with history context
            task = message.message
            if history:
                recent = history[-6:]
                hist_text = "\n".join(
                    f"{m['role'].upper()}: {m.get('content','')[:300]}"
                    for m in recent if m.get("content")
                )
                if hist_text:
                    task = f"[CONVERSATION HISTORY]\n{hist_text}\n\n[CURRENT QUERY]\n{message.message}"

            # Force-route to a specific agent if the user requested it
            if preferred_agent:
                task = (
                    f"[MANDATORY ROUTING: You MUST select {preferred_agent} to handle this query. "
                    f"Do not select any other agent.]\n\n{task}"
                )

            agents_used   = set()
            full_response = ""
            sources       = []

            async for msg in team.run_stream(task=task):
                if not hasattr(msg, "source"):
                    continue

                source = msg.source
                content = msg.content

                # Routing event — first time we see a new agent
                if source not in agents_used and source not in ("user", "_selector"):
                    agents_used.add(source)
                    yield _sse({"type": "routing", "agent": source})
                    await asyncio.sleep(0)

                if isinstance(content, str) and content.strip():
                    # Stream the text word-by-word for smooth UX
                    words = content.split()
                    accumulated = ""
                    for word in words:
                        accumulated += ("" if not accumulated else " ") + word
                        yield _sse({"type": "token", "content": accumulated})
                        await asyncio.sleep(0.02)
                    full_response = content

                elif isinstance(content, list):
                    # Tool calls and tool results
                    for item in content:
                        if hasattr(item, "type"):
                            item_type = item.type if hasattr(item, "type") else ""
                            if item_type == "tool-call" or (isinstance(item, dict) and item.get("type") == "tool-call"):
                                tool_name = getattr(item, "name", None) or (item.get("name") if isinstance(item, dict) else "tool")
                                yield _sse({"type": "tool_call", "tool": tool_name, "agent": source})
                                await asyncio.sleep(0)
                        elif isinstance(item, dict):
                            if item.get("type") == "tool-call":
                                yield _sse({"type": "tool_call", "tool": item.get("name", "tool"), "agent": source})
                                await asyncio.sleep(0)

            # Persist messages
            new_msgs = [
                {"id": str(uuid.uuid4()), "role": "user",      "content": message.message},
                {"id": str(uuid.uuid4()), "role": "assistant", "content": full_response,
                 "agent": ", ".join(a for a in agents_used if a not in ("user",))},
            ]
            _save_messages(workspace_id, session_id, new_msgs)

            # Done event
            yield _sse({
                "type":       "done",
                "sources":    sources,
                "agent_used": ", ".join(a for a in agents_used if a not in ("user",)),
                "session_id": session_id,
            })

        except Exception as e:
            yield _sse({"type": "error", "message": str(e)})

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control":    "no-cache",
            "X-Accel-Buffering": "no",
            "Connection":       "keep-alive",
        },
    )


@router.post("/session")
def create_session(workspace_id: str, current_user: dict = Depends(get_current_user)):
    """Create a new chat session and return its ID."""
    conn = get_db_connection()
    cur  = conn.cursor()
    try:
        cur.execute(
            "SELECT id FROM workspaces WHERE id = %s AND user_id = %s",
            (workspace_id, current_user["id"]),
        )
        if not cur.fetchone():
            raise HTTPException(status_code=404, detail="Workspace not found")
    finally:
        cur.close()
        conn.close()

    session_id = str(uuid.uuid4())[:8]
    return {"session_id": session_id, "workspace_id": workspace_id}


@router.get("/history")
def get_chat_history(
    workspace_id: str,
    session_id:   str = None,
    limit:        int = 50,
    current_user: dict = Depends(get_current_user),
):
    """Get chat history.

    - With session_id: returns messages for that session (Redis-first).
    - Without session_id: returns list of recent sessions.
    """
    conn = get_db_connection()
    cur  = conn.cursor()
    try:
        cur.execute(
            "SELECT id FROM workspaces WHERE id = %s AND user_id = %s",
            (workspace_id, current_user["id"]),
        )
        if not cur.fetchone():
            raise HTTPException(status_code=404, detail="Workspace not found")

        if session_id:
            r        = _redis()
            key      = f"chat:{workspace_id}:{session_id}"
            messages = r.lrange(key, 0, -1)
            if messages:
                return {"session_id": session_id, "messages": [json.loads(m) for m in messages]}

            cur.execute(
                """
                SELECT messages FROM chat_history
                WHERE workspace_id = %s AND session_id = %s
                ORDER BY created_at DESC LIMIT 1
                """,
                (workspace_id, session_id),
            )
            row  = cur.fetchone()
            msgs = row[0][-limit:] if row and row[0] else []
            return {"session_id": session_id, "messages": msgs}

        else:
            cur.execute(
                """
                SELECT session_id,
                       created_at,
                       jsonb_array_length(messages) AS message_count,
                       messages->0->>'content'       AS first_message
                FROM chat_history
                WHERE workspace_id = %s
                ORDER BY created_at DESC
                LIMIT 20
                """,
                (workspace_id,),
            )
            return {
                "sessions": [
                    {
                        "session_id":    r[0],
                        "created_at":    str(r[1]),
                        "message_count": r[2],
                        "first_message": r[3],
                    }
                    for r in cur.fetchall()
                ]
            }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cur.close()
        conn.close()
