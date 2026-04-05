from __future__ import annotations

import json
import os
import sys
import traceback
import uuid
from typing import Any
from urllib.parse import urlencode

import requests


PROTOCOL_VERSION = "2024-11-05"
SERVER_NAME = "hackbite-mcp"
SERVER_VERSION = "0.1.0"
DEFAULT_API_BASE = os.environ.get("HACKBITE_API_BASE", "http://127.0.0.1:8081").rstrip("/")


def _read_message() -> dict[str, Any] | None:
    line = sys.stdin.readline()
    if not line:
        raise EOFError
    line = line.strip()
    if not line:
        return None
    return json.loads(line)


def _write_message(payload: dict[str, Any]) -> None:
    sys.stdout.write(json.dumps(payload, ensure_ascii=True) + "\n")
    sys.stdout.flush()


def _tool_schema() -> list[dict[str, Any]]:
    return [
        {
            "name": "ask_hackbite",
            "description": "Run the full Hackbite answer pipeline using the local AI + RAG backend.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "project_id": {"type": "string", "description": "Indexed repository id"},
                    "query": {"type": "string", "description": "Developer question to answer"},
                    "session_id": {"type": "string", "description": "Conversation/session id"},
                    "user_role": {
                        "type": "string",
                        "description": "backend | frontend | security | architect | debugger",
                        "default": "backend",
                    },
                    "branch": {"type": "string", "default": "main"},
                    "path_prefix": {"type": ["string", "null"]},
                    "include_tests": {"type": "boolean", "default": False},
                    "backend_url": {"type": "string", "description": "Optional backend override"},
                },
                "required": ["project_id", "query"],
            },
        },
        {
            "name": "retrieve_hackbite_context",
            "description": "Retrieve grounded chunks from the Hackbite hybrid retrieval pipeline without generating a final answer.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "repo_id": {"type": "string"},
                    "q": {"type": "string"},
                    "branch": {"type": "string", "default": "main"},
                    "top_k": {"type": "integer", "default": 8},
                    "lang": {"type": ["string", "null"]},
                    "path_prefix": {"type": ["string", "null"]},
                    "include_tests": {"type": "boolean", "default": False},
                    "backend_url": {"type": "string"},
                },
                "required": ["repo_id", "q"],
            },
        },
        {
            "name": "get_hackbite_focused_graph",
            "description": "Fetch the focused graph for a query from the Hackbite backend.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "repo_id": {"type": "string"},
                    "q": {"type": "string"},
                    "branch": {"type": "string", "default": "main"},
                    "top_k": {"type": "integer", "default": 8},
                    "include_tests": {"type": "boolean", "default": False},
                    "backend_url": {"type": "string"},
                },
                "required": ["repo_id", "q"],
            },
        },
        {
            "name": "list_hackbite_repos",
            "description": "List indexed repositories known to the Hackbite backend.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "backend_url": {"type": "string"},
                },
            },
        },
    ]


def _backend_url(arguments: dict[str, Any]) -> str:
    return str(arguments.get("backend_url") or DEFAULT_API_BASE).rstrip("/")


def _request_json(method: str, url: str, **kwargs: Any) -> Any:
    response = requests.request(method, url, timeout=90, **kwargs)
    response.raise_for_status()
    return response.json()


def _json_result(data: Any, summary: str) -> dict[str, Any]:
    return {
        "content": [
            {"type": "text", "text": summary},
            {"type": "text", "text": json.dumps(data, indent=2, ensure_ascii=True)},
        ],
        "structuredContent": data,
    }


def _call_tool(name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    base = _backend_url(arguments)

    if name == "ask_hackbite":
        payload = {
            "project_id": arguments["project_id"],
            "session_id": arguments.get("session_id") or f"mcp-{uuid.uuid4().hex[:10]}",
            "query": arguments["query"],
            "user_role": arguments.get("user_role", "backend"),
            "branch": arguments.get("branch", "main"),
            "path_prefix": arguments.get("path_prefix"),
            "include_tests": bool(arguments.get("include_tests", False)),
        }
        data = _request_json("POST", f"{base}/ask", json=payload)
        summary = data.get("answer", "No answer returned.")
        return _json_result(data, summary)

    if name == "retrieve_hackbite_context":
        payload = {
            "repo_id": arguments["repo_id"],
            "branch": arguments.get("branch", "main"),
            "q": arguments["q"],
            "top_k": int(arguments.get("top_k", 8)),
            "lang": arguments.get("lang"),
            "path_prefix": arguments.get("path_prefix"),
            "include_tests": bool(arguments.get("include_tests", False)),
        }
        data = _request_json("POST", f"{base}/retrieve/query", json=payload)
        count = len((data or {}).get("chunks", []))
        return _json_result(data, f"Retrieved {count} grounded chunks from Hackbite.")

    if name == "get_hackbite_focused_graph":
        params = {
            "repo_id": arguments["repo_id"],
            "branch": arguments.get("branch", "main"),
            "mode": "focused",
            "q": arguments["q"],
            "top_k": int(arguments.get("top_k", 8)),
            "include_tests": str(bool(arguments.get("include_tests", False))).lower(),
        }
        data = _request_json("GET", f"{base}/graph/overview?{urlencode(params)}")
        summary = f"Focused graph returned {len(data.get('nodes', []))} nodes and {len(data.get('edges', []))} edges."
        return _json_result(data, summary)

    if name == "list_hackbite_repos":
        data = _request_json("GET", f"{base}/repos")
        repos = data.get("repos", [])
        summary = f"Backend returned {len(repos)} indexed repositories."
        return _json_result(data, summary)

    raise ValueError(f"Unknown tool: {name}")


def _handle_request(message: dict[str, Any]) -> dict[str, Any] | None:
    method = message.get("method")
    msg_id = message.get("id")
    params = message.get("params", {})

    if method == "initialize":
        return {
            "jsonrpc": "2.0",
            "id": msg_id,
            "result": {
                "protocolVersion": PROTOCOL_VERSION,
                "capabilities": {
                    "tools": {},
                },
                "serverInfo": {
                    "name": SERVER_NAME,
                    "version": SERVER_VERSION,
                },
            },
        }

    if method == "notifications/initialized":
        return None

    if method == "ping":
        return {"jsonrpc": "2.0", "id": msg_id, "result": {}}

    if method == "tools/list":
        return {
            "jsonrpc": "2.0",
            "id": msg_id,
            "result": {
                "tools": _tool_schema(),
            },
        }

    if method == "tools/call":
        name = params.get("name")
        arguments = params.get("arguments", {}) or {}
        result = _call_tool(str(name), arguments)
        return {"jsonrpc": "2.0", "id": msg_id, "result": result}

    return {
        "jsonrpc": "2.0",
        "id": msg_id,
        "error": {
            "code": -32601,
            "message": f"Method not found: {method}",
        },
    }


def main() -> int:
    while True:
        try:
            message = _read_message()
            if message is None:
                continue
            response = _handle_request(message)
            if response is not None:
                _write_message(response)
        except KeyboardInterrupt:
            return 0
        except EOFError:
            return 0
        except Exception as exc:
            msg_id = None
            if "message" in locals() and isinstance(message, dict):
                msg_id = message.get("id")
            _write_message(
                {
                    "jsonrpc": "2.0",
                    "id": msg_id,
                    "error": {
                        "code": -32000,
                        "message": str(exc),
                        "data": traceback.format_exc(),
                    },
                }
            )


if __name__ == "__main__":
    raise SystemExit(main())
