#!/usr/bin/env python3
"""
mcp_server/cnc_tools_server.py

Mission 06E — local stdio MCP-like Tool Server for CNC Agent Client.

This server intentionally exposes NO network port. It speaks newline-delimited
JSON-RPC over stdin/stdout and wraps the existing edge_backend.ai.tool_runner
logic without rewriting the 8 tool implementations.

Supported methods:
  - initialize
  - tools/list
  - tools/call
  - health/ping
  - shutdown

The response shape follows MCP-style concepts: tools/list returns name,
description and inputSchema; tools/call returns content text with the existing
JSON-string result from tool_runner.run_tool().
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any


def _configure_utf8_stdio() -> None:
    """Keep subprocess/pytest output stable on Windows cp1252 consoles."""
    for stream_name in ("stdout", "stderr"):
        stream = getattr(sys, stream_name, None)
        if stream is not None and hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8", errors="replace")
            except Exception:
                pass


_configure_utf8_stdio()

try:
    from dotenv import load_dotenv  # type: ignore
except Exception:  # pragma: no cover - dotenv is optional at import time
    load_dotenv = None  # type: ignore

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

if load_dotenv is not None:
    load_dotenv(PROJECT_ROOT / ".env", override=False)
    # .env.example is only a non-secret fallback after Mission 06F.
    if not (PROJECT_ROOT / ".env").exists():
        load_dotenv(PROJECT_ROOT / ".env.example", override=False)


def _tool_schemas_for_mcp() -> list[dict[str, Any]]:
    """Convert OpenAI function-call tool schemas to MCP-style tool schemas."""
    from edge_backend.ai.tool_definitions import TOOLS

    out: list[dict[str, Any]] = []
    for item in TOOLS:
        fn = item.get("function", {})
        out.append({
            "name": fn.get("name", ""),
            "description": fn.get("description", ""),
            "inputSchema": fn.get("parameters", {"type": "object", "properties": {}}),
        })
    return out


def _result(req_id: Any, result: Any) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": req_id, "result": result}


def _error(req_id: Any, code: int, message: str, data: Any | None = None) -> dict[str, Any]:
    err: dict[str, Any] = {"code": code, "message": message}
    if data is not None:
        err["data"] = data
    return {"jsonrpc": "2.0", "id": req_id, "error": err}


def _handle(req: dict[str, Any]) -> dict[str, Any] | None:
    method = req.get("method")
    req_id = req.get("id")
    params = req.get("params") or {}

    if method == "initialize":
        return _result(req_id, {
            "protocolVersion": "2024-11-05-local-stdio",
            "serverInfo": {"name": "cnc-tools-server", "version": "1.0.0"},
            "capabilities": {"tools": {"listChanged": False}},
            "transport": "stdio",
            "networkExposure": "none",
        })

    if method == "health/ping":
        return _result(req_id, {"ok": True, "server": "cnc-tools-server", "pid": os.getpid()})

    if method == "tools/list":
        return _result(req_id, {"tools": _tool_schemas_for_mcp()})

    if method == "tools/call":
        name = str(params.get("name") or "").strip()
        arguments = params.get("arguments") or {}
        if not name:
            return _error(req_id, -32602, "Missing tool name")
        if not isinstance(arguments, dict):
            return _error(req_id, -32602, "Tool arguments must be an object")

        known_tools = {t.get("name") for t in _tool_schemas_for_mcp()}
        if name not in known_tools:
            result_text = json.dumps({"error": f"Tool '{name}' not found"}, ensure_ascii=False)
        else:
            from edge_backend.ai import tool_runner

            result_text = tool_runner.run_tool(name, arguments)
        is_error = False
        try:
            parsed = json.loads(result_text)
            is_error = isinstance(parsed, dict) and "error" in parsed
        except Exception:
            parsed = None
        return _result(req_id, {
            "content": [{"type": "text", "text": result_text}],
            "isError": is_error,
            "raw_json": parsed,
        })

    if method == "shutdown":
        return _result(req_id, {"ok": True, "message": "shutdown accepted"})

    return _error(req_id, -32601, f"Unknown method: {method}")


def main() -> int:
    for raw in sys.stdin:
        line = raw.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
        except json.JSONDecodeError as exc:
            resp = _error(None, -32700, "Parse error", str(exc))
            print(json.dumps(resp, ensure_ascii=False), flush=True)
            continue

        try:
            resp = _handle(req)
        except Exception as exc:  # Never crash the JSON-RPC loop because one tool failed.
            resp = _error(req.get("id"), -32000, "Server error", str(exc))

        if resp is not None:
            print(json.dumps(resp, ensure_ascii=False), flush=True)

        if req.get("method") == "shutdown":
            break
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
