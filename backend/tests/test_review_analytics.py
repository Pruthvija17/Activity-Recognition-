import uuid

import pytest

import models
from database import SessionLocal
from services.jobs import save_events

THRESHOLD = 0.60


def _evt(person, activity, start, end, conf):
    return {"person_id": person, "activity": activity, "confidence": conf,
            "start": f"00:00:{int(start):02d}", "end": f"00:00:{int(end):02d}",
            "start_seconds": start, "end_seconds": end, "frame_start": int(start * 24)}


@pytest.fixture
def experiment(client):
    """A completed experiment with known events (inserted through the real save path)."""
    exp_id = f"VID_t{uuid.uuid4().hex[:6]}"
    db = SessionLocal()
    try:
        db.add(models.Experiment(id=exp_id, name="lab.mp4", video_filename="lab.mp4", status="completed"))
        db.flush()
        save_events(db, exp_id, [
            _evt("Person 01", "Walking", 0, 3, 0.90),
            _evt("Person 01", "Unknown", 3, 5, 0.30),
            _evt("Person 02", "Standing", 0, 4, 0.55),   # below threshold -> pending
            _evt("Person 02", "Reaching", 4, 6, 0.80),
        ], THRESHOLD)
        db.commit()
    finally:
        db.close()
    return exp_id


def _pending(client, exp_id):
    return {e["activity_type"]: e for e in client.get(f"/api/review/events?experiment_id={exp_id}").json()}


def _analytics(client, exp_id):
    return client.get(f"/api/analytics?experiment_id={exp_id}").json()


def test_unknown_and_low_confidence_events_are_pending(client, experiment):
    pending = _pending(client, experiment)
    assert set(pending) == {"Unknown", "Standing"}
    assert pending["Standing"]["person"] == "Person 02"
    assert pending["Standing"]["video"] == "lab.mp4"


def test_confirm_keeps_label_and_leaves_queue(client, experiment):
    evt = _pending(client, experiment)["Unknown"]
    r = client.post(f"/api/review/events/{evt['id']}", json={"action": "confirm"})
    assert r.status_code == 200
    body = r.json()
    assert body["review_status"] == "confirmed" and body["activity_type"] == "Unknown"
    assert body["reviewed_at"].endswith("Z")
    assert "Unknown" not in _pending(client, experiment)
    assert _analytics(client, experiment)["unknown_events"] == 1


def test_reclassify_keeps_original_prediction(client, experiment):
    evt = _pending(client, experiment)["Standing"]
    r = client.post(f"/api/review/events/{evt['id']}", json={"action": "reclassify", "activity": "Sitting"})
    body = r.json()
    assert body["activity_type"] == "Sitting"
    assert body["original_activity"] == "Standing"
    assert body["review_status"] == "reclassified"
    names = {d["name"] for d in _analytics(client, experiment)["activity_distribution"]}
    assert "Sitting" in names and "Standing" not in names

    reviewed = client.get(f"/api/review/events?experiment_id={experiment}&status=reviewed").json()
    assert [e["id"] for e in reviewed] == [evt["id"]]


def test_reclassify_rejects_unknown_activity_names(client, experiment):
    evt = _pending(client, experiment)["Standing"]
    r = client.post(f"/api/review/events/{evt['id']}", json={"action": "reclassify", "activity": "Dancing"})
    assert r.status_code == 400
    r = client.post(f"/api/review/events/{evt['id']}", json={"action": "delete"})
    assert r.status_code == 422


def test_reject_excludes_event_from_analytics(client, experiment):
    before = _analytics(client, experiment)
    evt = _pending(client, experiment)["Unknown"]
    client.post(f"/api/review/events/{evt['id']}", json={"action": "reject"})
    after = _analytics(client, experiment)
    assert after["total_events"] == before["total_events"] - 1
    assert after["rejected_events"] == 1
    assert after["unknown_events"] == 0
    person1 = next(p for p in after["person_stats"] if p["name"] == "Person 01")
    assert person1["events"] == 1 and person1["unknowns"] == 0


def test_review_unknown_event_404(client):
    assert client.post("/api/review/events/nope", json={"action": "confirm"}).status_code == 404


def test_analytics_figures(client, experiment):
    a = _analytics(client, experiment)
    assert a["total_events"] == 4
    assert a["people_count"] == 2
    assert a["pending_review"] == 2
    assert a["total_activity_seconds"] == pytest.approx(3 + 2 + 4 + 2)
    dist = {d["name"]: d for d in a["activity_distribution"]}
    assert dist["Walking"]["seconds"] == pytest.approx(3.0)
    assert dist["Walking"]["avg_confidence"] == pytest.approx(0.90)
    assert sum(b["count"] for b in a["confidence_histogram"]) == 4
    p2 = next(p for p in a["person_stats"] if p["name"] == "Person 02")
    assert p2["top_activity"] == "Standing" and p2["active_seconds"] == pytest.approx(6.0)


def test_analytics_unknown_experiment_404(client):
    assert client.get("/api/analytics?experiment_id=VID_nope").status_code == 404


def test_dashboard_summary(client, experiment):
    d = client.get("/api/dashboard/summary").json()
    assert d["experiments"]["total"] >= 1
    assert d["people_detected"] >= 2
    assert d["pending_review"] >= 2
    assert 0 < d["avg_confidence"] <= 1
    assert any(e["experiment_id"] == experiment for e in d["recent_events"])


def test_old_unsafe_event_endpoints_are_gone(client):
    assert client.post("/events/", json={}).status_code == 405
    assert client.put("/events/x", json={"activity_type": "Walking"}).status_code in (404, 405)
    assert client.post("/experiments/", json={"id": "x", "name": "y"}).status_code == 405
