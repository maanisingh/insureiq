import os
import sys
import uuid
import json
import boto3
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent.parent / "config" / ".env")

try:
    from fastmcp import FastMCP
except ImportError:
    from mcp import FastMCP

import redis
import psycopg2
from psycopg2.extras import RealDictCursor

mcp = FastMCP("chat-memory")

# Bedrock for semantic memory search
EMBED_MODEL = "amazon.titan-embed-text-v1"
AWS_REGION  = os.getenv("AWS_REGION", "us-east-1")
AWS_KEY     = os.getenv("AWS_ACCESS_KEY_ID")
AWS_SECRET  = os.getenv("AWS_SECRET_ACCESS_KEY")


def _embed(text: str) -> list[float]:
    kwargs = {"region_name": AWS_REGION}
    if AWS_KEY and AWS_SECRET:
        kwargs["aws_access_key_id"]     = AWS_KEY
        kwargs["aws_secret_access_key"] = AWS_SECRET
    client = boto3.client("bedrock-runtime", **kwargs)
    resp   = client.invoke_model(
        modelId=EMBED_MODEL,
        contentType="application/json",
        accept="application/json",
        body=json.dumps({"inputText": text[:8000]}),
    )
    return json.loads(resp["body"].read())["embedding"]

# Redis connection
REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))
REDIS_DB   = int(os.getenv("REDIS_DB", "0"))

redis_client = redis.Redis(
    host=REDIS_HOST,
    port=REDIS_PORT,
    db=REDIS_DB,
    decode_responses=True
)

# PostgreSQL connection
def get_db_connection():
    return psycopg2.connect(
        host=os.getenv("DB_HOST", "localhost"),
        port=os.getenv("DB_PORT", "5433"),
        database=os.getenv("DB_NAME", "insurance_ai"),
        user=os.getenv("DB_USER", "insurance_ai"),
        password=os.getenv("DB_PASSWORD", "insurance_secure_2024")
    )

def _get_redis_key(workspace_id: str, session_id: str) -> str:
    return f"chat:{workspace_id}:{session_id}"

@mcp.tool()
def save_message(workspace_id: str, session_id: str, role: str, content: str) -> dict:
    """Save a chat message to memory
    
    Stores in both Redis (short-term) and PostgreSQL (long-term).
    
    Args:
        workspace_id: Workspace ID
        session_id: Session ID
        role: Message role (user or assistant)
        content: Message content
    """
    message_id = str(uuid.uuid4())
    message = {
        "id": message_id,
        "role": role,
        "content": content
    }
    
    # Save to Redis (short-term, last 50 messages per session)
    key = _get_redis_key(workspace_id, session_id)
    redis_client.rpush(key, json.dumps(message))
    redis_client.expire(key, 86400 * 30)  # 30 days TTL
    
    # Save to PostgreSQL (long-term)
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        # Check if session exists
        cur.execute("""
            SELECT id FROM chat_history 
            WHERE workspace_id = %s AND session_id = %s
        """, (workspace_id, session_id))
        
        existing = cur.fetchone()
        
        if existing:
            # Append to existing session
            cur.execute("""
                UPDATE chat_history 
                SET messages = messages || %s::jsonb, created_at = NOW()
                WHERE workspace_id = %s AND session_id = %s
            """, (json.dumps([message]), workspace_id, session_id))
        else:
            # Create new session
            cur.execute("""
                INSERT INTO chat_history (workspace_id, session_id, messages)
                VALUES (%s, %s, %s)
            """, (workspace_id, session_id, json.dumps([message])))
        
        conn.commit()
        cur.close()
        conn.close()
    except Exception as e:
        return {"status": "partial", "message_id": message_id, "redis": "ok", "postgres": str(e)}
    
    return {"status": "saved", "message_id": message_id}

@mcp.tool()
def get_conversation_history(workspace_id: str, session_id: str, limit: int = 20) -> list[dict]:
    """Get recent conversation history for a session
    
    Args:
        workspace_id: Workspace ID
        session_id: Session ID
        limit: Maximum number of messages (default: 20)
    """
    key = _get_redis_key(workspace_id, session_id)
    
    # Get from Redis first
    messages = redis_client.lrange(key, -limit, -1)
    
    if messages:
        return [json.loads(m) for m in messages]
    
    # Fallback to PostgreSQL
    try:
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("""
            SELECT messages FROM chat_history 
            WHERE workspace_id = %s AND session_id = %s
            ORDER BY created_at DESC LIMIT 1
        """, (workspace_id, session_id))
        
        result = cur.fetchone()
        cur.close()
        conn.close()
        
        if result and result.get("messages"):
            messages_list = result["messages"]
            return messages_list[-limit:]
    except Exception as e:
        return [{"error": str(e)}]
    
    return []

@mcp.tool()
def retrieve_memories(workspace_id: str, query: str, limit: int = 5) -> list[dict]:
    """Semantic search over past conversations using Bedrock Titan embeddings.

    Embeds the query, then scores recent chat messages by cosine similarity
    to find contextually relevant memories.

    Args:
        workspace_id: Workspace ID.
        query:        Search query.
        limit:        Maximum memories to return (default: 5).
    """
    import math

    def cosine_sim(a: list[float], b: list[float]) -> float:
        dot   = sum(x * y for x, y in zip(a, b))
        mag_a = math.sqrt(sum(x * x for x in a))
        mag_b = math.sqrt(sum(x * x for x in b))
        return dot / (mag_a * mag_b) if mag_a and mag_b else 0.0

    try:
        query_vec = _embed(query)
    except Exception:
        query_vec = None  # fallback to keyword search if Bedrock unavailable

    try:
        conn    = get_db_connection()
        cur     = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute(
            """
            SELECT messages, created_at, session_id FROM chat_history
            WHERE workspace_id = %s
            ORDER BY created_at DESC
            LIMIT 50
            """,
            (workspace_id,),
        )
        rows = cur.fetchall()
        cur.close()
        conn.close()
    except Exception as e:
        return [{"error": str(e)}]

    scored = []
    query_lower = query.lower()

    for row in rows:
        for msg in row.get("messages", []):
            content = msg.get("content", "")
            if not content:
                continue
            if query_vec:
                try:
                    msg_vec = _embed(content)
                    score   = cosine_sim(query_vec, msg_vec)
                except Exception:
                    score = 1.0 if query_lower in content.lower() else 0.0
            else:
                score = 1.0 if query_lower in content.lower() else 0.0

            if score > 0.3:
                scored.append({
                    "content":    content[:500],
                    "role":       msg.get("role"),
                    "score":      round(score, 4),
                    "timestamp":  str(row.get("created_at")),
                    "session_id": row.get("session_id"),
                })

    scored.sort(key=lambda x: x["score"], reverse=True)
    return scored[:limit]

@mcp.tool()
def create_session(workspace_id: str) -> dict:
    """Create a new chat session
    
    Args:
        workspace_id: Workspace ID
    """
    session_id = str(uuid.uuid4())[:8]
    
    redis_client.sadd(f"sessions:{workspace_id}", session_id)
    
    return {"session_id": session_id, "workspace_id": workspace_id}

@mcp.tool()
def list_sessions(workspace_id: str) -> list[dict]:
    """List all sessions in a workspace
    
    Args:
        workspace_id: Workspace ID
    """
    try:
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("""
            SELECT session_id, created_at, 
                   jsonb_array_length(messages) as message_count
            FROM chat_history
            WHERE workspace_id = %s
            ORDER BY created_at DESC
            LIMIT 50
        """, (workspace_id,))
        
        results = cur.fetchall()
        cur.close()
        conn.close()
        
        return [
            {
                "session_id": r["session_id"],
                "created_at": str(r["created_at"]),
                "message_count": r["message_count"]
            }
            for r in results
        ]
    except Exception as e:
        return [{"error": str(e)}]

@mcp.tool()
def health_check() -> dict:
    """Health check for the chat memory server"""
    try:
        # Test Redis
        redis_client.ping()
        
        # Test PostgreSQL
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT 1")
        cur.close()
        conn.close()
        
        return {"status": "healthy", "redis": "ok", "postgres": "ok"}
    except Exception as e:
        return {"status": "unhealthy", "error": str(e)}

if __name__ == "__main__":
    import sys
    
    transport = "stdio"
    if len(sys.argv) > 1 and sys.argv[1] == "--http":
        transport = "http"
        port = int(sys.argv[2]) if len(sys.argv) > 2 else 8003
    
    if transport == "http":
        mcp.run(transport="http", port=port)
    else:
        mcp.run(transport="stdio")