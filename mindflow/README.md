# Mindflow Feature (Hackathon)

This folder contains implementation notes and a runnable simulation harness for the new **Mindflow** feature.

## What is implemented

- Single orchestrator loop:
  1. chat reply
  2. node extraction (concept/decision/question/step)
  3. edge creation
  4. optional search + fetch enrichment (search-result nodes)
  5. drift scoring and optional workspace switch
- Workspace model with inheritance support.
- Drift detection using weighted rules + 2-turn trigger or strong transition phrase trigger.
- Backend API endpoint: `POST /mindflow/turn`

## API request

```json
{
  "project_id": "hackbite-small",
  "session_id": "demo-1",
  "message": "let's design a python API for this",
  "user_role": "general"
}
```

## API response (shape)

- `reply`: assistant response text
- `drift_detected`: boolean
- `drift_score`: float
- `active_workspace_id`: current workspace id
- `workspaces`: full workspace graph state
- `tool_trace`: per-turn tool calls for debugging/demo

## Local quick test

From `hackbite_2` root (using existing `.venv`):

```bash
source .venv/bin/activate
python mindflow/simulate_mindflow.py
```
