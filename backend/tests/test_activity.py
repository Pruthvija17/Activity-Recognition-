"""Unit tests for the activity engine using synthetic COCO-17 skeletons.

Skeletons are built in image coordinates (y grows down) with a torso length of 100 px, and
fed through TrackFeatures at 8 samples/s so motion features are exercised too.
"""
import math

import numpy as np
import pytest

from services.activity.features import TrackFeatures
from services.activity.rules import (
    HANDLING, LOW_REACH, PICKING, PLACING, REACHING, SITTING, STANDING, UNKNOWN, WALKING,
)
from services.activity.segmenter import Sample, SegmentConfig, segment_track
from services.activity.unknown import (
    REASON_AMBIGUOUS, REASON_LOW_PROB, REASON_NOT_VISIBLE, REASON_UPPER_BODY, OpenSetClassifier,
)

DT = 0.125  # 8 samples per second


def skeleton(x0=300.0, y0=300.0, *, trunk_deg=0.0, knees=None, ankles=None, wrists=None):
    """Return (kxy[17,2], kconf[17], box). Unspecified face keypoints are marked invisible."""
    k = np.zeros((17, 2))
    conf = np.full(17, 0.9)
    conf[0:5] = 0.0  # face not needed
    rad = math.radians(trunk_deg)
    sh = (x0 + 100 * math.sin(rad), y0 - 100 * math.cos(rad))
    k[5], k[6] = (sh[0] - 25, sh[1]), (sh[0] + 25, sh[1])
    k[11], k[12] = (x0 - 15, y0), (x0 + 15, y0)
    k[13], k[14] = knees or ((x0 - 15, y0 + 90), (x0 + 15, y0 + 90))
    k[15], k[16] = ankles or ((x0 - 15, y0 + 180), (x0 + 15, y0 + 180))
    k[9], k[10] = wrists or ((x0 - 35, y0 + 10), (x0 + 35, y0 + 10))
    k[7], k[8] = (k[5] + k[9]) / 2, (k[6] + k[10]) / 2
    xs, ys = k[5:, 0], k[5:, 1]
    box = (xs.min() - 10, sh[1] - 40, xs.max() + 10, ys.max() + 5)
    return k, conf, box


def run(frames, sensitivity="Medium"):
    """Feed a list of skeletons through features + classifier; return predictions."""
    tf = TrackFeatures()
    clf = OpenSetClassifier(sensitivity=sensitivity)
    preds = []
    for i, (k, c, box) in enumerate(frames):
        preds.append(clf.predict(tf.update(i * DT, k, c, box)))
    return preds


def settled(preds):
    """Label after motion features have warmed up (last sample)."""
    return preds[-1]


def test_standing_still():
    p = settled(run([skeleton()] * 16))
    assert p.label == STANDING, p


def test_walking_moves_body():
    frames = [skeleton(x0=200 + 1.6 * 100 * i * DT) for i in range(16)]  # 1.6 torso lengths / s
    assert settled(run(frames)).label == WALKING


def test_sitting_side_view():
    x0, y0 = 300, 300
    f = skeleton(knees=((x0 + 90, y0 + 5), (x0 + 95, y0 + 5)), ankles=((x0 + 90, y0 + 95), (x0 + 95, y0 + 95)))
    assert settled(run([f] * 16)).label == SITTING


def test_sitting_facing_camera():
    x0, y0 = 300, 300
    f = skeleton(knees=((x0 - 20, y0 + 30), (x0 + 20, y0 + 30)), ankles=((x0 - 20, y0 + 110), (x0 + 20, y0 + 110)))
    assert settled(run([f] * 16)).label == SITTING


def test_reaching_arm_out_and_up():
    x0, y0 = 300, 300
    f = skeleton(wrists=((x0 - 35, y0 + 10), (x0 + 125, y0 - 90)))
    assert settled(run([f] * 16)).label == REACHING


def test_low_reach_when_bending_with_hands_low():
    x0, y0 = 300, 300
    f = skeleton(trunk_deg=45, wrists=((x0 + 80, y0 + 60), (x0 + 95, y0 + 55)))
    assert settled(run([f] * 16)).label == LOW_REACH


def test_handling_hands_busy_in_front():
    """Hands working in front of the torso: ~1.5 Hz movements of about +-0.2 torso lengths."""
    x0, y0 = 300, 300
    frames = []
    for i in range(24):
        d = 20 * math.sin(2 * math.pi * 1.5 * i * DT)
        frames.append(skeleton(wrists=((x0 - 15 + d, y0 - 50 - d / 2), (x0 + 15 - d, y0 - 50 + d / 2))))
    assert settled(run(frames)).label == HANDLING


def test_keypoint_jitter_is_not_hand_activity():
    """Hands held still in front plus +-5 px detector jitter must not count as handling."""
    rng = np.random.default_rng(0)
    x0, y0 = 300, 300
    frames = []
    for _ in range(24):
        k, c, box = skeleton(wrists=((x0 - 10, y0 - 70), (x0 + 10, y0 - 70)))
        k += rng.uniform(-5, 5, size=k.shape)
        frames.append((k, c, box))
    assert settled(run(frames)).label != HANDLING


def test_fall_like_horizontal_torso_is_unknown():
    x0, y0 = 300, 300
    f = skeleton(trunk_deg=90, wrists=((x0 + 60, y0 + 10), (x0 + 70, y0 - 10)))
    p = settled(run([f] * 16))
    assert p.label == UNKNOWN
    assert p.reason in (REASON_AMBIGUOUS, REASON_LOW_PROB)


def test_invisible_torso_is_unknown():
    k, c, box = skeleton()
    c[5:7] = 0.1  # shoulders not detected
    p = settled(run([(k, c, box)] * 4))
    assert p.label == UNKNOWN and p.reason == REASON_NOT_VISIBLE


def test_probabilities_are_a_distribution():
    p = settled(run([skeleton()] * 16))
    assert abs(sum(p.probs.values()) - 1.0) < 1e-9
    assert 0.0 <= p.confidence <= 1.0


def test_sensitivity_changes_unknown_decisions():
    """An ambiguous pose: arm half-extended at chest height while standing."""
    x0, y0 = 300, 300
    f = skeleton(wrists=((x0 - 35, y0 + 10), (x0 + 85, y0 - 60)))
    low = settled(run([f] * 16, sensitivity="Low"))
    high = settled(run([f] * 16, sensitivity="High"))
    assert low.entropy == pytest.approx(high.entropy)
    assert low.label != UNKNOWN
    assert high.label == UNKNOWN


# ── segmenter ────────────────────────────────────────────────────────────────

CFG = SegmentConfig(sample_interval=DT)


def stream(spec, t0=0.0, carry=0.0):
    """spec: list of (label, seconds). Returns samples at 8/s with prob 0.9 for the label."""
    out, t = [], t0
    for label, secs in spec:
        for _ in range(int(round(secs / DT))):
            out.append(Sample(t=t, frame=int(t * 24), label=label, confidence=0.9,
                              probs={label: 0.9}, carry=carry))
            t += DT
    return out


def labels(segs):
    return [s.label for s in segs]


def test_segments_have_start_end_and_duration():
    segs = segment_track(stream([(WALKING, 3.0), (STANDING, 2.0)]), CFG)
    assert labels(segs) == [WALKING, STANDING]
    assert segs[0].start == 0.0 and segs[0].end == pytest.approx(3.0)
    assert segs[1].end == pytest.approx(5.0)
    assert segs[0].confidence == pytest.approx(0.9)


def test_single_sample_flicker_is_smoothed_away():
    samples = stream([(STANDING, 2.0), (REACHING, DT), (STANDING, 2.0)])
    assert labels(segment_track(samples, CFG)) == [STANDING]


def test_short_event_is_absorbed_into_longer_neighbour():
    samples = stream([(WALKING, 3.0), (REACHING, 0.5), (STANDING, 1.5)])
    assert REACHING not in labels(segment_track(samples, CFG))


def test_gap_splits_events():
    samples = stream([(WALKING, 2.0)]) + stream([(WALKING, 2.0)], t0=5.0)
    segs = segment_track(samples, CFG)
    assert len(segs) == 2 and segs[0].end <= 2.0 + DT and segs[1].start == 5.0


def test_lone_short_fragment_is_dropped():
    assert segment_track(stream([(WALKING, 0.5)]), CFG) == []


def test_unknown_runs_become_unknown_events():
    segs = segment_track(stream([(STANDING, 2.0), (UNKNOWN, 2.0), (STANDING, 2.0)]), CFG)
    assert labels(segs) == [STANDING, UNKNOWN, STANDING]


def test_pick_when_carrying_after_low_reach():
    samples = (stream([(STANDING, 2.0)], carry=0.0)
               + stream([(LOW_REACH, 1.5)], t0=2.0, carry=0.0)
               + stream([(WALKING, 2.0)], t0=3.5, carry=0.8))
    segs = segment_track(samples, CFG)
    assert PICKING in labels(segs)


def test_place_when_carrying_before_low_reach():
    samples = (stream([(WALKING, 2.0)], carry=0.8)
               + stream([(LOW_REACH, 1.5)], t0=2.0, carry=0.0)
               + stream([(STANDING, 2.0)], t0=3.5, carry=0.0))
    segs = segment_track(samples, CFG)
    assert PLACING in labels(segs)
    placing = next(s for s in segs if s.label == PLACING)
    assert placing.confidence > 0.8  # clear context keeps confidence high


def test_pick_place_without_context_has_reduced_confidence():
    segs = segment_track(stream([(LOW_REACH, 2.0)]), CFG)
    assert segs[0].label in (PICKING, PLACING)
    assert segs[0].confidence < 0.6


def _upper_body(frames):
    """Hide hips, knees and ankles (a person close to a desk webcam)."""
    out = []
    for k, c, box in frames:
        c = c.copy()
        c[11:17] = 0.0
        out.append((k, c, box))
    return out


def test_upper_body_reaching_is_still_recognised():
    x0, y0 = 300, 300
    f = skeleton(wrists=((x0 - 35, y0 + 10), (x0 + 125, y0 - 90)))
    p = settled(run(_upper_body([f] * 16)))
    assert p.label == REACHING


def test_upper_body_handling_is_still_recognised():
    x0, y0 = 300, 300
    frames = []
    for i in range(24):
        d = 20 * math.sin(2 * math.pi * 1.5 * i * DT)
        frames.append(skeleton(wrists=((x0 - 15 + d, y0 - 50 - d / 2), (x0 + 15 - d, y0 - 50 + d / 2))))
    assert settled(run(_upper_body(frames))).label == HANDLING


def test_upper_body_idle_is_unknown_with_reason():
    """Arms down, lower body hidden: standing vs sitting can't be told -> Unknown, and says why."""
    p = settled(run(_upper_body([skeleton()] * 16)))
    assert p.label == UNKNOWN and p.reason == REASON_UPPER_BODY


def test_unknown_segments_carry_their_reason():
    samples = stream([(STANDING, 2.0), (UNKNOWN, 2.0)])
    for s_ in samples:
        if s_.label == UNKNOWN:
            s_.reason = REASON_UPPER_BODY
    segs = segment_track(samples, CFG)
    assert segs[-1].label == UNKNOWN and segs[-1].note == REASON_UPPER_BODY
    assert segs[0].note == ""
