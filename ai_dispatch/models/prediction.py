"""
ML-based job duration predictor.
Uses a Random Forest Regressor trained on historical job data.
Features: job type, equipment age, tech experience, time of day, historical patterns.
Falls back to rule-based estimate when insufficient training data.
"""

from __future__ import annotations
import os
import json
import pickle
import logging
import math
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict, Any, Tuple

import numpy as np

logger = logging.getLogger(__name__)

# Minimum samples required before trusting ML predictions
MIN_TRAINING_SAMPLES = 50

# Job type to integer encoding
JOB_TYPE_ENCODING: Dict[str, int] = {
    "hvac_repair": 0, "hvac_install": 1, "hvac_maintenance": 2,
    "hvac_emergency": 3, "hvac_diagnostic": 4,
    "plumbing_repair": 5, "plumbing_install": 6, "plumbing_emergency": 7,
    "drain_cleaning": 8, "water_heater": 9,
    "electrical_repair": 10, "electrical_install": 11,
    "electrical_inspection": 12, "panel_upgrade": 13, "ev_charger": 14,
    "maintenance": 15, "inspection": 16, "estimate": 17,
}

# Job type baseline durations in minutes
JOB_BASELINES: Dict[str, int] = {
    "hvac_repair": 90, "hvac_install": 240, "hvac_maintenance": 60,
    "hvac_emergency": 120, "hvac_diagnostic": 60,
    "plumbing_repair": 75, "plumbing_install": 180, "plumbing_emergency": 90,
    "drain_cleaning": 60, "water_heater": 150,
    "electrical_repair": 75, "electrical_install": 180,
    "electrical_inspection": 90, "panel_upgrade": 300, "ev_charger": 180,
    "maintenance": 60, "inspection": 45, "estimate": 30,
}


def _extract_features(
    job_type: str,
    equipment_age_years: float,
    tech_experience_years: float,
    tech_avg_duration: float,
    hour_of_day: int,
    day_of_week: int,
    customer_lifetime_jobs: int,
    job_priority: int,
    tech_completion_rate: float,
) -> np.ndarray:
    """Convert raw inputs into a feature vector for the ML model."""
    return np.array([[
        JOB_TYPE_ENCODING.get(job_type, 15),  # Encoded job type
        min(equipment_age_years, 30),          # Cap at 30 years
        min(tech_experience_years, 30),        # Cap at 30 years
        tech_avg_duration,                     # Tech's historical avg
        hour_of_day,                           # 0-23
        day_of_week,                           # 0=Mon, 6=Sun
        min(customer_lifetime_jobs, 20),       # Customer familiarity
        job_priority,                          # 1=emergency, 5=low
        tech_completion_rate,                  # 0.0-1.0
        JOB_BASELINES.get(job_type, 60),       # Baseline anchor
    ]])


class DurationPredictor:
    """
    Predicts job duration using a trained ML model.
    Auto-trains from historical data stored in a JSON file.
    Falls back gracefully to rule-based estimates.
    """

    def __init__(self, model_path: Optional[str] = None, data_path: Optional[str] = None):
        # Default path changed from /tmp (wiped on Linux restart) to a persistent data dir
        self.model_path = model_path or "ai_dispatch/data/dispatch_model.pkl"
        self.data_path = data_path or str(
            Path(__file__).parent.parent / "data" / "historical_jobs.json"
        )
        self.model = None
        self.scaler = None
        self.is_trained = False
        self.training_samples = 0
        self._load_or_train()

    def _load_or_train(self):
        """Load existing model or train a fresh one from historical data."""
        if os.path.exists(self.model_path):
            try:
                with open(self.model_path, "rb") as f:
                    saved = pickle.load(f)
                    self.model = saved["model"]
                    self.scaler = saved["scaler"]
                    self.training_samples = saved.get("training_samples", 0)
                    self.is_trained = True
                    logger.info(f"Loaded duration model ({self.training_samples} samples)")
                    return
            except Exception as e:
                logger.warning(f"Failed to load saved model: {e}. Retraining...")

        self._train_from_historical_data()

    def _train_from_historical_data(self):
        """Train the Random Forest model from historical job JSON."""
        try:
            from sklearn.ensemble import RandomForestRegressor, GradientBoostingRegressor
            from sklearn.preprocessing import StandardScaler
            from sklearn.model_selection import train_test_split
            from sklearn.metrics import mean_absolute_error
        except ImportError:
            logger.warning("scikit-learn not installed. Using rule-based predictions only.")
            return

        if not os.path.exists(self.data_path):
            logger.warning(f"Historical data not found at {self.data_path}. Using baselines.")
            return

        try:
            with open(self.data_path) as f:
                records = json.load(f)
        except Exception as e:
            logger.error(f"Failed to load historical data: {e}")
            return

        completed = [r for r in records if r.get("actual_duration_minutes") and r["actual_duration_minutes"] > 0]
        if len(completed) < MIN_TRAINING_SAMPLES:
            logger.info(f"Only {len(completed)} samples. Need {MIN_TRAINING_SAMPLES} to train. Using baselines.")
            return

        X, y = [], []
        for r in completed:
            try:
                feats = _extract_features(
                    job_type=r.get("job_type", "maintenance"),
                    equipment_age_years=r.get("equipment_age_years", 5.0),
                    tech_experience_years=r.get("tech_experience_years", 3.0),
                    tech_avg_duration=r.get("tech_avg_duration", 75.0),
                    hour_of_day=r.get("hour_of_day", 10),
                    day_of_week=r.get("day_of_week", 1),
                    customer_lifetime_jobs=r.get("customer_lifetime_jobs", 2),
                    job_priority=r.get("job_priority", 4),
                    tech_completion_rate=r.get("tech_completion_rate", 0.95),
                )
                X.append(feats[0])
                y.append(r["actual_duration_minutes"])
            except Exception:
                continue

        if len(X) < MIN_TRAINING_SAMPLES:
            return

        X = np.array(X)
        y = np.array(y)

        scaler = StandardScaler()
        X_scaled = scaler.fit_transform(X)

        if len(X) >= 100:
            X_train, X_test, y_train, y_test = train_test_split(
                X_scaled, y, test_size=0.2, random_state=42
            )
            model = RandomForestRegressor(
                n_estimators=200,
                max_depth=12,
                min_samples_split=4,
                min_samples_leaf=2,
                random_state=42,
                n_jobs=-1,
            )
            model.fit(X_train, y_train)
            mae = mean_absolute_error(y_test, model.predict(X_test))
            logger.info(f"Duration model trained: {len(X)} samples, MAE={mae:.1f} min")
        else:
            model = RandomForestRegressor(n_estimators=100, random_state=42)
            model.fit(X_scaled, y)
            logger.info(f"Duration model trained: {len(X)} samples (no test split)")

        self.model = model
        self.scaler = scaler
        self.training_samples = len(X)
        self.is_trained = True

        try:
            with open(self.model_path, "wb") as f:
                pickle.dump({
                    "model": model,
                    "scaler": scaler,
                    "training_samples": len(X),
                    "trained_at": datetime.utcnow().isoformat(),
                }, f)
        except Exception as e:
            logger.warning(f"Could not save model: {e}")

    def predict(
        self,
        job_type: str,
        equipment_age_years: float = 5.0,
        tech_experience_years: float = 3.0,
        tech_avg_duration: float = 0.0,
        hour_of_day: Optional[int] = None,
        day_of_week: Optional[int] = None,
        customer_lifetime_jobs: int = 1,
        job_priority: int = 4,
        tech_completion_rate: float = 0.95,
    ) -> Tuple[int, float]:
        """
        Predict job duration in minutes.
        Returns (predicted_minutes, confidence_score 0.0-1.0).
        """
        now = datetime.utcnow()
        hour_of_day = hour_of_day if hour_of_day is not None else now.hour
        day_of_week = day_of_week if day_of_week is not None else now.weekday()
        baseline = JOB_BASELINES.get(job_type, 60)

        # If no tech avg, use baseline
        if tech_avg_duration <= 0:
            tech_avg_duration = float(baseline)

        if not self.is_trained:
            # Rule-based fallback with experience adjustment
            adj = baseline
            if tech_experience_years < 1:
                adj = int(baseline * 1.3)
            elif tech_experience_years > 5:
                adj = int(baseline * 0.85)
            return (max(15, adj), 0.5)

        try:
            features = _extract_features(
                job_type=job_type,
                equipment_age_years=equipment_age_years,
                tech_experience_years=tech_experience_years,
                tech_avg_duration=tech_avg_duration,
                hour_of_day=hour_of_day,
                day_of_week=day_of_week,
                customer_lifetime_jobs=customer_lifetime_jobs,
                job_priority=job_priority,
                tech_completion_rate=tech_completion_rate,
            )
            features_scaled = self.scaler.transform(features)
            prediction = float(self.model.predict(features_scaled)[0])
            duration = max(15, int(round(prediction / 5) * 5))  # Round to nearest 5 min

            # Confidence scales with training data volume
            confidence = min(0.95, 0.5 + 0.45 * math.log10(max(self.training_samples, 1) / 50))
            return (duration, confidence)

        except Exception as e:
            logger.error(f"ML prediction failed: {e}. Falling back to baseline.")
            return (baseline, 0.5)

    def add_completed_job(self, record: Dict[str, Any]):
        """
        Add a completed job record to the training dataset and retrain periodically.
        Call this whenever a job is completed with actual duration data.
        """
        if not os.path.exists(self.data_path):
            # Guard: os.path.dirname("bare_filename") returns "" → makedirs("") raises FileNotFoundError
            parent_dir = os.path.dirname(os.path.abspath(self.data_path))
            if parent_dir:
                os.makedirs(parent_dir, exist_ok=True)
            existing = []
        else:
            try:
                with open(self.data_path) as f:
                    existing = json.load(f)
            except Exception:
                existing = []

        existing.append(record)
        with open(self.data_path, "w") as f:
            json.dump(existing, f)

        # Retrain every 50 new records
        if len(existing) % 50 == 0:
            logger.info("Retraining duration model with new data...")
            if os.path.exists(self.model_path):
                os.remove(self.model_path)
            self._train_from_historical_data()
