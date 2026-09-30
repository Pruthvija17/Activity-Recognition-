"""Transparent rule-based activity scores.

Each posture class gets a score in [0, 1] from simple, explainable pose cues. Scores are turned
into a probability distribution with a softmax, so a pose that matches nothing well yields a flat
distribution (high entropy), which the open-set step turns into "Unknown".

Picking up vs placing an object cannot be told apart from a single pose; both are scored as one
internal LOW_REACH posture and split later by the segmenter using temporal context.
"""
import math
from typing import Dict, Optional

from .features import PoseFeatures

STANDING = "Standing"
SITTING = "Sitting"
WALKING = "Walking"
REACHING = "Reaching"
PICKING = "Picking up an object"
PLACING = "Placing an object"
HANDLING = "Handling experimental equipment"
UNKNOWN = "Unknown"
LOW_REACH = "Low reach (pick/place)"  # internal only, never stored

ACTIVITIES = [STANDING, SITTING, WALKING, REACHING, PICKING, PLACING, HANDLING]
INTERNAL_CLASSES = [STANDING, SITTING, WALKING, REACHING, LOW_REACH, HANDLING]


def ramp(x: Optional[float], lo: float, hi: float, missing: float = 0.0) -> float:
    """Linear 0..1 membership: 0 at `lo`, 1 at `hi` (works for descending ranges too)."""
    if x is None:
        return missing
    if hi == lo:
        return 1.0 if x >= hi else 0.0
    return max(0.0, min(1.0, (x - lo) / (hi - lo)))


def class_scores(f: PoseFeatures) -> Dict[str, float]:
    if not f.visible:
        return {c: 0.0 for c in INTERNAL_CLASSES}

    upright = ramp(f.trunk_angle, 40, 15)
    bent = ramp(f.trunk_angle, 25, 55)
    legs_straight = ramp(f.knee_angle, 135, 160, missing=0.6)

    if f.legs_visible:
        thighs_level = max(ramp(f.thigh_horizontal, 0.5, 0.8), ramp(f.thigh_ratio, 0.7, 0.4))
        sit = ramp(f.trunk_angle, 50, 25) * thighs_level
    else:
        # Legs hidden (e.g. behind a bench): a short, wide box is weak evidence of sitting.
        sit = 0.35 * ramp(f.aspect, 1.6, 1.1)

    moving = ramp(f.speed, 0.5, 1.2)
    still = 1.0 - ramp(f.speed, 0.3, 0.8)
    arm_out = ramp(f.arm_extension, 0.75, 1.05)
    hand_high = ramp(f.wrist_up, 0.4, 0.8)
    hand_low = max(ramp(f.wrist_down, 0.15, 0.5), bent * ramp(f.wrist_down, -0.2, 0.2))
    active = ramp(f.hand_activity, 0.35, 0.9)
    working = f.hands_front * active
    reaching = arm_out * hand_high

    scores = {
        WALKING: moving * (1 - 0.7 * sit),
        STANDING: upright * legs_straight * still * (1 - sit) * (1 - reaching) * (1 - hand_low) * (1 - 0.6 * working),
        SITTING: sit * (0.3 + 0.7 * still) * (1 - 0.6 * working),
        REACHING: reaching * (0.4 + 0.6 * still),
        LOW_REACH: hand_low * (0.4 + 0.6 * still),
        HANDLING: working * (0.3 + 0.7 * still) * (1 - 0.5 * reaching),
    }

    if f.upper_body_only:
        # Without hips/legs, standing / sitting / walking / low reaches cannot be judged.
        for c in (STANDING, SITTING, WALKING, LOW_REACH):
            scores[c] = 0.0

    # Atypical motion or body orientation matches none of the known activities:
    # very fast arm movement while not walking (e.g. flailing), or a near-horizontal torso (fall).
    atypical = max(ramp(f.hand_activity, 1.5, 3.0) * (1 - moving), ramp(f.trunk_angle, 60, 80))
    if atypical > 0:
        scores = {c: s * (1 - atypical) for c, s in scores.items()}
    return scores


def softmax(scores: Dict[str, float], temperature: float) -> Dict[str, float]:
    exps = {c: math.exp(temperature * s) for c, s in scores.items()}
    total = sum(exps.values())
    return {c: v / total for c, v in exps.items()}


def entropy_bits(probs: Dict[str, float]) -> float:
    return -sum(p * math.log2(p) for p in probs.values() if p > 0)
