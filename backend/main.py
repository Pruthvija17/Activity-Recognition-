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
import uuid
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
from api import videos as videos_api
from api import analytics as analytics_api
from api import review as review_api

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
# Experiments
# ─────────────────────────────────────────────────────────────────────────────

@app.get("/experiments/", response_model=List[schemas.Experiment])
def read_experiments(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    return db.query(models.Experiment).offset(skip).limit(limit).all()


@app.get("/experiments/{experiment_id}", response_model=schemas.Experiment)
def read_experiment(experiment_id: str, db: Session = Depends(get_db)):
    db_experiment = db.query(models.Experiment).filter(models.Experiment.id == experiment_id).first()
    if db_experiment is None:
        raise HTTPException(status_code=404, detail="Experiment not found")
    return db_experiment


@app.get("/experiments/{experiment_id}/events", response_model=List[schemas.ActivityEvent])
def get_experiment_events(experiment_id: str, db: Session = Depends(get_db)):
    """Get all activity events for a specific experiment."""
    events = db.query(models.ActivityEvent).filter(
        models.ActivityEvent.experiment_id == experiment_id
    ).all()
    return events


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
# Sequence Validation
# ─────────────────────────────────────────────────────────────────────────────

DEFAULT_SEQUENCE = [
    "Standing",
    "Walking",
    "Reaching",
    "Picking up an object",
    "Handling experimental equipment",
    "Placing an object",
    "Standing",
]


@app.get("/api/experiments/{experiment_id}/sequence", response_model=schemas.SequenceValidationResult)
def get_sequence_validation(experiment_id: str, db: Session = Depends(get_db)):
    """Validate the observed activity sequence against the expected sequence."""
    exp = db.query(models.Experiment).filter(models.Experiment.id == experiment_id).first()
    if not exp:
        raise HTTPException(status_code=404, detail="Experiment not found")

    # Load expected sequence
    config = db.query(models.ExperimentConfig).filter(
        models.ExperimentConfig.experiment_id == experiment_id
    ).first()
    expected = DEFAULT_SEQUENCE
    if config and config.expected_sequence:
        try:
            expected = json.loads(config.expected_sequence)
        except Exception:
            pass

    # Load observed events ordered by start_seconds then start_time
    events = (
        db.query(models.ActivityEvent)
        .filter(models.ActivityEvent.experiment_id == experiment_id)
        .filter(models.ActivityEvent.status != "Review")
        .order_by(models.ActivityEvent.start_time)
        .all()
    )
    observed = [e.activity_type for e in events]

    deviations = []
    observed_ptr = 0

    for step_idx, expected_step in enumerate(expected):
        # Find the expected step in remaining observed
        found_at = None
        for i in range(observed_ptr, len(observed)):
            if observed[i].lower() == expected_step.lower():
                found_at = i
                break

        if found_at is None:
            deviations.append(schemas.SequenceDeviationDetail(
                step_index=step_idx,
                expected=expected_step,
                observed=None,
                deviation_type="skipped",
            ))
        elif found_at > observed_ptr:
            # Some observed steps were between – mark as out_of_order
            deviations.append(schemas.SequenceDeviationDetail(
                step_index=step_idx,
                expected=expected_step,
                observed=observed[found_at],
                deviation_type="out_of_order",
            ))
            observed_ptr = found_at + 1
        else:
            observed_ptr = found_at + 1

    # Determine next expected step
    completed_steps = set()
    obs_ptr2 = 0
    for step in expected:
        for i in range(obs_ptr2, len(observed)):
            if observed[i].lower() == step.lower():
                completed_steps.add(step)
                obs_ptr2 = i + 1
                break

    next_step = None
    for step in expected:
        if step not in completed_steps:
            next_step = step
            break

    is_compliant = len(deviations) == 0
    message = (
        "Sequence Deviation Detected – Operator Review Required."
        if not is_compliant
        else "Experiment sequence is compliant."
    )

    return schemas.SequenceValidationResult(
        experiment_id=experiment_id,
        is_compliant=is_compliant,
        deviation_count=len(deviations),
        deviations=deviations,
        observed_sequence=observed,
        expected_sequence=expected,
        next_expected_step=next_step,
        message=message,
    )


@app.post("/api/experiments/{experiment_id}/sequence")
def set_sequence_config(
    experiment_id: str,
    body: schemas.SequenceConfigRequest,
    db: Session = Depends(get_db),
):
    """Set or update the expected activity sequence for an experiment."""
    exp = db.query(models.Experiment).filter(models.Experiment.id == experiment_id).first()
    if not exp:
        raise HTTPException(status_code=404, detail="Experiment not found")

    config = db.query(models.ExperimentConfig).filter(
        models.ExperimentConfig.experiment_id == experiment_id
    ).first()

    if config:
        config.expected_sequence = json.dumps(body.expected_sequence)
        config.updated_at = datetime.datetime.utcnow()
    else:
        config = models.ExperimentConfig(
            id=str(uuid.uuid4()),
            experiment_id=experiment_id,
            expected_sequence=json.dumps(body.expected_sequence),
        )
        db.add(config)

    db.commit()
    return {"status": "ok", "expected_sequence": body.expected_sequence}


# ─────────────────────────────────────────────────────────────────────────────
# Analytics, Dashboard & Review  (api/analytics.py, api/review.py)
# ─────────────────────────────────────────────────────────────────────────────

app.include_router(analytics_api.router)
app.include_router(review_api.router)


# ─────────────────────────────────────────────────────────────────────────────
# Reports
# ─────────────────────────────────────────────────────────────────────────────

@app.get("/api/reports")
def get_reports(db: Session = Depends(get_db)):
    """Return report data for all experiments using real DB data."""
    experiments = db.query(models.Experiment).all()
    reports = []
    for exp in experiments:
        events = db.query(models.ActivityEvent).filter(
            models.ActivityEvent.experiment_id == exp.id
        ).all()
        if not events:
            continue

        total = len(events)
        confirmed = sum(1 for e in events if e.status == "Confirmed")
        unknown = sum(1 for e in events if e.activity_type == "Unknown" or e.status == "Review")
        confidences = [e.confidence for e in events if e.confidence is not None]
        avg_conf = round(sum(confidences) / len(confidences) * 100, 1) if confidences else 0.0

        # Sequence deviation count
        config = db.query(models.ExperimentConfig).filter(
            models.ExperimentConfig.experiment_id == exp.id
        ).first()
        expected = DEFAULT_SEQUENCE
        if config and config.expected_sequence:
            try:
                expected = json.loads(config.expected_sequence)
            except Exception:
                pass

        observed = [e.activity_type for e in events if e.status != "Review"]
        observed_lower = [o.lower() for o in observed]
        deviations = sum(
            1 for step in expected if step.lower() not in observed_lower
        )

        reports.append({
            "id": f"REP-{exp.id}",
            "experiment_id": exp.id,
            "experiment": exp.name,
            "date": exp.start_time.strftime("%Y-%m-%d") if exp.start_time else "",
            "events_count": total,
            "confirmed_count": confirmed,
            "unknown_count": unknown,
            "deviations": deviations,
            "avg_confidence_pct": avg_conf,
            "status": exp.status,
        })
    return reports


@app.get("/api/reports/{experiment_id}/csv")
def get_report_csv(experiment_id: str, db: Session = Depends(get_db)):
    """Return CSV-compatible event data for an experiment."""
    exp = db.query(models.Experiment).filter(models.Experiment.id == experiment_id).first()
    if not exp:
        raise HTTPException(status_code=404, detail="Experiment not found")

    events = db.query(models.ActivityEvent).filter(
        models.ActivityEvent.experiment_id == experiment_id
    ).all()

    rows = [["Report_ID", "Experiment", "Person_ID", "Activity", "Start_Time", "End_Time", "Duration", "Confidence", "Status"]]
    for e in events:
        rows.append([
            f"REP-{experiment_id}",
            exp.name,
            e.person_id,
            e.activity_type,
            e.start_time,
            e.end_time,
            str(round(e.duration, 2)),
            f"{round(e.confidence * 100, 1)}%",
            e.status,
        ])

    return {"experiment_id": experiment_id, "rows": rows}


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
