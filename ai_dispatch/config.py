"""
Centralized configuration for the AI Dispatch Engine.
All settings can be overridden via environment variables or .env file.
"""

from __future__ import annotations
import logging
import os
from dataclasses import dataclass, field
from typing import List, Optional

logger = logging.getLogger(__name__)


# ─── Env helpers ──────────────────────────────────────────────────────────────

def _env(key: str, default: str = "") -> str:
    return os.getenv(key, default)


def _env_int(key: str, default: int) -> int:
    return int(os.getenv(key, str(default)))


def _env_float(key: str, default: float) -> float:
    return float(os.getenv(key, str(default)))


def _env_bool(key: str, default: bool = False) -> bool:
    return os.getenv(key, str(default)).lower() in ("true", "1", "yes")


# ─── Config dataclasses ───────────────────────────────────────────────────────

@dataclass
class ServerConfig:
    host: str = field(default_factory=lambda: _env("SERVER_HOST", "0.0.0.0"))
    port: int = field(default_factory=lambda: _env_int("SERVER_PORT", 8000))
    workers: int = field(default_factory=lambda: _env_int("SERVER_WORKERS", 1))
    reload: bool = field(default_factory=lambda: _env_bool("SERVER_RELOAD", False))
    log_level: str = field(default_factory=lambda: _env("LOG_LEVEL", "INFO"))
    cors_origins: List[str] = field(default_factory=lambda: (
        _env("CORS_ORIGINS", "*").split(",")
    ))


@dataclass
class EngineConfig:
    optimization_interval_seconds: int = field(
        default_factory=lambda: _env_int("OPTIMIZATION_INTERVAL", 30)
    )
    eta_refresh_interval_seconds: int = field(
        default_factory=lambda: _env_int("ETA_REFRESH_INTERVAL", 120)
    )
    tech_location_stale_threshold_seconds: int = field(
        default_factory=lambda: _env_int("LOCATION_STALE_THRESHOLD", 120)
    )
    max_distance_km: float = field(
        default_factory=lambda: _env_float("MAX_DISPATCH_DISTANCE_KM", 150.0)
    )


@dataclass
class OptimizerConfig:
    """
    Scoring weights for tech-job assignment.
    Weights (distance + skill + workload + performance + availability) should sum to 1.0.
    Priority bonuses are additive on top of the weighted score.
    """
    weight_distance: float = field(
        default_factory=lambda: _env_float("WEIGHT_DISTANCE", 0.30)
    )
    weight_skill: float = field(
        default_factory=lambda: _env_float("WEIGHT_SKILL", 0.30)
    )
    weight_workload: float = field(
        default_factory=lambda: _env_float("WEIGHT_WORKLOAD", 0.15)
    )
    weight_performance: float = field(
        default_factory=lambda: _env_float("WEIGHT_PERFORMANCE", 0.15)
    )
    weight_availability: float = field(
        default_factory=lambda: _env_float("WEIGHT_AVAILABILITY", 0.10)
    )
    bonus_emergency: float = field(
        default_factory=lambda: _env_float("BONUS_EMERGENCY", 0.50)
    )
    bonus_urgent: float = field(
        default_factory=lambda: _env_float("BONUS_URGENT", 0.25)
    )
    bonus_high: float = field(
        default_factory=lambda: _env_float("BONUS_HIGH", 0.10)
    )
    bonus_normal: float = field(
        default_factory=lambda: _env_float("BONUS_NORMAL", 0.0)
    )
    bonus_low: float = field(
        default_factory=lambda: _env_float("BONUS_LOW", -0.05)
    )
    max_distance_km: float = field(
        default_factory=lambda: _env_float("MAX_DISPATCH_DISTANCE_KM", 150.0)
    )
    max_reasonable_distance_km: float = field(
        default_factory=lambda: _env_float("MAX_REASONABLE_DISTANCE_KM", 80.0)
    )

    def validate(self):
        """Warn if weights don't sum to 1.0 (tolerance ±0.01)."""
        total = (
            self.weight_distance + self.weight_skill +
            self.weight_workload + self.weight_performance +
            self.weight_availability
        )
        if abs(total - 1.0) > 0.01:
            logger.warning(
                "Optimizer weights sum to %.4f (expected 1.0). "
                "Scores will be skewed. Check WEIGHT_* env vars.",
                total,
            )


@dataclass
class MapsConfig:
    google_api_key: str = field(default_factory=lambda: _env("GOOGLE_MAPS_API_KEY"))
    apple_team_id: str = field(default_factory=lambda: _env("APPLE_MAPS_TEAM_ID"))
    apple_key_id: str = field(default_factory=lambda: _env("APPLE_MAPS_KEY_ID"))
    apple_private_key_path: str = field(
        default_factory=lambda: _env("APPLE_MAPS_PRIVATE_KEY_PATH")
    )
    traffic_model: str = field(
        default_factory=lambda: _env("MAPS_TRAFFIC_MODEL", "best_guess")
    )
    cache_ttl_seconds: int = field(
        default_factory=lambda: _env_int("MAPS_CACHE_TTL", 300)
    )
    # Circuit breaker: disable API for this many seconds after consecutive failures
    circuit_breaker_threshold: int = field(
        default_factory=lambda: _env_int("MAPS_CIRCUIT_BREAKER_THRESHOLD", 3)
    )
    circuit_breaker_cooldown_seconds: int = field(
        default_factory=lambda: _env_int("MAPS_CIRCUIT_BREAKER_COOLDOWN", 300)
    )


@dataclass
class FSMConfig:
    provider: str = field(default_factory=lambda: _env("FSM_PROVIDER", "generic"))
    base_url: str = field(default_factory=lambda: _env("FSM_BASE_URL"))
    api_key: str = field(default_factory=lambda: _env("FSM_API_KEY"))
    webhook_secret: str = field(default_factory=lambda: _env("FSM_WEBHOOK_SECRET"))
    # If True, reject webhook requests that fail HMAC validation (not just warn)
    require_webhook_secret: bool = field(
        default_factory=lambda: _env_bool("REQUIRE_WEBHOOK_SECRET", False)
    )

    # ServiceTitan specific
    st_client_id: str = field(default_factory=lambda: _env("ST_CLIENT_ID"))
    st_client_secret: str = field(default_factory=lambda: _env("ST_CLIENT_SECRET"))
    st_app_key: str = field(default_factory=lambda: _env("ST_APP_KEY"))
    st_tenant_id: str = field(default_factory=lambda: _env("ST_TENANT_ID"))

    # Jobber specific
    jobber_api_key: str = field(default_factory=lambda: _env("JOBBER_API_KEY"))


@dataclass
class NotificationConfig:
    # Twilio SMS
    twilio_account_sid: str = field(default_factory=lambda: _env("TWILIO_ACCOUNT_SID"))
    twilio_auth_token: str = field(default_factory=lambda: _env("TWILIO_AUTH_TOKEN"))
    twilio_from_number: str = field(default_factory=lambda: _env("TWILIO_FROM_NUMBER"))

    # Email (SMTP or SendGrid)
    smtp_host: str = field(default_factory=lambda: _env("SMTP_HOST", "smtp.gmail.com"))
    smtp_port: int = field(default_factory=lambda: _env_int("SMTP_PORT", 587))
    smtp_user: str = field(default_factory=lambda: _env("SMTP_USER"))
    smtp_password: str = field(default_factory=lambda: _env("SMTP_PASSWORD"))
    email_from: str = field(default_factory=lambda: _env("EMAIL_FROM"))
    email_from_name: str = field(
        default_factory=lambda: _env("EMAIL_FROM_NAME", "Dispatch Team")
    )
    sendgrid_api_key: str = field(default_factory=lambda: _env("SENDGRID_API_KEY"))

    # Webhook
    webhook_url: str = field(default_factory=lambda: _env("NOTIFICATION_WEBHOOK_URL"))
    webhook_secret: str = field(default_factory=lambda: _env("NOTIFICATION_WEBHOOK_SECRET"))

    # Company
    company_name: str = field(default_factory=lambda: _env("COMPANY_NAME", "Field Service Co."))
    company_phone: str = field(default_factory=lambda: _env("COMPANY_PHONE"))
    rating_base_url: str = field(default_factory=lambda: _env("RATING_BASE_URL"))

    rate_limit_seconds: int = field(
        default_factory=lambda: _env_int("NOTIFICATION_RATE_LIMIT", 1800)
    )


@dataclass
class MLConfig:
    # Changed default from /tmp (wiped on Linux restart) to a persistent data dir
    model_path: str = field(
        default_factory=lambda: _env("ML_MODEL_PATH", "ai_dispatch/data/dispatch_model.pkl")
    )
    data_path: str = field(
        default_factory=lambda: _env("ML_DATA_PATH", "ai_dispatch/data/historical_jobs.json")
    )
    min_training_samples: int = field(
        default_factory=lambda: _env_int("ML_MIN_SAMPLES", 50)
    )
    retrain_every_n_completions: int = field(
        default_factory=lambda: _env_int("ML_RETRAIN_INTERVAL", 50)
    )


@dataclass
class AuthConfig:
    """API key authentication. Set API_KEYS to a comma-separated list of valid keys."""
    api_keys: List[str] = field(default_factory=lambda: [
        k.strip() for k in _env("API_KEYS", "").split(",") if k.strip()
    ])


@dataclass
class DatabaseConfig:
    """SQLite (default) or PostgreSQL persistence layer."""
    url: str = field(
        default_factory=lambda: _env(
            "DATABASE_URL", "sqlite+aiosqlite:///./dispatch.db"
        )
    )
    echo: bool = field(default_factory=lambda: _env_bool("DB_ECHO", False))


@dataclass
class AppConfig:
    server: ServerConfig = field(default_factory=ServerConfig)
    engine: EngineConfig = field(default_factory=EngineConfig)
    optimizer: OptimizerConfig = field(default_factory=OptimizerConfig)
    maps: MapsConfig = field(default_factory=MapsConfig)
    fsm: FSMConfig = field(default_factory=FSMConfig)
    notifications: NotificationConfig = field(default_factory=NotificationConfig)
    ml: MLConfig = field(default_factory=MLConfig)
    auth: AuthConfig = field(default_factory=AuthConfig)
    db: DatabaseConfig = field(default_factory=DatabaseConfig)
    debug: bool = field(default_factory=lambda: _env_bool("DEBUG", False))
    environment: str = field(
        default_factory=lambda: _env("ENVIRONMENT", "development")
    )


# Singleton config instance
config = AppConfig()
