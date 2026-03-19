"""
Job data models for the AI Dispatch System.
Covers HVAC, Plumbing, and Electrical job types.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional, List, Dict, Any
import uuid


class JobStatus(str, Enum):
    PENDING = "pending"           # Waiting for assignment
    ASSIGNED = "assigned"         # Technician assigned, not yet started
    EN_ROUTE = "en_route"         # Tech is traveling to job
    IN_PROGRESS = "in_progress"   # Job actively being worked
    ON_HOLD = "on_hold"           # Waiting on parts / customer
    COMPLETED = "completed"       # Job finished
    CANCELLED = "cancelled"       # Job cancelled


class JobPriority(int, Enum):
    EMERGENCY = 1    # No heat/AC in extreme weather, gas leak, flooding
    URGENT = 2       # System down, customer without service
    HIGH = 3         # Significant inconvenience, scheduled same-day
    NORMAL = 4       # Standard scheduled work
    LOW = 5          # Maintenance, non-urgent installs


class JobType(str, Enum):
    # HVAC
    HVAC_REPAIR = "hvac_repair"
    HVAC_INSTALL = "hvac_install"
    HVAC_MAINTENANCE = "hvac_maintenance"
    HVAC_EMERGENCY = "hvac_emergency"
    HVAC_DIAGNOSTIC = "hvac_diagnostic"
    # Plumbing
    PLUMBING_REPAIR = "plumbing_repair"
    PLUMBING_INSTALL = "plumbing_install"
    PLUMBING_EMERGENCY = "plumbing_emergency"
    DRAIN_CLEANING = "drain_cleaning"
    WATER_HEATER = "water_heater"
    # Electrical
    ELECTRICAL_REPAIR = "electrical_repair"
    ELECTRICAL_INSTALL = "electrical_install"
    ELECTRICAL_INSPECTION = "electrical_inspection"
    PANEL_UPGRADE = "panel_upgrade"
    EV_CHARGER = "ev_charger"
    # General
    MAINTENANCE = "maintenance"
    INSPECTION = "inspection"
    ESTIMATE = "estimate"


# Skills required per job type
JOB_TYPE_REQUIRED_SKILLS: Dict[JobType, List[str]] = {
    JobType.HVAC_REPAIR: ["hvac", "refrigerant_handling"],
    JobType.HVAC_INSTALL: ["hvac", "hvac_installation", "refrigerant_handling"],
    JobType.HVAC_MAINTENANCE: ["hvac"],
    JobType.HVAC_EMERGENCY: ["hvac", "refrigerant_handling"],
    JobType.HVAC_DIAGNOSTIC: ["hvac", "hvac_diagnostic"],
    JobType.PLUMBING_REPAIR: ["plumbing"],
    JobType.PLUMBING_INSTALL: ["plumbing", "plumbing_installation"],
    JobType.PLUMBING_EMERGENCY: ["plumbing"],
    JobType.DRAIN_CLEANING: ["plumbing", "drain_cleaning"],
    JobType.WATER_HEATER: ["plumbing", "water_heater"],
    JobType.ELECTRICAL_REPAIR: ["electrical", "electrical_repair"],
    JobType.ELECTRICAL_INSTALL: ["electrical", "electrical_installation"],
    JobType.ELECTRICAL_INSPECTION: ["electrical", "electrical_inspection"],
    JobType.PANEL_UPGRADE: ["electrical", "panel_upgrade"],
    JobType.EV_CHARGER: ["electrical", "ev_charger"],
    JobType.MAINTENANCE: ["general_maintenance"],
    JobType.INSPECTION: ["inspection"],
    JobType.ESTIMATE: [],
}

# Baseline estimated durations in minutes (used before ML kicks in)
JOB_TYPE_BASE_DURATION: Dict[JobType, int] = {
    JobType.HVAC_REPAIR: 90,
    JobType.HVAC_INSTALL: 240,
    JobType.HVAC_MAINTENANCE: 60,
    JobType.HVAC_EMERGENCY: 120,
    JobType.HVAC_DIAGNOSTIC: 60,
    JobType.PLUMBING_REPAIR: 75,
    JobType.PLUMBING_INSTALL: 180,
    JobType.PLUMBING_EMERGENCY: 90,
    JobType.DRAIN_CLEANING: 60,
    JobType.WATER_HEATER: 150,
    JobType.ELECTRICAL_REPAIR: 75,
    JobType.ELECTRICAL_INSTALL: 180,
    JobType.ELECTRICAL_INSPECTION: 90,
    JobType.PANEL_UPGRADE: 300,
    JobType.EV_CHARGER: 180,
    JobType.MAINTENANCE: 60,
    JobType.INSPECTION: 45,
    JobType.ESTIMATE: 30,
}


@dataclass
class CustomerInfo:
    customer_id: str
    name: str
    phone: str
    email: str
    address: str
    latitude: float
    longitude: float
    # Notification preferences
    sms_opt_in: bool = True
    email_opt_in: bool = True
    # History context
    lifetime_jobs: int = 0
    avg_satisfaction_score: float = 5.0
    notes: str = ""


@dataclass
class EquipmentInfo:
    equipment_id: Optional[str] = None
    make: Optional[str] = None
    model: Optional[str] = None
    year_installed: Optional[int] = None
    last_service_date: Optional[datetime] = None
    serial_number: Optional[str] = None
    warranty_expiry: Optional[datetime] = None
    known_issues: List[str] = field(default_factory=list)

    @property
    def age_years(self) -> Optional[float]:
        if self.year_installed:
            return datetime.utcnow().year - self.year_installed
        return None


@dataclass
class Job:
    job_type: JobType
    priority: JobPriority
    customer: CustomerInfo

    # Auto-generated
    job_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    status: JobStatus = JobStatus.PENDING
    created_at: datetime = field(default_factory=datetime.utcnow)
    scheduled_start: Optional[datetime] = None
    scheduled_end: Optional[datetime] = None
    actual_start: Optional[datetime] = None
    actual_end: Optional[datetime] = None

    # Assignment
    assigned_tech_id: Optional[str] = None
    assignment_time: Optional[datetime] = None

    # Predictions
    predicted_duration_minutes: Optional[int] = None
    predicted_eta: Optional[datetime] = None
    eta_sent_at: Optional[datetime] = None
    eta_last_updated: Optional[datetime] = None

    # Job details
    description: str = ""
    equipment: Optional[EquipmentInfo] = None
    parts_needed: List[str] = field(default_factory=list)
    special_instructions: str = ""
    attachments: List[str] = field(default_factory=list)

    # External references
    fsm_job_id: Optional[str] = None
    invoice_number: Optional[str] = None

    # Completion
    completion_notes: str = ""
    tech_rating: Optional[int] = None
    customer_satisfaction: Optional[int] = None
    actual_duration_minutes: Optional[int] = None

    # Dispatch scoring (set by optimizer)
    dispatch_score: float = 0.0
    urgency_score: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def required_skills(self) -> List[str]:
        return JOB_TYPE_REQUIRED_SKILLS.get(self.job_type, [])

    @property
    def base_duration_minutes(self) -> int:
        return JOB_TYPE_BASE_DURATION.get(self.job_type, 60)

    @property
    def is_emergency(self) -> bool:
        return self.priority == JobPriority.EMERGENCY

    @property
    def wait_time_minutes(self) -> float:
        if self.created_at:
            delta = datetime.utcnow() - self.created_at
            return delta.total_seconds() / 60
        return 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "job_id": self.job_id,
            "job_type": self.job_type.value,
            "priority": self.priority.value,
            "status": self.status.value,
            "customer": {
                "customer_id": self.customer.customer_id,
                "name": self.customer.name,
                "phone": self.customer.phone,
                "email": self.customer.email,
                "address": self.customer.address,
                "latitude": self.customer.latitude,
                "longitude": self.customer.longitude,
            },
            "assigned_tech_id": self.assigned_tech_id,
            "predicted_duration_minutes": self.predicted_duration_minutes,
            "predicted_eta": self.predicted_eta.isoformat() if self.predicted_eta else None,
            "scheduled_start": self.scheduled_start.isoformat() if self.scheduled_start else None,
            "created_at": self.created_at.isoformat(),
            "description": self.description,
            "dispatch_score": self.dispatch_score,
            "fsm_job_id": self.fsm_job_id,
        }
