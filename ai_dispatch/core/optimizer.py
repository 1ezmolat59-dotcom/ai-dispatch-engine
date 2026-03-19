"""
Tech Assignment Optimizer.
Scores every eligible technician against a job using a weighted multi-factor model:

  score = w_dist   * proximity_score
        + w_skill  * skill_match_score
        + w_load   * (1 - workload_ratio)
        + w_perf   * performance_score
        + w_avail  * availability_score
        + priority_bonus

All sub-scores are normalized to [0, 1] before weighting.
All weights and bonuses are configurable via OptimizerConfig / environment variables.
"""

from __future__ import annotations
import logging
import math
from datetime import datetime, timedelta
from typing import List, Optional, Tuple, Dict

from ..models.job import Job, JobPriority
from ..models.technician import Technician, TechnicianStatus
from ..models.assignment import AssignmentResult, AssignmentScore
from ..config import OptimizerConfig

logger = logging.getLogger(__name__)


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Fast Haversine distance in kilometres. Used as fallback when Maps API unavailable."""
    R = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (math.sin(dlat / 2) ** 2
         + math.cos(math.radians(lat1))
         * math.cos(math.radians(lat2))
         * math.sin(dlon / 2) ** 2)
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def _proximity_score(distance_km: float, hard_cutoff_km: float) -> float:
    """
    Converts distance to a 0-1 score using exponential decay.
    0 km  → 1.0 (perfect)
    80 km → ~0.07 (heavily penalized)
    >= hard_cutoff_km → 0.0
    """
    if distance_km >= hard_cutoff_km:
        return 0.0
    if distance_km <= 0:
        return 1.0
    return max(0.0, math.exp(-distance_km / 30.0))


def _availability_score(tech: Technician, now: Optional[datetime] = None) -> float:
    """
    Scores how quickly a tech can be available.
    AVAILABLE = 1.0
    EN_ROUTE  = 0.7 (can be pre-assigned for next job)
    ON_JOB    = 0.4 (will be free in estimated time)
    ON_BREAK  = 0.6
    others    = 0.0
    """
    now = now or datetime.utcnow()
    if tech.status == TechnicianStatus.AVAILABLE:
        return 1.0
    elif tech.status == TechnicianStatus.EN_ROUTE:
        return 0.7
    elif tech.status == TechnicianStatus.ON_JOB:
        # Partial credit based on queue depth
        queue_len = len(tech.job_queue)
        return max(0.1, 0.5 - queue_len * 0.1)
    elif tech.status == TechnicianStatus.ON_BREAK:
        return 0.6
    else:
        return 0.0


def _performance_score(tech: Technician) -> float:
    """
    Combines customer rating (40%) + on-time rate (30%) + completion rate (30%).
    Normalizes to 0-1.
    """
    rating_score = (tech.customer_rating - 1.0) / 4.0   # 1-5 scale → 0-1
    return (
        0.40 * rating_score
        + 0.30 * tech.on_time_rate
        + 0.30 * tech.completion_rate
    )


class TechAssignmentOptimizer:
    """
    Core AI optimizer that finds the best technician for a given job.
    Uses weighted multi-factor scoring with real distance data from Maps API.
    All weights are configurable via OptimizerConfig.
    """

    def __init__(self, maps_service=None, optimizer_config: Optional[OptimizerConfig] = None):
        self.maps_service = maps_service
        # Fall back to default config if none provided
        self.cfg = optimizer_config if optimizer_config is not None else OptimizerConfig()

        # Build priority → bonus lookup from config for fast access
        self._priority_bonuses: Dict[JobPriority, float] = {
            JobPriority.EMERGENCY: self.cfg.bonus_emergency,
            JobPriority.URGENT:    self.cfg.bonus_urgent,
            JobPriority.HIGH:      self.cfg.bonus_high,
            JobPriority.NORMAL:    self.cfg.bonus_normal,
            JobPriority.LOW:       self.cfg.bonus_low,
        }

    def _get_distance_and_travel(
        self,
        tech: Technician,
        job: Job,
    ) -> Tuple[float, float]:
        """
        Returns (distance_km, travel_time_minutes).
        Uses Maps API if available and healthy, Haversine fallback otherwise.
        """
        tech_lat, tech_lon = tech.current_location_or_home
        job_lat = job.customer.latitude
        job_lon = job.customer.longitude

        if self.maps_service:
            try:
                result = self.maps_service.get_distance_matrix(
                    origins=[(tech_lat, tech_lon)],
                    destinations=[(job_lat, job_lon)],
                )
                if result:
                    return result[0]["distance_km"], result[0]["duration_minutes"]
            except Exception as e:
                logger.debug(f"Maps API failed for tech {tech.tech_id}: {e}. Using Haversine.")

        dist = haversine_km(tech_lat, tech_lon, job_lat, job_lon)
        travel_time = (dist / 40.0) * 60  # Assume 40 km/h average urban speed
        return dist, travel_time

    def score_technician(
        self,
        tech: Technician,
        job: Job,
        distance_km: float,
        travel_time_minutes: float,
    ) -> AssignmentScore:
        """Compute the full scoring breakdown for one tech-job pair."""
        prox = _proximity_score(distance_km, self.cfg.max_distance_km)
        skill = tech.skill_match_score(job.required_skills)
        workload = max(0.0, 1.0 - tech.workload_ratio)
        perf = _performance_score(tech)
        avail = _availability_score(tech)
        priority_bonus = self._priority_bonuses.get(job.priority, 0.0)

        total = (
            self.cfg.weight_distance    * prox
            + self.cfg.weight_skill     * skill
            + self.cfg.weight_workload  * workload
            + self.cfg.weight_performance * perf
            + self.cfg.weight_availability * avail
            + priority_bonus
        )

        return AssignmentScore(
            total_score=max(0.0, total),
            distance_score=prox,
            skill_match_score=skill,
            workload_score=workload,
            performance_score=perf,
            availability_score=avail,
            priority_bonus=priority_bonus,
            distance_km=distance_km,
            travel_time_minutes=travel_time_minutes,
        )

    def find_best_technician(
        self,
        job: Job,
        technicians: List[Technician],
        predicted_duration_minutes: int,
        now: Optional[datetime] = None,
    ) -> Optional[AssignmentResult]:
        """
        Find the optimal technician for a job.
        Returns AssignmentResult with full scoring context, or None if no eligible tech.
        """
        now = now or datetime.utcnow()
        candidates: List[Tuple[float, AssignmentScore, Technician, float]] = []

        for tech in technicians:
            # Hard eligibility gates
            if not tech.is_available_for_assignment:
                logger.debug(f"Tech {tech.name} not available for assignment")
                continue
            if not tech.has_all_skills(job.required_skills):
                logger.debug(f"Tech {tech.name} lacks required skills: {job.required_skills}")
                continue
            if not tech.schedule.is_working(now):
                logger.debug(f"Tech {tech.name} not on schedule right now")
                continue

            distance_km, travel_time = self._get_distance_and_travel(tech, job)

            if distance_km >= self.cfg.max_distance_km:
                logger.debug(f"Tech {tech.name} too far: {distance_km:.1f} km (cutoff: {self.cfg.max_distance_km} km)")
                continue

            score = self.score_technician(tech, job, distance_km, travel_time)

            # Emergency override: add bonus if tech has skill + is available
            if job.is_emergency and tech.has_all_skills(job.required_skills):
                score = AssignmentScore(
                    total_score=score.total_score + 0.3,
                    distance_score=score.distance_score,
                    skill_match_score=score.skill_match_score,
                    workload_score=score.workload_score,
                    performance_score=score.performance_score,
                    availability_score=score.availability_score,
                    priority_bonus=score.priority_bonus,
                    distance_km=distance_km,
                    travel_time_minutes=travel_time,
                )

            candidates.append((score.total_score, score, tech, travel_time))

        if not candidates:
            logger.warning(f"No eligible technicians found for job {job.job_id} ({job.job_type})")
            return None

        # Sort by score descending
        candidates.sort(key=lambda x: x[0], reverse=True)
        best_score_val, best_score, best_tech, travel_time = candidates[0]

        # Build alternatives list (next 3)
        alternatives = []
        for _, sc, tech, _ in candidates[1:4]:
            alternatives.append({
                "tech_id": tech.tech_id,
                "tech_name": tech.name,
                "score": round(sc.total_score, 4),
                "distance_km": round(sc.distance_km, 2),
                "skill_match": round(sc.skill_match_score, 4),
            })

        # Calculate ETA times
        predicted_arrival = now + timedelta(minutes=travel_time)
        predicted_completion = predicted_arrival + timedelta(minutes=predicted_duration_minutes)

        # Build Maps deep links
        job_lat = job.customer.latitude
        job_lon = job.customer.longitude
        google_link = (
            f"https://www.google.com/maps/dir/?api=1"
            f"&destination={job_lat},{job_lon}"
            f"&travelmode=driving"
        )
        apple_link = f"maps://?daddr={job_lat},{job_lon}&dirflg=d"

        return AssignmentResult(
            job_id=job.job_id,
            tech_id=best_tech.tech_id,
            tech_name=best_tech.name,
            travel_time_minutes=travel_time,
            predicted_job_duration_minutes=predicted_duration_minutes,
            predicted_arrival=predicted_arrival,
            predicted_completion=predicted_completion,
            distance_km=best_score.distance_km,
            maps_deep_link_google=google_link,
            maps_deep_link_apple=apple_link,
            scores=best_score,
            alternative_techs=alternatives,
            assignment_confidence=min(0.99, best_score_val),
        )

    def optimize_batch(
        self,
        jobs: List[Job],
        technicians: List[Technician],
        durations: Dict[str, int],
        now: Optional[datetime] = None,
    ) -> List[AssignmentResult]:
        """
        Optimize assignments for multiple pending jobs at once.
        Processes in priority order and updates tech availability after each assignment.
        """
        now = now or datetime.utcnow()

        # Sort jobs by priority then wait time
        sorted_jobs = sorted(
            jobs,
            key=lambda j: (j.priority.value, -j.wait_time_minutes)
        )

        results = []
        tech_queue_counts: Dict[str, int] = {t.tech_id: len(t.job_queue) for t in technicians}

        for job in sorted_jobs:
            # Only consider techs that haven't hit their daily limit
            available_techs = [
                t for t in technicians
                if tech_queue_counts.get(t.tech_id, 0) < t.max_jobs_per_day
            ]

            duration = durations.get(job.job_id, job.base_duration_minutes)
            result = self.find_best_technician(job, available_techs, duration, now)

            if result:
                results.append(result)
                # Update simulated queue count so next job sees updated load
                tech_queue_counts[result.tech_id] = tech_queue_counts.get(result.tech_id, 0) + 1

        return results
