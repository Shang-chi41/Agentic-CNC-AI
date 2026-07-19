#!/usr/bin/env python3
"""Smoke test for Mission 06E local stdio MCP Tool Server.

This does not call an LLM and does not run CNC hardware. It verifies the tool
server boundary: initialize -> tools/list -> tools/call. The tool call uses an
unknown tool name deliberately so it does not require Neo4j/MongoDB connectivity
and still proves the server wraps tool_runner safely.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path


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

ROOT = Path(__file__).resolve().parents[1]


def rpc(proc: subprocess.Popen[str], method: str, params: dict | None = None, req_id: int = 1) -> dict:
    payload = {"jsonrpc": "2.0", "id": req_id, "method": method, "params": params or {}}
    assert proc.stdin and proc.stdout
    proc.stdin.write(json.dumps(payload, ensure_ascii=False) + "\n")
    proc.stdin.flush()
    line = proc.stdout.readline().strip()
    if not line:
        raise RuntimeError("empty response from MCP server")
    resp = json.loads(line)
    if resp.get("error"):
        raise RuntimeError(json.dumps(resp["error"], ensure_ascii=False))
    return resp["result"]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--module", default="mcp_server.cnc_tools_server")
    parser.add_argument("--expect-tools", type=int, default=8)
    args = parser.parse_args()

    proc = subprocess.Popen(
        [sys.executable, "-m", args.module],
        cwd=ROOT,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        bufsize=1,
    )
    try:
        init = rpc(proc, "initialize", {}, 1)
        tools_result = rpc(proc, "tools/list", {}, 2)
        tools = tools_result.get("tools", [])
        names = [t.get("name") for t in tools]
        if len(tools) != args.expect_tools:
            raise RuntimeError(f"expected {args.expect_tools} tools, got {len(tools)}: {names}")
        if "get_neo4j_context" not in names or "validate_gcode" not in names:
            raise RuntimeError(f"required tools missing: {names}")
        # Unknown tool call must return a JSON error from tool_runner, not crash the server.
        call = rpc(proc, "tools/call", {"name": "__missing_tool__", "arguments": {}}, 3)
        text = call.get("content", [{}])[0].get("text", "")
        if "not" not in text.lower() and "khong" not in text.lower():
            raise RuntimeError(f"unexpected unknown-tool response: {text}")
        print("MCP SMOKE PASS")
        print("Tools:", ", ".join(names))
        print("Server:", init.get("serverInfo", {}))
        return 0
    finally:
        try:
            rpc(proc, "shutdown", {}, 99)
        except Exception:
            pass
        proc.terminate()
        try:
            proc.wait(timeout=2)
        except subprocess.TimeoutExpired:
            proc.kill()


if __name__ == "__main__":
    raise SystemExit(main())
