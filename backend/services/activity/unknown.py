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

    def predict(self, features: PoseFeatures) -> Prediction:
        if not features.visible:
            uniform = {c: 1.0 / len(INTERNAL_CLASSES) for c in INTERNAL_CLASSES}
            return Prediction(UNKNOWN, 0.0, INTERNAL_CLASSES[0], entropy_bits(uniform), uniform,
                              reason="pose not visible (shoulders/hips not detected)")

        probs = softmax(class_scores(features), self.temperature)
        best = max(probs, key=probs.get)
        conf = probs[best]
        ent = entropy_bits(probs)
        if ent > self.entropy_threshold:
            return Prediction(UNKNOWN, conf, best, ent, probs, reason=f"ambiguous (entropy {ent:.2f} bits)")
        if conf < self.min_probability:
            return Prediction(UNKNOWN, conf, best, ent, probs, reason=f"low probability ({conf:.2f})")
        return Prediction(best, conf, best, ent, probs)
