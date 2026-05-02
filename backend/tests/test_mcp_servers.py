"""Tests for all 7 MCP server health checks."""

import os
import sys
import pytest
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / "config" / ".env")

# Add project root to path so MCP servers can be imported
sys.path.insert(0, str(Path(__file__).parent.parent))


def _import_server(module_path: str):
    import importlib.util
    spec   = importlib.util.spec_from_file_location("server", module_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class TestMCPHealthChecks:
    """Call each MCP server's health_check() function directly."""

    def _server(self, name: str):
        path = Path(__file__).parent.parent / "mcp_servers" / name / "server.py"
        return _import_server(str(path))

    def test_chat_memory_health(self):
        server = self._server("chat_memory")
        result = server.health_check()
        assert result["status"] == "healthy"
        assert result.get("redis") == "ok"
        assert result.get("postgres") == "ok"

    def test_database_health(self):
        server = self._server("database")
        result = server.health_check()
        assert result["status"] == "healthy"

    def test_policy_ops_health(self):
        server = self._server("policy_ops")
        result = server.health_check()
        assert result["status"] == "healthy"

    def test_graphrag_base_health(self):
        server = self._server("graphrag_base")
        result = server.health_check()
        assert result["status"] == "healthy"
        assert result.get("qdrant") == "connected"

    def test_graphrag_workspace_health(self):
        server = self._server("graphrag_workspace")
        result = server.health_check()
        assert result["status"] == "healthy"
        assert result.get("qdrant_workspace") == "connected"

    def test_qdrant_vector_health(self):
        server = self._server("qdrant_vector")
        result = server.health_check()
        assert result["status"] in ("healthy", "degraded")
        assert "global"    in result
        assert "workspace" in result

    def test_search_tools_health(self):
        server = self._server("search_tools")
        result = server.health_check()
        # Allow unhealthy if network unavailable in CI
        assert "status" in result
