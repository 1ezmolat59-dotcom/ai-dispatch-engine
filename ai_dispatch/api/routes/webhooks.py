"""
Webhook ingestion endpoints for FSM and external system events.
Handles inbound events: new jobs, status changes, tech location updates.

HMAC signature validation is enforced on every route via the _webhook_auth
FastAPI dependency. Set FSM_WEBHOOK_SECRET to enable it; omitting the secret
allows all requests through (with a warning) for backward compatibility.
Set REQUIRE_WEBHOOK_SECRET=true to reject unsigned requests outright.
"""

from __future__ import annotations
import hashlib
import hmac
import logging
from typing import Any, Dict, Optional
from fastapi import APIRouter, HTTPException, Request, Depends
from pydantic import BaseModel

from ...models.job import Job, JobType, JobPriority, JobStatus, CustomerInfo
from ...models.technician import TechnicianStatus
from ...core.dispatch_engine import DispatchEngine
from ...config import config as app_config
from .jobs import get_engine

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/webhooks", tags=["webhooks"])


# ─── Pydantic event models ─────────────────────────────────────────────────────

class FSMJobCreatedEvent(BaseModel):
    """Inbound webhook from FSM when a new job is created."""
    event: str = "job.created"
    job_id: str
    job_type: str
    priority: int = 4
    customer_id: str
    customer_name: str
    customer_phone: str
    customer_email: str
    customer_address: str
    customer_lat: float
    customer_lon: float
    description: str = ""
    equipment_make: Optional[str] = None
    equipment_model: Optional[str] = None
    equipment_year: Optional[int] = None


class FSMStatusChangeEvent(BaseModel):
    """Inbound webhook from FSM when job status changes."""
    event: str
    job_id: str
    new_status: str
    tech_id: Optional[str] = None
    notes: Optional[str] = None
    actual_duration_minutes: Optional[int] = None


class TechLocationEvent(BaseModel):
    """Real-time GPS event from tech mobile app."""
    tech_id: str
    latitude: float
    longitude: float
    accuracy: float = 10.0
    heading: Optional[float] = None
    speed_kmh: Optional[float] = None


class TechStatusEvent(BaseModel):
    """Tech status change from mobile app (arrived, started, completed)."""
    tech_id: str
    job_id: Optional[str] = None
    status: str


# ─── HMAC validation dependency ───────────────────────────────────────────────

async def _webhook_auth(request: Request):
    """
    FastAPI dependency that validates the HMAC-SHA256 signature on every webhook.

    Expected header: X-Dispatch-Signature: sha256=<hex_digest>

    Behaviour:
    - No secret configured → warn and allow through (backward compat)
    - Secret configured, invalid/missing sig → 401 Unauthorized
    - REQUIRE_WEBHOOK_SECRET=true AND no secret → 500 (misconfiguration)
    """
    secret = app_config.fsm.webhook_secret

    if not secret:
        if app_config.fsm.require_webhook_secret:
            # Operator requested strict mode but forgot to set the secret — loud failure
            logger.error(
                "REQUIRE_WEBHOOK_SECRET=true but FSM_WEBHOOK_SECRET is not set. "
                "This is a misconfiguration. Set FSM_WEBHOOK_SECRET or disable "
                "REQUIRE_WEBHOOK_SECRET."
            )
            raise HTTPException(
                status_code=500,
                detail="Server misconfiguration: webhook secret required but not set.",
            )
        # Permissive fallback — warn but allow (supports zero-config dev mode)
        logger.warning(
            "FSM_WEBHOOK_SECRET not configured — webhook request accepted without "
            "HMAC validation. Set FSM_WEBHOOK_SECRET to secure this endpoint."
        )
        return

    # Read raw body (Starlette caches it so Pydantic can still parse it after)
    body = await request.body()
    expected = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    received = request.headers.get("X-Dispatch-Signature", "").replace("sha256=", "")

    if not received:
        logger.warning("Webhook received without X-Dispatch-Signature header")
        raise HTTPException(
            status_code=401,
            detail="Missing X-Dispatch-Signature header.",
        )

    if not hmac.compare_digest(expected, received):
        logger.warning("Webhook HMAC signature mismatch — request rejected")
        raise HTTPException(
            status_code=401,
            detail="Invalid webhook signature.",
        )


# ─── Routes ───────────────────────────────────────────────────────────────────

@router.post(
    "/fsm/job-created",
    summary="FSM webhook: new job created",
    dependencies=[Depends(_webhook_auth)],
)
async def on_fsm_job_created(
    event: FSMJobCreatedEvent,
    engine: DispatchEngine = Depends(get_engine),
) -> Dict[str, Any]:
    """
    Receive a new job from your FSM and add it to the dispatch queue.
    Map this endpoint as the webhook URL in your FSM settings.
    """
    try:
        job_type = JobType(event.job_type)
    except ValueError:
        job_type = JobType.MAINTENANCE
        logger.warning(f"Unknown FSM job type '{event.job_type}', defaulting to maintenance")

    customer = CustomerInfo(
        customer_id=event.customer_id,
        name=event.customer_name,
        phone=event.customer_phone,
        email=event.customer_email,
        address=event.customer_address,
        latitude=event.customer_lat,
        longitude=event.customer_lon,
    )

    from ...models.job import EquipmentInfo
    equipment = None
    if event.equipment_make or event.equipment_model:
        equipment = EquipmentInfo(
            make=event.equipment_make,
            model=event.equipment_model,
            year_installed=event.equipment_year,
        )

    job = Job(
        job_type=job_type,
        priority=JobPriority(min(max(event.priority, 1), 5)),
        customer=customer,
        description=event.description,
        equipment=equipment,
        fsm_job_id=event.job_id,
    )

    internal_id = engine.add_job(job)
    logger.info(f"FSM webhook: new job {event.job_id} → internal {internal_id}")

    return {
        "received": True,
        "internal_job_id": internal_id,
        "fsm_job_id": event.job_id,
        "status": "queued_for_dispatch",
    }


@router.post(
    "/fsm/job-status",
    summary="FSM webhook: job status changed",
    dependencies=[Depends(_webhook_auth)],
)
async def on_fsm_status_change(
    event: FSMStatusChangeEvent,
    engine: DispatchEngine = Depends(get_engine),
) -> Dict[str, Any]:
    """Handle status change events from the FSM."""
    job = next(
        (j for j in engine._jobs.values() if j.fsm_job_id == event.job_id),
        None,
    )
    if not job:
        logger.warning(f"Status webhook for unknown FSM job {event.job_id}")
        return {"received": True, "warning": "job_not_found"}

    if event.event == "job.completed" and event.actual_duration_minutes:
        engine.mark_job_completed(job.job_id, event.actual_duration_minutes)
        return {"received": True, "action": "job_completed"}

    if event.new_status == "in_progress":
        job.status = JobStatus.IN_PROGRESS
        job.actual_start = __import__("datetime").datetime.utcnow()
        return {"received": True, "action": "status_updated"}

    return {"received": True, "action": "no_action"}


@router.post(
    "/tech/location",
    summary="Mobile app: technician GPS update",
    dependencies=[Depends(_webhook_auth)],
)
async def on_tech_location(
    event: TechLocationEvent,
    engine: DispatchEngine = Depends(get_engine),
) -> Dict[str, Any]:
    """High-frequency GPS update from technician mobile app."""
    if event.tech_id not in engine._technicians:
        raise HTTPException(404, f"Technician {event.tech_id} not found")
    engine.update_technician_location(event.tech_id, event.latitude, event.longitude)
    return {"received": True}


@router.post(
    "/tech/status",
    summary="Mobile app: technician status update",
    dependencies=[Depends(_webhook_auth)],
)
async def on_tech_status(
    event: TechStatusEvent,
    engine: DispatchEngine = Depends(get_engine),
) -> Dict[str, Any]:
    """Status transitions from the tech mobile app."""
    if event.tech_id not in engine._technicians:
        raise HTTPException(404, f"Technician {event.tech_id} not found")

    try:
        status = TechnicianStatus(event.status)
    except ValueError:
        raise HTTPException(400, f"Invalid status: {event.status}")

    engine.update_technician_status(event.tech_id, status)

    # If tech arrived, send arrival notification
    if status == TechnicianStatus.ON_JOB and event.job_id and engine.notification_service:
        job = engine._jobs.get(event.job_id)
        tech = engine._technicians.get(event.tech_id)
        if job and tech:
            try:
                await engine.notification_service.send_arrival(job, tech)
            except Exception as e:
                logger.error(f"Arrival notification failed: {e}")

    return {"received": True, "tech_id": event.tech_id, "status": event.status}
