import uuid
import datetime
from typing import List, Dict, Any
from pathlib import Path

from src.core.config import logger, settings
from src.schemas.models import Repo, RepoFile, IndexJob, Symbol, Chunk, Embedding
from src.storage.repositories import DBRepository
from src.scanner.repo_scanner import RepoScanner
from src.parser.ast_parser import ASTParser
from src.chunker.semantic_chunker import SemanticChunker
from src.embedder.base import get_embedder

class IndexingPipeline:
    def __init__(self, repo_path: str, repo_id: str, branch: str = "main"):
        self.repo_path = Path(repo_path).resolve()
        self.repo_id = repo_id
        self.branch = branch
        
        self.db = DBRepository()
        self.scanner = RepoScanner(str(self.repo_path))
        self.parser = ASTParser()
        self.chunker = SemanticChunker()
        self.embedder = get_embedder()
        self.job = None
        
        # Simple local commit SHA simulation since we might not actually have git wrapper
        # In a real app we'd use GitPython to get `git rev-parse HEAD`.
        # Here we just use a timestamp for demo purposes if it's not provided.
        self.commit_sha = "latest_local_" + datetime.datetime.utcnow().strftime("%Y%md%H%M%S")

    def run(self, mode: str = "full"):
        """Run the indexing pipeline."""
        job_id = str(uuid.uuid4())
        self.job = IndexJob(job_id=job_id, repo_id=self.repo_id, mode=mode, status="running")
        self.db.save_job(self.job)
        
        logger.info(f"Starting {mode} indexing job {job_id} for repo {self.repo_id}")
        
        try:
            self._ensure_repo_entry()
            
            # 1. Scan files
            valid_files = list(self.scanner.scan())
            self.job.stats["files_scanned"] = len(valid_files)
            
            # Bulk hold items
            all_db_files = []
            all_db_symbols = []
            all_db_chunks = []
            all_db_embeddings = []

            for file_rel_path in valid_files:
                full_path = self.repo_path / file_rel_path
                
                try:
                    content, content_hash, size_bytes = self.scanner.get_file_content_and_hash(full_path)
                except UnicodeDecodeError:
                    continue  # binary file
                except Exception as e:
                    self.job.errors.append(f"Failed to read {file_rel_path}: {e}")
                    self.job.stats["errors"] += 1
                    continue
                
                # Check for incremental bypass (simplified: check if hash exists for this repo/branch in db)
                if mode == "incremental":
                    existing = self.db.files.find_one({
                        "repo_id": self.repo_id, 
                        "branch": self.branch, 
                        "file_path": file_rel_path,
                        "file_hash": content_hash
                    })
                    if existing:
                        continue # Skip already indexed unchanged file
                
                language = self.scanner.get_supported_language(file_rel_path)
                
                # Create RepoFile
                repo_file = RepoFile(
                    repo_id=self.repo_id,
                    branch=self.branch,
                    commit_sha=self.commit_sha,
                    file_path=file_rel_path,
                    language=language,
                    size_bytes=size_bytes,
                    file_hash=content_hash
                )
                all_db_files.append(repo_file)
                self.job.stats["files_parsed"] += 1

                # 2. Extract Symbols
                symbol_data_list = self.parser.parse(content, language)
                for s in symbol_data_list:
                    symbol_id = f"{repo_file.file_hash}_{s.name}_{s.start_line}"
                    all_db_symbols.append(Symbol(
                        repo_id=self.repo_id,
                        branch=self.branch,
                        commit_sha=self.commit_sha,
                        symbol_id=symbol_id,
                        file_path=file_rel_path,
                        symbol_type=s.symbol_type,
                        name=s.name,
                        signature=s.signature,
                        start_line=s.start_line,
                        end_line=s.end_line
                    ))
                self.job.stats["symbols_extracted"] += len(symbol_data_list)

                # 3. Create Chunks
                chunk_data_list = self.chunker.chunk_file(content, symbol_data_list)
                chunks = self.chunker.to_models(
                    chunk_data_list, 
                    repo_id=self.repo_id, 
                    branch=self.branch, 
                    commit_sha=self.commit_sha, 
                    file_path=file_rel_path, 
                    language=language
                )
                all_db_chunks.extend(chunks)
                self.job.stats["chunks_created"] += len(chunks)

            # 4. Generate Embeddings (batch them)
            # Embed chunks
            if all_db_chunks:
                texts_to_embed = [c.content for c in all_db_chunks]
                
                # Embed in chunks
                batch_size = settings.embedding_batch_size
                all_vectors = []
                for i in range(0, len(texts_to_embed), batch_size):
                    batch = texts_to_embed[i:i+batch_size]
                    vectors = self.embedder.embed_texts(batch)
                    all_vectors.extend(vectors)
                
                for c, vec in zip(all_db_chunks, all_vectors):
                    # We create Embedding docs
                    all_db_embeddings.append(Embedding(
                        repo_id=c.repo_id,
                        branch=c.branch,
                        commit_sha=c.commit_sha,
                        chunk_id=c.chunk_id,
                        embedding_model=settings.embedding_model,
                        embedding_dim=settings.embedding_dim,
                        vector=vec
                    ))
                self.job.stats["embeddings_created"] += len(all_db_embeddings)

            # 5. Persist to DB
            logger.info("Upserting records to MongoDB...")
            self.db.bulk_upsert_files(all_db_files)
            self.db.bulk_upsert_symbols(all_db_symbols)
            self.db.bulk_upsert_chunks(all_db_chunks)
            self.db.bulk_upsert_embeddings(all_db_embeddings)
            
            total_upserts = len(all_db_files) + len(all_db_symbols) + len(all_db_chunks) + len(all_db_embeddings)
            self.job.stats["upserts"] = total_upserts
            
            # 6. Cleanup Stale records (if full or incremental and file was deleted)
            # Simplified: Delete anything in this repo/branch that does NOT match this commit_sha
            logger.info("Cleaning up stale records...")
            deleted_count = self.db.delete_stale_data(self.repo_id, self.branch, self.commit_sha)
            self.job.stats["deletes"] = deleted_count
            
            self.job.status = "completed"

        except Exception as e:
            logger.error(f"Job {self.job.job_id} failed", error=str(e))
            self.job.status = "failed"
            self.job.errors.append(str(e))
        finally:
            self.job.finished_at = datetime.datetime.utcnow()
            self.db.save_job(self.job)
            logger.info(f"Finished job {job_id}. Status: {self.job.status}")

        return self.job

    def _ensure_repo_entry(self):
        repo_name = self.repo_path.name
        self.db.upsert_repo(Repo(
            repo_id=self.repo_id,
            name=repo_name,
            root_path=str(self.repo_path),
            default_branch=self.branch,
            last_indexed_commit=self.commit_sha
        ))
