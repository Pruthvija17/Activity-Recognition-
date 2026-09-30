"""
BAS Activity Intelligence – FastAPI Backend
Port: 8000
"""
from contextlib import asynccontextmanager
from fastapi import FastAPI, Depends, HTTPException, WebSocket, WebSocketDisconnect, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from typing import List, Optional
import json
import time
import asyncio
import datetime
import logging

import config
config.setup_logging()
log = logging.getLogger("bas.api")

import models
import schemas
from database import engine, get_db, SessionLocal, check_db
from runtime import ai_pipeline, jobs
from services import media
from api import videos as videos_api
from api import analytics as analytics_api
from api import review as review_api
from api import experiments as experiments_api
from api import reports as reports_api

API_VERSION = "2.1.0"

# ── DB Init ───────────────────────────────────────────────────────────────────
models.Base.metadata.create_all(bind=engine)


# ── Startup: apply saved settings to pipeline ─────────────────────────────────
def _apply_saved_settings():
    """Load SystemSettings row and apply thresholds to the running pipeline."""
    db = SessionLocal()
    try:
        settings = db.query(models.SystemSettings).filter(models.SystemSettings.id == 1).first()
        if not settings:
            # Seed default row
            settings = models.SystemSettings(id=1)
            db.add(settings)
            db.commit()
            db.refresh(settings)
        ai_pipeline.update_thresholds(settings.confidence_threshold, settings.unknown_sensitivity)
    except Exception as e:
        log.error("Could not load saved settings: %s", e)
    finally:
        db.close()


def _recover_interrupted_jobs():
    """Experiments left mid-processing by a crash/restart can never finish; mark them failed."""
    db = SessionLocal()
    try:
        stuck = db.query(models.Experiment).filter(
            models.Experiment.status.in_(["processing", "queued"])
        ).all()
        for exp in stuck:
            exp.status = "failed"
            exp.message = "Processing was interrupted by a backend restart. Process the video again."
            log.warning("Experiment %s was interrupted by a restart; marked failed.", exp.id)
        db.commit()
    except Exception as e:
        log.error("Could not recover interrupted jobs: %s", e)
    finally:
        db.close()


@asynccontextmanager
async def lifespan(_app: FastAPI):
    _apply_saved_settings()
    _recover_interrupted_jobs()
    status = ai_pipeline.get_model_status()
    log.info(
        "BAS AI API %s started | database=%s | pose_model=%s | engine=%s",
        API_VERSION, "ok" if check_db() else "ERROR",
        "ready" if status["detector_ready"] else "NOT READY", status["engine"],
    )
    if ai_pipeline.load_error:
        log.error("AI pipeline not ready: %s", ai_pipeline.load_error)
    jobs.start()
    yield
    jobs.stop()


app = FastAPI(title="BAS Activity Intelligence API", version=API_VERSION, lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=config.CORS_ORIGINS,
    # No cookies/auth are used; listing headers explicitly makes preflights answer them
    # (with credentials on, a "*" header wildcard is not echoed and Range requests fail).
    allow_credentials=False,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "Range", "Accept"],
    expose_headers=["Content-Range", "Accept-Ranges", "Content-Length"],
)


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    """Log full details server-side; never leak stack traces to the UI."""
    log.exception("Unhandled error on %s %s", request.method, request.url.path)
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error. Check the backend logs for details."},
    )

# ─────────────────────────────────────────────────────────────────────────────
# Core Endpoints
# ─────────────────────────────────────────────────────────────────────────────

@app.get("/")
def read_root():
    return {"message": "BAS Activity Intelligence API is running", "version": API_VERSION}


@app.get("/health")
def health_check():
    """Liveness probe: answers as long as the API process is serving requests."""
    return {"status": "ok"}


@app.get("/api/system/status")
def system_status():
    """Readiness of every component. A missing component reports false; it never crashes the API."""
    hw = hardware_status()
    model = ai_pipeline.get_model_status()
    return {
        "backend": True,
        "version": API_VERSION,
        "database": check_db(),
        "yolo_model": model["detector_ready"],
        "activity_model": model["classifier_ready"],
        "trained_activity_model": False,
        "activity_engine": model["engine"],
        "model_ready": model["model_ready"],
        "model_error": model["load_error"],
        "missing_packages": sorted(model["import_errors"].keys()),
        "ffmpeg": media.ffmpeg_available(),
        "cuda": hw.cuda_available,
        "device": hw.cuda_device_name or "CPU",
        "timestamp": datetime.datetime.utcnow().isoformat() + "Z",
    }


@app.get("/api/model/status")
def model_status():
    """Return comprehensive diagnostic status of AI pipeline and weight files."""
    return ai_pipeline.get_model_status()


# ─────────────────────────────────────────────────────────────────────────────
# Hardware Status
# ─────────────────────────────────────────────────────────────────────────────

@app.get("/api/model/hardware", response_model=schemas.HardwareStatusResponse)
def hardware_status():
    """Detect and return real hardware acceleration status. No fake GPU info."""
    cuda_available = False
    cuda_device_name = None
    cuda_device_count = 0
    torch_available = False
    opencv_available = False

    try:
        import torch  # type: ignore
        torch_available = True
        cuda_available = torch.cuda.is_available()
        if cuda_available:
            cuda_device_count = torch.cuda.device_count()
            cuda_device_name = torch.cuda.get_device_name(0) if cuda_device_count > 0 else None
    except ImportError:
        pass

    try:
        import cv2  # type: ignore
        opencv_available = True
    except ImportError:
        pass

    return schemas.HardwareStatusResponse(
        cuda_available=cuda_available,
        cuda_device_name=cuda_device_name,
        cuda_device_count=cuda_device_count,
        backend="cuda" if cuda_available else "cpu",
        opencv_available=opencv_available,
        torch_available=torch_available,
    )


# ─────────────────────────────────────────────────────────────────────────────
# System Settings
# ─────────────────────────────────────────────────────────────────────────────

@app.get("/api/settings", response_model=schemas.SystemSettingsResponse)
def get_settings(db: Session = Depends(get_db)):
    """Return current pipeline calibration settings."""
    settings = db.query(models.SystemSettings).filter(models.SystemSettings.id == 1).first()
    if not settings:
        settings = models.SystemSettings(id=1)
        db.add(settings)
        db.commit()
        db.refresh(settings)
    return settings


@app.put("/api/settings", response_model=schemas.SystemSettingsResponse)
def update_settings(body: schemas.SystemSettingsUpdate, db: Session = Depends(get_db)):
    """Persist updated settings and apply thresholds to the running pipeline immediately."""
    settings = db.query(models.SystemSettings).filter(models.SystemSettings.id == 1).first()
    if not settings:
        settings = models.SystemSettings(id=1)
        db.add(settings)

    if not (50 <= body.confidence_threshold <= 95):
        raise HTTPException(status_code=400, detail="confidence_threshold must be between 50 and 95")
    if body.unknown_sensitivity not in ("Low", "Medium", "High"):
        raise HTTPException(status_code=400, detail="unknown_sensitivity must be Low, Medium, or High")

    settings.confidence_threshold = body.confidence_threshold
    settings.unknown_sensitivity = body.unknown_sensitivity
    settings.camera_source = body.camera_source
    settings.updated_at = datetime.datetime.utcnow()
    db.commit()
    db.refresh(settings)

    # Apply to the running pipeline immediately
    ai_pipeline.update_thresholds(settings.confidence_threshold, settings.unknown_sensitivity)

    return settings


# ─────────────────────────────────────────────────────────────────────────────
# Video Upload & Processing  (api/videos.py)
# ─────────────────────────────────────────────────────────────────────────────

app.include_router(videos_api.router)


# ─────────────────────────────────────────────────────────────────────────────
# Activity Events
# ─────────────────────────────────────────────────────────────────────────────

@app.get("/events/", response_model=List[schemas.ActivityEvent])
def read_events(
    skip: int = 0,
    limit: int = 500,
    experiment_id: Optional[str] = None,
    db: Session = Depends(get_db),
):
    query = db.query(models.ActivityEvent)
    if experiment_id:
        query = query.filter(models.ActivityEvent.experiment_id == experiment_id)
    return query.offset(skip).limit(limit).all()


# ─────────────────────────────────────────────────────────────────────────────
# Analytics, Dashboard & Review  (api/analytics.py, api/review.py)
# ─────────────────────────────────────────────────────────────────────────────

app.include_router(analytics_api.router)
app.include_router(review_api.router)


# ─────────────────────────────────────────────────────────────────────────────
# Experiments & Reports  (api/experiments.py, api/reports.py)
# ─────────────────────────────────────────────────────────────────────────────

app.include_router(experiments_api.router)
app.include_router(reports_api.router)


# ─────────────────────────────────────────────────────────────────────────────
# WebSocket – Live Monitor
# ─────────────────────────────────────────────────────────────────────────────

class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

    async def broadcast(self, message: str):
        dead = []
        for connection in self.active_connections:
            try:
                await connection.send_text(message)
            except Exception:
                dead.append(connection)
        for d in dead:
            self.disconnect(d)


manager = ConnectionManager()


@app.websocket("/ws/live")
async def websocket_endpoint(websocket: WebSocket):
    """
    Live monitor WebSocket.
    Sends real system status: backend health, model status, last experiment info.
    Does NOT send fake/simulated activity detections.
    """
    await manager.connect(websocket)
    try:
        while True:
            db = SessionLocal()
            try:
                # Real status data
                last_exp = (
                    db.query(models.Experiment)
                    .order_by(models.Experiment.start_time.desc())
                    .first()
                )
                last_events = []
                if last_exp:
                    events = (
                        db.query(models.ActivityEvent)
                        .filter(models.ActivityEvent.experiment_id == last_exp.id)
                        .order_by(models.ActivityEvent.start_time.desc())
                        .limit(5)
                        .all()
                    )
                    last_events = [
                        {
                            "person_id": e.person_id,
                            "activity": e.activity_type,
                            "confidence": e.confidence,
                            "start_time": e.start_time,
                            "end_time": e.end_time,
                            "status": e.status,
                        }
                        for e in events
                    ]

                status_payload = {
                    "type": "status",
                    "timestamp": time.strftime("%H:%M:%S"),
                    "backend_online": True,
                    "model_ready": ai_pipeline.model_ready,
                    "last_experiment_id": last_exp.id if last_exp else None,
                    "last_experiment_name": last_exp.name if last_exp else None,
                    "last_experiment_status": last_exp.status if last_exp else None,
                    "recent_events": last_events,
                    # No fake detections – real detections would come from a live camera feed
                    "live_detections": [],
                    "note": "Live detections require a real-time camera feed integration.",
                }
            finally:
                db.close()

            await websocket.send_text(json.dumps(status_payload))
            await asyncio.sleep(2.0)
    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception:
        manager.disconnect(websocket)
