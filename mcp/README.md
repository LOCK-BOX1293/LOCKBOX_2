# Hackbite MCP Server

This folder exposes the existing Hackbite backend as a small MCP server over stdio.

It does not reimplement retrieval or answering. It forwards tool calls to the local
Hackbite FastAPI backend, so agents can use the same `/ask`, `/retrieve/query`, and
focused graph endpoints that power the app and extension.

## Tools

- `ask_hackbite`
  - Runs the full agent + RAG answer pipeline through `POST /ask`
- `retrieve_hackbite_context`
  - Returns grounded retrieved chunks through `POST /retrieve/query`
- `get_hackbite_focused_graph`
  - Returns a focused query graph through `GET /graph/overview?mode=focused`
- `list_hackbite_repos`
  - Lists indexed repositories through `GET /repos`

## Run

From the repo root:

```bash
python mcp/server.py
```

By default it calls:

```text
http://127.0.0.1:8081
```

Override with:

```bash
HACKBITE_API_BASE=http://127.0.0.1:8081 python mcp/server.py
```

## Example MCP client config

```json
{
  "mcpServers": {
    "hackbite": {
      "command": "python",
      "args": ["/home/rudra/Code/hackbite_2/mcp/server.py"],
      "env": {
        "HACKBITE_API_BASE": "http://127.0.0.1:8081"
      }
    }
  }
}
```

## Notes

- The backend must already be running.
- This server uses only the standard library plus `requests`, which is already in the repo requirements.
