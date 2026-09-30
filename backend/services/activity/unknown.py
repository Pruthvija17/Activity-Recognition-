"""Open-set decision: accept the best known class, or declare the sample Unknown.

A sample is Unknown when
  * the pose is not visible enough to classify (no shoulders/hips), or
  * the class distribution is too flat: entropy above the sensitivity threshold, or
  * the best class probability is below an absolute floor.
Sensitivity (Settings page) selects the entropy threshold, in bits. With six internal classes the
maximum possible entropy is log2(6) = 2.58 bits.
"""
from dataclasses import dataclass
from typing import Dict

from .features import PoseFeatures
from .rules import INTERNAL_CLASSES, UNKNOWN, class_scores, entropy_bits, softmax

DEFAULT_ENTROPY_BITS = {"Low": 2.5, "Medium": 1.75, "High": 1.0}

# Short reasons stored on Unknown events (shown to reviewers).
REASON_NOT_VISIBLE = "person not clearly visible"
REASON_UPPER_BODY = "only upper body visible"
REASON_AMBIGUOUS = "ambiguous between activities"
REASON_LOW_PROB = "no activity matched well"
REASON_UNFAMILIAR = "unlike trained examples"


@dataclass
class Prediction:
    label: str                 # best internal class, or UNKNOWN
    confidence: float          # probability of `label` (for UNKNOWN: probability of the best known class)
    best_known: str            # best internal class even when the label is UNKNOWN
    entropy: float
    probs: Dict[str, float]
    reason: str = ""           # why the sample is Unknown


@dataclass
class OpenSetClassifier:
    temperature: float = 6.0
    min_probability: float = 0.40
    entropy_bits: Dict[str, float] = None
    sensitivity: str = "Medium"

    def __post_init__(self):
        if self.entropy_bits is None:
            self.entropy_bits = dict(DEFAULT_ENTROPY_BITS)

    @property
    def entropy_threshold(self) -> float:
        return self.entropy_bits.get(self.sensitivity, self.entropy_bits["Medium"])

    @staticmethod
    def not_visible(classes=INTERNAL_CLASSES) -> Prediction:
        uniform = {c: 1.0 / len(classes) for c in classes}
        return Prediction(UNKNOWN, 0.0, classes[0], entropy_bits(uniform), uniform, reason=REASON_NOT_VISIBLE)

    def decide(self, probs: Dict[str, float]) -> Prediction:
        """Open-set decision on any class distribution (rule scores or a trained model)."""
        best = max(probs, key=probs.get)
        conf = probs[best]
        ent = entropy_bits(probs)
        if ent > self.entropy_threshold:
            return Prediction(UNKNOWN, conf, best, ent, probs, reason=REASON_AMBIGUOUS)
        if conf < self.min_probability:
            return Prediction(UNKNOWN, conf, best, ent, probs, reason=REASON_LOW_PROB)
        return Prediction(best, conf, best, ent, probs)

    def predict(self, features: PoseFeatures) -> Prediction:
        """Rule-based prediction for one pose."""
        if not features.visible:
            return self.not_visible()
        pred = self.decide(softmax(class_scores(features), self.temperature))
        if pred.label == UNKNOWN and features.upper_body_only:
            pred.reason = REASON_UPPER_BODY
        return pred
