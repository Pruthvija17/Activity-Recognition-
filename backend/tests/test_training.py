"""Training pipeline end to end on synthetic pose sequences (no video / YOLO needed).

Synthetic data only proves the machinery works (windows, split by video, training, spec, loading,
engine switch); it says nothing about accuracy on real footage.
"""
import csv
import json
import math
import os
import random

import pytest
import torch

from services.activity.engine import ActivityEngine
from services.activity.features import TrackFeatures
from services.activity.rules import ACTIVITIES, UNKNOWN
from services.activity.sequence import FEATURE_DIM, feature_vector
from services.activity.temporal import TemporalModel, spec_path_for
from services.activity.unknown import OpenSetClassifier
from test_activity import skeleton
from training.dataset import feature_cache_path
from training.evaluate import markdown_report
from training.labels import read_labels
from training.train import InsufficientData, build_windows, save_model, train_model

FPS = 8.0
DT = 1 / FPS
STANDING, SITTING, WALKING, REACHING, PICKING, PLACING, HANDLING = ACTIVITIES


def _pose(kind: str, i: int, n: int, x0: float, y0: float, s: float):
    """Skeleton for sample i of n of an activity, with the person at (x0, y0) and scale s."""
    def sk(**kw):
        k, c, box = skeleton(x0, y0, **kw)
        # scale around the hip centre
        k = (k - [x0, y0]) * s + [x0, y0]
        return k, c, box

    phase = i / max(1, n - 1)
    if kind == STANDING:
        return sk()
    if kind == WALKING:
        return skeleton(x0 + 1.5 * 100 * s * i * DT, y0)
    if kind == SITTING:
        return sk(knees=((x0 + 90, y0 + 5), (x0 + 95, y0 + 5)), ankles=((x0 + 90, y0 + 95), (x0 + 95, y0 + 95)))
    if kind == REACHING:
        return sk(wrists=((x0 - 35, y0 + 10), (x0 + 125, y0 - 90)))
    if kind == HANDLING:
        d = 20 * math.sin(2 * math.pi * 1.5 * i * DT)
        return sk(wrists=((x0 - 15 + d, y0 - 50 - d / 2), (x0 + 15 - d, y0 - 50 + d / 2)))
    if kind in (PICKING, PLACING):
        # Picking: bend down with hands low, then rise carrying (hands together in front).
        # Placing: the reverse order. Identical poses - only the order differs.
        down_first = kind == PICKING
        bending = phase < 0.55 if down_first else phase >= 0.45
        if bending:
            return sk(trunk_deg=45, wrists=((x0 + 80, y0 + 60), (x0 + 95, y0 + 55)))
        return sk(wrists=((x0 - 8, y0 - 55), (x0 + 8, y0 - 55)))
    if kind == UNKNOWN:
        return sk(trunk_deg=90, wrists=((x0 + 60, y0 + 10), (x0 + 70, y0 - 10)))
    raise ValueError(kind)


SEGMENTS = [(STANDING, 3.0), (WALKING, 3.0), (SITTING, 3.0), (REACHING, 3.0),
            (PICKING, 2.5), (HANDLING, 3.0), (PLACING, 2.5), (UNKNOWN, 2.5)]


def make_video(tmp_path, name: str, seed: int, cache_dir: str):
    """Write a dummy 'video' file, its feature cache and its label rows."""
    rng = random.Random(seed)
    video = tmp_path / f"{name}.mp4"
    video.write_bytes(b"synthetic")
    tf = TrackFeatures()
    times, vectors, rows = [], [], []
    t = 0.0
    order = SEGMENTS[:]
    rng.shuffle(order)
    for kind, secs in order:
        n = int(secs * FPS)
        x0, y0, s = 250 + rng.uniform(-60, 60), 300 + rng.uniform(-40, 40), rng.uniform(0.8, 1.2)
        start = t
        for i in range(n):
            k, c, box = _pose(kind, i, n, x0, y0, s)
            k = k + [[rng.gauss(0, 2), rng.gauss(0, 2)] for _ in range(17)]
            times.append(round(t, 4))
            vectors.append(feature_vector(tf.update(t, k, c, box)))
            t += DT
        rows.append([str(video), f"{start + 0.01:.3f}", f"{t - DT:.3f}", kind, "Person 01"])
    with open(feature_cache_path(cache_dir, str(video)), "w", encoding="utf-8") as fh:
        json.dump({"video": str(video), "sample_interval": DT, "tracks": {"Person 01": {"t": times, "vectors": vectors}}}, fh)
    return rows


@pytest.fixture(scope="module")
def dataset(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("train")
    cache = str(tmp / "features")
    os.makedirs(cache)
    rows = []
    # 12 short sessions: enough windows per class for calibration to be meaningful.
    for v in range(12):
        rows += make_video(tmp, f"session{v}", seed=v, cache_dir=cache)
    labels = tmp / "labels.csv"
    with open(labels, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["video", "start_s", "end_s", "activity", "person"])
        w.writerows(rows)
    return tmp, str(labels), cache


@pytest.fixture(scope="module")
def trained(dataset):
    tmp, labels, cache = dataset
    windows, segments, fps = build_windows(labels, cache, window=16, stride=4)
    state, spec, test = train_model(windows, segments, window=16, stride=4, sample_fps=fps, epochs=60, seed=0)
    out = str(tmp / "model" / "activity_gru.pt")
    save_model(state, spec, out)
    return out, spec, test, windows


def test_feature_vector_layout():
    k, c, box = skeleton()
    v = feature_vector(TrackFeatures().update(0.0, k, c, box))
    assert len(v) == FEATURE_DIM and v[-2] == 1.0 and v[-1] == 0.0  # visible, not upper-body-only
    k2, c2, box2 = skeleton()
    c2[5:7] = 0.0  # no shoulders -> not visible -> all zeros
    assert feature_vector(TrackFeatures().update(0.0, k2, c2, box2)) == [0.0] * FEATURE_DIM


def test_labels_are_validated(tmp_path):
    bad = tmp_path / "bad.csv"
    bad.write_text("video,start_s,end_s,activity,person\nx.mp4,5,2,Dancing,\n", encoding="utf-8")
    with pytest.raises(ValueError) as e:
        read_labels(str(bad))
    assert "unknown activity" in str(e.value) and "line 2" in str(e.value)


def test_windows_cover_every_class(dataset):
    _, labels, cache = dataset
    windows, _, fps = build_windows(labels, cache, window=16, stride=4)
    counts = windows.counts()
    assert fps == FPS
    assert all(counts[a] > 0 for a in ACTIVITIES) and counts[UNKNOWN] > 0
    assert all(len(x) == 16 and len(x[0]) == FEATURE_DIM for x in windows.X)


def test_split_is_by_video_and_refuses_too_few_videos(dataset, trained):
    _, spec, _, _ = trained
    d = spec["data"]
    assert d["split"] == "by video"
    assert not set(d["train_videos"]) & set(d["test_videos"])
    assert not set(d["train_videos"]) & set(d["val_videos"])

    _, labels, cache = dataset
    windows, segments, fps = build_windows(labels, cache, window=16, stride=4)
    two = set(sorted(set(windows.groups))[:2])
    keep = [i for i, g in enumerate(windows.groups) if g in two]
    windows.X = [windows.X[i] for i in keep]
    windows.y = [windows.y[i] for i in keep]
    windows.groups = [windows.groups[i] for i in keep]
    with pytest.raises(InsufficientData):
        train_model(windows, [segments[i] for i in keep], window=16, stride=4, sample_fps=fps, epochs=1)


def test_trained_model_learns_synthetic_activities(trained):
    _, spec, test, _ = trained
    # Synthetic data is easy; this checks the training loop works, not real-world accuracy.
    assert test["accuracy"] >= 0.85, test
    # Picking and placing contain the same poses in opposite order: only a temporal model separates them.
    assert test["per_class"][PICKING]["recall"] >= 0.6
    assert test["per_class"][PLACING]["recall"] >= 0.6
    assert spec["metrics"]["test_accuracy"] == test["accuracy"]
    # A fall-like pose never seen in training must not be forced into a known class.
    o = test["open_set"]
    assert o["unknown_windows"] >= 1 and o["unknown_recall"] == 1.0, o
    assert o["false_unknown_rate"] <= 0.2, o
    assert spec["feature_dim"] == FEATURE_DIM and spec["classes"] == list(ACTIVITIES)


def test_report_is_written(trained):
    _, spec, test, _ = trained
    md = markdown_report(spec, test)
    assert "macro F1" in md and "Confusion matrix" in md and "Picking up an object" in md


def test_model_loads_and_drives_the_engine(trained):
    out, _, _, windows = trained
    model, err = TemporalModel.load(out)
    assert err is None and model is not None
    engine = ActivityEngine(OpenSetClassifier(), model)
    assert engine.trained and "Trained temporal model" in engine.name

    probs, novelty = model.analyze(windows.X[0])
    assert set(probs) == set(ACTIVITIES) and abs(sum(probs.values()) - 1) < 1e-5
    assert novelty >= 0.0

    state = engine.new_track()
    labels = []
    rng = random.Random(1)
    for i in range(24):
        k, c, box = _pose(SITTING, i, 24, 300, 300, 1.0)
        # Real detector output always jitters a little; a perfectly still pose is itself "unfamiliar".
        k = k + [[rng.gauss(0, 2), rng.gauss(0, 2)] for _ in range(17)]
        _, pred, _ = engine.observe(state, i * DT, k, c, box)
        labels.append(pred.label)
    assert labels[-1] == SITTING


def test_incompatible_spec_is_refused(trained, tmp_path):
    out, spec, _, _ = trained
    bad = str(tmp_path / "old_model.pt")
    torch.save(torch.load(out, weights_only=True), bad)
    with open(spec_path_for(bad), "w", encoding="utf-8") as fh:
        json.dump({**spec, "feature_version": 0}, fh)
    model, err = TemporalModel.load(bad)
    assert model is None and "retrain" in err


def test_missing_model_means_rules(tmp_path):
    model, err = TemporalModel.load(str(tmp_path / "nothing.pt"))
    assert model is None and err is None


def test_pipeline_switches_engine_and_back(trained, client):
    import runtime

    out, _, _, _ = trained
    try:
        runtime.ai_pipeline.reload_activity_model(out)
        s = client.get("/api/system/status").json()
        assert s["trained_activity_model"] is True
        assert "Trained temporal model" in s["activity_engine"]
        assert s["activity_model_info"]["metrics"]["test_accuracy"] is not None
    finally:
        runtime.ai_pipeline.reload_activity_model(str(tmp_path_placeholder()))
    s = client.get("/api/system/status").json()
    assert s["trained_activity_model"] is False and s["activity_engine"] == "Rule-based pose baseline"


def tmp_path_placeholder():
    return os.path.join(os.path.dirname(__file__), "no_such_model.pt")


def test_training_summary_counts_reviewed_labels(client, sample_video):
    # Upload a real file so a reviewed event has a video to point at.
    with open(sample_video, "rb") as f:
        vid = client.post("/api/videos/upload", files={"file": ("lab.mp4", f.read(), "video/mp4")}).json()["video_id"]
    from database import SessionLocal
    from services.jobs import save_events

    db = SessionLocal()
    try:
        save_events(db, vid, [{"person_id": "Person 01", "activity": "Unknown", "confidence": 0.3, "start": "00:00:00",
                               "end": "00:00:02", "start_seconds": 0.0, "end_seconds": 2.0}], 0.6)
        db.commit()
    finally:
        db.close()
    before = client.get("/api/training/summary").json()
    evt = next(e for e in client.get(f"/api/review/events?experiment_id={vid}").json())
    client.post(f"/api/review/events/{evt['id']}", json={"action": "reclassify", "activity": "Sitting"})
    after = client.get("/api/training/summary").json()
    sitting = lambda s: next(a["segments"] for a in s["per_activity"] if a["activity"] == "Sitting")  # noqa: E731
    assert sitting(after) == sitting(before) + 1
    assert after["ready"] is False  # far below the recommended amount of data

    csv_text = client.get("/api/training/labels.csv").content.decode()
    assert csv_text.splitlines()[0] == "video,start_s,end_s,activity,person"
    assert any(",Sitting,Person 01" in line for line in csv_text.splitlines())
