# Hackbite 3 DB Setup Status

## Atlas project and cluster

- Project: `Project 0` (`69cfcc1f07acaa54ca60ab95`)
- Cluster: `Cluster0` (M0)
- User created: `hackbite3_app`
- DB: `hackbite3`

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

## Search indexes on `hackbite3.chunks`

- `chunks_text_v1` (type: `search`) — status: created/building
- `chunks_vector_v1` (type: `vectorSearch`) — status: created/building

## Notes

- Vector dimensions are set to `1536`.
- Keep embedding model dimensions aligned with index dimensions.
- On M0, Atlas has strict search index limits. Removed old temporary indexes to free capacity.
