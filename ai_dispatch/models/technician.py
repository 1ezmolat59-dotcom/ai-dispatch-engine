"""
Technician data models for the AI Dispatch System.
Tracks skills, certifications, location, and workload.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime, time
from enum import Enum
from typing import Optional, List, Dict, Any
import uuid


class TechnicianStatus(str, Enum):
    AVAILABLE = "available"         # Free and ready for assignment
    EN_ROUTE = "en_route"           # Traveling to job
    ON_JOB = "on_job"               # Actively working a job
    ON_BREAK = "on_break"           # On scheduled break
    OVERTIME = "overtime"           # In overtime hours
    OFF_DUTY = "off_duty"           # Not working today
    UNAVAILABLE = "unavailable"     # Sick, PTO, etc.


class SkillLevel(int, Enum):
    APPRENTICE = 1      # Learning under supervision
    JOURNEYMAN = 2      # Can work independently on standard jobs
    SENIOR = 3          # Handles complex jobs, mentors others
    MASTER = 4          # Expert level, all job types


@dataclass
class Skill:
    skill_id: str
    name: str
    category: str           # hvac | plumbing | electrical | general
    level: SkillLevel
    certified: bool = False
    certification_expiry: Optional[datetime] = None
    notes: str = ""

    @property
    def is_certification_valid(self) -> bool:
        if not self.certified:
            return True  # No cert required
        if self.certification_expiry is None:
            return True  # No expiry
        return datetime.utcnow() < self.certification_expiry

    def to_dict(self) -> Dict[str, Any]:
        return {
            "skill_id": self.skill_id,
            "name": self.name,
            "category": self.category,
            "level": self.level.value,
            "certified": self.certified,
        }


@dataclass
class WorkSchedule:
    """Defines a technician's weekly work schedule."""
    monday_start: Optional[time] = time(8, 0)
    monday_end: Optional[time] = time(17, 0)
    tuesday_start: Optional[time] = time(8, 0)
    tuesday_end: Optional[time] = time(17, 0)
    wednesday_start: Optional[time] = time(8, 0)
    wednesday_end: Optional[time] = time(17, 0)
    thursday_start: Optional[time] = time(8, 0)
    thursday_end: Optional[time] = time(17, 0)
    friday_start: Optional[time] = time(8, 0)
    friday_end: Optional[time] = time(17, 0)
    saturday_start: Optional[time] = None
    saturday_end: Optional[time] = None
    sunday_start: Optional[time] = None
    sunday_end: Optional[time] = None
    timezone: str = "America/New_York"

    def is_working(self, dt: datetime) -> bool:
        """Check if a technician is scheduled to work at a given datetime."""
        day_map = {
            0: (self.monday_start, self.monday_end),
            1: (self.tuesday_start, self.tuesday_end),
            2: (self.wednesday_start, self.wednesday_end),
            3: (self.thursday_start, self.thursday_end),
            4: (self.friday_start, self.friday_end),
            5: (self.saturday_start, self.saturday_end),
            6: (self.sunday_start, self.sunday_end),
        }
        start, end = day_map.get(dt.weekday(), (None, None))
        if start is None or end is None:
            return False
        current_time = dt.time()
        return start <= current_time <= end


@dataclass
class TechnicianLocation:
    latitude: float
    longitude: float
    updated_at: datetime = field(default_factory=datetime.utcnow)
    accuracy_meters: float = 10.0
    heading: Optional[float] = None    # Degrees 0-360
    speed_kmh: Optional[float] = None  # Current speed

    def is_stale(self, max_age_seconds: int = 120) -> bool:
        """Returns True if location data is older than max_age_seconds."""
        age = (datetime.utcnow() - self.updated_at).total_seconds()
        return age > max_age_seconds


@dataclass
class Technician:
    name: str
    phone: str
    email: str
    skills: List[Skill]

    # Auto-generated
    tech_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    status: TechnicianStatus = TechnicianStatus.AVAILABLE
    created_at: datetime = field(default_factory=datetime.utcnow)

    # Location
    location: Optional[TechnicianLocation] = None
    home_base_lat: float = 0.0
    home_base_lon: float = 0.0

    # Current workload
    current_job_id: Optional[str] = None
    job_queue: List[str] = field(default_factory=list)   # Ordered list of job IDs
    current_job_eta: Optional[datetime] = None

    # Schedule & capacity
    schedule: WorkSchedule = field(default_factory=WorkSchedule)
    max_jobs_per_day: int = 8
    jobs_completed_today: int = 0
    shift_start: Optional[datetime] = None
    shift_end: Optional[datetime] = None

    # Performance metrics
    avg_job_duration_minutes: float = 0.0
    avg_drive_time_minutes: float = 0.0
    completion_rate: float = 1.0         # 0.0-1.0
    customer_rating: float = 4.5         # 1.0-5.0
    on_time_rate: float = 0.9            # 0.0-1.0
    jobs_completed_lifetime: int = 0
    years_experience: float = 0.0

    # Vehicle
    vehicle_type: str = "van"
    vehicle_id: Optional[str] = None
    truck_stock: List[str] = field(default_factory=list)  # Parts on truck

    # External references
    fsm_tech_id: Optional[str] = None
    employee_id: Optional[str] = None

    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def skill_names(self) -> List[str]:
        """Return list of skill name strings this tech has."""
        return [s.name for s in self.skills]

    @property
    def skill_categories(self) -> List[str]:
        """Return unique categories (hvac, plumbing, electrical)."""
        return list({s.category for s in self.skills})

    def has_skill(self, skill_name: str) -> bool:
        """Check if technician has a specific skill."""
        return any(s.name == skill_name and s.is_certification_valid for s in self.skills)

    def has_all_skills(self, required_skills: List[str]) -> bool:
        """Check if tech has ALL required skills for a job."""
        if not required_skills:
            return True
        return all(self.has_skill(skill) for skill in required_skills)

    def skill_match_score(self, required_skills: List[str]) -> float:
        """
        Returns 0.0-1.0 representing how well this tech matches job requirements.
        Weighs both coverage and skill level.
        """
        if not required_skills:
            return 1.0
        matched = 0
        level_bonus = 0.0
        for req_skill in required_skills:
            for skill in self.skills:
                if skill.name == req_skill and skill.is_certification_valid:
                    matched += 1
                    level_bonus += (skill.level.value - 1) * 0.05  # Up to 0.15 bonus per skill
                    break
        base_score = matched / len(required_skills)
        return min(1.0, base_score + level_bonus)

    @property
    def is_available_for_assignment(self) -> bool:
        return self.status in (
            TechnicianStatus.AVAILABLE,
            TechnicianStatus.EN_ROUTE,  # Can be pre-assigned next job
        ) and len(self.job_queue) < self.max_jobs_per_day

    @property
    def workload_ratio(self) -> float:
        """0.0 = no work, 1.0 = at capacity."""
        return len(self.job_queue) / max(self.max_jobs_per_day, 1)

    @property
    def current_location_or_home(self) -> tuple[float, float]:
        """Returns current GPS or home base fallback."""
        if self.location and not self.location.is_stale():
            return (self.location.latitude, self.location.longitude)
        return (self.home_base_lat, self.home_base_lon)

    def to_dict(self) -> Dict[str, Any]:
        lat, lon = self.current_location_or_home
        return {
            "tech_id": self.tech_id,
            "name": self.name,
            "phone": self.phone,
            "email": self.email,
            "status": self.status.value,
            "skills": [s.to_dict() for s in self.skills],
            "skill_categories": self.skill_categories,
            "current_job_id": self.current_job_id,
            "job_queue_length": len(self.job_queue),
            "location": {"latitude": lat, "longitude": lon},
            "jobs_completed_today": self.jobs_completed_today,
            "customer_rating": self.customer_rating,
            "on_time_rate": self.on_time_rate,
            "years_experience": self.years_experience,
            "fsm_tech_id": self.fsm_tech_id,
        }
