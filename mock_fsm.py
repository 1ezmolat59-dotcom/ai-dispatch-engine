"""
Mock FSM Server — simulates a generic field service management REST API.
Runs on port 8001.  The dispatch engine's GenericFSMAdapter talks to this.

Start with:  python mock_fsm.py
"""

from __future__ import annotations
import logging
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException, Header, Request
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

logging.basicConfig(level=logging.INFO, format="%(asctime)s | FSM | %(message)s")
logger = logging.getLogger("mock_fsm")

app = FastAPI(title="Mock FSM Server", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── In-memory stores ──────────────────────────────────────────────────────────

_jobs: Dict[str, Dict] = {}
_technicians: Dict[str, Dict] = {}
_assignments: List[Dict] = []
_locations: Dict[str, Dict] = {}

# ── Auth check (accepts mock-fsm-key or no key for dev convenience) ───────────

def _auth(authorization: Optional[str] = Header(default=None)):
    if authorization and "mock-fsm-key" not in authorization:
        raise HTTPException(401, "Invalid FSM API key")


# ── Health ────────────────────────────────────────────────────────────────────

@app.get("/")
async def root():
    return {"service": "Mock FSM", "status": "running", "jobs": len(_jobs), "techs": len(_technicians)}


@app.get("/health")
async def health():
    return {"status": "healthy"}


# ── Jobs ─────────────────────────────────────────────────────────────────────

@app.get("/jobs")
async def list_jobs(status: Optional[str] = None):
    jobs = list(_jobs.values())
    if status:
        jobs = [j for j in jobs if j["status"] == status]
    return jobs


@app.post("/jobs")
async def create_job(payload: Dict[str, Any]):
    job_id = payload.get("job_id") or str(uuid.uuid4())
    job = {
        "id": job_id,
        "status": "pending",
        "created_at": datetime.utcnow().isoformat(),
        **payload,
    }
    _jobs[job_id] = job
    logger.info(f"Job created: {job_id} | type={payload.get('job_type')} | priority={payload.get('priority')}")
    return job


@app.get("/jobs/{job_id}")
async def get_job(job_id: str):
    job = _jobs.get(job_id)
    if not job:
        raise HTTPException(404, f"Job {job_id} not found")
    return job


@app.post("/jobs/{job_id}/assign")
async def assign_job(job_id: str, payload: Dict[str, Any]):
    job = _jobs.get(job_id)
    if not job:
        # Auto-create if the dispatch engine sends an FSM job ID we don't have
        job = {"id": job_id, "status": "pending"}
        _jobs[job_id] = job

    job["status"] = "assigned"
    job["tech_id"] = payload.get("tech_id")
    job["eta"] = payload.get("eta")
    job["assigned_at"] = datetime.utcnow().isoformat()

    assignment = {
        "job_id": job_id,
        "tech_id": payload.get("tech_id"),
        "eta": payload.get("eta"),
        "assigned_at": datetime.utcnow().isoformat(),
    }
    _assignments.append(assignment)
    logger.info(f"Job {job_id} assigned → tech {payload.get('tech_id')} | ETA {payload.get('eta')}")
    return {"success": True, "job": job}


@app.patch("/jobs/{job_id}/eta")
async def update_eta(job_id: str, payload: Dict[str, Any]):
    job = _jobs.get(job_id)
    if not job:
        raise HTTPException(404, f"Job {job_id} not found")
    job["eta"] = payload.get("eta")
    job["eta_updated_at"] = datetime.utcnow().isoformat()
    logger.info(f"ETA updated for job {job_id}: {payload.get('eta')}")
    return {"success": True}


@app.post("/jobs/{job_id}/complete")
async def complete_job(job_id: str, payload: Dict[str, Any]):
    job = _jobs.get(job_id)
    if not job:
        raise HTTPException(404, f"Job {job_id} not found")
    job["status"] = "completed"
    job["completed_at"] = datetime.utcnow().isoformat()
    job["duration_minutes"] = payload.get("duration_minutes")
    job["notes"] = payload.get("notes", "")
    logger.info(f"Job {job_id} completed | duration={payload.get('duration_minutes')} min")
    return {"success": True}


# ── Technicians ──────────────────────────────────────────────────────────────

@app.get("/technicians")
async def list_technicians():
    return list(_technicians.values())


@app.post("/technicians")
async def create_technician(payload: Dict[str, Any]):
    tech_id = payload.get("tech_id") or str(uuid.uuid4())
    tech = {"id": tech_id, **payload}
    _technicians[tech_id] = tech
    logger.info(f"Technician registered: {tech_id} | {payload.get('name')}")
    return tech


@app.patch("/technicians/{tech_id}/location")
async def update_location(tech_id: str, payload: Dict[str, Any]):
    _locations[tech_id] = {
        "tech_id": tech_id,
        "latitude": payload.get("latitude"),
        "longitude": payload.get("longitude"),
        "updated_at": datetime.utcnow().isoformat(),
    }
    return {"success": True}


# ── Assignments log ───────────────────────────────────────────────────────────

@app.get("/assignments")
async def list_assignments():
    return _assignments


# ── Webhook simulation — dispatches a test job to the AI engine ───────────────

@app.post("/simulate/new-job")
async def simulate_new_job(payload: Optional[Dict[str, Any]] = None):
    """
    POST to this endpoint to push a simulated new-job webhook to the dispatch engine.
    The dispatch engine must be running on port 8000.
    """
    import httpx
    payload = payload or {}
    job_id = str(uuid.uuid4())
    event = {
        "event": "job.created",
        "job_id": job_id,
        "job_type": payload.get("job_type", "hvac_repair"),
        "priority": payload.get("priority", 4),
        "customer_id": str(uuid.uuid4()),
        "customer_name": payload.get("customer_name", "Test Customer"),
        "customer_phone": "+15555550100",
        "customer_email": "test@demo.com",
        "customer_address": "350 W 57th St, New York, NY",
        "customer_lat": 40.7614 + (0.01 * (hash(job_id) % 10 - 5)),
        "customer_lon": -73.9776 + (0.01 * (hash(job_id[:8]) % 10 - 5)),
        "description": payload.get("description", "Simulated job from mock FSM"),
    }

    import hmac, hashlib, json
    body = json.dumps(event).encode()
    secret = "mock-webhook-secret"
    sig = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()

    try:
        async with httpx.AsyncClient() as client:
            r = await client.post(
                "http://localhost:8000/api/v1/webhooks/fsm/job-created",
                content=body,
                headers={
                    "Content-Type": "application/json",
                    "X-API-Key": "dev-secret-key",
                    "X-Dispatch-Signature": f"sha256={sig}",
                },
                timeout=5.0,
            )
            return {"simulated": True, "job_id": job_id, "dispatch_response": r.json()}
    except Exception as e:
        return {"simulated": True, "job_id": job_id, "error": str(e),
                "note": "Dispatch engine may not be running yet"}


if __name__ == "__main__":
    logger.info("Mock FSM Server starting on http://localhost:8001")
    logger.info("Docs: http://localhost:8001/docs")
    uvicorn.run(app, host="0.0.0.0", port=8001, log_level="info")
