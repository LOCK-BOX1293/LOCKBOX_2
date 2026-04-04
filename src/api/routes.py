import asyncio
import json
import sys
import uuid
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional
from src.agents.models import (
    AgentRequest,
    ContextChunk,
    GuardAgentResponse,
    OrchestratorInput,
    RoleAgentResponse,
    StandardResponse,
    SuperplaneExecuteRequest,
    SuperplaneExecuteResponse,
)
from src.agents.services import guard_agent, memory_agent, orchestrator_agent, role_agent
from src.orchestration.superplane import SuperplaneClient
from src.storage.repositories import DBRepository

app = FastAPI(title="Hackbite Retrieval API")

ROOT_DIR = Path(__file__).resolve().parents[2]
STATIC_DIR = ROOT_DIR / "src" / "api" / "static"
PIPELINE_PATH = ROOT_DIR / "config" / "superplane_pipeline.json"

if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

INDEX_RUNS: Dict[str, Dict[str, Any]] = {}

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
    answer: Optional[str] = None
    agents_used: List[str] = Field(default_factory=list)
    confidence: float = 0.0
    sources: List[str] = Field(default_factory=list)
    trace_id: Optional[str] = None


class IndexRunRequest(BaseModel):
    repo_path: str = "./"
    repo_id: str
    branch: str = "main"

@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/control")
def control_center():
    target = STATIC_DIR / "control.html"
    if not target.exists():
        raise HTTPException(status_code=404, detail="Control UI not found")
    return FileResponse(str(target))


async def _run_index_command(run_id: str, args: List[str]):
    INDEX_RUNS[run_id]["status"] = "running"
    INDEX_RUNS[run_id]["started_at"] = datetime.utcnow().isoformat()

    proc = await asyncio.create_subprocess_exec(
        *args,
        cwd=str(ROOT_DIR),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await proc.communicate()

    INDEX_RUNS[run_id]["ended_at"] = datetime.utcnow().isoformat()
    INDEX_RUNS[run_id]["exit_code"] = proc.returncode
    INDEX_RUNS[run_id]["stdout"] = stdout.decode("utf-8", errors="ignore")[-20000:]
    INDEX_RUNS[run_id]["stderr"] = stderr.decode("utf-8", errors="ignore")[-20000:]
    INDEX_RUNS[run_id]["status"] = "completed" if proc.returncode == 0 else "failed"


@app.post("/admin/index/{mode}")
async def admin_run_index(mode: str, payload: IndexRunRequest):
    if mode not in {"full", "incremental"}:
        raise HTTPException(status_code=400, detail="mode must be full or incremental")

    run_id = str(uuid.uuid4())
    cmd = [
        sys.executable,
        "-m",
        "src.cli.main",
        "index",
        mode,
        "--repo-path",
        payload.repo_path,
        "--repo-id",
        payload.repo_id,
        "--branch",
        payload.branch,
    ]

    INDEX_RUNS[run_id] = {
        "run_id": run_id,
        "mode": mode,
        "command": cmd,
        "status": "queued",
        "created_at": datetime.utcnow().isoformat(),
        "repo_id": payload.repo_id,
        "branch": payload.branch,
    }

    asyncio.create_task(_run_index_command(run_id, cmd))
    return INDEX_RUNS[run_id]


@app.post("/admin/index/ensure-indexes")
async def admin_ensure_indexes():
    run_id = str(uuid.uuid4())
    cmd = [sys.executable, "-m", "src.cli.main", "index", "ensure-indexes"]
    INDEX_RUNS[run_id] = {
        "run_id": run_id,
        "mode": "ensure-indexes",
        "command": cmd,
        "status": "queued",
        "created_at": datetime.utcnow().isoformat(),
    }
    asyncio.create_task(_run_index_command(run_id, cmd))
    return INDEX_RUNS[run_id]


@app.get("/admin/index/runs")
async def admin_list_runs():
    return {"runs": list(INDEX_RUNS.values())[-20:]}


@app.get("/admin/index/runs/{run_id}")
async def admin_get_run(run_id: str):
    if run_id not in INDEX_RUNS:
        raise HTTPException(status_code=404, detail="run_id not found")
    return INDEX_RUNS[run_id]


@app.get("/admin/pipeline")
async def admin_get_pipeline():
    if not PIPELINE_PATH.exists():
        raise HTTPException(status_code=404, detail="pipeline config not found")
    with PIPELINE_PATH.open("r", encoding="utf-8") as f:
        return json.load(f)


@app.put("/admin/pipeline")
async def admin_update_pipeline(config: Dict[str, Any]):
    PIPELINE_PATH.parent.mkdir(parents=True, exist_ok=True)
    with PIPELINE_PATH.open("w", encoding="utf-8") as f:
        json.dump(config, f, indent=2)
    return {"updated": True, "path": str(PIPELINE_PATH)}


@app.get("/admin/jobs/latest")
async def admin_latest_job(repo_id: str = Query(...)):
    db = DBRepository()
    job = db.get_job(repo_id=repo_id)
    if not job:
        return {"job": None}
    return {"job": job.model_dump()}


@app.post("/role-agent", response_model=RoleAgentResponse)
async def role_agent_endpoint(request: AgentRequest):
    return role_agent(request)


@app.post("/memory-agent")
async def memory_agent_endpoint(request: AgentRequest):
    return memory_agent(request)


@app.post("/orchestrator", response_model=StandardResponse)
async def orchestrator_endpoint(payload: OrchestratorInput):
    return orchestrator_agent(payload)


@app.post("/guard", response_model=GuardAgentResponse)
async def guard_endpoint(response: StandardResponse):
    return guard_agent(response)


@app.post("/superplane/execute", response_model=SuperplaneExecuteResponse)
async def superplane_execute(payload: SuperplaneExecuteRequest):
    client = SuperplaneClient()
    return await client.execute(payload)

@app.get("/retrieve", response_model=RetrieveResponse)
async def retrieve(
    q: str = Query(..., description="The query string"),
    repo_id: str = Query(..., description="Repository ID"),
    branch: str = Query("main", description="Branch name"),
    top_k: int = Query(5, description="Number of results to return")
):
    try:
        client = SuperplaneClient()
        execution = await client.execute(
            SuperplaneExecuteRequest(query=q, repo_id=repo_id, branch=branch, top_k=top_k)
        )
        
        packs = []
        for chunk in execution.chunks:
            if isinstance(chunk, ContextChunk):
                data = chunk.model_dump()
            else:
                data = chunk
            packs.append(
                ContextPack(
                    chunk_id=data["chunk_id"],
                    file_path=data["file_path"],
                    start_line=data["start_line"],
                    end_line=data["end_line"],
                    content=data["content"],
                    score=data["score"],
                    confidence=data["confidence"],
                    reason=data["reason"],
                )
            )
            
        return RetrieveResponse(
            query=q,
            results=packs,
            answer=execution.answer,
            agents_used=execution.agents_used,
            confidence=execution.confidence,
            sources=execution.sources,
            trace_id=execution.trace_id,
        )
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))
