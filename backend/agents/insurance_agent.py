"""
InsuranceAgent — entry point that delegates to the AutoGen multi-agent team.

The multi-agent system (agents/multi_agent.py) handles the full pipeline:
  RAGAgent          → knowledge base + workspace document search
  ResearchAgent     → web search + HuggingFace dataset discovery
  PricingAgent      → actuarial pricing + Python code execution
  PolicyAgent       → policy creation + 40-page document generation
  UnderwritingAgent → risk scoring + appetite + UW memos

State (chat history, messages) is persisted to Redis + PostgreSQL
after every run, independent of AutoGen's internal message passing.
"""

import os
import json
import uuid
import asyncio
import redis
import psycopg2
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / "config" / ".env")


# ── State helpers ─────────────────────────────────────────────────────────────

def _redis_client() -> redis.Redis:
    return redis.Redis(
        host=os.getenv("REDIS_HOST", "localhost"),
        port=int(os.getenv("REDIS_PORT", "6379")),
        db=int(os.getenv("REDIS_DB", "0")),
        decode_responses=True,
    )


def _db_conn():
    return psycopg2.connect(
        host=os.getenv("DB_HOST", "localhost"),
        port=os.getenv("DB_PORT", "5433"),
        database=os.getenv("DB_NAME", "insurance_ai"),
        user=os.getenv("DB_USER", "insurance_ai"),
        password=os.getenv("DB_PASSWORD", "insurance_secure_2024"),
    )


def _load_history(workspace_id: str, session_id: str, limit: int = 10) -> list[dict]:
    """Load recent chat history from Redis (fast) or PostgreSQL (fallback)."""
    key = f"chat:{workspace_id}:{session_id}"
    try:
        r        = _redis_client()
        messages = r.lrange(key, -limit, -1)
        if messages:
            return [json.loads(m) for m in messages]
    except Exception:
        pass

    try:
        conn = _db_conn()
        cur  = conn.cursor()
        cur.execute(
            "SELECT messages FROM chat_history WHERE workspace_id = %s AND session_id = %s ORDER BY created_at DESC LIMIT 1",
            (workspace_id, session_id),
        )
        row = cur.fetchone()
        cur.close()
        conn.close()
        if row and row[0]:
            return row[0][-limit:]
    except Exception:
        pass
    return []


def _save_messages(workspace_id: str, session_id: str, messages: list[dict]) -> None:
    """Persist messages to Redis + PostgreSQL."""
    key = f"chat:{workspace_id}:{session_id}"
    try:
        r = _redis_client()
        for msg in messages:
            r.rpush(key, json.dumps(msg))
        r.expire(key, 86400 * 30)
    except Exception:
        pass

    try:
        conn = _db_conn()
        cur  = conn.cursor()
        cur.execute(
            "SELECT id FROM chat_history WHERE workspace_id = %s AND session_id = %s",
            (workspace_id, session_id),
        )
        if cur.fetchone():
            cur.execute(
                "UPDATE chat_history SET messages = messages || %s::jsonb WHERE workspace_id = %s AND session_id = %s",
                (json.dumps(messages), workspace_id, session_id),
            )
        else:
            cur.execute(
                "INSERT INTO chat_history (workspace_id, session_id, messages) VALUES (%s, %s, %s)",
                (workspace_id, session_id, json.dumps(messages)),
            )
        conn.commit()
        cur.close()
        conn.close()
    except Exception:
        pass


# ── Main agent entry point ────────────────────────────────────────────────────

class InsuranceAgent:
    """Stateless facade — delegates to the AutoGen multi-agent team.

    All state is in Redis/PostgreSQL. Each call builds a fresh team
    with the workspace_id bound into the tool closures.
    """

    def chat(
        self,
        message:      str,
        workspace_id: str,
        session_id:   str,
        user_id:      str,
    ) -> dict:
        """Run the multi-agent pipeline and return the response.

        Args:
            message:      User's message text.
            workspace_id: Workspace UUID (scopes RAG and policy tools).
            session_id:   Chat session ID.
            user_id:      Authenticated user UUID.

        Returns:
            {"response": str, "sources": list, "session_id": str, "agent_used": str}
        """
        # Load history for context
        history = _load_history(workspace_id, session_id)

        # Run multi-agent team (AutoGen is async — run in event loop)
        try:
            result = asyncio.run(
                _run_async(message, workspace_id, history)
            )
        except RuntimeError:
            # Python 3.10+ doesn't create a default event loop in non-main threads
            # (FastAPI runs sync routes in AnyIO worker threads).
            # Create a fresh loop for this call.
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                result = loop.run_until_complete(
                    _run_async(message, workspace_id, history)
                )
            finally:
                loop.close()

        response   = result.get("response", "I was unable to generate a response.")
        agent_used = result.get("agent_used", "unknown")
        sources    = result.get("sources", [])

        # Persist conversation
        new_messages = [
            {"id": str(uuid.uuid4()), "role": "user",      "content": message},
            {"id": str(uuid.uuid4()), "role": "assistant", "content": response,
             "agent": agent_used},
        ]
        _save_messages(workspace_id, session_id, new_messages)

        return {
            "response":   response,
            "sources":    sources,
            "session_id": session_id,
            "agent_used": agent_used,
        }


async def _run_async(message: str, workspace_id: str, history: list[dict]) -> dict:
    from agents.multi_agent import run_team
    return await run_team(message, workspace_id, history)


# Module-level singleton
agent = InsuranceAgent()
