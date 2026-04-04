# Frontend Wiring (Backend + Agents)

This document explains **why backend exists**, **why node logic exists**, and exactly **what frontend should wire**.

## Why backend exists

Backend handles all heavy/authoritative logic:

1. scan/index codebase
2. store symbols/chunks/edges in Mongo
3. retrieve relevant context for query
4. run expert-answer generation
5. produce graph payload for UI

Frontend should only render and interact with backend outputs.

## Why node + edge logic exists

To make code understanding clickable and traceable:

- **node (file/symbol)** = where logic lives
- **edge (calls/imports/references/contains)** = how logic connects

This enables:

- click node -> show code + functions
- click edge -> show relation context between two symbols

## API endpoints to wire

1. `POST /ask`
   - agent pipeline result (answer + citations + graph)
2. `GET /graph/overview`
   - full or focused graph data
3. `GET /graph/node/{node_id}`
   - code and metadata for selected node
4. `GET /graph/edge-context`
   - relation details for selected edge
5. `GET /health`
   - service heartbeat

## Ports

- Backend API: `8081`
- Frontend Vite: `5173`

## Env

Frontend:

- `VITE_API_BASE=http://localhost:8081`

Backend uses root `.env` for Mongo + model configs.

## Recommended frontend interaction order

1. on load: get full graph
2. on question submit: call `/ask`
3. render returned answer + citations
4. replace graph with focused graph from response (or call focused overview)
5. node click -> load node details
6. edge click -> load edge context
