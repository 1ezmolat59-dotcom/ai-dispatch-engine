"""
Dispatch management routes — board overview, metrics, manual controls.
"""

from __future__ import annotations
from typing import Any, Dict, List
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ...core.dispatch_engine import DispatchEngine
from .jobs import get_engine

router = APIRouter(prefix="/dispatch", tags=["dispatch"])


@router.get("/board", summary="Get full dispatch board snapshot")
async def get_board(engine: DispatchEngine = Depends(get_engine)) -> Dict[str, Any]:
    """Returns the complete current state of the dispatch board."""
    snapshot = engine.get_board_snapshot()
    return snapshot.to_dict()


@router.get("/metrics", summary="Get real-time performance metrics")
async def get_metrics(engine: DispatchEngine = Depends(get_engine)) -> Dict[str, Any]:
    """Key dispatch performance indicators."""
    from ...models.job import JobStatus
    from ...models.technician import TechnicianStatus

    jobs = list(engine._jobs.values())
    techs = list(engine._technicians.values())

    pending = [j for j in jobs if j.status == JobStatus.PENDING]
    assigned = [j for j in jobs if j.status == JobStatus.ASSIGNED]
    in_progress = [j for j in jobs if j.status == JobStatus.IN_PROGRESS]
    emergencies = [j for j in jobs if j.is_emergency]

    available_techs = [t for t in techs if t.status == TechnicianStatus.AVAILABLE]
    on_job_techs = [t for t in techs if t.status in (TechnicianStatus.ON_JOB, TechnicianStatus.EN_ROUTE)]

    avg_wait = (
        sum(j.wait_time_minutes for j in pending) / len(pending)
        if pending else 0.0
    )

    assignments = list(engine._assignments.values())
    avg_score = (
        sum(r.scores.total_score for r in assignments if r.scores) / len(assignments)
        if assignments else 0.0
    )

    return {
        "jobs": {
            "pending": len(pending),
            "assigned": len(assigned),
            "in_progress": len(in_progress),
            "emergencies_active": len(emergencies),
            "avg_wait_time_minutes": round(avg_wait, 1),
        },
        "technicians": {
            "total": len(techs),
            "available": len(available_techs),
            "on_job": len(on_job_techs),
            "utilization_rate": round(len(on_job_techs) / max(len(techs), 1), 2),
        },
        "ai": {
            "optimizer_assignments": len(assignments),
            "avg_assignment_score": round(avg_score, 4),
            "ml_predictor_trained": engine.predictor.is_trained,
            "ml_training_samples": engine.predictor.training_samples,
        },
        "engine": {
            "running": engine._running,
            "optimization_interval_seconds": engine.optimization_interval,
        }
    }


@router.post("/optimize", summary="Trigger an immediate optimization pass")
async def trigger_optimization(engine: DispatchEngine = Depends(get_engine)):
    """Force an optimization cycle right now (instead of waiting for the scheduler)."""
    import asyncio
    asyncio.create_task(engine._trigger_optimization())
    return {"message": "Optimization triggered", "status": "running"}


@router.get("/assignments", summary="Get recent assignment decisions")
async def get_assignments(
    limit: int = 20,
    engine: DispatchEngine = Depends(get_engine)
) -> List[Dict[str, Any]]:
    limit = min(limit, 50)
    return [r.to_dict() for r in engine._recent_assignments[:limit]]


@router.get("/assignments/{job_id}", summary="Get assignment details for a specific job")
async def get_assignment(job_id: str, engine: DispatchEngine = Depends(get_engine)):
    result = engine._assignments.get(job_id)
    if not result:
        raise HTTPException(404, f"No assignment found for job {job_id}")
    return result.to_dict()
