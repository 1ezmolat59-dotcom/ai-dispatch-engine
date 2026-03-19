"""
Demo / seed endpoint — populates the engine with realistic sample data.
Call POST /api/v1/demo/seed to load technicians + jobs instantly.
Only available when ENVIRONMENT != production.
"""

from __future__ import annotations
import random
import uuid
from datetime import datetime
from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException

from ...core.dispatch_engine import DispatchEngine
from ...models.job import Job, JobType, JobPriority, CustomerInfo, EquipmentInfo
from ...models.technician import Technician, TechnicianStatus, Skill, SkillLevel, WorkSchedule
from datetime import time as dtime
from ...config import config as app_config
from .jobs import get_engine

router = APIRouter(prefix="/demo", tags=["demo"])

random.seed()  # fresh seed each call so locations vary


# ── sample data ───────────────────────────────────────────────────────────────

_TECH_PROFILES = [
    {
        "name": "Marcus Johnson",
        "phone": "+15550001001",
        "email": "marcus@dispatch.demo",
        "skills": [
            {"skill_id": "hvac", "name": "hvac", "category": "hvac", "level": SkillLevel.MASTER},
            {"skill_id": "refrig", "name": "refrigerant_handling", "category": "hvac", "level": SkillLevel.SENIOR},
            {"skill_id": "hvac_diag", "name": "hvac_diagnostic", "category": "hvac", "level": SkillLevel.SENIOR},
        ],
        "years_experience": 12.0,
        "customer_rating": 4.9,
        "on_time_rate": 0.96,
        "home_base_lat": 40.7128,
        "home_base_lon": -74.0060,
    },
    {
        "name": "Priya Patel",
        "phone": "+15550001002",
        "email": "priya@dispatch.demo",
        "skills": [
            {"skill_id": "plumb", "name": "plumbing", "category": "plumbing", "level": SkillLevel.SENIOR},
            {"skill_id": "plumb_inst", "name": "plumbing_installation", "category": "plumbing", "level": SkillLevel.JOURNEYMAN},
            {"skill_id": "drain", "name": "drain_cleaning", "category": "plumbing", "level": SkillLevel.SENIOR},
            {"skill_id": "wh", "name": "water_heater", "category": "plumbing", "level": SkillLevel.JOURNEYMAN},
        ],
        "years_experience": 7.5,
        "customer_rating": 4.7,
        "on_time_rate": 0.91,
        "home_base_lat": 40.7282,
        "home_base_lon": -73.9942,
    },
    {
        "name": "Derek Williams",
        "phone": "+15550001003",
        "email": "derek@dispatch.demo",
        "skills": [
            {"skill_id": "elec", "name": "electrical", "category": "electrical", "level": SkillLevel.MASTER},
            {"skill_id": "elec_rep", "name": "electrical_repair", "category": "electrical", "level": SkillLevel.MASTER},
            {"skill_id": "elec_inst", "name": "electrical_installation", "category": "electrical", "level": SkillLevel.SENIOR},
            {"skill_id": "panel", "name": "panel_upgrade", "category": "electrical", "level": SkillLevel.SENIOR},
            {"skill_id": "ev", "name": "ev_charger", "category": "electrical", "level": SkillLevel.JOURNEYMAN},
        ],
        "years_experience": 15.0,
        "customer_rating": 4.8,
        "on_time_rate": 0.94,
        "home_base_lat": 40.7489,
        "home_base_lon": -73.9680,
    },
    {
        "name": "Sofia Reyes",
        "phone": "+15550001004",
        "email": "sofia@dispatch.demo",
        "skills": [
            {"skill_id": "hvac2", "name": "hvac", "category": "hvac", "level": SkillLevel.JOURNEYMAN},
            {"skill_id": "gen_maint", "name": "general_maintenance", "category": "general", "level": SkillLevel.SENIOR},
            {"skill_id": "insp", "name": "inspection", "category": "general", "level": SkillLevel.SENIOR},
        ],
        "years_experience": 4.0,
        "customer_rating": 4.5,
        "on_time_rate": 0.88,
        "home_base_lat": 40.7614,
        "home_base_lon": -73.9776,
    },
    {
        "name": "Ahmed Hassan",
        "phone": "+15550001005",
        "email": "ahmed@dispatch.demo",
        "skills": [
            {"skill_id": "plumb2", "name": "plumbing", "category": "plumbing", "level": SkillLevel.MASTER},
            {"skill_id": "drain2", "name": "drain_cleaning", "category": "plumbing", "level": SkillLevel.MASTER},
            {"skill_id": "wh2", "name": "water_heater", "category": "plumbing", "level": SkillLevel.SENIOR},
            {"skill_id": "plumb_em", "name": "plumbing_installation", "category": "plumbing", "level": SkillLevel.SENIOR},
        ],
        "years_experience": 9.0,
        "customer_rating": 4.6,
        "on_time_rate": 0.92,
        "home_base_lat": 40.6892,
        "home_base_lon": -74.0445,
    },
]

_JOB_SCENARIOS = [
    {
        "job_type": JobType.HVAC_EMERGENCY,
        "priority": JobPriority.EMERGENCY,
        "description": "No heat — outdoor temp dropping. Family with infant.",
        "customer_name": "Rachel Green",
        "equipment_make": "Carrier",
        "equipment_year": 2008,
    },
    {
        "job_type": JobType.PLUMBING_REPAIR,
        "priority": JobPriority.URGENT,
        "description": "Burst pipe under kitchen sink, water pooling on floor.",
        "customer_name": "Tom Bradley",
        "equipment_make": None,
        "equipment_year": None,
    },
    {
        "job_type": JobType.ELECTRICAL_REPAIR,
        "priority": JobPriority.HIGH,
        "description": "Half the outlets in the master bedroom are dead.",
        "customer_name": "Linda Chen",
        "equipment_make": "Square D",
        "equipment_year": 2005,
    },
    {
        "job_type": JobType.HVAC_MAINTENANCE,
        "priority": JobPriority.NORMAL,
        "description": "Annual A/C tune-up before summer season.",
        "customer_name": "James Ortega",
        "equipment_make": "Trane",
        "equipment_year": 2019,
    },
    {
        "job_type": JobType.DRAIN_CLEANING,
        "priority": JobPriority.NORMAL,
        "description": "Slow drain in main bathroom, recurring issue.",
        "customer_name": "Aisha Williams",
        "equipment_make": None,
        "equipment_year": None,
    },
    {
        "job_type": JobType.PANEL_UPGRADE,
        "priority": JobPriority.NORMAL,
        "description": "Upgrade 100A panel to 200A for new EV charger.",
        "customer_name": "Kevin Park",
        "equipment_make": "Eaton",
        "equipment_year": 1998,
    },
    {
        "job_type": JobType.WATER_HEATER,
        "priority": JobPriority.HIGH,
        "description": "Water heater not producing hot water. 10-year-old unit.",
        "customer_name": "Maria Santos",
        "equipment_make": "Rheem",
        "equipment_year": 2014,
    },
    {
        "job_type": JobType.EV_CHARGER,
        "priority": JobPriority.NORMAL,
        "description": "Install Level 2 EV charger in garage.",
        "customer_name": "David Kim",
        "equipment_make": "ChargePoint",
        "equipment_year": None,
    },
]

_NEIGHBORHOODS = [
    (40.7614, -73.9776, "350 W 57th St, New York, NY"),
    (40.7282, -73.7949, "142-15 Hillside Ave, Jamaica, NY"),
    (40.6501, -73.9496, "1000 Flatbush Ave, Brooklyn, NY"),
    (40.8448, -73.8648, "900 Morris Park Ave, Bronx, NY"),
    (40.5795, -74.1502, "2765 Richmond Ave, Staten Island, NY"),
    (40.7489, -73.9680, "425 Lexington Ave, New York, NY"),
    (40.7128, -74.0059, "200 Liberty St, New York, NY"),
    (40.7831, -73.9712, "2880 Broadway, New York, NY"),
]


@router.post("/seed", summary="Seed demo technicians + jobs (dev only)")
async def seed_demo_data(engine: DispatchEngine = Depends(get_engine)) -> Dict[str, Any]:
    """
    Populate the engine with 5 technicians and 8 realistic dispatch jobs.
    Triggers immediate optimization after seeding.
    """
    if app_config.environment == "production":
        raise HTTPException(403, "Demo seed disabled in production")

    added_techs = []
    added_jobs = []

    # ── Technicians ───────────────────────────────────────────────────────────
    for profile in _TECH_PROFILES:
        # Skip if already registered (same name)
        if any(t.name == profile["name"] for t in engine._technicians.values()):
            continue

        skills = [
            Skill(
                skill_id=s["skill_id"],
                name=s["name"],
                category=s["category"],
                level=s["level"],
                certified=s["level"].value >= SkillLevel.SENIOR.value,
            )
            for s in profile["skills"]
        ]
        tech = Technician(
            name=profile["name"],
            phone=profile["phone"],
            email=profile["email"],
            skills=skills,
            years_experience=profile["years_experience"],
            customer_rating=profile["customer_rating"],
            on_time_rate=profile["on_time_rate"],
            home_base_lat=profile["home_base_lat"],
            home_base_lon=profile["home_base_lon"],
            avg_job_duration_minutes=75.0,
            jobs_completed_lifetime=random.randint(100, 800),
            completion_rate=round(random.uniform(0.90, 0.99), 2),
        )
        # 24h schedule so demo works in any timezone
        schedule_24h = WorkSchedule(
            monday_start=dtime(0, 0), monday_end=dtime(23, 59),
            tuesday_start=dtime(0, 0), tuesday_end=dtime(23, 59),
            wednesday_start=dtime(0, 0), wednesday_end=dtime(23, 59),
            thursday_start=dtime(0, 0), thursday_end=dtime(23, 59),
            friday_start=dtime(0, 0), friday_end=dtime(23, 59),
            saturday_start=dtime(0, 0), saturday_end=dtime(23, 59),
            sunday_start=dtime(0, 0), sunday_end=dtime(23, 59),
        )
        tech.schedule = schedule_24h
        engine.add_technician(tech)
        added_techs.append({"tech_id": tech.tech_id, "name": tech.name})

    # ── Jobs ──────────────────────────────────────────────────────────────────
    for i, scenario in enumerate(_JOB_SCENARIOS):
        lat, lon, address = _NEIGHBORHOODS[i % len(_NEIGHBORHOODS)]
        # Slight jitter so pins don't stack
        lat += random.uniform(-0.005, 0.005)
        lon += random.uniform(-0.005, 0.005)

        customer = CustomerInfo(
            customer_id=str(uuid.uuid4()),
            name=scenario["customer_name"],
            phone=f"+1555{random.randint(1000000, 9999999)}",
            email=f"{scenario['customer_name'].lower().replace(' ', '.')}@demo.com",
            address=address,
            latitude=lat,
            longitude=lon,
            sms_opt_in=True,
            email_opt_in=True,
            lifetime_jobs=random.randint(0, 10),
        )
        equipment = None
        if scenario["equipment_make"]:
            equipment = EquipmentInfo(
                make=scenario["equipment_make"],
                year_installed=scenario["equipment_year"],
            )
        job = Job(
            job_type=scenario["job_type"],
            priority=scenario["priority"],
            customer=customer,
            description=scenario["description"],
            equipment=equipment,
            fsm_job_id=f"DEMO-{i+1:04d}",
        )
        engine.add_job(job)
        added_jobs.append({
            "job_id": job.job_id,
            "type": job.job_type.value,
            "priority": job.priority.value,
            "customer": scenario["customer_name"],
        })

    return {
        "seeded": True,
        "technicians_added": len(added_techs),
        "jobs_added": len(added_jobs),
        "technicians": added_techs,
        "jobs": added_jobs,
        "message": "Demo data loaded. Optimization will run within 15 seconds.",
    }


@router.delete("/reset", summary="Clear all jobs and technicians (dev only)")
async def reset_demo(engine: DispatchEngine = Depends(get_engine)) -> Dict[str, Any]:
    if app_config.environment == "production":
        raise HTTPException(403, "Reset disabled in production")
    engine._jobs.clear()
    engine._technicians.clear()
    engine._assignments.clear()
    engine._recent_assignments.clear()
    return {"reset": True, "message": "All jobs and technicians cleared."}
