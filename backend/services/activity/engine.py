"""The activity engine used by both video processing and live monitoring.

Per tracked person it keeps pose features and (when a trained model is loaded) a window of feature
vectors. With a trained temporal model, predictions come from the model once enough history exists;
before that (the first ~1 s of a track) and without a model, the transparent rules are used.
Either way the same open-set decision turns weak or ambiguous predictions into Unknown.
"""
import logging
from collections import deque
from dataclasses import dataclass, field
from typing import Deque, List, Optional, Tuple

from .features import PoseFeatures, TrackFeatures
from .sequence import feature_vector
from .temporal import TemporalModel
from .rules import UNKNOWN
from .unknown import OpenSetClassifier, Prediction

log = logging.getLogger("bas.engine")

RULES_ENGINE = "Rule-based pose baseline"


@dataclass
class TrackState:
    features: TrackFeatures
    vectors: Deque[List[float]] = field(default_factory=lambda: deque(maxlen=64))


class ActivityEngine:
    def __init__(self, classifier: OpenSetClassifier, temporal: Optional[TemporalModel] = None,
                 feature_window_seconds: float = 1.0, keypoint_visibility: float = 0.5):
        self.classifier = classifier
        self.temporal = temporal
        self.feature_window_seconds = feature_window_seconds
        self.keypoint_visibility = keypoint_visibility

    @property
    def trained(self) -> bool:
        return self.temporal is not None

    @property
    def name(self) -> str:
        if not self.temporal:
            return RULES_ENGINE
        trained_at = str(self.temporal.spec.get("trained_at", ""))[:10]
        return f"Trained temporal model (GRU{', ' + trained_at if trained_at else ''})"

    def new_track(self) -> TrackState:
        return TrackState(TrackFeatures(window_seconds=self.feature_window_seconds,
                                        keypoint_visibility=self.keypoint_visibility))

    def observe(self, state: TrackState, t: float, kxy, kconf, box) -> Tuple[PoseFeatures, Prediction, List[float]]:
        """Update one person's state with a new frame; returns (features, prediction, feature vector)."""
        f = state.features.update(t, kxy, kconf, box)
        vec = feature_vector(f)
        state.vectors.append(vec)
        if self.temporal is None:
            return f, self.classifier.predict(f), vec
        if not f.visible:
            return f, self.classifier.not_visible(self.temporal.classes), vec
        if len(state.vectors) < self.temporal.min_window:
            return f, self.classifier.predict(f), vec  # warm-up: not enough history yet
        probs, novelty = self.temporal.analyze(state.vectors)
        pred = self.classifier.decide(probs)
        if novelty > 1.0 and pred.label != UNKNOWN:
            # Confident, but unlike every training example of that class: treat as unexpected.
            pred = Prediction(UNKNOWN, pred.confidence, pred.best_known, pred.entropy, probs,
                              reason=f"unlike trained examples of {pred.best_known} (distance x{novelty:.1f})")
        return f, pred, vec
