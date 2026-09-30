"""Live camera monitoring.

The browser samples camera frames (a few per second) and sends them as JPEG over a WebSocket.
Each frame runs through the same detector / tracker / features / open-set classifier as uploaded
videos, using a dedicated model instance (so a background video job and a live session don't share
tracker state). Frames are also recorded, so when the session stops its events are segmented,
stored and reviewable against the recording, exactly like an uploaded experiment.

Timing: each frame is stamped with real elapsed time and written into the recording at that
time's slot (gaps are filled by repeating the previous frame). So durations stay real even when
fewer frames arrive than requested, and the recording lines up exactly with the events.
"""
import datetime
import logging
import os
import threading
import time
import uuid
from collections import Counter
from typing import Dict, List, Optional

import config
import models
from database import SessionLocal
from pipeline import AIVideoPipeline, build_events
from services.activity.features import TrackFeatures
from services.activity.rules import LOW_REACH, UNKNOWN
from services.activity.segmenter import Sample
from services.jobs import JobManager, save_events
from services import media

try:
    import cv2
    import numpy as np
except Exception:  # pragma: no cover - reported via /api/system/status
    cv2 = np = None

log = logging.getLogger("bas.live")

IDLE_TIMEOUT_SECONDS = 30.0
MAX_WIDTH = 1280


class LiveSession:
    def __init__(self, experiment_id: str, pipeline: AIVideoPipeline, fps: float, record_path: str):
        from ultralytics import YOLO  # imported lazily: only needed when a session starts

        self.experiment_id = experiment_id
        self.pipeline = pipeline
        self.cfg = pipeline.engine
        self.fps = fps
        self.record_path = record_path
        self.model = YOLO(config.POSE_WEIGHTS_PATH)  # fresh instance -> fresh tracker state
        self.features: Dict[int, TrackFeatures] = {}
        self.tracks: Dict[int, List[Sample]] = {}
        self.labels: Dict[int, str] = {}
        self.frame_index = 0          # frames received and analysed
        self.written = 0              # frames in the recording (at self.fps)
        self.first_frame_at: Optional[float] = None
        self.last_frame = None
        self.writer = None
        self.frame_size = None
        self.started_at = time.monotonic()
        self.last_frame_at = self.started_at
        self.inference_ms: List[float] = []
        self.finished = False
        self.lock = threading.Lock()

    @property
    def smoothing_samples(self) -> int:
        return max(1, int(round(self.cfg.smoothing_seconds * self.fps)))

    def _label(self, tid: int) -> str:
        if tid not in self.labels:
            self.labels[tid] = f"Person {len(self.labels) + 1:02d}"
        return self.labels[tid]

    def _current_activity(self, samples: List[Sample]) -> tuple:
        """Majority label over the smoothing window and its mean probability."""
        window = samples[-self.smoothing_samples:]
        label, _ = Counter(s.label for s in window).most_common(1)[0]
        if label == UNKNOWN:
            conf = sum(s.confidence for s in window) / len(window)
        else:
            conf = sum(s.probs.get(label, 0.0) for s in window) / len(window)
        return label, conf

    def process(self, jpeg: bytes) -> dict:
        with self.lock:
            if self.finished:
                raise RuntimeError("Session already stopped.")
            frame = cv2.imdecode(np.frombuffer(jpeg, np.uint8), cv2.IMREAD_COLOR)
            if frame is None:
                raise ValueError("Frame is not a decodable JPEG/PNG image.")
            h, w = frame.shape[:2]
            if w > MAX_WIDTH:
                frame = cv2.resize(frame, (MAX_WIDTH, int(h * MAX_WIDTH / w)))
                h, w = frame.shape[:2]

            if self.writer is None:
                self.frame_size = (w, h)
                self.writer = cv2.VideoWriter(self.record_path, cv2.VideoWriter_fourcc(*"mp4v"), self.fps, (w, h))
            elif (w, h) != self.frame_size:
                frame = cv2.resize(frame, self.frame_size)
                w, h = self.frame_size
            # Place the frame at its real-time slot; pad any gap with the previous frame.
            now = time.monotonic()
            if self.first_frame_at is None:
                self.first_frame_at = now
            slot = int(round((now - self.first_frame_at) * self.fps))
            if self.last_frame is not None:
                while self.written < slot:
                    self.writer.write(self.last_frame)
                    self.written += 1
            slot = self.written  # arrived early (or first frame): take the next free slot
            self.writer.write(frame)
            self.written += 1
            self.last_frame = frame

            t = slot / self.fps
            t0 = time.perf_counter()
            r = self.model.track(frame, persist=True, classes=[0], verbose=False,
                                 conf=self.cfg.detector_confidence, tracker=self.cfg.tracker)[0]
            people = []
            if r.boxes is not None and r.boxes.id is not None and r.keypoints is not None:
                ids = r.boxes.id.int().tolist()
                xyxy = r.boxes.xyxy.cpu().numpy()
                kxy = r.keypoints.xy.cpu().numpy()
                kconf = r.keypoints.conf.cpu().numpy() if r.keypoints.conf is not None else None
                for i, tid in enumerate(ids):
                    tf = self.features.setdefault(tid, TrackFeatures(
                        window_seconds=self.cfg.feature_window_seconds,
                        keypoint_visibility=self.cfg.keypoint_visibility,
                    ))
                    f = tf.update(t, kxy[i], kconf[i] if kconf is not None else None, xyxy[i])
                    pred = self.pipeline.classifier.predict(f)
                    samples = self.tracks.setdefault(tid, [])
                    samples.append(Sample(t=t, frame=slot, label=pred.label,
                                          confidence=pred.confidence, probs=pred.probs, carry=f.carry))
                    label, conf = self._current_activity(samples)
                    x1, y1, x2, y2 = (float(v) for v in xyxy[i])
                    people.append({
                        "person": self._label(tid),
                        "track_id": tid,
                        "box": [x1 / w, y1 / h, x2 / w, y2 / h],
                        # Pick/place is only resolved when the session is segmented.
                        "activity": "Picking up / placing an object" if label == LOW_REACH else label,
                        "confidence": round(conf, 3),
                        "unknown": label == UNKNOWN,
                    })
            elapsed_ms = (time.perf_counter() - t0) * 1000
            self.inference_ms = (self.inference_ms + [elapsed_ms])[-20:]
            self.frame_index += 1
            self.last_frame_at = time.monotonic()
            return {
                "type": "result",
                "frame": slot,
                "t": round(t, 3),
                "inference_ms": round(elapsed_ms, 1),
                "avg_inference_ms": round(sum(self.inference_ms) / len(self.inference_ms), 1),
                "people": people,
            }

    def finish(self) -> tuple:
        with self.lock:
            self.finished = True
            if self.writer is not None:
                self.writer.release()
            interval = 1.0 / self.fps
            events, people, dropped = build_events(self.tracks, self.cfg, interval, labels=self.labels)
            return events, people, dropped


class LiveManager:
    """At most one live session at a time (one camera, one CPU)."""

    def __init__(self, pipeline: AIVideoPipeline, jobs: JobManager):
        self.pipeline = pipeline
        self.jobs = jobs
        self.current: Optional[LiveSession] = None
        self._lock = threading.Lock()

    def start(self, fps: float, name: Optional[str] = None) -> LiveSession:
        with self._lock:
            if self.current and not self.current.finished:
                idle = time.monotonic() - self.current.last_frame_at
                if idle < IDLE_TIMEOUT_SECONDS:
                    raise RuntimeError("A live session is already running.")
                log.warning("Finalising abandoned live session %s (idle %.0fs)", self.current.experiment_id, idle)
                self._stop_locked(self.current.experiment_id)

            experiment_id = f"LIVE_{uuid.uuid4().hex[:8]}"
            stamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
            filename = name or f"Live camera {stamp}"
            record_path = os.path.join(config.UPLOADS_DIR, f"{experiment_id}_camera.mp4")
            session = LiveSession(experiment_id, self.pipeline, fps, record_path)
            db = SessionLocal()
            try:
                db.add(models.Experiment(
                    id=experiment_id, name=filename, video_filename=filename, video_path=record_path,
                    source="camera", status="live", fps=fps, progress=0.0, engine=None,
                    codec="mpeg4", preview_status="pending" if media.ffmpeg_available() else "unavailable",
                ))
                db.commit()
            finally:
                db.close()
            self.current = session
            log.info("Live session %s started at %.1f fps", experiment_id, fps)
            return session

    def get(self, experiment_id: str) -> Optional[LiveSession]:
        s = self.current
        return s if s and s.experiment_id == experiment_id and not s.finished else None

    def stop(self, experiment_id: str) -> Optional[dict]:
        with self._lock:
            return self._stop_locked(experiment_id)

    def _stop_locked(self, experiment_id: str) -> Optional[dict]:
        session = self.get(experiment_id)
        if session is None:
            return None
        t0 = time.monotonic()
        events, people, dropped = session.finish()
        duration = session.written / session.fps
        db = SessionLocal()
        try:
            exp = db.get(models.Experiment, experiment_id)
            save_events(db, experiment_id, events, self.pipeline.confidence_threshold)
            exp.status = "completed"
            exp.progress = 100.0
            exp.duration_seconds = round(duration, 3)
            exp.frame_count = session.written
            exp.engine = self.pipeline.get_model_status()["engine"]
            exp.processed_at = datetime.datetime.utcnow()
            exp.processing_seconds = round(time.monotonic() - session.started_at, 1)
            if session.frame_index == 0:
                exp.message = "No camera frames were received, so nothing was analysed."
                exp.preview_status = None
                if os.path.exists(session.record_path):
                    os.remove(session.record_path)
                exp.video_path = None
            else:
                exp.message = (f"Live session complete: {people} people tracked, {len(events)} activity events "
                               f"over {duration:.1f} s ({session.frame_index} frames analysed).")
                exp.file_size = os.path.getsize(session.record_path) if os.path.exists(session.record_path) else None
            db.commit()
            preview = exp.preview_status == "pending"
            summary = {"experiment_id": experiment_id, "events": len(events), "people": people,
                       "duration_seconds": round(duration, 2), "frames": session.frame_index,
                       "dropped_short_tracks": dropped, "message": exp.message}
        finally:
            db.close()
        if self.current is session:
            self.current = None
        if preview:
            self.jobs.enqueue_preview(experiment_id)
        log.info("Live session %s stopped: %s (finalised in %.1fs)", experiment_id, summary["message"],
                 time.monotonic() - t0)
        return summary
