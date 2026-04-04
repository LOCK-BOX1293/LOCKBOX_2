from typing import Any, Dict, List
from src.storage.repositories import DBRepository
from src.core.config import settings
from src.embedder.base import get_embedder

class Retriever:
    def __init__(self):
        self.db_repo = DBRepository()
        self.embedder = get_embedder()

    def vector_search(self, repo_id: str, branch: str, query: str, top_k: int = 10) -> List[Dict[str, Any]]:
        # Generate query embedding
        query_vector = self.embedder.embed_queries([query])[0]

        pipeline = [
            {
                "$vectorSearch": {
                    "index": "vector_index",
                    "path": "vector",
                    "queryVector": query_vector,
                    "numCandidates": top_k * 5,
                    "limit": top_k,
                    "filter": {
                        "repo_id": repo_id,
                        "branch": branch
                    }
                }
            },
            {
                "$project": {
                    "_id": 0,
                    "chunk_id": 1,
                    "score": {"$meta": "vectorSearchScore"}
                }
            }
        ]

        results = list(self.db_repo.embeddings.aggregate(pipeline))
        return results

    def lexical_search(self, repo_id: str, branch: str, query: str, top_k: int = 10) -> List[Dict[str, Any]]:
        pipeline = [
            {
                "$search": {
                    "index": "chunk_text_index",
                    "text": {
                        "query": query,
                        "path": ["content", "file_path"]
                    }
                }
            },
            {
                "$match": {
                    "repo_id": repo_id,
                    "branch": branch
                }
            },
            {
                "$limit": top_k
            },
            {
                "$project": {
                    "_id": 0,
                    "chunk_id": 1,
                    "score": {"$meta": "searchScore"}
                }
            }
        ]
        
        results = list(self.db_repo.chunks.aggregate(pipeline))
        return results

    def get_chunk_details(self, repo_id: str, branch: str, chunk_ids: List[str]) -> Dict[str, Any]:
        pipeline = [
            {
                "$match": {
                    "repo_id": repo_id,
                    "branch": branch,
                    "chunk_id": {"$in": chunk_ids}
                }
            },
            {
                "$project": {
                    "_id": 0,
                    "vector": 0,
                    "content_hash": 0
                }
            }
        ]
        docs = list(self.db_repo.chunks.aggregate(pipeline))
        return {d["chunk_id"]: d for d in docs}

    def retrieve_hybrid(self, repo_id: str, branch: str, query: str, top_k: int = 5) -> List[Dict[str, Any]]:
        # 1. Fetch from Vector & Lexical
        try:
            vector_results = self.vector_search(repo_id, branch, query, top_k=top_k)
        except Exception as e:
            from src.core.config import logger
            logger.error("Vector search failed (index might not exist). Make sure to run ensure-indexes.", error=str(e))
            vector_results = []
            
        try:
            lexical_results = self.lexical_search(repo_id, branch, query, top_k=top_k)
        except Exception as e:
            from src.core.config import logger
            logger.error("Lexical search failed (index might not exist). Make sure to run ensure-indexes.", error=str(e))
            lexical_results = []

        # 2. Reciprocal Rank Fusion
        fused_scores = {}
        k_rf = 60

        def add_to_fusion(results, weight=1.0):
            for rank, res in enumerate(results):
                cid = res["chunk_id"]
                score = weight * (1.0 / (k_rf + rank + 1))
                if cid not in fused_scores:
                    fused_scores[cid] = 0.0
                fused_scores[cid] += score

        add_to_fusion(vector_results, weight=1.0)
        add_to_fusion(lexical_results, weight=1.0)

        # Sort by fused score
        sorted_chunks = sorted(fused_scores.items(), key=lambda x: x[1], reverse=True)
        top_chunks = sorted_chunks[:top_k]

        if not top_chunks:
            return []

        # 3. Retrieve chunk details
        target_ids = [c[0] for c in top_chunks]
        chunk_details = self.get_chunk_details(repo_id, branch, target_ids)

        final_results = []
        for cid, score in top_chunks:
            if cid in chunk_details:
                doc = chunk_details[cid]
                # Optional: format reason
                reason = "Matched via hybrid search"
                final_results.append({
                    "chunk": doc,
                    "score": round(score, 4),
                    "confidence": round(score * 100, 2),
                    "reason": reason
                })

        return final_results
