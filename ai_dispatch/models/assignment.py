"""
Assignment models — the result of the AI dispatch optimizer.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, List, Dict, Any


@dataclass
class AssignmentScore:
    """Breakdown of how each factor contributed to the assignment decision."""
    total_score: float
    distance_score: float           # Proximity to job site
    skill_match_score: float        # Skills coverage quality
    workload_score: float           # How busy the tech is (less = better)
    performance_score: float        # Historical ratings and completion rate
    availability_score: float       # How quickly tech can start
    priority_bonus: float           # Extra weight for urgent/emergency jobs
    distance_km: float
    travel_time_minutes: float


@dataclass
class AssignmentResult:
    """
    The full output of one dispatch optimization decision.
    Includes the chosen technician, predicted duration, ETA, and scoring breakdown.
    """
    job_id: str
    tech_id: str
    tech_name: str
    assigned_at: datetime = field(default_factory=datetime.utcnow)

    # Timing predictions
    travel_time_minutes: float = 0.0
    predicted_job_duration_minutes: int = 60
    predicted_arrival: Optional[datetime] = None
    predicted_completion: Optional[datetime] = None

    # Routing
    distance_km: float = 0.0
    route_polyline: Optional[str] = None    # Encoded polyline for map display
    maps_deep_link_google: Optional[str] = None
    maps_deep_link_apple: Optional[str] = None

    # Scoring breakdown
    scores: Optional[AssignmentScore] = None

    # Alternatives considered (top 3 runners-up)
    alternative_techs: List[Dict[str, Any]] = field(default_factory=list)

    # Notification
    customer_eta_sent: bool = False
    eta_message: str = ""

    # Confidence
    duration_confidence: float = 0.7    # 0.0-1.0 (ML model confidence)
    assignment_confidence: float = 0.9  # 0.0-1.0 (optimizer confidence)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "job_id": self.job_id,
            "tech_id": self.tech_id,
            "tech_name": self.tech_name,
            "assigned_at": self.assigned_at.isoformat(),
            "travel_time_minutes": round(self.travel_time_minutes, 1),
            "predicted_job_duration_minutes": self.predicted_job_duration_minutes,
            "predicted_arrival": self.predicted_arrival.isoformat() if self.predicted_arrival else None,
            "predicted_completion": self.predicted_completion.isoformat() if self.predicted_completion else None,
            "distance_km": round(self.distance_km, 2),
            "maps_deep_link_google": self.maps_deep_link_google,
            "maps_deep_link_apple": self.maps_deep_link_apple,
            "scores": {
                "total": round(self.scores.total_score, 4),
                "distance": round(self.scores.distance_score, 4),
                "skill_match": round(self.scores.skill_match_score, 4),
                "workload": round(self.scores.workload_score, 4),
                "performance": round(self.scores.performance_score, 4),
                "availability": round(self.scores.availability_score, 4),
            } if self.scores else None,
            "alternatives": self.alternative_techs,
            "customer_eta_sent": self.customer_eta_sent,
            "eta_message": self.eta_message,
            "duration_confidence": self.duration_confidence,
        }


@dataclass
class DispatchBoardSnapshot:
    """
    A point-in-time view of the full dispatch board state.
    Broadcast via WebSocket to dashboard clients.
    """
    snapshot_id: str
    timestamp: datetime = field(default_factory=datetime.utcnow)
    pending_jobs: List[Dict] = field(default_factory=list)
    assigned_jobs: List[Dict] = field(default_factory=list)
    in_progress_jobs: List[Dict] = field(default_factory=list)
    completed_jobs_today: List[Dict] = field(default_factory=list)
    technicians: List[Dict] = field(default_factory=list)
    recent_assignments: List[Dict] = field(default_factory=list)
    metrics: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "snapshot_id": self.snapshot_id,
            "timestamp": self.timestamp.isoformat(),
            "pending_jobs": self.pending_jobs,
            "assigned_jobs": self.assigned_jobs,
            "in_progress_jobs": self.in_progress_jobs,
            "completed_jobs_today": self.completed_jobs_today,
            "technicians": self.technicians,
            "recent_assignments": self.recent_assignments,
            "metrics": self.metrics,
        }
