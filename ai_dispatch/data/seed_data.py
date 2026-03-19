"""
Generates synthetic historical job data for initial ML model training.
Run this once: python -m ai_dispatch.data.seed_data
"""

import json
import random
import math
from datetime import datetime, timedelta
from pathlib import Path

random.seed(42)

JOB_TYPES = [
    ("hvac_repair", 90, 30),
    ("hvac_install", 240, 60),
    ("hvac_maintenance", 60, 15),
    ("hvac_emergency", 120, 40),
    ("hvac_diagnostic", 60, 20),
    ("plumbing_repair", 75, 25),
    ("plumbing_install", 180, 50),
    ("plumbing_emergency", 90, 30),
    ("drain_cleaning", 60, 15),
    ("water_heater", 150, 40),
    ("electrical_repair", 75, 25),
    ("electrical_install", 180, 50),
    ("electrical_inspection", 90, 20),
    ("panel_upgrade", 300, 60),
    ("ev_charger", 180, 45),
    ("maintenance", 60, 20),
    ("inspection", 45, 15),
    ("estimate", 30, 10),
]


def generate_historical_records(n: int = 500) -> list:
    records = []
    base_date = datetime.utcnow() - timedelta(days=180)

    for i in range(n):
        job_type, baseline, std = random.choice(JOB_TYPES)
        equipment_age = random.uniform(0, 25)
        tech_exp = random.uniform(0.5, 20)
        priority = random.choices([1, 2, 3, 4, 5], weights=[5, 10, 20, 50, 15])[0]
        hour = random.randint(7, 18)
        dow = random.randint(0, 5)  # Mon-Sat
        customer_jobs = random.randint(0, 15)
        completion_rate = random.uniform(0.80, 1.0)

        # Simulate realistic duration with multiple influences
        duration = baseline
        duration += (equipment_age - 5) * 1.5     # Older = longer
        duration -= (tech_exp - 3) * 2.0           # More exp = faster
        duration += (5 - priority) * 5             # Urgent jobs resolved faster
        if hour >= 16:
            duration *= 1.08                       # Afternoon fatigue
        if dow == 0:
            duration *= 0.97                       # Monday fresh start
        duration += random.gauss(0, std)           # Random noise
        duration = max(15, int(duration))

        tech_avg = baseline + random.gauss(0, 10)

        records.append({
            "job_type": job_type,
            "equipment_age_years": round(equipment_age, 1),
            "tech_experience_years": round(tech_exp, 1),
            "tech_avg_duration": round(max(15, tech_avg), 1),
            "hour_of_day": hour,
            "day_of_week": dow,
            "customer_lifetime_jobs": customer_jobs,
            "job_priority": priority,
            "tech_completion_rate": round(completion_rate, 3),
            "actual_duration_minutes": duration,
            "recorded_at": (base_date + timedelta(days=i * 0.36)).isoformat(),
        })

    return records


if __name__ == "__main__":
    out_path = Path(__file__).parent / "historical_jobs.json"
    records = generate_historical_records(500)
    with open(out_path, "w") as f:
        json.dump(records, f, indent=2)
    print(f"Generated {len(records)} historical records -> {out_path}")
