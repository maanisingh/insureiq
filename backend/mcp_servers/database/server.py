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

mcp = FastMCP("database")

def get_db_connection():
    return psycopg2.connect(
        host=os.getenv("DB_HOST", "localhost"),
        port=os.getenv("DB_PORT", "5433"),
        database=os.getenv("DB_NAME", "insurance_ai"),
        user=os.getenv("DB_USER", "insurance_ai"),
        password=os.getenv("DB_PASSWORD", "insurance_secure_2024")
    )

@mcp.tool()
def execute_query(query: str, params: tuple = None) -> list[dict]:
    """Execute a raw SQL query (read-only)
    
    Args:
        query: SQL query to execute
        params: Query parameters (optional)
    """
    # Only allow SELECT queries for safety
    if not query.strip().upper().startswith("SELECT"):
        return [{"error": "Only SELECT queries are allowed"}]
    
    try:
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute(query, params or ())
        
        results = cur.fetchall()
        cur.close()
        conn.close()
        
        return [dict(r) for r in results]
    except Exception as e:
        return [{"error": str(e)}]

@mcp.tool()
def get_table_info(table_name: str) -> dict:
    """Get information about a table
    
    Args:
        table_name: Name of the table
    """
    try:
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        
        cur.execute("""
            SELECT column_name, data_type, is_nullable, column_default
            FROM information_schema.columns
            WHERE table_name = %s
            ORDER BY ordinal_position
        """, (table_name,))
        
        results = cur.fetchall()
        cur.close()
        conn.close()
        
        return {"table": table_name, "columns": [dict(r) for r in results]}
    except Exception as e:
        return {"error": str(e)}

@mcp.tool()
def list_tables() -> list[dict]:
    """List all tables in the database"""
    try:
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        
        cur.execute("""
            SELECT table_name, table_type
            FROM information_schema.tables
            WHERE table_schema = 'public'
            ORDER BY table_name
        """)
        
        results = cur.fetchall()
        cur.close()
        conn.close()
        
        return [dict(r) for r in results]
    except Exception as e:
        return [{"error": str(e)}]

@mcp.tool()
def health_check() -> dict:
    """Health check for the database server"""
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT 1, version()")
        result = cur.fetchone()
        cur.close()
        conn.close()
        
        return {
            "status": "healthy",
            "postgres": "ok",
            "version": result[1]
        }
    except Exception as e:
        return {"status": "unhealthy", "error": str(e)}

if __name__ == "__main__":
    import sys
    
    transport = "stdio"
    if len(sys.argv) > 1 and sys.argv[1] == "--http":
        transport = "http"
        port = int(sys.argv[2]) if len(sys.argv) > 2 else 8006
    
    if transport == "http":
        mcp.run(transport="http", port=port)
    else:
        mcp.run(transport="stdio")