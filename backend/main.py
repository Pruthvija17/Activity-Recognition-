"""
BAS Activity Intelligence – FastAPI Backend
Port: 8000
"""
from contextlib import asynccontextmanager
from fastapi import FastAPI, Depends, HTTPException, WebSocket, WebSocketDisconnect, File, UploadFile, Body, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from sqlalchemy.orm import Session
from typing import List, Optional
import json
import shutil
import os
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
import pipeline

API_VERSION = "2.1.0"

# ── DB Init ───────────────────────────────────────────────────────────────────
models.Base.metadata.create_all(bind=engine)

# ── Pipeline (models are loaded once, here) ───────────────────────────────────
ai_pipeline = pipeline.AIVideoPipeline()

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
    yield


app = FastAPI(title="BAS Activity Intelligence API", version=API_VERSION, lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=config.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    """Log full details server-side; never leak stack traces to the UI."""
    log.exception("Unhandled error on %s %s", request.method, request.url.path)
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error. Check the backend logs for details."},
    )

# In-memory index of uploaded videos for quick lookup within a session
uploaded_videos: dict = {}

ALLOWED_EXTENSIONS = {".mp4", ".avi", ".mov"}
MAX_FILE_SIZE = 500 * 1024 * 1024  # 500 MB

UPLOADS_DIR = config.UPLOADS_DIR

# Activity colours for analytics charts
ACTIVITY_COLORS = {
    "Standing": "#0F4C81",
    "Sitting": "#16A34A",
    "Walking": "#38BDF8",
    "Reaching": "#F59E0B",
    "Picking up an object": "#8B5CF6",
    "Placing an object": "#EC4899",
    "Handling experimental equipment": "#14B8A6",
    "Unknown": "#EF4444",
}


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _hms_to_seconds(hms: str) -> float:
    """Convert HH:MM:SS or MM:SS string to total seconds."""
    try:
        parts = hms.strip().split(":")
        if len(parts) == 3:
            return int(parts[0]) * 3600 + int(parts[1]) * 60 + float(parts[2])
        if len(parts) == 2:
            return int(parts[0]) * 60 + float(parts[1])
        return float(parts[0])
    except Exception:
        return 0.0


def _find_video_path(video_id: str) -> Optional[str]:
    """Find the video file path by video_id prefix."""
    if video_id in uploaded_videos:
        return uploaded_videos[video_id].get("file_path")
    if os.path.exists(UPLOADS_DIR):
        for f in os.listdir(UPLOADS_DIR):
            if f.startswith(video_id):
                return os.path.join(UPLOADS_DIR, f)
    return None


def _ensure_participant(db: Session, experiment_id: str, person_id_label: str) -> models.Participant:
    """Get or create a Participant record."""
    participant_id = f"{experiment_id}_{person_id_label.replace(' ', '_')}"
    participant = db.query(models.Participant).filter(
        models.Participant.id == participant_id
    ).first()
    if not participant:
        participant = models.Participant(
            id=participant_id,
            experiment_id=experiment_id,
            tracked_id=person_id_label,
        )
        db.add(participant)
        db.commit()
        db.refresh(participant)
    return participant


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
# Video Upload & Processing
# ─────────────────────────────────────────────────────────────────────────────

@app.post("/api/videos/upload")
async def upload_video_file(file: UploadFile = File(...), db: Session = Depends(get_db)):
    if not file.filename:
        raise HTTPException(status_code=400, detail="No file provided or empty filename.")

    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid file format '{ext}'. Only MP4, AVI, and MOV files are allowed.",
        )

    video_id = f"VID_{uuid.uuid4().hex[:8]}"
    save_filename = f"{video_id}_{file.filename}"
    save_path = os.path.join(UPLOADS_DIR, save_filename)

    file_size = 0
    try:
        with open(save_path, "wb") as buffer:
            while chunk := await file.read(1024 * 1024):
                file_size += len(chunk)
                if file_size > MAX_FILE_SIZE:
                    buffer.close()
                    if os.path.exists(save_path):
                        os.remove(save_path)
                    raise HTTPException(status_code=400, detail="File size exceeds the 500 MB limit.")
                buffer.write(chunk)
    except HTTPException:
        raise
    except Exception as e:
        log.exception("Upload failed for %s", file.filename)
        if os.path.exists(save_path):
            os.remove(save_path)
        raise HTTPException(status_code=500, detail=f"Upload failed: {str(e)}")

    # Persist experiment record
    db_experiment = models.Experiment(
        id=video_id,
        name=file.filename,
        video_filename=file.filename,
        video_path=save_path,
    )
    db.add(db_experiment)
    db.commit()

    log.info("Uploaded %s as %s (%.1f MB)", file.filename, video_id, file_size / 1e6)
    uploaded_videos[video_id] = {
        "video_id": video_id,
        "filename": file.filename,
        "file_size": file_size,
        "file_path": save_path,
        "status": "uploaded",
    }

    return {
        "video_id": video_id,
        "filename": file.filename,
        "file_size": file_size,
        "status": "uploaded",
    }


@app.post("/api/videos/process/{video_id}")
async def process_video_by_id(video_id: str, db: Session = Depends(get_db)):
    file_path = _find_video_path(video_id)
    if not file_path or not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail=f"Video ID '{video_id}' not found.")

    # Update experiment status
    db_experiment = db.query(models.Experiment).filter(models.Experiment.id == video_id).first()
    if not db_experiment:
        raise HTTPException(status_code=404, detail="Experiment record not found.")
    db_experiment.status = "processing"
    db.commit()

    # Run pipeline
    log.info("Processing started: %s", video_id)
    t0 = time.time()
    result = ai_pipeline.process_video(file_path)
    log.info("Processing finished: %s in %.1fs — %s", video_id, time.time() - t0, result.get("message", ""))
    model_ready = result.get("model_ready", False)
    message = result.get("message", "")

    if not model_ready:
        db_experiment.status = "failed"
        db.commit()
        raise HTTPException(
            status_code=400,
            detail=f"AI Model Weights Missing: {message}",
        )

    raw_events = result.get("events", [])
    metadata = result.get("metadata", {})

    saved_events = []
    for evt in raw_events:
        participant = _ensure_participant(db, video_id, evt.get("person_id", "Person 01"))
        start_hms = evt.get("start", "00:00:00")
        end_hms = evt.get("end", "00:00:05")
        start_sec = evt.get("start_seconds", _hms_to_seconds(start_hms))
        end_sec = evt.get("end_seconds", _hms_to_seconds(end_hms))
        duration = round(end_sec - start_sec, 2)
        confidence = float(evt.get("confidence", 0.0))
        activity = evt.get("activity", "Unknown")
        status = "Review" if activity.lower() in ("unknown", "unexpected") or confidence < 0.6 else "Confirmed"

        event_id = str(uuid.uuid4())
        db_event = models.ActivityEvent(
            id=event_id,
            experiment_id=video_id,
            person_id=participant.id,
            video_id=video_id,
            activity_type=activity,
            start_time=start_hms,
            end_time=end_hms,
            start_seconds=start_sec,
            end_seconds=end_sec,
            duration=duration,
            confidence=confidence,
            status=status,
            frame_number=evt.get("frame_start"),
        )
        db.add(db_event)
        saved_events.append({
            "person_id": evt.get("person_id"),
            "activity": activity,
            "confidence": confidence,
            "start": start_hms,
            "end": end_hms,
            "duration": duration,
            "status": status,
        })

    db_experiment.status = "processed"
    db.commit()

    return {
        "video_id": video_id,
        "status": "processed",
        "model_ready": True,
        "events_count": len(saved_events),
        "results": saved_events,
        "metadata": metadata,
        "message": message,
    }


@app.get("/api/videos/")
def list_videos(db: Session = Depends(get_db)):
    """List all uploaded videos / experiments."""
    experiments = db.query(models.Experiment).all()
    result = []
    for exp in experiments:
        file_path = exp.video_path or _find_video_path(exp.id)
        result.append({
            "video_id": exp.id,
            "filename": exp.video_filename or exp.name,
            "status": exp.status,
            "start_time": exp.start_time.isoformat() if exp.start_time else None,
            "file_exists": os.path.exists(file_path) if file_path else False,
        })
    return result


@app.get("/api/videos/{video_id}")
def serve_video(video_id: str, db: Session = Depends(get_db)):
    """Serve the actual uploaded video file for playback."""
    file_path = _find_video_path(video_id)
    if not file_path or not os.path.exists(file_path):
        # Try looking up via DB
        exp = db.query(models.Experiment).filter(models.Experiment.id == video_id).first()
        if exp and exp.video_path and os.path.exists(exp.video_path):
            file_path = exp.video_path
        else:
            raise HTTPException(status_code=404, detail=f"Video file for ID '{video_id}' not found.")

    filename = os.path.basename(file_path)
    ext = os.path.splitext(filename)[1].lower()
    media_types = {".mp4": "video/mp4", ".avi": "video/x-msvideo", ".mov": "video/quicktime"}
    media_type = media_types.get(ext, "video/mp4")

    return FileResponse(
        path=file_path,
        media_type=media_type,
        filename=filename,
        headers={"Accept-Ranges": "bytes"},
    )


# Legacy upload endpoint (keeps backward compat)
@app.post("/api/upload/")
async def upload_video_legacy(file: UploadFile = File(...), db: Session = Depends(get_db)):
    res = await upload_video_file(file, db)
    return {"experiment_id": res["video_id"], "message": "Video uploaded. Use /api/videos/process/{video_id} to process."}


# ─────────────────────────────────────────────────────────────────────────────
# Experiments
# ─────────────────────────────────────────────────────────────────────────────

@app.post("/experiments/", response_model=schemas.Experiment)
def create_experiment(experiment: schemas.ExperimentCreate, db: Session = Depends(get_db)):
    db_experiment = models.Experiment(**experiment.model_dump())
    db.add(db_experiment)
    db.commit()
    db.refresh(db_experiment)
    return db_experiment


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

@app.post("/events/", response_model=schemas.ActivityEvent)
def create_event(event: schemas.ActivityEventCreate, db: Session = Depends(get_db)):
    db_event = models.ActivityEvent(**event.model_dump())
    db.add(db_event)
    db.commit()
    db.refresh(db_event)
    return db_event


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


@app.put("/events/{event_id}", response_model=schemas.ActivityEvent)
def update_event(
    event_id: str,
    activity_type: Optional[str] = None,
    body: Optional[schemas.EventUpdateRequest] = Body(default=None),
    db: Session = Depends(get_db),
):
    """Update event classification. Accepts query param or JSON body."""
    db_event = db.query(models.ActivityEvent).filter(models.ActivityEvent.id == event_id).first()
    if not db_event:
        raise HTTPException(status_code=404, detail="Event not found")

    # Prefer body over query param
    new_activity = (body.activity_type if body else None) or activity_type
    if not new_activity:
        raise HTTPException(status_code=400, detail="activity_type is required")

    db_event.activity_type = new_activity
    db_event.status = "Confirmed" if new_activity.lower() != "unknown" else "Review"
    db.commit()
    db.refresh(db_event)
    return db_event


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
# Analytics
# ─────────────────────────────────────────────────────────────────────────────

def _compute_analytics(events: list, experiment_id: Optional[str] = None) -> dict:
    """Compute analytics stats from a list of ActivityEvent ORM objects."""
    if not events:
        return {
            "experiment_id": experiment_id,
            "total_events": 0,
            "confirmed_events": 0,
            "unknown_events": 0,
            "sequence_deviations": 0,
            "avg_confidence": 0.0,
            "experiment_duration_seconds": 0.0,
            "activity_distribution": [],
            "person_stats": [],
            "model_ready": ai_pipeline.model_ready,
        }

    total = len(events)
    confirmed = sum(1 for e in events if e.status == "Confirmed")
    unknown = sum(1 for e in events if e.activity_type == "Unknown" or e.status == "Review")
    confidences = [e.confidence for e in events if e.confidence is not None]
    avg_conf = round(sum(confidences) / len(confidences), 4) if confidences else 0.0

    # Duration: max end_seconds – min start_seconds
    start_times = [e.start_seconds for e in events if e.start_seconds is not None]
    end_times = [e.end_seconds for e in events if e.end_seconds is not None]
    if not start_times:
        start_times = [_hms_to_seconds(e.start_time) for e in events]
        end_times = [_hms_to_seconds(e.end_time) for e in events]
    exp_duration = round((max(end_times) - min(start_times)), 2) if end_times and start_times else 0.0

    # Activity distribution
    activity_counts: dict = {}
    for e in events:
        act = e.activity_type
        activity_counts[act] = activity_counts.get(act, 0) + 1

    distribution = [
        {
            "name": act,
            "value": count,
            "color": ACTIVITY_COLORS.get(act, "#94A3B8"),
        }
        for act, count in sorted(activity_counts.items(), key=lambda x: -x[1])
    ]

    # Per-person stats
    person_map: dict = {}
    for e in events:
        pid = e.person_id
        if pid not in person_map:
            person_map[pid] = {"activities": 0, "unknowns": 0, "confidences": []}
        person_map[pid]["activities"] += 1
        if e.activity_type == "Unknown":
            person_map[pid]["unknowns"] += 1
        if e.confidence is not None:
            person_map[pid]["confidences"].append(e.confidence)

    person_stats = [
        {
            "name": pid,
            "activities": v["activities"],
            "unknowns": v["unknowns"],
            "avg_confidence": round(
                sum(v["confidences"]) / len(v["confidences"]), 4
            ) if v["confidences"] else 0.0,
        }
        for pid, v in person_map.items()
    ]

    return {
        "experiment_id": experiment_id,
        "total_events": total,
        "confirmed_events": confirmed,
        "unknown_events": unknown,
        "sequence_deviations": 0,  # Populated separately via sequence endpoint
        "avg_confidence": avg_conf,
        "experiment_duration_seconds": exp_duration,
        "activity_distribution": distribution,
        "person_stats": person_stats,
        "model_ready": ai_pipeline.model_ready,
    }


@app.get("/api/analytics")
def get_analytics(db: Session = Depends(get_db)):
    """Aggregate analytics across all experiments."""
    events = db.query(models.ActivityEvent).all()
    return _compute_analytics(events)


@app.get("/api/analytics/{experiment_id}")
def get_experiment_analytics(experiment_id: str, db: Session = Depends(get_db)):
    """Per-experiment analytics."""
    exp = db.query(models.Experiment).filter(models.Experiment.id == experiment_id).first()
    if not exp:
        raise HTTPException(status_code=404, detail="Experiment not found")
    events = db.query(models.ActivityEvent).filter(
        models.ActivityEvent.experiment_id == experiment_id
    ).all()
    return _compute_analytics(events, experiment_id=experiment_id)


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
