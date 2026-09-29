"""Turn per-sample predictions of one tracked person into activity events.

Steps (per contiguous stretch of a track):
  1. majority-vote smoothing over a short sliding window,
  2. hysteresis: a label change must persist for `hysteresis_seconds`, else it is absorbed,
  3. minimum event duration: shorter runs are absorbed into the longer neighbour,
  4. pick/place resolution for LOW_REACH runs using the hands' carrying posture before vs after
     (object carried before a low reach -> placing; carried after -> picking).
A gap longer than `max_gap_seconds` (person lost / left the view) always ends an event.
"""
from collections import Counter
from dataclasses import dataclass, field
from typing import Dict, List

from .rules import LOW_REACH, PICKING, PLACING, UNKNOWN


@dataclass
class Sample:
    t: float
    frame: int
    label: str
    confidence: float          # probability of `label` (best known class prob for Unknown)
    probs: Dict[str, float]
    carry: float = 0.0


@dataclass
class SegmentConfig:
    sample_interval: float = 0.125
    smoothing_seconds: float = 0.6
    hysteresis_seconds: float = 0.4
    min_event_seconds: float = 1.0
    max_gap_seconds: float = 1.0
    pick_place_context_seconds: float = 2.0


@dataclass
class Segment:
    label: str
    start: float
    end: float
    frame_start: int
    frame_end: int
    confidence: float
    samples: List[Sample] = field(default_factory=list, repr=False)

    @property
    def duration(self) -> float:
        return self.end - self.start


def _chunks(samples: List[Sample], max_gap: float) -> List[List[Sample]]:
    chunks: List[List[Sample]] = []
    for s in samples:
        if chunks and s.t - chunks[-1][-1].t <= max_gap:
            chunks[-1].append(s)
        else:
            chunks.append([s])
    return chunks


def _smooth(labels: List[str], half: int) -> List[str]:
    if half <= 0:
        return list(labels)
    out = []
    for i, own in enumerate(labels):
        counts = Counter(labels[max(0, i - half): i + half + 1])
        best, n = counts.most_common(1)[0]
        out.append(own if counts[own] == n else best)
    return out


def _runs(labels: List[str]) -> List[List]:
    runs: List[List] = []
    for i, lab in enumerate(labels):
        if runs and runs[-1][0] == lab:
            runs[-1][2] = i + 1
        else:
            runs.append([lab, i, i + 1])
    return runs


def _merge_same(runs: List[List]) -> List[List]:
    out: List[List] = []
    for r in runs:
        if out and out[-1][0] == r[0]:
            out[-1][2] = r[2]
        else:
            out.append(list(r))
    return out


def _absorb_short(runs: List[List], too_short) -> List[List]:
    """Repeatedly merge the shortest too-short run into its longer neighbour."""
    runs = _merge_same(runs)
    while len(runs) > 1:
        short = [i for i, r in enumerate(runs) if too_short(r)]
        if not short:
            break
        i = min(short, key=lambda k: runs[k][2] - runs[k][1])
        left = runs[i - 1] if i > 0 else None
        right = runs[i + 1] if i + 1 < len(runs) else None
        target = left if right is None or (left is not None and (left[2] - left[1]) >= (right[2] - right[1])) else right
        runs[i][0] = target[0]
        runs = _merge_same(runs)
    return runs


def _run_confidence(label: str, samples: List[Sample]) -> float:
    if label == UNKNOWN:
        vals = [s.confidence for s in samples]
    else:
        vals = [s.probs.get(label, 0.0) for s in samples]
    return sum(vals) / len(vals) if vals else 0.0


def _segment_chunk(chunk: List[Sample], cfg: SegmentConfig) -> List[Segment]:
    dt = cfg.sample_interval
    half = int(round(cfg.smoothing_seconds / dt / 2))
    labels = _smooth([s.label for s in chunk], half)
    runs = _runs(labels)

    min_samples = max(1, int(round(cfg.hysteresis_seconds / dt)))
    runs = _absorb_short(runs, lambda r: r[2] - r[1] < min_samples)

    def run_seconds(r) -> float:
        end = chunk[r[2]].t if r[2] < len(chunk) else chunk[-1].t + dt
        return end - chunk[r[1]].t

    runs = _absorb_short(runs, lambda r: run_seconds(r) < cfg.min_event_seconds)

    segments = []
    for label, i0, i1 in runs:
        part = chunk[i0:i1]
        end = chunk[i1].t if i1 < len(chunk) else chunk[-1].t + dt
        segments.append(Segment(
            label=label,
            start=chunk[i0].t,
            end=end,
            frame_start=part[0].frame,
            frame_end=part[-1].frame,
            confidence=_run_confidence(label, part),
            samples=part,
        ))
    # A lone fragment shorter than the minimum duration is tracking noise, not an event.
    if len(segments) == 1 and segments[0].duration < cfg.min_event_seconds:
        return []
    return segments


def _resolve_pick_place(seg: Segment, all_samples: List[Sample], cfg: SegmentConfig) -> None:
    ctx = cfg.pick_place_context_seconds
    before = [s.carry for s in all_samples if seg.start - ctx <= s.t < seg.start]
    after = [s.carry for s in all_samples if seg.end < s.t <= seg.end + ctx]
    carry_before = sum(before) / len(before) if before else 0.0
    carry_after = sum(after) / len(after) if after else 0.0
    diff = carry_after - carry_before
    seg.label = PICKING if diff >= 0 else PLACING
    # Weak or missing context -> lower confidence, so the event is sent for review.
    certainty = min(1.0, abs(diff) / 0.4)
    seg.confidence = seg.confidence * (0.6 + 0.4 * certainty)


def segment_track(samples: List[Sample], cfg: SegmentConfig) -> List[Segment]:
    samples = sorted(samples, key=lambda s: s.t)
    segments: List[Segment] = []
    for chunk in _chunks(samples, cfg.max_gap_seconds):
        segments.extend(_segment_chunk(chunk, cfg))
    for seg in segments:
        if seg.label == LOW_REACH:
            _resolve_pick_place(seg, samples, cfg)
    return segments
