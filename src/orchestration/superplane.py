import json
import uuid
from pathlib import Path
from typing import Any, Dict

import httpx

from src.agents.models import (
    AgentRequest,
    OrchestratorInput,
    SuperplaneExecuteRequest,
    SuperplaneExecuteResponse,
)
from src.agents.services import guard_agent, memory_agent, orchestrator_agent, role_agent
from src.core.config import logger, settings


class LocalSuperplaneRunner:
    def __init__(self, pipeline_file: str = "config/superplane_pipeline.json"):
        self.pipeline_file = Path(pipeline_file)

    def load_pipeline(self) -> Dict[str, Any]:
        if not self.pipeline_file.exists():
            return {
                "sequence": ["role", "memory", "orchestrator", "guard"],
                "routing": {
                    "skip_memory_if_simple": True,
                    "force_memory_if_debug": True,
                },
            }
        with self.pipeline_file.open("r", encoding="utf-8") as f:
            return json.load(f)

    async def execute(self, request: SuperplaneExecuteRequest) -> SuperplaneExecuteResponse:
        trace_id = str(uuid.uuid4())
        pipeline = self.load_pipeline()

        base_req = AgentRequest(
            query=request.query,
            repo_id=request.repo_id,
            branch=request.branch,
            top_k=request.top_k,
            trace_id=trace_id,
        )

        role = role_agent(base_req)
        agents_used = ["role"]

        routing_cfg = pipeline.get("routing", {})
        call_memory = True
        if routing_cfg.get("skip_memory_if_simple", True) and role.simple_query:
            call_memory = False
        if routing_cfg.get("force_memory_if_debug", True) and role.debug_query:
            call_memory = True

        mem = None
        if call_memory:
            mem = memory_agent(base_req)
            agents_used.append("memory")

        orchestrator_input = OrchestratorInput(
            request=base_req,
            role=role,
            memory=mem,
            agents_used=agents_used + ["orchestrator"],
        )
        orchestration_result = orchestrator_agent(orchestrator_input)

        guarded = guard_agent(orchestration_result, trace_id=trace_id)

        chunks = mem.chunks if mem else []

        return SuperplaneExecuteResponse(
            answer=guarded.response.answer,
            agents_used=guarded.response.agents_used,
            confidence=guarded.response.confidence,
            sources=guarded.response.sources,
            trace_id=trace_id,
            chunks=chunks,
            routing={
                "simple_query": role.simple_query,
                "debug_query": role.debug_query,
                "memory_called": call_memory,
                "guard_accepted": guarded.accepted,
                "guard_reasons": guarded.reasons,
            },
        )


class SuperplaneClient:
    def __init__(self):
        self.local_runner = LocalSuperplaneRunner()

    async def execute(self, request: SuperplaneExecuteRequest) -> SuperplaneExecuteResponse:
        if settings.superplane_base_url:
            endpoint = f"{settings.superplane_base_url.rstrip('/')}/execute"
            payload = request.model_dump()
            try:
                async with httpx.AsyncClient(timeout=20.0) as client:
                    response = await client.post(endpoint, json=payload)
                    response.raise_for_status()
                    data = response.json()
                    return SuperplaneExecuteResponse(**data)
            except Exception as exc:
                logger.error("superplane_remote_failed", endpoint=endpoint, error=str(exc))
                return await self.local_runner.execute(request)

        return await self.local_runner.execute(request)
