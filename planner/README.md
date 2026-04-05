# Planner prototype

This is a conversation-first memory graph prototype with a real minimal backend.

What it has:
- chat input with backend-streamed assistant text
- backend graph planning with node creation, linking, placement, and workspace drift
- optional grounded search through the existing repo env when Gemini is configured
- right-click node actions in the frontend

Start the backend:

```bash
cd /home/rudra/Code/hackbite_2_mindflow_ui/test/planner
npm run backend
```

Start the frontend:

```bash
cd /home/rudra/Code/hackbite_2_mindflow_ui/test/planner
npm run dev
```

Default ports:
- frontend: `5173`
- backend: `8788`

The backend loads env from the repo root:
- `/home/rudra/Code/hackbite_2_mindflow_ui/.env`
- `/home/rudra/Code/hackbite_2_mindflow_ui/.env.example`
