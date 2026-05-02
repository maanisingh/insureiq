import os
import uuid
import json
from typing import Optional, List

try:
    from fastmcp import FastMCP
except ImportError:
    from mcp import FastMCP

import psycopg2
from psycopg2.extras import RealDictCursor

mcp = FastMCP("policy-ops")

def get_db_connection():
    return psycopg2.connect(
        host=os.getenv("DB_HOST", "localhost"),
        port=os.getenv("DB_PORT", "5433"),
        database=os.getenv("DB_NAME", "insurance_ai"),
        user=os.getenv("DB_USER", "insurance_ai"),
        password=os.getenv("DB_PASSWORD", "insurance_secure_2024")
    )

def _verify_workspace(workspace_id: str, user_id: str = None) -> bool:
    """Verify workspace belongs to user"""
    if user_id:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("""
            SELECT id FROM workspaces 
            WHERE id = %s AND user_id = %s
        """, (workspace_id, user_id))
        result = cur.fetchone()
        cur.close()
        conn.close()
        return result is not None
    return True

@mcp.tool()
def create_policy(workspace_id: str, policy_data: dict, user_id: str = None) -> dict:
    """Create a new policy in the workspace
    
    Args:
        workspace_id: Workspace ID
        policy_data: Policy data as dict (type, holder, premium, etc.)
        user_id: Optional user ID for ownership verification
    """
    if user_id and not _verify_workspace(workspace_id, user_id):
        return {"error": "Workspace not found or access denied"}
    
    policy_id = str(uuid.uuid4())
    policy_number = f"POL-{policy_id[:8].upper()}"
    
    try:
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        
        cur.execute("""
            INSERT INTO policies (id, workspace_id, policy_number, policy_data, policy_type)
            VALUES (%s, %s, %s, %s, %s)
            RETURNING id, policy_number, policy_type, created_at
        """, (
            policy_id, 
            workspace_id, 
            policy_number, 
            json.dumps(policy_data),
            policy_data.get("type", "general")
        ))
        
        result = cur.fetchone()
        conn.commit()
        cur.close()
        conn.close()
        
        return {
            "id": str(result["id"]),
            "policy_number": result["policy_number"],
            "policy_type": result["policy_type"],
            "created_at": str(result["created_at"])
        }
    except Exception as e:
        return {"error": str(e)}

@mcp.tool()
def get_policy(workspace_id: str, policy_id: str = None, policy_number: str = None, user_id: str = None) -> dict:
    """Get policy by ID or policy number
    
    Args:
        workspace_id: Workspace ID
        policy_id: Policy UUID (optional)
        policy_number: Policy number like POL-XXXXXXXX (optional)
        user_id: Optional user ID for ownership verification
    """
    if user_id and not _verify_workspace(workspace_id, user_id):
        return {"error": "Workspace not found or access denied"}
    
    if not policy_id and not policy_number:
        return {"error": "Must provide either policy_id or policy_number"}
    
    try:
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        
        if policy_id:
            cur.execute("""
                SELECT id, policy_number, policy_data, policy_type, status, created_at, updated_at
                FROM policies WHERE id = %s AND workspace_id = %s
            """, (policy_id, workspace_id))
        else:
            cur.execute("""
                SELECT id, policy_number, policy_data, policy_type, status, created_at, updated_at
                FROM policies WHERE policy_number = %s AND workspace_id = %s
            """, (policy_number, workspace_id))
        
        result = cur.fetchone()
        cur.close()
        conn.close()
        
        if result:
            return {
                "id": str(result["id"]),
                "policy_number": result["policy_number"],
                "policy_data": result["policy_data"],
                "policy_type": result["policy_type"],
                "status": result["status"],
                "created_at": str(result["created_at"]),
                "updated_at": str(result["updated_at"])
            }
        return {"error": "Policy not found"}
    except Exception as e:
        return {"error": str(e)}

@mcp.tool()
def list_policies(workspace_id: str, limit: int = 50, user_id: str = None) -> list[dict]:
    """List all policies in workspace
    
    Args:
        workspace_id: Workspace ID
        limit: Maximum number of policies (default: 50)
        user_id: Optional user ID for ownership verification
    """
    if user_id and not _verify_workspace(workspace_id, user_id):
        return [{"error": "Workspace not found or access denied"}]
    
    try:
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        
        cur.execute("""
            SELECT id, policy_number, policy_type, status, created_at
            FROM policies WHERE workspace_id = %s
            ORDER BY created_at DESC LIMIT %s
        """, (workspace_id, limit))
        
        results = cur.fetchall()
        cur.close()
        conn.close()
        
        return [
            {
                "id": str(r["id"]),
                "policy_number": r["policy_number"],
                "policy_type": r["policy_type"],
                "status": r["status"],
                "created_at": str(r["created_at"])
            }
            for r in results
        ]
    except Exception as e:
        return [{"error": str(e)}]

@mcp.tool()
def update_policy(workspace_id: str, policy_id: str, policy_data: dict, user_id: str = None) -> dict:
    """Update policy data
    
    Args:
        workspace_id: Workspace ID
        policy_id: Policy UUID
        policy_data: Updated policy data
        user_id: Optional user ID for ownership verification
    """
    if user_id and not _verify_workspace(workspace_id, user_id):
        return {"error": "Workspace not found or access denied"}
    
    try:
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        
        cur.execute("""
            UPDATE policies 
            SET policy_data = %s, updated_at = NOW()
            WHERE id = %s AND workspace_id = %s
            RETURNING id, updated_at
        """, (json.dumps(policy_data), policy_id, workspace_id))
        
        result = cur.fetchone()
        conn.commit()
        cur.close()
        conn.close()
        
        if result:
            return {"id": str(result["id"]), "updated_at": str(result["updated_at"])}
        return {"error": "Policy not found"}
    except Exception as e:
        return {"error": str(e)}

@mcp.tool()
def delete_policy(workspace_id: str, policy_id: str, user_id: str = None) -> dict:
    """Delete a policy
    
    Args:
        workspace_id: Workspace ID
        policy_id: Policy UUID
        user_id: Optional user ID for ownership verification
    """
    if user_id and not _verify_workspace(workspace_id, user_id):
        return {"error": "Workspace not found or access denied"}
    
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        cur.execute("""
            DELETE FROM policies WHERE id = %s AND workspace_id = %s
        """, (policy_id, workspace_id))
        
        conn.commit()
        deleted = cur.rowcount > 0
        cur.close()
        conn.close()
        
        return {"deleted": deleted}
    except Exception as e:
        return {"error": str(e)}

@mcp.tool()
def health_check() -> dict:
    """Health check for the policy ops server"""
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT 1")
        cur.close()
        conn.close()
        return {"status": "healthy", "postgres": "ok"}
    except Exception as e:
        return {"status": "unhealthy", "error": str(e)}

if __name__ == "__main__":
    import sys
    
    transport = "stdio"
    if len(sys.argv) > 1 and sys.argv[1] == "--http":
        transport = "http"
        port = int(sys.argv[2]) if len(sys.argv) > 2 else 8005
    
    if transport == "http":
        mcp.run(transport="http", port=port)
    else:
        mcp.run(transport="stdio")