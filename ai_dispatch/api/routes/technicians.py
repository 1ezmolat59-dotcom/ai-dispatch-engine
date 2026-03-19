"""
Technicians API routes.
"""

from __future__ import annotations
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field

from ...models.technician import (
    Technician, TechnicianStatus, Skill, SkillLevel, WorkSchedule
)
from ...core.dispatch_engine import DispatchEngine
from .jobs import get_engine

router = APIRouter(prefix="/technicians", tags=["technicians"])


# ─── Request models ───────────────────────────────────────────────────────────

class SkillCreate(BaseModel):
    skill_id: str
    name: str
    category: str
    level: int = Field(ge=1, le=4)
    certified: bool = False


class TechnicianCreate(BaseModel):
    name: str
    phone: str
    email: str
    skills: List[SkillCreate]
    home_base_lat: float = 0.0
    home_base_lon: float = 0.0
    years_experience: float = 0.0
    customer_rating: float = Field(default=4.5, ge=1.0, le=5.0)
    on_time_rate: float = Field(default=0.9, ge=0.0, le=1.0)
    fsm_tech_id: Optional[str] = None
    employee_id: Optional[str] = None
    vehicle_id: Optional[str] = None


class LocationUpdate(BaseModel):
    latitude: float = Field(ge=-90.0, le=90.0)
    longitude: float = Field(ge=-180.0, le=180.0)
    accuracy_meters: float = 10.0
    heading: Optional[float] = None
    speed_kmh: Optional[float] = None


class StatusUpdate(BaseModel):
    status: TechnicianStatus


# ─── Routes ───────────────────────────────────────────────────────────────────

@router.post("/", status_code=201, summary="Register a new technician")
async def create_technician(
    payload: TechnicianCreate,
    engine: DispatchEngine = Depends(get_engine)
) -> Dict[str, Any]:
    skills = [
        Skill(
            skill_id=s.skill_id,
            name=s.name,
            category=s.category,
            level=SkillLevel(s.level),
            certified=s.certified,
        )
        for s in payload.skills
    ]
    tech = Technician(
        name=payload.name,
        phone=payload.phone,
        email=payload.email,
        skills=skills,
        home_base_lat=payload.home_base_lat,
        home_base_lon=payload.home_base_lon,
        years_experience=payload.years_experience,
        customer_rating=payload.customer_rating,
        on_time_rate=payload.on_time_rate,
        fsm_tech_id=payload.fsm_tech_id,
        employee_id=payload.employee_id,
        vehicle_id=payload.vehicle_id,
    )
    engine.add_technician(tech)
    return {"tech_id": tech.tech_id, "name": tech.name, "status": "registered"}


@router.get("/", summary="List all technicians")
async def list_technicians(
    status: Optional[str] = None,
    engine: DispatchEngine = Depends(get_engine)
) -> List[Dict[str, Any]]:
    techs = list(engine._technicians.values())
    if status:
        try:
            target = TechnicianStatus(status)
            techs = [t for t in techs if t.status == target]
        except ValueError:
            raise HTTPException(400, f"Invalid status: {status}")
    return [t.to_dict() for t in techs]


@router.get("/{tech_id}", summary="Get technician details")
async def get_technician(tech_id: str, engine: DispatchEngine = Depends(get_engine)):
    tech = engine._technicians.get(tech_id)
    if not tech:
        raise HTTPException(404, f"Technician {tech_id} not found")
    d = tech.to_dict()
    d["job_queue"] = tech.job_queue
    d["jobs_completed_today"] = tech.jobs_completed_today
    d["avg_job_duration_minutes"] = round(tech.avg_job_duration_minutes, 1)
    return d


@router.patch("/{tech_id}/location", summary="Update technician GPS location")
async def update_location(
    tech_id: str,
    payload: LocationUpdate,
    engine: DispatchEngine = Depends(get_engine)
):
    if tech_id not in engine._technicians:
        raise HTTPException(404, f"Technician {tech_id} not found")
    engine.update_technician_location(tech_id, payload.latitude, payload.longitude)
    return {"tech_id": tech_id, "location_updated": True}


@router.patch("/{tech_id}/status", summary="Update technician status")
async def update_status(
    tech_id: str,
    payload: StatusUpdate,
    engine: DispatchEngine = Depends(get_engine)
):
    if tech_id not in engine._technicians:
        raise HTTPException(404, f"Technician {tech_id} not found")
    engine.update_technician_status(tech_id, payload.status)
    return {"tech_id": tech_id, "status": payload.status.value}


@router.get("/{tech_id}/schedule", summary="Get technician's job queue for today")
async def get_tech_schedule(
    tech_id: str,
    engine: DispatchEngine = Depends(get_engine)
) -> Dict[str, Any]:
    tech = engine._technicians.get(tech_id)
    if not tech:
        raise HTTPException(404, f"Technician {tech_id} not found")
    queue_jobs = []
    for job_id in tech.job_queue:
        job = engine._jobs.get(job_id)
        if job:
            queue_jobs.append(job.to_dict())
    return {
        "tech_id": tech_id,
        "tech_name": tech.name,
        "status": tech.status.value,
        "jobs_completed_today": tech.jobs_completed_today,
        "queue": queue_jobs,
        "capacity_remaining": tech.max_jobs_per_day - len(tech.job_queue),
    }
