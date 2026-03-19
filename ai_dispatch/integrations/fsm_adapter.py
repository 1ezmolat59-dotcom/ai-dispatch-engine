"""
FSM Adapter — Generic REST API adapter for Field Service Management tools.

Implements a standard interface so the dispatch engine stays FSM-agnostic.
Ships with:
  - GenericFSMAdapter  — configurable for any REST FSM (Jobber, FieldEdge, etc.)
  - ServiceTitanAdapter — pre-configured for ServiceTitan's API v2

Adding a new FSM:
  1. Subclass FSMAdapter
  2. Override the abstract methods
  3. Pass your adapter to DispatchEngine(fsm_adapter=MyAdapter())
"""

from __future__ import annotations
import logging
import os
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any, Dict, List, Optional

import httpx

logger = logging.getLogger(__name__)


class FSMAdapter(ABC):
    """Abstract base class all FSM adapters must implement."""

    @abstractmethod
    async def get_pending_jobs(self) -> List[Dict[str, Any]]:
        """Pull unassigned/pending jobs from the FSM."""
        ...

    @abstractmethod
    async def assign_job(self, job_id: str, tech_id: str, eta: Optional[datetime]) -> bool:
        """Push a job assignment back to the FSM."""
        ...

    @abstractmethod
    async def update_job_eta(self, job_id: str, eta: datetime) -> bool:
        """Update the ETA on an existing job."""
        ...

    @abstractmethod
    async def get_technicians(self) -> List[Dict[str, Any]]:
        """Pull the current technician list from the FSM."""
        ...

    @abstractmethod
    async def complete_job(self, job_id: str, notes: str, duration_minutes: int) -> bool:
        """Mark a job as completed."""
        ...


class GenericFSMAdapter(FSMAdapter):
    """
    Configurable REST adapter for any FSM that speaks JSON over HTTP.

    Configure via environment variables or constructor kwargs:
      FSM_BASE_URL       — e.g. https://api.yourfsm.com/v1
      FSM_API_KEY        — API key or token
      FSM_AUTH_HEADER    — Header name (default: Authorization)
      FSM_AUTH_PREFIX    — Prefix (default: Bearer)

    Override endpoint paths in subclasses or via the endpoints dict.
    """

    DEFAULT_ENDPOINTS = {
        "jobs_pending": "/jobs?status=pending",
        "job_assign": "/jobs/{job_id}/assign",
        "job_eta": "/jobs/{job_id}/eta",
        "job_complete": "/jobs/{job_id}/complete",
        "technicians": "/technicians",
        "tech_location": "/technicians/{tech_id}/location",
    }

    def __init__(
        self,
        base_url: Optional[str] = None,
        api_key: Optional[str] = None,
        auth_header: str = "Authorization",
        auth_prefix: str = "Bearer",
        endpoints: Optional[Dict[str, str]] = None,
        timeout_seconds: int = 10,
        webhook_secret: Optional[str] = None,
    ):
        self.base_url = (base_url or os.getenv("FSM_BASE_URL", "")).rstrip("/")
        self.api_key = api_key or os.getenv("FSM_API_KEY", "")
        self.auth_header = auth_header
        self.auth_prefix = auth_prefix
        self.endpoints = {**self.DEFAULT_ENDPOINTS, **(endpoints or {})}
        self.timeout = timeout_seconds
        self.webhook_secret = webhook_secret or os.getenv("FSM_WEBHOOK_SECRET", "")

        self._client = httpx.AsyncClient(
            base_url=self.base_url,
            headers={
                self.auth_header: f"{self.auth_prefix} {self.api_key}",
                "Content-Type": "application/json",
                "User-Agent": "AIDispatch/1.0",
            },
            timeout=self.timeout,
        )

    async def _get(self, path: str, params: Optional[Dict] = None) -> Optional[Dict]:
        try:
            r = await self._client.get(path, params=params)
            r.raise_for_status()
            return r.json()
        except httpx.HTTPStatusError as e:
            logger.error(f"FSM GET {path} failed: {e.response.status_code} {e.response.text[:200]}")
        except httpx.RequestError as e:
            logger.error(f"FSM GET {path} connection error: {e}")
        return None

    async def _post(self, path: str, payload: Dict) -> Optional[Dict]:
        try:
            r = await self._client.post(path, json=payload)
            r.raise_for_status()
            return r.json()
        except httpx.HTTPStatusError as e:
            logger.error(f"FSM POST {path} failed: {e.response.status_code} {e.response.text[:200]}")
        except httpx.RequestError as e:
            logger.error(f"FSM POST {path} connection error: {e}")
        return None

    async def _patch(self, path: str, payload: Dict) -> Optional[Dict]:
        try:
            r = await self._client.patch(path, json=payload)
            r.raise_for_status()
            return r.json()
        except httpx.HTTPStatusError as e:
            logger.error(f"FSM PATCH {path} failed: {e.response.status_code}")
        except httpx.RequestError as e:
            logger.error(f"FSM PATCH {path} error: {e}")
        return None

    # ─── FSMAdapter interface ─────────────────────────────────────────────────

    async def get_pending_jobs(self) -> List[Dict[str, Any]]:
        path = self.endpoints["jobs_pending"]
        data = await self._get(path)
        if data is None:
            return []
        # Normalize to list
        return data if isinstance(data, list) else data.get("jobs", data.get("data", []))

    async def assign_job(self, job_id: str, tech_id: str, eta: Optional[datetime]) -> bool:
        path = self.endpoints["job_assign"].format(job_id=job_id)
        payload: Dict[str, Any] = {"tech_id": tech_id, "status": "assigned"}
        if eta:
            payload["eta"] = eta.isoformat()
        result = await self._post(path, payload)
        return result is not None

    async def update_job_eta(self, job_id: str, eta: datetime) -> bool:
        path = self.endpoints["job_eta"].format(job_id=job_id)
        result = await self._patch(path, {"eta": eta.isoformat()})
        return result is not None

    async def get_technicians(self) -> List[Dict[str, Any]]:
        path = self.endpoints["technicians"]
        data = await self._get(path)
        if data is None:
            return []
        return data if isinstance(data, list) else data.get("technicians", data.get("data", []))

    async def complete_job(self, job_id: str, notes: str, duration_minutes: int) -> bool:
        path = self.endpoints["job_complete"].format(job_id=job_id)
        result = await self._post(path, {
            "status": "completed",
            "notes": notes,
            "duration_minutes": duration_minutes,
            "completed_at": datetime.utcnow().isoformat(),
        })
        return result is not None

    async def push_tech_location(self, tech_id: str, lat: float, lon: float) -> bool:
        path = self.endpoints["tech_location"].format(tech_id=tech_id)
        result = await self._patch(path, {
            "latitude": lat, "longitude": lon,
            "updated_at": datetime.utcnow().isoformat(),
        })
        return result is not None


class ServiceTitanAdapter(GenericFSMAdapter):
    """
    ServiceTitan API v2 adapter.
    Docs: https://developer.servicetitan.io/apis/

    Required env vars:
      ST_CLIENT_ID     — OAuth2 client ID
      ST_CLIENT_SECRET — OAuth2 client secret
      ST_APP_KEY       — Application key
      ST_TENANT_ID     — Your ServiceTitan tenant ID
    """

    ST_AUTH_URL = "https://auth.servicetitan.io/connect/token"
    ST_BASE_URL = "https://api.servicetitan.io"

    # ServiceTitan uses different status names
    ST_ENDPOINTS = {
        "jobs_pending": "/jpm/v2/tenant/{tenant_id}/jobs?jobStatus=Pending&pageSize=50",
        "job_assign": "/jpm/v2/tenant/{tenant_id}/jobs/{job_id}",
        "job_eta": "/jpm/v2/tenant/{tenant_id}/appointments/{job_id}",
        "job_complete": "/jpm/v2/tenant/{tenant_id}/jobs/{job_id}",
        "technicians": "/settings/v2/tenant/{tenant_id}/technicians?active=true",
        "tech_location": "/dispatch/v2/tenant/{tenant_id}/technicians/{tech_id}/location",
    }

    def __init__(self):
        self.client_id = os.getenv("ST_CLIENT_ID", "")
        self.client_secret = os.getenv("ST_CLIENT_SECRET", "")
        self.app_key = os.getenv("ST_APP_KEY", "")
        self.tenant_id = os.getenv("ST_TENANT_ID", "")
        self._access_token: Optional[str] = None
        self._token_expiry: Optional[datetime] = None

        # Format endpoints with tenant_id
        endpoints = {
            k: v.format(tenant_id=self.tenant_id)
            for k, v in self.ST_ENDPOINTS.items()
        }
        super().__init__(
            base_url=self.ST_BASE_URL,
            api_key="",  # Uses OAuth token, not static key
            endpoints=endpoints,
        )

    async def _ensure_token(self):
        """Fetch/refresh OAuth2 access token."""
        if (self._access_token and self._token_expiry
                and datetime.utcnow() < self._token_expiry):
            return

        try:
            async with httpx.AsyncClient() as client:
                r = await client.post(
                    self.ST_AUTH_URL,
                    data={
                        "grant_type": "client_credentials",
                        "client_id": self.client_id,
                        "client_secret": self.client_secret,
                    },
                    headers={"ST-App-Key": self.app_key},
                    timeout=10.0,
                )
                r.raise_for_status()
                token_data = r.json()
                self._access_token = token_data["access_token"]
                expires_in = token_data.get("expires_in", 3600)
                from datetime import timedelta
                self._token_expiry = datetime.utcnow() + timedelta(seconds=expires_in - 60)
                # Update client headers
                self._client.headers["Authorization"] = f"Bearer {self._access_token}"
                logger.info("ServiceTitan OAuth token refreshed")
        except Exception as e:
            logger.error(f"ServiceTitan auth failed: {e}")

    async def get_pending_jobs(self) -> List[Dict[str, Any]]:
        await self._ensure_token()
        return await super().get_pending_jobs()

    async def assign_job(self, job_id: str, tech_id: str, eta: Optional[datetime]) -> bool:
        await self._ensure_token()
        # ServiceTitan uses PATCH to update job dispatch status
        path = self.endpoints["job_assign"].format(job_id=job_id)
        payload: Dict[str, Any] = {
            "technicianId": int(tech_id) if tech_id.isdigit() else tech_id,
            "jobStatus": "Dispatched",
        }
        if eta:
            payload["appointmentStartTime"] = eta.isoformat()
        result = await self._patch(path, payload)
        return result is not None


class JobberAdapter(GenericFSMAdapter):
    """
    Jobber API adapter.
    Docs: https://developer.getjobber.com/

    Uses Jobber's GraphQL API for reads and REST for mutations.
    """

    JOBBER_BASE_URL = "https://api.getjobber.com/api"
    JOBBER_ENDPOINTS = {
        "jobs_pending": "/jobs?status=unscheduled",
        "job_assign": "/jobs/{job_id}/assign",
        "job_eta": "/jobs/{job_id}",
        "job_complete": "/jobs/{job_id}/complete",
        "technicians": "/staff",
        "tech_location": "/staff/{tech_id}",
    }

    def __init__(self):
        super().__init__(
            base_url=self.JOBBER_BASE_URL,
            api_key=os.getenv("JOBBER_API_KEY", ""),
            endpoints=self.JOBBER_ENDPOINTS,
        )
