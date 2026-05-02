import uuid
import json

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from typing import Optional

from app.routers.auth import get_current_user
from app.database import get_db_connection

router = APIRouter()


class CreatePolicyRequest(BaseModel):
    policy_data: dict
    workspace_id: str


class UpdatePolicyRequest(BaseModel):
    policy_data: dict


class PolicyResponse(BaseModel):
    id: str
    policy_number: str
    policy_type: str = None
    policy_data: dict = None
    status: str = None
    created_at: str = None


@router.get("", response_model=list[dict])
def list_policies(
    workspace_id: str,
    limit: int = 50,
    current_user: dict = Depends(get_current_user)
):
    """List all policies in workspace"""
    conn = get_db_connection()
    cur = conn.cursor()
    
    try:
        cur.execute("""
            SELECT id FROM workspaces 
            WHERE id = %s AND user_id = %s
        """, (workspace_id, current_user["id"]))
        
        if not cur.fetchone():
            raise HTTPException(status_code=404, detail="Workspace not found")
        
        cur.execute("""
            SELECT id, policy_number, policy_type, status, created_at
            FROM policies WHERE workspace_id = %s
            ORDER BY created_at DESC LIMIT %s
        """, (workspace_id, limit))
        
        results = cur.fetchall()
        
        return [
            {
                "id": str(r[0]),
                "policy_number": r[1],
                "policy_type": r[2],
                "status": r[3],
                "created_at": str(r[4])
            }
            for r in results
        ]
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cur.close()
        conn.close()


@router.post("", response_model=dict, status_code=status.HTTP_201_CREATED)
def create_policy(request: CreatePolicyRequest, current_user: dict = Depends(get_current_user)):
    """Create a new policy"""
    conn = get_db_connection()
    cur = conn.cursor()
    
    try:
        cur.execute("""
            SELECT id FROM workspaces 
            WHERE id = %s AND user_id = %s
        """, (request.workspace_id, current_user["id"]))
        
        if not cur.fetchone():
            raise HTTPException(status_code=404, detail="Workspace not found")
        
        policy_id = str(uuid.uuid4())
        policy_number = f"POL-{policy_id[:8].upper()}"
        
        cur.execute("""
            INSERT INTO policies (id, workspace_id, policy_number, policy_data, policy_type)
            VALUES (%s, %s, %s, %s, %s)
            RETURNING id, policy_number, policy_type, created_at
        """, (
            policy_id, 
            request.workspace_id, 
            policy_number, 
            json.dumps(request.policy_data),
            request.policy_data.get("type", "general")
        ))
        
        result = cur.fetchone()
        conn.commit()
        
        return {
            "id": str(result[0]),
            "policy_number": result[1],
            "policy_type": result[2],
            "created_at": str(result[3])
        }
    except HTTPException:
        raise
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cur.close()
        conn.close()


@router.get("/{policy_id}", response_model=dict)
def get_policy(
    policy_id: str,
    workspace_id: str,
    current_user: dict = Depends(get_current_user)
):
    """Get policy by ID"""
    conn = get_db_connection()
    cur = conn.cursor()
    
    try:
        cur.execute("""
            SELECT id FROM workspaces 
            WHERE id = %s AND user_id = %s
        """, (workspace_id, current_user["id"]))
        
        if not cur.fetchone():
            raise HTTPException(status_code=404, detail="Workspace not found")
        
        cur.execute("""
            SELECT id, policy_number, policy_data, policy_type, status, created_at, updated_at
            FROM policies WHERE id = %s AND workspace_id = %s
        """, (policy_id, workspace_id))
        
        result = cur.fetchone()
        
        if not result:
            raise HTTPException(status_code=404, detail="Policy not found")
        
        return {
            "id": str(result[0]),
            "policy_number": result[1],
            "policy_data": result[2],
            "policy_type": result[3],
            "status": result[4],
            "created_at": str(result[5]),
            "updated_at": str(result[6])
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cur.close()
        conn.close()


@router.patch("/{policy_id}")
def update_policy(
    policy_id: str,
    workspace_id: str,
    request: UpdatePolicyRequest,
    current_user: dict = Depends(get_current_user)
):
    """Update policy"""
    conn = get_db_connection()
    cur = conn.cursor()
    
    try:
        cur.execute("""
            SELECT id FROM workspaces 
            WHERE id = %s AND user_id = %s
        """, (workspace_id, current_user["id"]))
        
        if not cur.fetchone():
            raise HTTPException(status_code=404, detail="Workspace not found")
        
        cur.execute("""
            UPDATE policies 
            SET policy_data = %s, updated_at = NOW()
            WHERE id = %s AND workspace_id = %s
            RETURNING id, updated_at
        """, (json.dumps(request.policy_data), policy_id, workspace_id))
        
        result = cur.fetchone()
        conn.commit()
        
        if not result:
            raise HTTPException(status_code=404, detail="Policy not found")
        
        return {"id": str(result[0]), "updated_at": str(result[1])}
    except HTTPException:
        raise
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cur.close()
        conn.close()


@router.delete("/{policy_id}")
def delete_policy(
    policy_id: str,
    workspace_id: str,
    current_user: dict = Depends(get_current_user)
):
    """Delete policy"""
    conn = get_db_connection()
    cur = conn.cursor()
    
    try:
        cur.execute("""
            SELECT id FROM workspaces 
            WHERE id = %s AND user_id = %s
        """, (workspace_id, current_user["id"]))
        
        if not cur.fetchone():
            raise HTTPException(status_code=404, detail="Workspace not found")
        
        cur.execute("""
            DELETE FROM policies WHERE id = %s AND workspace_id = %s
        """, (policy_id, workspace_id))
        
        conn.commit()
        
        if cur.rowcount == 0:
            raise HTTPException(status_code=404, detail="Policy not found")
        
        return {"deleted": True}
    except HTTPException:
        raise
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cur.close()
        conn.close()