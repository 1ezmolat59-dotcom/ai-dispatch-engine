"""
AI Dispatch Engine — Entry Point

Bootstraps:
  1. Configuration from environment / .env
  2. Services: Maps, FSM Adapter, Notifications
  3. ML model (trains if needed)
  4. Dispatch Engine (starts optimization loop)
  5. FastAPI server

Usage:
    python main.py
    # or with uvicorn directly:
    uvicorn main:app --host 0.0.0.0 --port 8000 --reload
"""

from __future__ import annotations
import logging
import os
import sys

# ─── Logging setup ────────────────────────────────────────────────────────────
logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


def _load_dotenv():
    """Load .env file if present (optional — python-dotenv not required)."""
    env_path = os.path.join(os.path.dirname(__file__), ".env")
    if os.path.exists(env_path):
        with open(env_path) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, _, value = line.partition("=")
                    os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))
        logger.info(f"Loaded .env from {env_path}")


_load_dotenv()

# ─── Import after env load ────────────────────────────────────────────────────
from ai_dispatch.config import config
from ai_dispatch.integrations.maps_service import MapsService
from ai_dispatch.integrations.notification_service import NotificationService
from ai_dispatch.api.server import create_app


def _build_fsm_adapter():
    """Build the appropriate FSM adapter based on FSM_PROVIDER env var."""
    provider = config.fsm.provider.lower()
    if provider == "servicetitan":
        from ai_dispatch.integrations.fsm_adapter import ServiceTitanAdapter
        logger.info("Using ServiceTitan FSM adapter")
        return ServiceTitanAdapter()
    elif provider == "jobber":
        from ai_dispatch.integrations.fsm_adapter import JobberAdapter
        logger.info("Using Jobber FSM adapter")
        return JobberAdapter()
    elif provider == "generic" and config.fsm.base_url:
        from ai_dispatch.integrations.fsm_adapter import GenericFSMAdapter
        logger.info(f"Using Generic FSM adapter → {config.fsm.base_url}")
        return GenericFSMAdapter(
            base_url=config.fsm.base_url,
            api_key=config.fsm.api_key,
            webhook_secret=config.fsm.webhook_secret,
        )
    else:
        logger.info("No FSM adapter configured (standalone mode)")
        return None


def _maybe_seed_data():
    """Generate seed historical data if the data file doesn't exist yet."""
    data_path = config.ml.data_path
    if not os.path.exists(data_path):
        logger.info("No historical data found. Generating seed data for ML training...")
        try:
            from ai_dispatch.data.seed_data import generate_historical_records
            import json
            # Bug fix: os.path.dirname("bare_filename") returns "" which causes
            # os.makedirs("") to raise FileNotFoundError. Always resolve absolute first.
            parent_dir = os.path.dirname(os.path.abspath(data_path))
            if parent_dir:
                os.makedirs(parent_dir, exist_ok=True)
            records = generate_historical_records(500)
            with open(data_path, "w") as f:
                json.dump(records, f)
            logger.info(f"Generated {len(records)} seed records → {data_path}")
        except Exception as e:
            logger.warning(f"Seed data generation failed: {e}")


def _startup_checks():
    """Emit warnings for known mis-configurations at startup."""
    # Multi-worker split-state warning
    if config.server.workers > 1 and not config.server.reload:
        logger.warning(
            "⚠️  SERVER_WORKERS=%d with in-memory state — each worker process "
            "will have an independent copy of jobs/technicians. Data will be "
            "inconsistent across requests. Set SERVER_WORKERS=1 or enable "
            "DATABASE_URL persistence (Phase 3).",
            config.server.workers,
        )

    # API auth warning
    if not config.auth.api_keys:
        logger.warning(
            "⚠️  API_KEYS not set — all API endpoints are publicly accessible. "
            "Set API_KEYS=your-secret-key to enable authentication."
        )

    # Webhook secret warning
    if not config.fsm.webhook_secret:
        logger.warning(
            "⚠️  FSM_WEBHOOK_SECRET not set — webhook endpoints accept requests "
            "without HMAC validation. Set FSM_WEBHOOK_SECRET to secure them."
        )

    # Validate optimizer weights
    config.optimizer.validate()


# ─── Generate seed data + startup checks ─────────────────────────────────────
_maybe_seed_data()
_startup_checks()

maps_service = MapsService(
    google_api_key=config.maps.google_api_key,
    apple_maps_team_id=config.maps.apple_team_id,
    apple_maps_key_id=config.maps.apple_key_id,
    traffic_model=config.maps.traffic_model,
)

fsm_adapter = _build_fsm_adapter()

notification_service = NotificationService(
    twilio_account_sid=config.notifications.twilio_account_sid,
    twilio_auth_token=config.notifications.twilio_auth_token,
    twilio_from_number=config.notifications.twilio_from_number,
    smtp_host=config.notifications.smtp_host,
    smtp_port=config.notifications.smtp_port,
    smtp_user=config.notifications.smtp_user,
    smtp_password=config.notifications.smtp_password,
    email_from=config.notifications.email_from,
    email_from_name=config.notifications.email_from_name,
    sendgrid_api_key=config.notifications.sendgrid_api_key,
    company_name=config.notifications.company_name,
    company_phone=config.notifications.company_phone,
    rating_base_url=config.notifications.rating_base_url,
    webhook_url=config.notifications.webhook_url,
)

# Create the FastAPI app (used by uvicorn when referenced as main:app)
app = create_app(
    maps_service=maps_service,
    fsm_adapter=fsm_adapter,
    notification_service=notification_service,
    optimization_interval=config.engine.optimization_interval_seconds,
    cors_origins=config.server.cors_origins,
    ml_config=config.ml,
    optimizer_config=config.optimizer,
    auth_config=config.auth,
    db_config=config.db,
)


# ─── Direct execution ─────────────────────────────────────────────────────────
if __name__ == "__main__":
    try:
        import uvicorn
    except ImportError:
        logger.error("uvicorn not installed. Run: pip install uvicorn")
        sys.exit(1)

    logger.info(
        f"\n{'='*60}\n"
        f"  AI Dispatch Engine v1.0.0\n"
        f"  http://{config.server.host}:{config.server.port}\n"
        f"  Docs: http://{config.server.host}:{config.server.port}/docs\n"
        f"  WebSocket: ws://{config.server.host}:{config.server.port}/ws/board\n"
        f"  FSM: {config.fsm.provider or 'none'}\n"
        f"  Maps: {'configured' if config.maps.google_api_key else 'haversine fallback'}\n"
        f"  SMS: {'configured' if config.notifications.twilio_account_sid else 'disabled'}\n"
        f"  Auth: {'enabled' if config.auth.api_keys else 'DISABLED (no API_KEYS set)'}\n"
        f"  DB: {config.db.url.split('///')[0]}\n"
        f"{'='*60}"
    )

    uvicorn.run(
        "main:app",
        host=config.server.host,
        port=config.server.port,
        reload=config.server.reload,
        log_level=config.server.log_level.lower(),
        workers=config.server.workers if not config.server.reload else 1,
    )
