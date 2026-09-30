"""Background video-processing jobs.

A single worker thread processes one video at a time (inference is CPU-bound, so running
jobs in parallel would only slow each one down). State lives in the database so the UI can
poll it and so it survives page reloads; a backend restart marks unfinished jobs as failed.
"""
import logging
import os
import queue
import threading
import time
import uuid
from typing import Optional

import models
from database import SessionLocal
from services import media
from config import utcnow

log = logging.getLogger("bas.jobs")

ACTIVE_STATES = ("queued", "processing")
PROGRESS_WRITE_INTERVAL = 1.0  # seconds between progress writes to the DB


def _ensure_participant(db, experiment_id: str, person_label: str) -> models.Participant:
    participant_id = f"{experiment_id}_{person_label.replace(' ', '_')}"
    participant = db.get(models.Participant, participant_id)
    if not participant:
        participant = models.Participant(id=participant_id, experiment_id=experiment_id, tracked_id=person_label)
        db.add(participant)
        db.flush()
    return participant


def _clear_results(db, experiment_id: str) -> None:
    """Re-processing replaces the previous results of the same experiment."""
    db.query(models.ActivityEvent).filter(models.ActivityEvent.experiment_id == experiment_id).delete()
    db.query(models.Participant).filter(models.Participant.experiment_id == experiment_id).delete()


def save_events(db, experiment_id: str, events: list, confidence_threshold: float) -> int:
    for evt in events:
        participant = _ensure_participant(db, experiment_id, evt.get("person_id", "Person 01"))
        confidence = float(evt.get("confidence", 0.0))
        activity = evt.get("activity", "Unknown")
        needs_review = activity.lower() in ("unknown", "unexpected") or confidence < confidence_threshold
        start_sec = float(evt["start_seconds"])
        end_sec = float(evt["end_seconds"])
        db.add(models.ActivityEvent(
            id=str(uuid.uuid4()),
            experiment_id=experiment_id,
            person_id=participant.id,
            video_id=experiment_id,
            activity_type=activity,
            start_time=evt.get("start"),
            end_time=evt.get("end"),
            start_seconds=start_sec,
            end_seconds=end_sec,
            duration=round(end_sec - start_sec, 2),
            confidence=confidence,
            status="Review" if needs_review else "Confirmed",
            review_status="pending" if needs_review else "auto",
            frame_number=evt.get("frame_start"),
            note=evt.get("note"),
        ))
    return len(events)


class JobManager:
    def __init__(self, pipeline):
        self.pipeline = pipeline
        # Items are ("process" | "preview", experiment_id); None stops the worker.
        self._queue: "queue.Queue[Optional[tuple]]" = queue.Queue()
        self._thread: Optional[threading.Thread] = None
        self.current: Optional[str] = None

    # ── lifecycle ────────────────────────────────────────────────────────────
    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._thread = threading.Thread(target=self._run, name="video-jobs", daemon=True)
        self._thread.start()
        log.info("Job worker started")

    def stop(self) -> None:
        self._queue.put(None)

    def enqueue(self, experiment_id: str) -> None:
        self._queue.put(("process", experiment_id))
        log.info("Queued %s (queue length %d)", experiment_id, self._queue.qsize())

    def enqueue_preview(self, experiment_id: str) -> None:
        """Create a browser-playable preview for an already-processed video."""
        self._queue.put(("preview", experiment_id))

    def backfill_playback(self) -> None:
        """Videos stored before codec detection existed: detect the codec, and queue a preview
        for completed ones the browser cannot play."""
        db = SessionLocal()
        try:
            for exp in db.query(models.Experiment).filter(models.Experiment.codec.is_(None)).all():
                if not exp.video_path or not os.path.exists(exp.video_path):
                    continue
                exp.codec, exp.preview_status = media.classify_playback(exp.video_path)
                log.info("Detected codec for %s: %s (preview %s)", exp.id, exp.codec, exp.preview_status)
            db.commit()
            for exp in db.query(models.Experiment).filter(models.Experiment.status == "completed",
                                                          models.Experiment.preview_status == "pending").all():
                self.enqueue_preview(exp.id)
        finally:
            db.close()

    def queue_length(self) -> int:
        return self._queue.qsize()

    # ── worker ───────────────────────────────────────────────────────────────
    def _run(self) -> None:
        while True:
            item = self._queue.get()
            if item is None:
                return
            kind, experiment_id = item
            self.current = experiment_id
            try:
                if kind == "preview":
                    self._preview_only(experiment_id)
                else:
                    self._process(experiment_id)
            except Exception:
                log.exception("Job %s (%s) crashed", experiment_id, kind)
                if kind == "process":
                    self._fail(experiment_id, "Video processing failed unexpectedly. Check backend logs.")
            finally:
                self.current = None

    def _fail(self, experiment_id: str, message: str) -> None:
        db = SessionLocal()
        try:
            exp = db.get(models.Experiment, experiment_id)
            if exp:
                exp.status = "failed"
                exp.message = message
                db.commit()
        finally:
            db.close()

    def _preview_only(self, experiment_id: str) -> None:
        db = SessionLocal()
        try:
            exp = db.get(models.Experiment, experiment_id)
            if exp and exp.preview_status in ("pending", "failed") and exp.video_path and os.path.exists(exp.video_path):
                self._make_preview(db, exp, show_progress=False)
        finally:
            db.close()

    @staticmethod
    def _make_preview(db, exp: models.Experiment, show_progress: bool = True) -> None:
        """Best effort: a failed preview never fails the analysis, it only affects playback."""
        if show_progress:
            exp.progress, exp.message = 95.0, "Creating a browser-playable preview..."
            db.commit()
        dst = media.preview_path_for(exp.video_path)
        try:
            t0 = time.monotonic()
            media.make_preview(exp.video_path, dst)
            exp.preview_status, exp.preview_path = "ready", dst
            log.info("Preview ready for %s (%s -> h264) in %.1fs", exp.id, exp.codec, time.monotonic() - t0)
        except Exception as e:
            exp.preview_status = "failed"
            log.error("Preview failed for %s: %s", exp.id, e)
        db.commit()

    def _process(self, experiment_id: str) -> None:
        db = SessionLocal()
        try:
            exp = db.get(models.Experiment, experiment_id)
            if exp is None:
                log.warning("Job %s: experiment no longer exists", experiment_id)
                return
            if not exp.video_path or not os.path.exists(exp.video_path):
                exp.status, exp.message = "failed", "Video file is missing on the server. Upload it again."
                db.commit()
                return

            exp.status, exp.progress, exp.message = "processing", 0.0, None
            if exp.codec is None:
                exp.codec, exp.preview_status = media.classify_playback(exp.video_path)
            db.commit()
            log.info("Processing started: %s (%s)", experiment_id, exp.video_filename)

            last_write = [0.0]
            wants_preview = exp.preview_status in ("pending", "failed") and media.ffmpeg_available()
            # Leave the last 10 % of the bar for the preview transcode when one is needed.
            scale = 90.0 if wants_preview else 100.0

            def on_progress(fraction: float) -> None:
                now = time.monotonic()
                if now - last_write[0] < PROGRESS_WRITE_INTERVAL:
                    return
                last_write[0] = now
                exp.progress = round(fraction * scale, 1)
                db.commit()

            t0 = time.monotonic()
            result = self.pipeline.process_video(exp.video_path, progress_cb=on_progress)
            elapsed = time.monotonic() - t0
            meta = result.get("metadata") or {}
            message = result.get("message", "")

            if not result.get("model_ready"):
                exp.status, exp.message = "failed", message or "AI model is not ready."
                db.commit()
                log.error("Processing refused for %s: %s", experiment_id, exp.message)
                return
            if result.get("failed"):
                exp.status, exp.message = "failed", message
                db.commit()
                log.error("Processing failed for %s: %s", experiment_id, message)
                return

            _clear_results(db, experiment_id)
            count = save_events(db, experiment_id, result.get("events", []), self.pipeline.confidence_threshold)
            db.commit()
            if wants_preview:
                self._make_preview(db, exp)
            exp.status = "completed"
            exp.progress = 100.0
            exp.message = message
            exp.engine = meta.get("activity_engine")
            exp.processed_at = utcnow()
            exp.processing_seconds = round(elapsed, 1)
            db.commit()
            log.info("Processing finished: %s in %.1fs - %d events, %s people, %s sampled frames",
                     experiment_id, elapsed, count, meta.get("people"), meta.get("sampled_frames"))
        finally:
            db.close()
