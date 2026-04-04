from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel
from typing import List, Dict, Any, Optional
from src.retrieval.search import Retriever

app = FastAPI(title="Hackbite Retrieval API")

class ContextPack(BaseModel):
    chunk_id: str
    file_path: str
    start_line: int
    end_line: int
    content: str
    score: float
    confidence: float
    reason: str

class RetrieveResponse(BaseModel):
    query: str
    results: List[ContextPack]

@app.get("/health")
def health():
    return {"status": "ok"}

@app.get("/retrieve", response_model=RetrieveResponse)
def retrieve(
    q: str = Query(..., description="The query string"),
    repo_id: str = Query(..., description="Repository ID"),
    branch: str = Query("main", description="Branch name"),
    top_k: int = Query(5, description="Number of results to return")
):
    try:
        retriever = Retriever()
        search_results = retriever.retrieve_hybrid(repo_id, branch, q, top_k=top_k)
        
        packs = []
        for result in search_results:
            chunk = result["chunk"]
            packs.append(
                ContextPack(
                    chunk_id=chunk["chunk_id"],
                    file_path=chunk["file_path"],
                    start_line=chunk["start_line"],
                    end_line=chunk["end_line"],
                    content=chunk["content"],
                    score=result["score"],
                    confidence=result["confidence"],
                    reason=result["reason"]
                )
            )
            
        return RetrieveResponse(query=q, results=packs)
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))
