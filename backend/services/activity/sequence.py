"""Fixed-length feature vectors for the trainable temporal activity model.

One vector per person per sampled frame. Changing the layout changes FEATURE_VERSION, and a model
trained on another version is refused at load time (instead of silently producing garbage).
"""
from typing import List

from .features import PoseFeatures

FEATURE_VERSION = 2  # v2: upper-body-only flag

# (attribute, scale) - scalar pose features; None values become 0 with a "present" flag.
SCALARS = [
    ("trunk_angle", 1 / 90),
    ("knee_angle", 1 / 180),
    ("hip_angle", 1 / 180),
    ("thigh_ratio", 1.0),
    ("thigh_horizontal", 1.0),
    ("arm_extension", 1.0),
    ("wrist_up", 1.0),
    ("wrist_down", 1.0),
    ("hands_front", 1.0),
    ("hands_gap", 1.0),
    ("speed", 1.0),
    ("hand_activity", 1.0),
    ("aspect", 1 / 3),
]
MOTION_CLIP = 5.0  # torso lengths per second; anything faster is tracking noise

FEATURE_DIM = 17 * 3 + len(SCALARS) * 2 + 2


def feature_vector(f: PoseFeatures) -> List[float]:
    if not f.visible or f.keypoints is None:
        return [0.0] * FEATURE_DIM
    out = list(f.keypoints)
    for name, scale in SCALARS:
        v = getattr(f, name)
        if v is None:
            out += [0.0, 0.0]
        else:
            if name in ("speed", "hand_activity"):
                v = min(float(v), MOTION_CLIP)
            out += [float(v) * scale, 1.0]
    out.append(1.0)  # pose visible
    out.append(1.0 if f.upper_body_only else 0.0)
    return out
