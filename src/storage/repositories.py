from typing import Any, Dict, List, Optional
from pymongo import ASCENDING, DESCENDING, UpdateOne, IndexModel
from pymongo.errors import OperationFailure
from src.storage.mongo import get_db
from src.schemas.models import Repo, RepoFile, Symbol, Chunk, Embedding, Edge, IndexJob, Session
from src.core.config import logger, settings

class DBRepository:
    def __init__(self):
        self.db = get_db()
        self.repos = self.db.repos
        self.files = self.db.files
        self.symbols = self.db.symbols
        self.chunks = self.db.chunks
        self.embeddings = self.db.embeddings
        self.edges = self.db.edges
        self.index_jobs = self.db.index_jobs
        self.sessions = self.db.sessions

    def ensure_indexes(self):
        logger.info("Ensuring standard database indexes...")
        
        # 1. Standard indexes
        self.chunks.create_index([("repo_id", ASCENDING), ("branch", ASCENDING), ("file_path", ASCENDING)])
        self.chunks.create_index([("repo_id", ASCENDING), ("branch", ASCENDING), ("content_hash", ASCENDING)])
        
        self.symbols.create_index([("repo_id", ASCENDING), ("branch", ASCENDING), ("file_path", ASCENDING), ("name", ASCENDING)])
        
        self.files.create_index([("repo_id", ASCENDING), ("branch", ASCENDING), ("file_path", ASCENDING), ("commit_sha", ASCENDING)])
        
        self.index_jobs.create_index([("repo_id", ASCENDING), ("started_at", DESCENDING)])
        
        # 2. Unique constraints
        self.files.create_index([("repo_id", ASCENDING), ("branch", ASCENDING), ("commit_sha", ASCENDING), ("file_path", ASCENDING)], unique=True)
        self.chunks.create_index([("repo_id", ASCENDING), ("branch", ASCENDING), ("commit_sha", ASCENDING), ("chunk_id", ASCENDING)], unique=True)
        self.symbols.create_index([("repo_id", ASCENDING), ("branch", ASCENDING), ("commit_sha", ASCENDING), ("symbol_id", ASCENDING)], unique=True)
        self.embeddings.create_index([("repo_id", ASCENDING), ("branch", ASCENDING), ("commit_sha", ASCENDING), ("chunk_id", ASCENDING)], unique=True)

        logger.info("Standard indexes verified.")

        # 3. Atlas Search & Vector Search Indexes
        try:
            self._ensure_atlas_search_indexes()
            logger.info("Atlas Search indexes verified/created.")
        except OperationFailure as e:
            logger.error("Failed to ensure Atlas search indexes. Must run on Atlas Cluster MongoDB >= 7.0", error=str(e))
        except Exception as e:
            logger.warning(f"Could not automatically ensure vector/search index. {str(e)}")

    def _ensure_atlas_search_indexes(self):
        # We use db.command to run search index creation as typical pymongo create_index focuses on b-tree
        # Define vector index on embeddings
        vector_index_def = {
            "name": "vector_index",
            "type": "vectorSearch",
            "definition": {
                "fields": [
                    {
                        "type": "vector",
                        "numDimensions": settings.embedding_dim,
                        "path": "vector",
                        "similarity": "cosine"
                    },
                    {
                        "type": "filter",
                        "path": "repo_id"
                    },
                    {
                        "type": "filter",
                        "path": "branch"
                    }
                ]
            }
        }
        
        # Text indexes on chunks and symbols
        chunk_text_index_def = {
            "name": "chunk_text_index",
            "type": "search",
            "definition": {
                "mappings": {
                    "dynamic": False,
                    "fields": {
                        "content": {"type": "string"},
                        "file_path": {"type": "string"},
                        "repo_id": {"type": "string"},
                        "branch": {"type": "string"}
                    }
                }
            }
        }
        
        symbol_text_index_def = {
            "name": "symbol_text_index",
            "type": "search",
            "definition": {
                "mappings": {
                    "dynamic": False,
                    "fields": {
                        "name": {"type": "string"},
                        "file_path": {"type": "string"},
                        "repo_id": {"type": "string"},
                        "branch": {"type": "string"}
                    }
                }
            }
        }

        # Check existing and create if missing
        for coll, index_def in [
            (self.embeddings, vector_index_def),
            (self.chunks, chunk_text_index_def),
            (self.symbols, symbol_text_index_def)
        ]:
            existing_indexes = list(coll.list_search_indexes())
            existing_names = [idx['name'] for idx in existing_indexes]
            if index_def["name"] not in existing_names:
                logger.info(f"Creating Atlas Search index {index_def['name']} on {coll.name}")
                coll.create_search_index(index_def)
                

    # CRUD & Upsert Logic
    def upsert_repo(self, repo: Repo):
        self.repos.update_one({"repo_id": repo.repo_id}, {"$set": repo.model_dump()}, upsert=True)

    def bulk_upsert_files(self, files: List[RepoFile]):
        if not files: return
        ops = [
            UpdateOne(
                {
                    "repo_id": f.repo_id, 
                    "branch": f.branch, 
                    "commit_sha": f.commit_sha,
                    "file_path": f.file_path
                },
                {"$set": f.model_dump()},
                upsert=True
            ) for f in files
        ]
        if ops:
            self.files.bulk_write(ops, ordered=False)

    def bulk_upsert_chunks(self, chunks: List[Chunk]):
        if not chunks: return
        ops = [
            UpdateOne(
                {
                    "repo_id": c.repo_id, 
                    "branch": c.branch, 
                    "commit_sha": c.commit_sha,
                    "chunk_id": c.chunk_id
                },
                {"$set": c.model_dump()},
                upsert=True
            ) for c in chunks
        ]
        if ops:
            self.chunks.bulk_write(ops, ordered=False)

    def bulk_upsert_symbols(self, symbols: List[Symbol]):
        if not symbols: return
        ops = [
            UpdateOne(
                {
                    "repo_id": s.repo_id, 
                    "branch": s.branch, 
                    "commit_sha": s.commit_sha,
                    "symbol_id": s.symbol_id
                },
                {"$set": s.model_dump()},
                upsert=True
            ) for s in symbols
        ]
        if ops:
            self.symbols.bulk_write(ops, ordered=False)

    def bulk_upsert_embeddings(self, embeddings: List[Embedding]):
        if not embeddings: return
        ops = [
            UpdateOne(
                {
                    "repo_id": e.repo_id, 
                    "branch": e.branch, 
                    "commit_sha": e.commit_sha,
                    "chunk_id": e.chunk_id
                },
                {"$set": e.model_dump()},
                upsert=True
            ) for e in embeddings
        ]
        if ops:
            self.embeddings.bulk_write(ops, ordered=False)

    def save_job(self, job: IndexJob):
        self.index_jobs.update_one({"job_id": job.job_id}, {"$set": job.model_dump()}, upsert=True)

    def get_job(self, repo_id: str, job_id: Optional[str] = None) -> Optional[IndexJob]:
        query = {"repo_id": repo_id}
        if job_id:
            query["job_id"] = job_id
        res = self.index_jobs.find_one(query, sort=[("started_at", DESCENDING)])
        return IndexJob(**res) if res else None

    def delete_stale_data(self, repo_id: str, branch: str, active_commit_sha: str):
        """Removes data for a repo/branch that does not match the active_commit_sha."""
        query = {
            "repo_id": repo_id,
            "branch": branch,
            "commit_sha": {"$ne": active_commit_sha}
        }
        
        # We can tally these for job stats
        f_del = self.files.delete_many(query).deleted_count
        s_del = self.symbols.delete_many(query).deleted_count
        c_del = self.chunks.delete_many(query).deleted_count
        e_del = self.embeddings.delete_many(query).deleted_count
        
        return f_del + s_del + c_del + e_del
