"""
AI Dispatch Engine — the central orchestrator.

Continuously runs an optimization loop:
  1. Pulls pending jobs
  2. Queries tech locations / availability
  3. Predicts job durations via ML
  4. Runs tech assignment optimizer
  5. Pushes assignments to FSM
  6. Sends customer ETAs
  7. Broadcasts board updates via WebSocket
  8. Re-optimizes whenever state changes
"""

from __future__ import annotations
import asyncio
import logging
import uuid
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Callable, Any

from ..models.job import Job, JobStatus, JobPriority
from ..models.technician import Technician, TechnicianStatus
from ..models.assignment import AssignmentResult, DispatchBoardSnapshot
from ..models.prediction import DurationPredictor
from .optimizer import TechAssignmentOptimizer

logger = logging.getLogger(__name__)


class DispatchEngine:
    """
    The AI dispatch brain. Runs an async optimization loop with configurable
    polling interval. Emits real-time board snapshots and handles all
    assignment lifecycle events.
    """

    def __init__(
        self,
        maps_service=None,
        fsm_adapter=None,
        notification_service=None,
        optimization_interval_seconds: int = 30,
        eta_update_interval_seconds: int = 120,
        ml_config=None,
        optimizer_config=None,
    ):
        self.maps_service = maps_service
        self.fsm_adapter = fsm_adapter
        self.notification_service = notification_service
        self.optimization_interval = optimization_interval_seconds
        self.eta_update_interval = eta_update_interval_seconds

        # In-memory state (replace with DB layer for production)
        self._jobs: Dict[str, Job] = {}
        self._technicians: Dict[str, Technician] = {}
        self._assignments: Dict[str, AssignmentResult] = {}   # job_id → result
        self._recent_assignments: List[AssignmentResult] = []

        # Core AI components — receive config so paths and weights come from environment
        self.predictor = DurationPredictor(
            model_path=ml_config.model_path if ml_config else None,
            data_path=ml_config.data_path if ml_config else None,
        )
        self.optimizer = TechAssignmentOptimizer(
            maps_service=maps_service,
            optimizer_config=optimizer_config,
        )

        # Event callbacks (register from API server)
        self._board_update_callbacks: List[Callable[[DispatchBoardSnapshot], Any]] = []
        self._assignment_callbacks: List[Callable[[AssignmentResult], Any]] = []

        # Loop control
        self._running = False
        self._loop_task: Optional[asyncio.Task] = None
        self._eta_task: Optional[asyncio.Task] = None

    # ─── Lifecycle ────────────────────────────────────────────────────────────

    async def start(self):
        """Start the continuous optimization loop."""
        if self._running:
            logger.warning("Dispatch engine already running")
            return
        self._running = True
        self._loop_task = asyncio.create_task(self._optimization_loop())
        self._eta_task = asyncio.create_task(self._eta_refresh_loop())
        logger.info("Dispatch engine started")

    async def stop(self):
        """Gracefully stop the engine."""
        self._running = False
        if self._loop_task:
            self._loop_task.cancel()
        if self._eta_task:
            self._eta_task.cancel()
        logger.info("Dispatch engine stopped")

    # ─── State Management ─────────────────────────────────────────────────────

    def add_job(self, job: Job) -> str:
        """Register a new job for dispatch consideration."""
        self._jobs[job.job_id] = job
        logger.info(f"Job added: {job.job_id} | {job.job_type.value} | P{job.priority.value}")
        asyncio.create_task(self._trigger_optimization())
        return job.job_id

    def update_job(self, job: Job):
        """Update an existing job (e.g. status change, reschedule)."""
        self._jobs[job.job_id] = job
        asyncio.create_task(self._trigger_optimization())

    def remove_job(self, job_id: str):
        """Remove a job (completed, cancelled)."""
        self._jobs.pop(job_id, None)
        self._assignments.pop(job_id, None)

    def add_technician(self, tech: Technician):
        """Register a technician with the engine."""
        self._technicians[tech.tech_id] = tech
        logger.info(f"Technician registered: {tech.name} ({tech.tech_id})")

    def update_technician_location(self, tech_id: str, lat: float, lon: float):
        """Real-time GPS location update from mobile app or tracking device."""
        tech = self._technicians.get(tech_id)
        if tech:
            from ..models.technician import TechnicianLocation
            tech.location = TechnicianLocation(latitude=lat, longitude=lon)

    def update_technician_status(self, tech_id: str, status: TechnicianStatus):
        """Status change (arrived, started job, completed, etc.)."""
        tech = self._technicians.get(tech_id)
        if tech:
            tech.status = status
            asyncio.create_task(self._trigger_optimization())

    def mark_job_completed(self, job_id: str, actual_duration_minutes: int):
        """
        Record job completion. Feeds actual duration back to ML predictor.
        """
        job = self._jobs.get(job_id)
        if not job:
            return
        job.status = JobStatus.COMPLETED
        job.actual_end = datetime.utcnow()
        job.actual_duration_minutes = actual_duration_minutes

        # Feed back to ML
        tech = self._technicians.get(job.assigned_tech_id) if job.assigned_tech_id else None
        self.predictor.add_completed_job({
            "job_type": job.job_type.value,
            "equipment_age_years": job.equipment.age_years or 5.0 if job.equipment else 5.0,
            "tech_experience_years": tech.years_experience if tech else 3.0,
            "tech_avg_duration": tech.avg_job_duration_minutes if tech else 75.0,
            "hour_of_day": job.actual_start.hour if job.actual_start else 10,
            "day_of_week": job.actual_start.weekday() if job.actual_start else 1,
            "customer_lifetime_jobs": job.customer.lifetime_jobs,
            "job_priority": job.priority.value,
            "tech_completion_rate": tech.completion_rate if tech else 0.95,
            "actual_duration_minutes": actual_duration_minutes,
        })

        if tech:
            tech.jobs_completed_today += 1
            tech.jobs_completed_lifetime += 1
            # Update rolling average
            n = tech.jobs_completed_lifetime
            tech.avg_job_duration_minutes = (
                (tech.avg_job_duration_minutes * (n - 1) + actual_duration_minutes) / n
            )
            tech.current_job_id = None
            tech.status = TechnicianStatus.AVAILABLE

        self.remove_job(job_id)
        logger.info(f"Job {job_id} completed: {actual_duration_minutes} min actual")

    # ─── Core Optimization Loop ───────────────────────────────────────────────

    async def _optimization_loop(self):
        """Main loop: runs optimization on schedule or after triggered events."""
        while self._running:
            try:
                await self._run_optimization_cycle()
                await self._broadcast_board_update()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Optimization loop error: {e}", exc_info=True)
            await asyncio.sleep(self.optimization_interval)

    async def _trigger_optimization(self):
        """Trigger an immediate optimization cycle (e.g., on new job or tech status change)."""
        await asyncio.sleep(0.5)  # Brief debounce
        try:
            await self._run_optimization_cycle()
            await self._broadcast_board_update()
        except Exception as e:
            logger.error(f"Triggered optimization failed: {e}", exc_info=True)

    async def _run_optimization_cycle(self):
        """One full optimization pass over all pending jobs."""
        pending_jobs = [
            j for j in self._jobs.values()
            if j.status == JobStatus.PENDING
        ]
        if not pending_jobs:
            return

        available_techs = list(self._technicians.values())

        # Step 1: Predict durations for all pending jobs
        durations: Dict[str, int] = {}
        for job in pending_jobs:
            tech_id = None
            if job.assigned_tech_id:
                tech_id = job.assigned_tech_id
            tech = self._technicians.get(tech_id) if tech_id else None

            duration, confidence = self.predictor.predict(
                job_type=job.job_type.value,
                equipment_age_years=(
                    job.equipment.age_years if job.equipment and job.equipment.age_years else 5.0
                ),
                tech_experience_years=tech.years_experience if tech else 3.0,
                tech_avg_duration=tech.avg_job_duration_minutes if tech else 0.0,
                customer_lifetime_jobs=job.customer.lifetime_jobs,
                job_priority=job.priority.value,
                tech_completion_rate=tech.completion_rate if tech else 0.95,
            )
            job.predicted_duration_minutes = duration
            durations[job.job_id] = duration

        # Step 2: Run assignment optimizer
        results = self.optimizer.optimize_batch(
            jobs=pending_jobs,
            technicians=available_techs,
            durations=durations,
        )

        # Step 3: Apply assignments
        for result in results:
            await self._apply_assignment(result)

    async def _apply_assignment(self, result: AssignmentResult):
        """Apply an assignment: update job + tech state, push to FSM, send ETA."""
        job = self._jobs.get(result.job_id)
        tech = self._technicians.get(result.tech_id)
        if not job or not tech:
            return

        # Idempotency: don't re-assign if already same tech
        existing = self._assignments.get(result.job_id)
        if existing and existing.tech_id == result.tech_id:
            return

        # Update job
        job.status = JobStatus.ASSIGNED
        job.assigned_tech_id = result.tech_id
        job.assignment_time = datetime.utcnow()
        job.predicted_eta = result.predicted_arrival
        job.predicted_duration_minutes = result.predicted_job_duration_minutes

        # Update tech
        if job.job_id not in tech.job_queue:
            tech.job_queue.append(job.job_id)
        if tech.current_job_id is None:
            tech.current_job_id = job.job_id
            tech.status = TechnicianStatus.EN_ROUTE

        self._assignments[result.job_id] = result

        # Keep a rolling log of last 50 assignments
        self._recent_assignments.insert(0, result)
        self._recent_assignments = self._recent_assignments[:50]

        logger.info(
            f"Assigned job {result.job_id} → {result.tech_name} | "
            f"ETA: {result.predicted_arrival.strftime('%H:%M') if result.predicted_arrival else 'N/A'} | "
            f"Score: {result.scores.total_score:.3f}"
        )

        # Push to FSM
        if self.fsm_adapter:
            try:
                await self.fsm_adapter.assign_job(
                    job_id=job.fsm_job_id or job.job_id,
                    tech_id=tech.fsm_tech_id or tech.tech_id,
                    eta=result.predicted_arrival,
                )
            except Exception as e:
                logger.error(f"FSM assignment push failed: {e}")

        # Send ETA notification
        if self.notification_service and job.predicted_eta:
            try:
                eta_message = await self.notification_service.send_eta(
                    job=job,
                    tech=tech,
                    eta=result.predicted_arrival,
                    travel_time_minutes=result.travel_time_minutes,
                )
                result.customer_eta_sent = True
                result.eta_message = eta_message
                job.eta_sent_at = datetime.utcnow()
            except Exception as e:
                logger.error(f"ETA notification failed: {e}")

        # Fire assignment callbacks
        for cb in self._assignment_callbacks:
            try:
                await cb(result) if asyncio.iscoroutinefunction(cb) else cb(result)
            except Exception as e:
                logger.error(f"Assignment callback error: {e}")

    async def _eta_refresh_loop(self):
        """
        Periodically recalculate ETAs for all active en-route jobs
        and send updated notifications if ETA changed significantly (>10 min).
        """
        while self._running:
            await asyncio.sleep(self.eta_update_interval)
            try:
                await self._refresh_active_etas()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"ETA refresh error: {e}")

    async def _refresh_active_etas(self):
        """Recalculate ETAs for all en-route jobs."""
        en_route_jobs = [
            j for j in self._jobs.values()
            if j.status in (JobStatus.ASSIGNED, JobStatus.EN_ROUTE)
            and j.assigned_tech_id
            and j.predicted_eta
        ]
        for job in en_route_jobs:
            tech = self._technicians.get(job.assigned_tech_id)
            if not tech:
                continue

            try:
                dist, travel_time = self.optimizer._get_distance_and_travel(tech, job)
                new_eta = datetime.utcnow() + timedelta(minutes=travel_time)

                # Only update if changed by more than 10 minutes
                old_eta = job.predicted_eta
                if abs((new_eta - old_eta).total_seconds()) > 600:
                    job.predicted_eta = new_eta
                    job.eta_last_updated = datetime.utcnow()

                    if self.notification_service:
                        await self.notification_service.send_eta_update(
                            job=job,
                            tech=tech,
                            new_eta=new_eta,
                            old_eta=old_eta,
                        )
                    logger.info(
                        f"ETA updated for job {job.job_id}: "
                        f"{old_eta.strftime('%H:%M')} → {new_eta.strftime('%H:%M')}"
                    )
            except Exception as e:
                logger.debug(f"ETA refresh skipped for {job.job_id}: {e}")

    # ─── Board Snapshot ───────────────────────────────────────────────────────

    def get_board_snapshot(self) -> DispatchBoardSnapshot:
        """Generate a current snapshot of the full dispatch board."""
        now = datetime.utcnow()
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)

        pending = [j.to_dict() for j in self._jobs.values() if j.status == JobStatus.PENDING]
        assigned = [j.to_dict() for j in self._jobs.values() if j.status == JobStatus.ASSIGNED]
        in_progress = [j.to_dict() for j in self._jobs.values() if j.status == JobStatus.IN_PROGRESS]
        completed_today: List[Dict] = []  # Would pull from persistent store in production

        techs = [t.to_dict() for t in self._technicians.values()]
        recent = [r.to_dict() for r in self._recent_assignments[:10]]

        # Board metrics
        total_techs = len(self._technicians)
        available_count = sum(
            1 for t in self._technicians.values()
            if t.status == TechnicianStatus.AVAILABLE
        )
        on_job_count = sum(
            1 for t in self._technicians.values()
            if t.status in (TechnicianStatus.ON_JOB, TechnicianStatus.EN_ROUTE)
        )

        metrics = {
            "total_pending": len(pending),
            "total_assigned": len(assigned),
            "total_in_progress": len(in_progress),
            "emergency_jobs": sum(1 for j in self._jobs.values() if j.is_emergency),
            "total_technicians": total_techs,
            "available_technicians": available_count,
            "on_job_technicians": on_job_count,
            "utilization_rate": round(on_job_count / max(total_techs, 1), 2),
            "avg_wait_time_minutes": round(
                sum(j.wait_time_minutes for j in self._jobs.values() if j.status == JobStatus.PENDING)
                / max(len(pending), 1), 1
            ),
        }

        return DispatchBoardSnapshot(
            snapshot_id=str(uuid.uuid4()),
            pending_jobs=pending,
            assigned_jobs=assigned,
            in_progress_jobs=in_progress,
            completed_jobs_today=completed_today,
            technicians=techs,
            recent_assignments=recent,
            metrics=metrics,
        )

    async def _broadcast_board_update(self):
        """Push board snapshot to all registered callbacks (WebSocket clients)."""
        snapshot = self.get_board_snapshot()
        for cb in self._board_update_callbacks:
            try:
                if asyncio.iscoroutinefunction(cb):
                    await cb(snapshot)
                else:
                    cb(snapshot)
            except Exception as e:
                logger.debug(f"Board update callback error: {e}")

    # ─── Callback Registration ────────────────────────────────────────────────

    def on_board_update(self, callback: Callable):
        """Register a callback to receive board snapshots (for WebSocket broadcast)."""
        self._board_update_callbacks.append(callback)

    def on_assignment(self, callback: Callable):
        """Register a callback fired on each new assignment."""
        self._assignment_callbacks.append(callback)

    # ─── Manual Dispatch ─────────────────────────────────────────────────────

    async def manual_assign(self, job_id: str, tech_id: str) -> Optional[AssignmentResult]:
        """
        Force a manual assignment override (dispatcher decision takes precedence).
        Bypasses optimization scoring.
        """
        job = self._jobs.get(job_id)
        tech = self._technicians.get(tech_id)
        if not job or not tech:
            logger.error(f"Manual assign failed: job={job_id}, tech={tech_id}")
            return None

        dist, travel_time = self.optimizer._get_distance_and_travel(tech, job)
        duration = job.predicted_duration_minutes or job.base_duration_minutes
        now = datetime.utcnow()

        result = AssignmentResult(
            job_id=job_id,
            tech_id=tech_id,
            tech_name=tech.name,
            travel_time_minutes=travel_time,
            predicted_job_duration_minutes=duration,
            predicted_arrival=now + timedelta(minutes=travel_time),
            predicted_completion=now + timedelta(minutes=travel_time + duration),
            distance_km=dist,
            assignment_confidence=1.0,  # Manual = 100% confidence in decision
        )
        await self._apply_assignment(result)
        logger.info(f"Manual assignment: job {job_id} → {tech.name}")
        return result
