import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from app.routers.auth import get_current_user
from app.database import get_db_connection

router = APIRouter()


class CreateWorkspaceRequest(BaseModel):
    name:        str
    description: Optional[str] = None


class WorkspaceResponse(BaseModel):
    id:          str
    name:        str
    description: Optional[str] = None
    created_at:  str


@router.get("", response_model=list[WorkspaceResponse])
def list_workspaces(current_user: dict = Depends(get_current_user)):
    """List all workspaces for current user"""
    conn = get_db_connection()
    cur = conn.cursor()
    
    try:
        cur.execute("""
            SELECT id, name, description, created_at 
            FROM workspaces WHERE user_id = %s
            ORDER BY created_at DESC
        """, (current_user["id"],))
        
        results = cur.fetchall()
        
        return [
            {
                "id": str(r[0]),
                "name": r[1],
                "description": r[2],
                "created_at": str(r[3])
            }
            for r in results
        ]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cur.close()
        conn.close()


@router.post("", response_model=WorkspaceResponse, status_code=status.HTTP_201_CREATED)
def create_workspace(request: CreateWorkspaceRequest, current_user: dict = Depends(get_current_user)):
    """Create new workspace"""
    workspace_id = str(uuid.uuid4())
    conn = get_db_connection()
    cur = conn.cursor()
    
    try:
        cur.execute("""
            INSERT INTO workspaces (id, user_id, name, description)
            VALUES (%s, %s, %s, %s)
            RETURNING id, name, description, created_at
        """, (workspace_id, current_user["id"], request.name, request.description))
        
        result = cur.fetchone()
        conn.commit()
        
        return {
            "id": str(result[0]),
            "name": result[1],
            "description": result[2],
            "created_at": str(result[3])
        }
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cur.close()
        conn.close()


@router.get("/{workspace_id}", response_model=WorkspaceResponse)
def get_workspace(workspace_id: str, current_user: dict = Depends(get_current_user)):
    """Get workspace by ID"""
    conn = get_db_connection()
    cur = conn.cursor()
    
    try:
        cur.execute("""
            SELECT id, name, description, created_at 
            FROM workspaces WHERE id = %s AND user_id = %s
        """, (workspace_id, current_user["id"]))
        
        result = cur.fetchone()
        
        if not result:
            raise HTTPException(status_code=404, detail="Workspace not found")
        
        return {
            "id": str(result[0]),
            "name": result[1],
            "description": result[2],
            "created_at": str(result[3])
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cur.close()
        conn.close()


@router.delete("/{workspace_id}")
def delete_workspace(workspace_id: str, current_user: dict = Depends(get_current_user)):
    """Delete workspace"""
    conn = get_db_connection()
    cur = conn.cursor()
    
    try:
        cur.execute("""
            DELETE FROM workspaces WHERE id = %s AND user_id = %s
        """, (workspace_id, current_user["id"]))
        
        conn.commit()
        
        if cur.rowcount == 0:
            raise HTTPException(status_code=404, detail="Workspace not found")
        
        return {"deleted": True}
    except HTTPException:
        raise
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cur.close()
        conn.close()