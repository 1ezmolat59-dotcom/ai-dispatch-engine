"""
FastAPI application factory.
Wires up all routes, WebSocket board streaming, and the dispatch engine lifecycle.
"""

from __future__ import annotations
import asyncio
import json
import logging
import uuid
from contextlib import asynccontextmanager
from typing import Optional, Set

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from ..core.dispatch_engine import DispatchEngine
from ..integrations.maps_service import MapsService
from ..integrations.fsm_adapter import GenericFSMAdapter, ServiceTitanAdapter
from ..integrations.notification_service import NotificationService
from .routes import jobs as jobs_routes, technicians as tech_routes, dispatch as dispatch_routes, webhooks as webhook_routes
from .routes import demo as demo_routes
from .routes.jobs import set_engine

logger = logging.getLogger(__name__)


# ─── WebSocket Connection Manager ────────────────────────────────────────────

class BoardConnectionManager:
    """Manages all active WebSocket connections to the dispatch board."""

    def __init__(self):
        self.active: Set[WebSocket] = set()

    async def connect(self, ws: WebSocket):
        await ws.accept()
        self.active.add(ws)
        logger.info(f"WebSocket client connected. Total: {len(self.active)}")

    def disconnect(self, ws: WebSocket):
        self.active.discard(ws)
        logger.info(f"WebSocket client disconnected. Remaining: {len(self.active)}")

    async def broadcast(self, message: str):
        dead = set()
        for ws in self.active:
            try:
                await ws.send_text(message)
            except Exception:
                dead.add(ws)
        for ws in dead:
            self.active.discard(ws)


manager = BoardConnectionManager()


# ─── App Factory ─────────────────────────────────────────────────────────────

def create_app(
    maps_service: Optional[MapsService] = None,
    fsm_adapter: Optional[GenericFSMAdapter] = None,
    notification_service: Optional[NotificationService] = None,
    optimization_interval: int = 30,
    api_title: str = "AI Dispatch Engine",
    api_version: str = "1.0.0",
    cors_origins: Optional[list] = None,
    ml_config=None,
    optimizer_config=None,
    auth_config=None,
    db_config=None,
) -> FastAPI:
    """
    Create and configure the FastAPI application.

    Args:
        maps_service: Configured MapsService instance (Google + Apple Maps).
        fsm_adapter: Configured FSM adapter (ServiceTitan, Jobber, etc.).
        notification_service: Configured NotificationService (Twilio + Email).
        optimization_interval: Seconds between optimization cycles.
        api_title: OpenAPI title.
        api_version: API version string.
        cors_origins: Allowed CORS origins (default: all).
        ml_config: MLConfig with model/data paths.
        optimizer_config: OptimizerConfig with scoring weights.
        auth_config: AuthConfig with API keys for request authentication.
        db_config: DatabaseConfig (reserved for Phase 3 persistence).
    """

    # ─── Engine initialization ────────────────────────────────────────────────
    engine = DispatchEngine(
        maps_service=maps_service,
        fsm_adapter=fsm_adapter,
        notification_service=notification_service,
        optimization_interval_seconds=optimization_interval,
        ml_config=ml_config,
        optimizer_config=optimizer_config,
    )

    # Register board update callback → WebSocket broadcast
    async def _on_board_update(snapshot):
        if manager.active:
            await manager.broadcast(json.dumps(snapshot.to_dict()))

    engine.on_board_update(_on_board_update)

    # ─── App lifespan ─────────────────────────────────────────────────────────
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        logger.info("Starting AI Dispatch Engine...")
        await engine.start()
        yield
        logger.info("Shutting down AI Dispatch Engine...")
        await engine.stop()

    # ─── FastAPI app ──────────────────────────────────────────────────────────
    app = FastAPI(
        title=api_title,
        version=api_version,
        description=(
            "AI-powered dispatch optimization engine for HVAC/Plumbing/Electrical. "
            "Auto-assigns nearest qualified technicians, predicts job duration with ML, "
            "and sends automated ETAs to customers. Integrates with Google Maps, "
            "Apple Maps, and any FSM via REST API."
        ),
        lifespan=lifespan,
        docs_url="/docs",
        redoc_url="/redoc",
    )

    # CORS
    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins or ["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # API Key authentication middleware (Phase 2)
    # Skips auth for health, docs, OpenAPI schema, and WebSocket endpoints.
    if auth_config and auth_config.api_keys:
        from .middleware.auth import APIKeyMiddleware
        app.add_middleware(APIKeyMiddleware, valid_keys=set(auth_config.api_keys))
        logger.info("API key authentication enabled (%d key(s) configured)", len(auth_config.api_keys))

    # Inject engine into route modules
    set_engine(engine)

    # ─── Routers ──────────────────────────────────────────────────────────────
    app.include_router(jobs_routes.router, prefix="/api/v1")
    app.include_router(tech_routes.router, prefix="/api/v1")
    app.include_router(dispatch_routes.router, prefix="/api/v1")
    app.include_router(webhook_routes.router, prefix="/api/v1")
    app.include_router(demo_routes.router, prefix="/api/v1")

    # ─── WebSocket endpoint ───────────────────────────────────────────────────
    @app.websocket("/ws/board")
    async def board_stream(websocket: WebSocket):
        """
        Real-time dispatch board WebSocket stream.
        Connect here from your dashboard UI to get live board updates.
        Broadcasts a DispatchBoardSnapshot every time state changes.
        """
        await manager.connect(websocket)
        try:
            # Send current state immediately on connect
            snapshot = engine.get_board_snapshot()
            await websocket.send_text(json.dumps(snapshot.to_dict()))

            # Keep alive and handle client pings
            while True:
                data = await asyncio.wait_for(websocket.receive_text(), timeout=60)
                if data == "ping":
                    await websocket.send_text("pong")
        except (WebSocketDisconnect, asyncio.TimeoutError):
            manager.disconnect(websocket)
        except Exception as e:
            logger.error(f"WebSocket error: {e}")
            manager.disconnect(websocket)

    # ─── Health & root ────────────────────────────────────────────────────────
    @app.get("/", include_in_schema=False)
    async def root():
        return {
            "name": "AI Dispatch Engine",
            "version": api_version,
            "status": "running" if engine._running else "stopped",
            "docs": "/docs",
            "websocket": "/ws/board",
        }

    @app.get("/health", tags=["system"])
    async def health():
        return {
            "status": "healthy",
            "engine_running": engine._running,
            "active_jobs": len(engine._jobs),
            "active_techs": len(engine._technicians),
            "ws_connections": len(manager.active),
            "ml_trained": engine.predictor.is_trained,
        }

    @app.exception_handler(Exception)
    async def global_exception_handler(request, exc):
        logger.error(f"Unhandled exception: {exc}", exc_info=True)
        return JSONResponse(status_code=500, content={"error": "Internal server error"})

    return app
