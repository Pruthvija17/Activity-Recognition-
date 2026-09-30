"""
BAS Activity Intelligence – FastAPI Backend
Port: 8000
"""
from contextlib import asynccontextmanager
from fastapi import FastAPI, Depends, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
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
from api import live as live_api
from api import training as training_api
from config import utcnow

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
            models.Experiment.status.in_(["processing", "queued", "live"])
        ).all()
        for exp in stuck:
            exp.message = (
                "Live session was interrupted by a backend restart; its events were not saved."
                if exp.status == "live" else
                "Processing was interrupted by a backend restart. Process the video again."
            )
            exp.status = "failed"
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
    jobs.backfill_playback()
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
        "trained_activity_model": model["trained_model"],
        "activity_model_error": model["activity_model_error"],
        "activity_model_info": model["activity_model_info"],
        "activity_engine": model["engine"],
        "model_ready": model["model_ready"],
        "model_error": model["load_error"],
        "missing_packages": sorted(model["import_errors"].keys()),
        "ffmpeg": media.ffmpeg_available(),
        "cuda": hw.cuda_available,
        "device": hw.cuda_device_name or "CPU",
        "timestamp": utcnow().isoformat() + "Z",
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
    settings.updated_at = utcnow()
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
# Live camera monitoring  (api/live.py)
# ─────────────────────────────────────────────────────────────────────────────

app.include_router(live_api.router)
app.include_router(training_api.router)
