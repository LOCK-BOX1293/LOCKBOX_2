// Hackbite 2 MongoDB schema bootstrap
// Usage:
//   mongosh "$MONGODB_URI" --file infra/mongodb/init_schema.js

const dbName = "hackbite2";
const targetDb = db.getSiblingDB(dbName);

print(`Using database: ${dbName}`);

const collections = [
  "projects",
  "index_jobs",
  "documents",
  "chunks",
  "symbols",
  "edges",
  "retrieval_runs",
  "answers",
  "sessions",
  "events",
];

collections.forEach((name) => {
  const exists = targetDb.getCollectionInfos({ name }).length > 0;
  if (!exists) {
    targetDb.createCollection(name);
    print(`Created collection: ${name}`);
  } else {
    print(`Collection exists: ${name}`);
  }
});

// projects
targetDb.projects.createIndex({ project_key: 1 }, { unique: true, name: "ux_project_key" });
targetDb.projects.createIndex({ repo_url: 1, default_branch: 1 }, { name: "ix_repo_branch" });

// index_jobs
targetDb.index_jobs.createIndex({ project_id: 1, status: 1, updated_at: -1 }, { name: "ix_jobs_project_status_updated" });
targetDb.index_jobs.createIndex({ project_id: 1, created_at: -1 }, { name: "ix_jobs_project_created" });

// documents
targetDb.documents.createIndex({ project_id: 1, file_path: 1, git_sha: 1 }, { unique: true, name: "ux_doc_project_path_sha" });
targetDb.documents.createIndex({ project_id: 1, language: 1 }, { name: "ix_doc_project_language" });

// chunks
targetDb.chunks.createIndex({ project_id: 1, chunk_key: 1 }, { unique: true, name: "ux_chunk_project_key" });
targetDb.chunks.createIndex({ project_id: 1, file_path: 1, start_line: 1 }, { name: "ix_chunk_path_line" });
targetDb.chunks.createIndex({ project_id: 1, symbol_name: 1 }, { name: "ix_chunk_symbol" });

// symbols
targetDb.symbols.createIndex({ project_id: 1, symbol_fqn: 1 }, { unique: true, name: "ux_symbol_project_fqn" });
targetDb.symbols.createIndex({ project_id: 1, file_path: 1 }, { name: "ix_symbol_path" });

// edges
targetDb.edges.createIndex({ project_id: 1, from_symbol_fqn: 1, edge_type: 1 }, { name: "ix_edge_from_type" });
targetDb.edges.createIndex({ project_id: 1, to_symbol_fqn: 1, edge_type: 1 }, { name: "ix_edge_to_type" });

// retrieval_runs
targetDb.retrieval_runs.createIndex({ project_id: 1, session_id: 1, created_at: -1 }, { name: "ix_rr_project_session_created" });

// answers
targetDb.answers.createIndex({ project_id: 1, session_id: 1, created_at: -1 }, { name: "ix_ans_project_session_created" });

// sessions
targetDb.sessions.createIndex({ project_id: 1, user_id: 1, updated_at: -1 }, { name: "ix_session_user_updated" });
targetDb.sessions.createIndex({ expires_at: 1 }, { expireAfterSeconds: 0, name: "ttl_session_expires" });

// events
targetDb.events.createIndex({ project_id: 1, session_id: 1, ts: -1 }, { name: "ix_events_session_ts" });
targetDb.events.createIndex({ expires_at: 1 }, { expireAfterSeconds: 0, name: "ttl_events_expires" });

print("Schema bootstrap complete.");
