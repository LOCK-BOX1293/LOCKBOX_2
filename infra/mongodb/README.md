# MongoDB Atlas bootstrap

This folder contains MongoDB setup artifacts for Hackbite 2.

## Files

- `init_schema.js` - creates collections and core indexes
- `search-index-chunks-text.json` - Atlas Search text index for code chunks
- `search-index-chunks-vector.json` - Atlas Vector Search index for embeddings

## Apply

1. Run schema bootstrap using mongosh.
2. Create Atlas Search indexes using Atlas CLI search commands.
