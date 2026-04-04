# Hackbite 2 Agent System

This file defines the specialized agents used in Hackbite 2.

## Core Agents

1. **Orchestrator Agent**
   - Plans request flow
   - Routes work to specialist agents
   - Merges outputs and enforces answer format

2. **Ingestion Agent**
   - Scans repository files
   - Extracts semantic chunks + symbol metadata
   - Emits indexing jobs

3. **Indexing Agent**
   - Builds vector index
   - Builds lexical (BM25) index
   - Builds code relation graph
  
4. **Retrieval Agent**
   - Runs hybrid retrieval (vector + lexical + graph)
   - Reranks results
   - Returns compact context package

5. **Explanation Agent**
   - Produces grounded answer from retrieved evidence only
   - Adds citations and confidence

6. **Visual Mapper Agent**
   - Converts context to clickable graph data
   - Adds "why this node" evidence for UI

7. **Session Memory Agent**
   - Stores session history and user focus
   - Improves follow-up query relevance

## Prompt Strategy

- Use one base system contract per agent
- Add role-specialist prompt for expert voice
- Enforce: no evidence -> say unknown
- Always return citations in machine-readable format
