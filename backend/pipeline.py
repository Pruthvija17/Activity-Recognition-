"""BAS activity-recognition pipeline.

    video frames -> YOLO11 pose (person boxes + 17 keypoints) -> ByteTrack IDs
      -> pose features (services/activity/features.py)
      -> rule scores + softmax + open-set Unknown decision (rules.py, unknown.py)
      -> smoothing / hysteresis / min-duration / pick-vs-place (segmenter.py)
      -> activity events per person

Activity labels come from a trained temporal model (weights/activity_gru.pt) when one exists and
matches the current feature layout, otherwise from a transparent rule-based baseline on pose
keypoints. Models are loaded once per process.
"""
import json
import logging
import os
import shutil
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional

from config import ACTIVITY_MODEL_PATH, MODEL_CONFIG_PATH, POSE_WEIGHTS_NAME, POSE_WEIGHTS_PATH, WEIGHTS_DIR
from services.activity.engine import RULES_ENGINE, ActivityEngine, TrackState
from services.activity.temporal import TemporalModel
from services.activity.rules import ACTIVITIES, UNKNOWN
from services.activity.segmenter import Sample, SegmentConfig, segment_track
from services.activity.unknown import DEFAULT_ENTROPY_BITS, OpenSetClassifier

log = logging.getLogger("bas.pipeline")

# Optional heavy dependencies: a missing package must be reported via the
# status endpoint, not crash the whole API on import.
IMPORT_ERRORS: Dict[str, str] = {}
try:
    import cv2
except Exception as e:  # pragma: no cover - depends on environment
    cv2 = None
    IMPORT_ERRORS["opencv"] = str(e)
try:
    from ultralytics import YOLO
except Exception as e:  # pragma: no cover - depends on environment
    YOLO = None
    IMPORT_ERRORS["ultralytics"] = str(e)

ENGINE_NAME = RULES_ENGINE  # name when no trained model is loaded


def hms(seconds: float) -> str:
    s = max(0.0, float(seconds))
    return f"{int(s // 3600):02d}:{int(s % 3600 // 60):02d}:{int(s % 60):02d}"


@dataclass
class EngineConfig:
    """Tunable parameters, read from weights/model_config.json (defaults below)."""
    sample_fps: float = 8.0
    detector_confidence: float = 0.25
    keypoint_visibility: float = 0.5
    tracker: str = "bytetrack.yaml"
    min_track_seconds: float = 1.0
    feature_window_seconds: float = 1.0
    softmax_temperature: float = 6.0
    unknown_min_probability: float = 0.40
    entropy_threshold_bits: Dict[str, float] = field(default_factory=lambda: dict(DEFAULT_ENTROPY_BITS))
    smoothing_seconds: float = 0.6
    hysteresis_seconds: float = 0.4
    min_event_seconds: float = 1.0
    max_gap_seconds: float = 1.0
    pick_place_context_seconds: float = 2.0

    @classmethod
    def from_json(cls, data: dict) -> "EngineConfig":
        c = cls()
        det, samp = data.get("detector", {}), data.get("sampling", {})
        trk, eng = data.get("tracking", {}), data.get("activity_engine", {})
        seg = data.get("event_segmentation", {})
        c.sample_fps = float(samp.get("sample_fps", c.sample_fps))
        c.detector_confidence = float(det.get("confidence_threshold", c.detector_confidence))
        c.keypoint_visibility = float(det.get("keypoint_visibility", c.keypoint_visibility))
        c.tracker = det.get("tracker", c.tracker)
        c.min_track_seconds = float(trk.get("min_track_seconds", c.min_track_seconds))
        c.feature_window_seconds = float(eng.get("feature_window_seconds", c.feature_window_seconds))
        c.softmax_temperature = float(eng.get("softmax_temperature", c.softmax_temperature))
        c.unknown_min_probability = float(eng.get("unknown_min_probability", c.unknown_min_probability))
        c.entropy_threshold_bits.update(eng.get("entropy_threshold_bits", {}))
        c.smoothing_seconds = float(seg.get("smoothing_window_seconds", c.smoothing_seconds))
        c.hysteresis_seconds = float(seg.get("hysteresis_seconds", c.hysteresis_seconds))
        c.min_event_seconds = float(seg.get("min_event_duration_seconds", c.min_event_seconds))
        c.max_gap_seconds = float(seg.get("max_gap_seconds", c.max_gap_seconds))
        c.pick_place_context_seconds = float(seg.get("pick_place_context_seconds", c.pick_place_context_seconds))
        return c

    def segment_config(self, sample_interval: float) -> SegmentConfig:
        return SegmentConfig(
            sample_interval=sample_interval,
            smoothing_seconds=self.smoothing_seconds,
            hysteresis_seconds=self.hysteresis_seconds,
            min_event_seconds=self.min_event_seconds,
            max_gap_seconds=self.max_gap_seconds,
            pick_place_context_seconds=self.pick_place_context_seconds,
        )


def build_events(tracks: Dict[int, List[Sample]], cfg: EngineConfig, sample_interval: float,
                 labels: Optional[Dict[int, str]] = None) -> tuple:
    """Filter short tracks, number people in order of appearance and segment each track.

    `labels` (track id -> "Person NN") keeps names already shown to an operator, e.g. live.
    """
    kept = {
        tid: s for tid, s in tracks.items()
        if s and (s[-1].t - s[0].t + sample_interval) >= cfg.min_track_seconds
    }
    order = sorted(kept, key=lambda tid: kept[tid][0].t)
    seg_cfg = cfg.segment_config(sample_interval)
    events = []
    names: Dict[int, str] = {}
    for number, tid in enumerate(order, start=1):
        person = (labels or {}).get(tid) or f"Person {number:02d}"
        names[tid] = person
        for seg in segment_track(kept[tid], seg_cfg):
            events.append({
                "person_id": person,
                "track_id": tid,
                "activity": seg.label,
                "confidence": round(seg.confidence, 4),
                "start": hms(seg.start),
                "end": hms(seg.end),
                "start_seconds": round(seg.start, 3),
                "end_seconds": round(seg.end, 3),
                "duration": round(seg.duration, 3),
                "frame_start": seg.frame_start,
                "frame_end": seg.frame_end,
            })
    events.sort(key=lambda e: (e["start_seconds"], e["person_id"]))
    return events, len(order), len(tracks) - len(kept), names


class AIVideoPipeline:
    SUPPORTED_ACTIVITIES = ACTIVITIES

    def __init__(self):
        self.model = None
        self.model_loaded = self.model_ready = False
        self.detector_loaded = self.classifier_loaded = False
        self.load_error: Optional[str] = None
        self._confidence_threshold = 0.60
        self.config = self._read_config()
        self.engine = EngineConfig.from_json(self.config)
        self.classifier = OpenSetClassifier(
            temperature=self.engine.softmax_temperature,
            min_probability=self.engine.unknown_min_probability,
            entropy_bits=dict(self.engine.entropy_threshold_bits),
        )
        self.activity_model_error: Optional[str] = None
        self.reload_activity_model()
        self.load_models()

    def reload_activity_model(self, path: str = ACTIVITY_MODEL_PATH) -> None:
        """Use a trained temporal model if valid weights exist, else the rule baseline."""
        temporal, error = TemporalModel.load(path)
        self.activity_model_error = error
        self.activity = ActivityEngine(self.classifier, temporal,
                                       feature_window_seconds=self.engine.feature_window_seconds,
                                       keypoint_visibility=self.engine.keypoint_visibility)
        if temporal:
            log.info("Activity engine: %s (%s)", self.activity.name, path)
        elif error:
            log.error("Trained activity model not used: %s", error)

    @staticmethod
    def _read_config() -> dict:
        if not os.path.exists(MODEL_CONFIG_PATH):
            return {}
        try:
            with open(MODEL_CONFIG_PATH, encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            log.warning("Could not read %s, using defaults: %s", MODEL_CONFIG_PATH, e)
            return {}

    # ── status / configuration ───────────────────────────────────────────────
    def get_model_status(self):
        return {
            "model_ready": self.model_ready,
            "detector_ready": self.detector_loaded,
            "classifier_ready": self.classifier_loaded,
            "baseline_mode": not self.activity.trained,
            "engine": self.activity.name,
            "trained_model": self.activity.trained,
            "activity_model_error": self.activity_model_error,
            "activity_model_info": self._activity_model_info(),
            "classifier_type": ("YOLO pose keypoints + trained temporal GRU" if self.activity.trained else
                                "YOLO pose keypoints + rule-based activity baseline (no trained activity model)"),
            "weights_directory": WEIGHTS_DIR,
            "files": {"pose_model": {"path": POSE_WEIGHTS_PATH, "exists": os.path.exists(POSE_WEIGHTS_PATH)}},
            "import_errors": IMPORT_ERRORS,
            "load_error": self.load_error,
            "activities": self.SUPPORTED_ACTIVITIES,
            "unknown_sensitivity": self.classifier.sensitivity,
            "entropy_threshold_bits": self.classifier.entropy_threshold,
            "instructions": ("Activity labels come from a rule-based baseline on pose keypoints. "
                             "A trained temporal model will be used automatically once its weights exist."),
        }

    def _activity_model_info(self) -> Optional[dict]:
        if not self.activity.trained:
            return None
        spec = self.activity.temporal.spec
        return {k: spec.get(k) for k in ("trained_at", "classes", "window", "sample_fps", "metrics", "data")}

    @property
    def confidence_threshold(self) -> float:
        """Events below this confidence (0-1) are sent to the Review Queue."""
        return self._confidence_threshold

    def update_thresholds(self, confidence_threshold: int, unknown_sensitivity: str):
        self._confidence_threshold = max(0.5, min(0.95, float(confidence_threshold) / 100))
        if unknown_sensitivity in self.classifier.entropy_bits:
            self.classifier.sensitivity = unknown_sensitivity

    def load_models(self):
        if IMPORT_ERRORS:
            self.load_error = ("Missing Python packages: " + ", ".join(sorted(IMPORT_ERRORS))
                               + ". Run: pip install -r backend/requirements.txt")
            log.error(self.load_error)
            return
        if not os.path.exists(POSE_WEIGHTS_PATH):
            # Let ultralytics fetch the official weights once, then keep them in weights/.
            log.warning("Pose weights not found at %s; attempting one-time download of %s",
                        POSE_WEIGHTS_PATH, POSE_WEIGHTS_NAME)
            try:
                YOLO(POSE_WEIGHTS_NAME)
                if os.path.exists(POSE_WEIGHTS_NAME) and not os.path.exists(POSE_WEIGHTS_PATH):
                    shutil.move(POSE_WEIGHTS_NAME, POSE_WEIGHTS_PATH)
            except Exception as e:
                self.load_error = f"Pose model {POSE_WEIGHTS_NAME} missing from {WEIGHTS_DIR} and download failed: {e}"
                log.error(self.load_error)
                return
        try:
            log.info("Loading pose model: %s", POSE_WEIGHTS_PATH)
            self.model = YOLO(POSE_WEIGHTS_PATH)
            self.model_loaded = self.detector_loaded = self.classifier_loaded = self.model_ready = True
            log.info("Pose model loaded; activity engine: %s.", self.activity.name)
        except Exception as e:
            self.load_error = f"Pose model failed to load: {e}"
            log.error(self.load_error)

    # ── processing ───────────────────────────────────────────────────────────
    def get_video_metadata(self, path):
        cap = cv2.VideoCapture(path)
        if not cap.isOpened():
            raise RuntimeError("Could not open video")
        fps = float(cap.get(cv2.CAP_PROP_FPS) or 0)
        frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
        w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH) or 0)
        h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT) or 0)
        cap.release()
        duration = frames / fps if fps else 0
        return {"fps": round(fps, 3), "frame_count": frames, "width": w, "height": h,
                "duration_seconds": round(duration, 3), "duration": hms(duration),
                "filename": os.path.basename(path)}

    def process_video(self, path: str, progress_cb: Optional[Callable[[float], None]] = None,
                      collect_features: bool = False):
        """Run detection + tracking + activity recognition over a video file.

        progress_cb(fraction) is called with 0..1 as frames are processed.
        collect_features=True also returns per-person feature-vector sequences (for training).
        """
        if not os.path.exists(path):
            return {"model_ready": False, "events": [], "metadata": {}, "message": "Video file not found."}
        if not self.model_ready:
            return {"model_ready": False, "events": [], "metadata": {},
                    "message": self.load_error or "Pose model is not loaded."}

        meta = self.get_video_metadata(path)
        fps = meta["fps"] or 30.0
        stride = max(1, round(fps / self.engine.sample_fps))
        sample_interval = stride / fps
        total = max(1, meta["frame_count"])

        states: Dict[int, TrackState] = {}
        tracks: Dict[int, List[Sample]] = {}
        feature_tracks: Dict[int, dict] = {}
        detections = sampled = unknown_samples = 0
        try:
            stream = self.model.track(
                source=path, stream=True, persist=False, classes=[0], verbose=False,
                conf=self.engine.detector_confidence, tracker=self.engine.tracker, vid_stride=stride,
            )
            for idx, r in enumerate(stream):
                frame = idx * stride
                t = frame / fps
                sampled += 1
                if progress_cb and idx % 5 == 0:
                    progress_cb(min(1.0, frame / total))
                boxes = r.boxes
                # Only confirmed tracks carry an ID; unconfirmed detections are skipped rather than
                # being given a made-up identity.
                if boxes is None or boxes.id is None or r.keypoints is None:
                    continue
                ids = boxes.id.int().tolist()
                xyxy = boxes.xyxy.cpu().numpy()
                kxy = r.keypoints.xy.cpu().numpy()
                kconf = r.keypoints.conf.cpu().numpy() if r.keypoints.conf is not None else None
                for i, tid in enumerate(ids):
                    state = states.setdefault(tid, self.activity.new_track())
                    f, pred, vec = self.activity.observe(state, t, kxy[i], kconf[i] if kconf is not None else None,
                                                         xyxy[i])
                    if collect_features:
                        ft = feature_tracks.setdefault(tid, {"t": [], "vectors": []})
                        ft["t"].append(round(t, 4))
                        ft["vectors"].append(vec)
                    if pred.label == UNKNOWN:
                        unknown_samples += 1
                    tracks.setdefault(tid, []).append(Sample(
                        t=t, frame=frame, label=pred.label, confidence=pred.confidence,
                        probs=pred.probs, carry=f.carry,
                    ))
                    detections += 1
        except Exception as e:
            log.exception("Video processing failed for %s", path)
            return {"model_ready": True, "failed": True, "events": [], "metadata": meta,
                    "message": f"Video processing failed: {e}"}

        events, people, dropped, names = build_events(tracks, self.engine, sample_interval)
        engine_name = self.activity.name
        if progress_cb:
            progress_cb(1.0)

        if not detections:
            message = "Processing complete, but no people were detected in the video, so no activity events were produced."
        else:
            message = f"Processing complete: {people} people tracked, {len(events)} activity events ({engine_name})."
        result = {
            "model_ready": True,
            "events": events,
            "metadata": {
                **meta,
                "sample_every_frames": stride,
                "sampled_frames": sampled,
                "detections": detections,
                "unknown_samples": unknown_samples,
                "people": people,
                "dropped_short_tracks": dropped,
                "activity_engine": engine_name,
                "unknown_sensitivity": self.classifier.sensitivity,
            },
            "message": message,
        }
        if collect_features:
            # Keyed by the same person names as the events, so labels can refer to "Person 01".
            result["feature_tracks"] = {names[tid]: ft for tid, ft in feature_tracks.items() if tid in names}
            result["sample_interval"] = sample_interval
        return result
