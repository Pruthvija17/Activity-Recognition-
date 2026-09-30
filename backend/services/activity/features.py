"""Per-person pose features for activity classification.

Input: COCO-17 keypoints in image pixels (y grows downwards) plus per-keypoint confidence.
All distances are expressed in torso lengths (L = shoulder-mid to hip-mid), so features do not
depend on how far the person is from the camera. Motion features are per second, so they do not
depend on the sampling rate.
"""
import math
from collections import deque
from dataclasses import dataclass, field
from typing import Deque, List, Optional, Sequence, Tuple

Point = Tuple[float, float]

# COCO-17 keypoint indices
L_SH, R_SH = 5, 6
L_WR, R_WR = 9, 10
L_HIP, R_HIP = 11, 12
L_KNEE, R_KNEE = 13, 14
L_ANK, R_ANK = 15, 16

MIN_TORSO_PX = 8.0


def _dist(a: Point, b: Point) -> float:
    return math.hypot(a[0] - b[0], a[1] - b[1])


def _mid(a: Optional[Point], b: Optional[Point]) -> Optional[Point]:
    if a and b:
        return ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)
    return a or b


def _angle(a: Point, b: Point, c: Point) -> Optional[float]:
    """Angle ABC in degrees."""
    v1 = (a[0] - b[0], a[1] - b[1])
    v2 = (c[0] - b[0], c[1] - b[1])
    n = math.hypot(*v1) * math.hypot(*v2)
    if n < 1e-6:
        return None
    cos = max(-1.0, min(1.0, (v1[0] * v2[0] + v1[1] * v2[1]) / n))
    return math.degrees(math.acos(cos))


def _mean(values: Sequence[Optional[float]]) -> Optional[float]:
    vals = [v for v in values if v is not None]
    return sum(vals) / len(vals) if vals else None


@dataclass
class PoseFeatures:
    visible: bool                       # shoulders and hips found -> features below are meaningful
    trunk_angle: Optional[float] = None  # degrees from vertical (0 upright, 90 horizontal)
    knee_angle: Optional[float] = None   # hip-knee-ankle, 180 = straight
    hip_angle: Optional[float] = None    # shoulder-hip-knee, 180 = straight
    thigh_ratio: Optional[float] = None  # thigh length / L (short when foreshortened, e.g. seated facing camera)
    thigh_horizontal: Optional[float] = None  # 0 vertical thigh .. 1 horizontal thigh
    legs_visible: bool = False
    arm_extension: Optional[float] = None  # max shoulder-wrist distance / L
    wrist_up: Optional[float] = None       # max height of a wrist above hip level, in L
    wrist_down: Optional[float] = None     # max depth of a wrist below hip level, in L
    hands_front: float = 0.0               # 0..1 share of wrists in front of the torso, between hip and shoulder
    hands_gap: Optional[float] = None      # distance between wrists / L
    aspect: float = 0.0                    # bbox height / width
    speed: Optional[float] = None          # body (hip-mid) speed in L per second
    hand_activity: Optional[float] = None  # wrist motion relative to the body, L per second
    torso_px: float = 0.0
    # 17 x (x, y, visible): keypoints relative to the hip centre in torso lengths (zeros if hidden)
    keypoints: Optional[List[float]] = None

    @property
    def carry(self) -> float:
        """0..1: both hands together in front of the torso (a carrying / holding posture)."""
        if self.hands_gap is None:
            return 0.0
        together = max(0.0, min(1.0, (1.0 - self.hands_gap) / 0.6))
        return self.hands_front * together


@dataclass
class _HistoryEntry:
    t: float
    hip: Point
    torso: float
    wrists_rel: List[Optional[Point]]


@dataclass
class TrackFeatures:
    """Keeps a short per-person history so motion features can be computed."""
    window_seconds: float = 1.0
    keypoint_visibility: float = 0.5
    history: Deque[_HistoryEntry] = field(default_factory=lambda: deque(maxlen=64))

    def _pt(self, kxy, kconf, i) -> Optional[Point]:
        if kconf is not None and float(kconf[i]) < self.keypoint_visibility:
            return None
        x, y = float(kxy[i][0]), float(kxy[i][1])
        if x <= 0 and y <= 0:
            return None
        return (x, y)

    def update(self, t: float, kxy, kconf, box: Sequence[float]) -> PoseFeatures:
        x1, y1, x2, y2 = (float(v) for v in box)
        aspect = (y2 - y1) / max(1.0, x2 - x1)
        p = lambda i: self._pt(kxy, kconf, i)  # noqa: E731

        ls, rs, lh, rh = p(L_SH), p(R_SH), p(L_HIP), p(R_HIP)
        sh, hip = _mid(ls, rs), _mid(lh, rh)
        if not sh or not hip or _dist(sh, hip) < MIN_TORSO_PX:
            return PoseFeatures(visible=False, aspect=aspect)

        L = _dist(sh, hip)
        f = PoseFeatures(visible=True, aspect=aspect, torso_px=L)
        kps: List[float] = []
        for i in range(17):
            q = p(i)
            kps += [(q[0] - hip[0]) / L, (q[1] - hip[1]) / L, 1.0] if q else [0.0, 0.0, 0.0]
        f.keypoints = kps

        # Torso orientation: angle between hip->shoulder and straight up.
        cos_up = -(sh[1] - hip[1]) / L
        f.trunk_angle = math.degrees(math.acos(max(-1.0, min(1.0, cos_up))))

        # Legs
        knee_angles, hip_angles, thigh_ratios, thigh_h = [], [], [], []
        for s, h, k, a in ((ls, lh, p(L_KNEE), p(L_ANK)), (rs, rh, p(R_KNEE), p(R_ANK))):
            h = h or hip
            if k is None:
                continue
            f.legs_visible = True
            if a is not None:
                knee_angles.append(_angle(h, k, a))
            hip_angles.append(_angle(s or sh, h, k))
            thigh = _dist(h, k)
            thigh_ratios.append(thigh / L)
            if thigh > 1e-6:
                thigh_h.append(abs(k[0] - h[0]) / thigh)
        f.knee_angle = _mean(knee_angles)
        f.hip_angle = _mean(hip_angles)
        f.thigh_ratio = _mean(thigh_ratios)
        f.thigh_horizontal = _mean(thigh_h)

        # Arms
        wrists = [p(L_WR), p(R_WR)]
        shoulders = [ls or sh, rs or sh]
        ext, ups, downs, front = [], [], [], []
        for w, s in zip(wrists, shoulders):
            if w is None:
                continue
            ext.append(_dist(w, s) / L)
            above_hip = (hip[1] - w[1]) / L
            ups.append(above_hip)
            downs.append(-above_hip)
            lateral = abs(w[0] - (sh[0] + hip[0]) / 2) / L
            # Raised forearms at torso height (hanging arms sit at/below hip level and don't count).
            front.append(1.0 if (0.15 <= above_hip <= 1.0 and lateral <= 0.9) else 0.0)
        f.arm_extension = max(ext) if ext else None
        f.wrist_up = max(ups) if ups else None
        f.wrist_down = max(downs) if downs else None
        f.hands_front = sum(front) / 2.0  # a hidden wrist counts as "not in front"
        if wrists[0] and wrists[1]:
            f.hands_gap = _dist(wrists[0], wrists[1]) / L

        # Motion over the recent window
        rel = [((w[0] - hip[0]) / L, (w[1] - hip[1]) / L) if w else None for w in wrists]
        self.history.append(_HistoryEntry(t=t, hip=hip, torso=L, wrists_rel=rel))
        self._motion(f, t)
        return f

    def _motion(self, f: PoseFeatures, t: float) -> None:
        recent = [e for e in self.history if t - e.t <= self.window_seconds]
        if len(recent) < 2 or recent[-1].t - recent[0].t < 0.2:
            return
        first, last = recent[0], recent[-1]
        dt = last.t - first.t
        torso = sorted(e.torso for e in recent)[len(recent) // 2]
        f.speed = _dist(first.hip, last.hip) / torso / dt

        # Keypoints jitter by a few pixels every frame; summing raw step lengths would turn that
        # noise into "hand activity". Smooth each wrist track (3-sample moving average) first, so
        # only sustained, low-frequency hand motion (actual manipulation) is measured.
        smoothed = [self._smoothed_wrists(recent, j) for j in range(len(recent))]
        moves, span = 0.0, 0.0
        for j in range(1, len(recent)):
            step = recent[j].t - recent[j - 1].t
            if step <= 0:
                continue
            d = [_dist(wa, wb) for wa, wb in zip(smoothed[j - 1], smoothed[j]) if wa and wb]
            if d:
                moves += max(d)
                span += step
        if span > 0:
            f.hand_activity = moves / span

    @staticmethod
    def _smoothed_wrists(entries: List[_HistoryEntry], j: int) -> List[Optional[Point]]:
        out: List[Optional[Point]] = []
        for side in range(2):
            pts = [e.wrists_rel[side] for e in entries[max(0, j - 1): j + 2] if e.wrists_rel[side]]
            out.append((sum(p[0] for p in pts) / len(pts), sum(p[1] for p in pts) / len(pts)) if pts else None)
        return out
