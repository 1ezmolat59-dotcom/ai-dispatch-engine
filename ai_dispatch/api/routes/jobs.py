"""
Jobs API routes.
"""

from __future__ import annotations
from datetime import datetime
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field

from ...models.job import Job, JobType, JobPriority, JobStatus, CustomerInfo, EquipmentInfo
from ...core.dispatch_engine import DispatchEngine

router = APIRouter(prefix="/jobs", tags=["jobs"])


# ─── Request / Response models ────────────────────────────────────────────────

class CustomerCreate(BaseModel):
    customer_id: str
    name: str
    phone: str
    email: str
    address: str
    latitude: float
    longitude: float
    sms_opt_in: bool = True
    email_opt_in: bool = True
    lifetime_jobs: int = 0


class EquipmentCreate(BaseModel):
    make: Optional[str] = None
    model: Optional[str] = None
    year_installed: Optional[int] = None
    serial_number: Optional[str] = None


class JobCreate(BaseModel):
    job_type: JobType
    priority: JobPriority
    customer: CustomerCreate
    description: str = ""
    equipment: Optional[EquipmentCreate] = None
    special_instructions: str = ""
    fsm_job_id: Optional[str] = None
    scheduled_start: Optional[datetime] = None

    class Config:
        use_enum_values = True


class JobCompletionRequest(BaseModel):
    actual_duration_minutes: int = Field(gt=0, le=600)
    notes: str = ""
    customer_satisfaction: Optional[int] = Field(None, ge=1, le=5)


class ManualAssignRequest(BaseModel):
    tech_id: str


# ─── Dependency ───────────────────────────────────────────────────────────────

_engine_ref: Optional[DispatchEngine] = None

def get_engine() -> DispatchEngine:
    if _engine_ref is None:
        raise HTTPException(503, "Dispatch engine not initialized")
    return _engine_ref

def set_engine(engine: DispatchEngine):
    global _engine_ref
    _engine_ref = engine


# ─── Routes ───────────────────────────────────────────────────────────────────

@router.post("/", status_code=201, summary="Create and queue a new job")
async def create_job(payload: JobCreate, engine: DispatchEngine = Depends(get_engine)):
    customer = CustomerInfo(
        customer_id=payload.customer.customer_id,
        name=payload.customer.name,
        phone=payload.customer.phone,
        email=payload.customer.email,
        address=payload.customer.address,
        latitude=payload.customer.latitude,
        longitude=payload.customer.longitude,
        sms_opt_in=payload.customer.sms_opt_in,
        email_opt_in=payload.customer.email_opt_in,
        lifetime_jobs=payload.customer.lifetime_jobs,
    )
    equipment = None
    if payload.equipment:
        equipment = EquipmentInfo(
            make=payload.equipment.make,
            model=payload.equipment.model,
            year_installed=payload.equipment.year_installed,
            serial_number=payload.equipment.serial_number,
        )
    job = Job(
        job_type=JobType(payload.job_type) if isinstance(payload.job_type, str) else payload.job_type,
        priority=JobPriority(payload.priority) if isinstance(payload.priority, int) else payload.priority,
        customer=customer,
        description=payload.description,
        equipment=equipment,
        special_instructions=payload.special_instructions,
        fsm_job_id=payload.fsm_job_id,
        scheduled_start=payload.scheduled_start,
    )
    job_id = engine.add_job(job)
    return {"job_id": job_id, "status": "queued", "message": "Job accepted and queued for dispatch"}


@router.get("/", summary="List all active jobs")
async def list_jobs(
    status: Optional[str] = None,
    engine: DispatchEngine = Depends(get_engine)
) -> List[Dict[str, Any]]:
    jobs = list(engine._jobs.values())
    if status:
        try:
            target_status = JobStatus(status)
            jobs = [j for j in jobs if j.status == target_status]
        except ValueError:
            raise HTTPException(400, f"Invalid status: {status}")
    return [j.to_dict() for j in sorted(jobs, key=lambda j: j.priority.value)]


@router.get("/{job_id}", summary="Get a specific job")
async def get_job(job_id: str, engine: DispatchEngine = Depends(get_engine)) -> Dict[str, Any]:
    job = engine._jobs.get(job_id)
    if not job:
        raise HTTPException(404, f"Job {job_id} not found")
    result = engine._assignments.get(job_id)
    response = job.to_dict()
    if result:
        response["assignment"] = result.to_dict()
    return response


@router.patch("/{job_id}/complete", summary="Mark job as completed")
async def complete_job(
    job_id: str,
    payload: JobCompletionRequest,
    engine: DispatchEngine = Depends(get_engine)
) -> Dict[str, Any]:
    job = engine._jobs.get(job_id)
    if not job:
        raise HTTPException(404, f"Job {job_id} not found")
    if payload.customer_satisfaction:
        job.customer_satisfaction = payload.customer_satisfaction
        job.completion_notes = payload.notes
    engine.mark_job_completed(job_id, payload.actual_duration_minutes)
    return {"job_id": job_id, "status": "completed", "actual_duration_minutes": payload.actual_duration_minutes}


@router.post("/{job_id}/assign", summary="Manually assign a job to a specific technician")
async def manual_assign(
    job_id: str,
    payload: ManualAssignRequest,
    engine: DispatchEngine = Depends(get_engine)
) -> Dict[str, Any]:
    result = await engine.manual_assign(job_id, payload.tech_id)
    if not result:
        raise HTTPException(400, "Assignment failed. Check job_id and tech_id.")
    return result.to_dict()


@router.delete("/{job_id}", summary="Cancel a job")
async def cancel_job(job_id: str, engine: DispatchEngine = Depends(get_engine)):
    job = engine._jobs.get(job_id)
    if not job:
        raise HTTPException(404, f"Job {job_id} not found")
    job.status = JobStatus.CANCELLED
    engine.remove_job(job_id)
    return {"job_id": job_id, "status": "cancelled"}


# ─── Bulk create ──────────────────────────────────────────────────────────────

class BulkJobCreate(BaseModel):
    """Request body for bulk job creation. Accepts 1-50 jobs per call."""
    jobs: List[JobCreate] = Field(..., min_length=1, max_length=50)


@router.post(
    "/bulk",
    status_code=207,
    summary="Bulk create jobs (max 50 per request)",
)
async def create_jobs_bulk(
    payload: BulkJobCreate,
    engine: DispatchEngine = Depends(get_engine),
) -> Dict[str, Any]:
    """
    Create multiple jobs in a single call.
    Returns HTTP 207 Multi-Status with per-item success/failure details.
    Failed items do not block the rest — all jobs are attempted.
    """
    results = []
    for job_data in payload.jobs:
        try:
            customer = CustomerInfo(
                customer_id=job_data.customer.customer_id,
                name=job_data.customer.name,
                phone=job_data.customer.phone,
                email=job_data.customer.email,
                address=job_data.customer.address,
                latitude=job_data.customer.latitude,
                longitude=job_data.customer.longitude,
                sms_opt_in=job_data.customer.sms_opt_in,
                email_opt_in=job_data.customer.email_opt_in,
                lifetime_jobs=job_data.customer.lifetime_jobs,
            )
            equipment = None
            if job_data.equipment:
                equipment = EquipmentInfo(
                    make=job_data.equipment.make,
                    model=job_data.equipment.model,
                    year_installed=job_data.equipment.year_installed,
                    serial_number=job_data.equipment.serial_number,
                )
            job = Job(
                job_type=JobType(job_data.job_type) if isinstance(job_data.job_type, str) else job_data.job_type,
                priority=JobPriority(job_data.priority) if isinstance(job_data.priority, int) else job_data.priority,
                customer=customer,
                description=job_data.description,
                equipment=equipment,
                special_instructions=job_data.special_instructions,
                fsm_job_id=job_data.fsm_job_id,
                scheduled_start=job_data.scheduled_start,
            )
            job_id = engine.add_job(job)
            results.append({"job_id": job_id, "status": "created"})
        except Exception as e:
            results.append({"error": str(e), "status": "failed"})

    created = sum(1 for r in results if r.get("status") == "created")
    return {
        "created": created,
        "failed": len(results) - created,
        "results": results,
    }
