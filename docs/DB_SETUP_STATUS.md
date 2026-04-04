# Hackbite 2 DB Setup Status

## Atlas project and cluster

- Project: `Project 0` (`69cfcc1f07acaa54ca60ab95`)
- Cluster: `Cluster0` (M0)
- User created: `hackbite2_app`
- DB: `hackbite2`

## Collections created

- projects
- index_jobs
- documents
- chunks
- symbols
- edges
- retrieval_runs
- answers
- sessions
- events

## Indexes created

### MongoDB indexes
- Unique and query indexes for all core collections
- TTL indexes:
  - `sessions.expires_at`
  - `events.expires_at`

### Atlas Search indexes on `hackbite2.chunks`
- `chunks_text_v1` (type: `search`) — status: building
- `chunks_vector_v1` (type: `vectorSearch`) — status: building

## Notes

- Vector index dimensions are set to `1536`.
- Keep your embedding model output dimensions aligned with index dimensions.
