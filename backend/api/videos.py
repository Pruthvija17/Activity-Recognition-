"""Video upload, background processing and playback."""
import datetime
import logging
import os
import re
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy import func
from sqlalchemy.orm import Session

import config
import models
from database import get_db
from runtime import ai_pipeline, jobs
from services.jobs import ACTIVE_STATES
from services import media

try:
    import cv2
except Exception:  # pragma: no cover - reported via /api/system/status
    cv2 = None

log = logging.getLogger("bas.videos")

router = APIRouter(prefix="/api/videos", tags=["videos"])

MEDIA_TYPES = {
    ".mp4": "video/mp4",
    ".avi": "video/x-msvideo",
    ".mov": "video/quicktime",
    ".webm": "video/webm",
}
MAX_FILE_SIZE = 500 * 1024 * 1024  # 500 MB
CHUNK_SIZE = 1024 * 1024


def _iso(dt: Optional[datetime.datetime]) -> Optional[str]:
    return dt.isoformat() + "Z" if dt else None


def _safe_filename(filename: str) -> str:
    """Strip directories and unusual characters so a client can't choose where the file lands."""
    base = os.path.basename(filename.replace("\\", "/"))
    stem, ext = os.path.splitext(base)
    stem = re.sub(r"[^A-Za-z0-9._-]+", "_", stem).strip("._") or "video"
    return stem[:80] + ext.lower()


def _probe_video(path: str) -> Optional[dict]:
    """Return basic metadata if OpenCV can decode the file, else None."""
    if cv2 is None:
        return {}
    cap = cv2.VideoCapture(path)
    try:
        if not cap.isOpened():
            return None
        ok, _ = cap.read()
        fps = float(cap.get(cv2.CAP_PROP_FPS) or 0)
        frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
        if not ok or fps <= 0:
            return None
        return {
            "fps": round(fps, 3),
            "frame_count": frames,
            "duration_seconds": round(frames / fps, 3) if frames > 0 else None,
        }
    finally:
        cap.release()


def video_info(exp: models.Experiment, events_count: Optional[int] = None) -> dict:
    return {
        "video_id": exp.id,
        "filename": exp.video_filename or exp.name,
        "status": exp.status,
        "progress": exp.progress or 0.0,
        "message": exp.message,
        "source": exp.source or "upload",
        "file_size": exp.file_size,
        "duration_seconds": exp.duration_seconds,
        "fps": exp.fps,
        "frame_count": exp.frame_count,
        "engine": exp.engine,
        "created_at": _iso(exp.start_time),
        "processed_at": _iso(exp.processed_at),
        "processing_seconds": exp.processing_seconds,
        "events_count": events_count,
        "file_exists": bool(exp.video_path and os.path.exists(exp.video_path)),
        "codec": exp.codec,
        "preview_status": exp.preview_status,
        "playable": exp.preview_status in (None, "not_needed", "ready"),
    }


def _get_experiment(db: Session, video_id: str) -> models.Experiment:
    exp = db.get(models.Experiment, video_id)
    if exp is None:
        raise HTTPException(status_code=404, detail=f"Video '{video_id}' not found.")
    return exp


def _events_count(db: Session, video_id: str) -> int:
    return db.query(models.ActivityEvent).filter(models.ActivityEvent.experiment_id == video_id).count()


@router.post("/upload", status_code=201)
async def upload_video(file: UploadFile = File(...), db: Session = Depends(get_db)):
    if not file.filename:
        raise HTTPException(status_code=400, detail="No file provided.")

    safe_name = _safe_filename(file.filename)
    ext = os.path.splitext(safe_name)[1]
    if ext not in MEDIA_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid file format '{ext or 'none'}'. Only MP4, AVI, MOV and WebM videos are allowed.",
        )

    video_id = f"VID_{uuid.uuid4().hex[:8]}"
    save_path = os.path.join(config.UPLOADS_DIR, f"{video_id}_{safe_name}")

    file_size = 0
    try:
        with open(save_path, "wb") as buffer:
            while chunk := await file.read(CHUNK_SIZE):
                file_size += len(chunk)
                if file_size > MAX_FILE_SIZE:
                    raise HTTPException(status_code=413, detail="File size exceeds the 500 MB limit.")
                buffer.write(chunk)
    except HTTPException:
        os.remove(save_path)
        raise
    except Exception:
        log.exception("Upload failed for %s", file.filename)
        if os.path.exists(save_path):
            os.remove(save_path)
        raise HTTPException(status_code=500, detail="Upload failed while saving the file. Check backend logs.")

    if file_size == 0:
        os.remove(save_path)
        raise HTTPException(status_code=400, detail="The uploaded file is empty.")

    meta = _probe_video(save_path)
    if meta is None:
        os.remove(save_path)
        raise HTTPException(
            status_code=400,
            detail="The file could not be read as a video (corrupt or unsupported encoding).",
        )

    codec = media.probe_codec(save_path)
    if media.browser_playable(save_path, codec):
        preview_status = "not_needed"
    else:
        preview_status = "pending" if media.ffmpeg_available() else "unavailable"

    exp = models.Experiment(
        id=video_id,
        name=file.filename,
        video_filename=file.filename,
        video_path=save_path,
        source="upload",
        status="uploaded",
        file_size=file_size,
        progress=0.0,
        codec=codec,
        preview_status=preview_status,
        **meta,
    )
    db.add(exp)
    db.commit()
    log.info("Uploaded %s as %s (%.1f MB, %s s)", file.filename, video_id, file_size / 1e6, meta.get("duration_seconds"))
    return video_info(exp, events_count=0)


@router.post("/{video_id}/process", status_code=202)
def process_video(video_id: str, db: Session = Depends(get_db)):
    """Queue a video for background processing. Poll GET /api/videos/{id}/status for progress."""
    exp = _get_experiment(db, video_id)
    if exp.status in ACTIVE_STATES:
        raise HTTPException(status_code=409, detail=f"Video is already {exp.status}.")
    if not ai_pipeline.model_ready:
        raise HTTPException(
            status_code=503,
            detail="Required AI model is missing. Check backend/weights/. " + (ai_pipeline.load_error or ""),
        )
    if not exp.video_path or not os.path.exists(exp.video_path):
        raise HTTPException(status_code=410, detail="Video file is missing on the server. Upload it again.")

    exp.status, exp.progress, exp.message = "queued", 0.0, None
    db.commit()
    info = video_info(exp)  # snapshot before the worker starts changing the row
    jobs.enqueue(video_id)
    return info


@router.get("/{video_id}/status")
def video_status(video_id: str, db: Session = Depends(get_db)):
    exp = _get_experiment(db, video_id)
    return video_info(exp, events_count=_events_count(db, video_id))


@router.get("")
@router.get("/", include_in_schema=False)
def list_videos(db: Session = Depends(get_db)):
    counts = dict(
        db.query(models.ActivityEvent.experiment_id, func.count(models.ActivityEvent.id))
        .group_by(models.ActivityEvent.experiment_id)
        .all()
    )
    experiments = db.query(models.Experiment).order_by(models.Experiment.start_time.desc()).all()
    return [video_info(e, events_count=counts.get(e.id, 0)) for e in experiments]


@router.get("/{video_id}")
def serve_video(video_id: str, db: Session = Depends(get_db)):
    """Stream the uploaded video file (supports range requests for seeking)."""
    exp = _get_experiment(db, video_id)
    # Prefer the browser-playable H.264 preview when one was made.
    if exp.preview_status == "ready" and exp.preview_path and os.path.exists(exp.preview_path):
        return FileResponse(path=exp.preview_path, media_type="video/mp4")
    if not exp.video_path or not os.path.exists(exp.video_path):
        raise HTTPException(status_code=404, detail=f"Video file for '{video_id}' is missing on the server.")
    ext = os.path.splitext(exp.video_path)[1].lower()
    return FileResponse(path=exp.video_path, media_type=MEDIA_TYPES.get(ext, "application/octet-stream"))
