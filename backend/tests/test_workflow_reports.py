import csv
import io
import time
import uuid

import pytest

import models
from database import SessionLocal
from services import media
from services.jobs import save_events
from services.workflow import ObservedStep, evaluate

WALK, REACH, PICK, HANDLE, PLACE = (
    "Walking", "Reaching", "Picking up an object", "Handling experimental equipment", "Placing an object")
FLOW = [WALK, REACH, PICK, HANDLE, PLACE]


def obs(*spec, person="Person 01"):
    """spec: activity names, each lasting 2 s back to back."""
    return [ObservedStep(a, i * 2.0, i * 2.0 + 2.0, person) for i, a in enumerate(spec)]


# ── workflow algorithm ───────────────────────────────────────────────────────

def test_exact_workflow_is_compliant():
    r = evaluate(FLOW, obs(*FLOW))
    assert r["is_compliant"] and r["deviation_count"] == 0
    assert r["completion"] == 1.0 and r["next_expected_step"] is None
    assert "matches" in r["message"]


def test_repeats_and_consecutive_duplicates_are_not_deviations():
    r = evaluate(FLOW, obs(WALK, WALK, REACH, PICK, WALK, HANDLE, PLACE))
    assert r["is_compliant"]
    assert r["observed_sequence"] == [WALK, REACH, PICK, WALK, HANDLE, PLACE]
    assert [n["type"] for n in r["notes"]] == ["repeated"]


def test_missing_step_reports_where_it_was_expected():
    r = evaluate(FLOW, obs(WALK, REACH, HANDLE, PLACE))
    assert not r["is_compliant"]
    [d] = r["deviations"]
    assert d["type"] == "missing" and d["activity"] == PICK
    assert d["time"] == 4.0  # when the next matched step (Handling) started
    assert "operator review required" in r["message"]
    assert r["next_expected_step"] == PICK


def test_out_of_order_step():
    r = evaluate(FLOW, obs(WALK, PICK, REACH, HANDLE, PLACE))
    types = sorted(d["type"] for d in r["deviations"])
    assert types == ["out_of_order"]
    assert r["deviations"][0]["activity"] in (REACH, PICK)


def test_unknown_and_unexpected_activities():
    r = evaluate(FLOW, obs(WALK, REACH, "Unknown", PICK, "Sitting", HANDLE, PLACE))
    by_type = {d["type"]: d for d in r["deviations"]}
    assert set(by_type) == {"unknown", "unexpected"}
    assert by_type["unknown"]["time"] == 4.0
    assert by_type["unexpected"]["activity"] == "Sitting"
    assert r["completion"] == 1.0  # all expected steps still happened


def test_nothing_observed():
    r = evaluate(FLOW, [])
    assert r["completion"] == 0.0 and r["deviation_count"] == len(FLOW)


# ── API: detail, workflow config, reports ────────────────────────────────────

def _evt(person, activity, start, end, conf):
    return {"person_id": person, "activity": activity, "confidence": conf,
            "start": f"00:00:{int(start):02d}", "end": f"00:00:{int(end):02d}",
            "start_seconds": start, "end_seconds": end, "frame_start": int(start * 24)}


@pytest.fixture
def experiment(client):
    exp_id = f"VID_w{uuid.uuid4().hex[:6]}"
    db = SessionLocal()
    try:
        db.add(models.Experiment(id=exp_id, name="lab run.mp4", video_filename="lab run.mp4", status="completed",
                                 duration_seconds=12.0, engine="Rule-based pose baseline"))
        db.flush()
        save_events(db, exp_id, [
            _evt("Person 01", WALK, 0, 2, 0.9),
            _evt("Person 01", REACH, 2, 4, 0.85),
            _evt("Person 01", "Unknown", 4, 6, 0.3),
            _evt("Person 01", HANDLE, 6, 9, 0.5),     # low confidence -> pending
            _evt("Person 02", "Standing", 0, 12, 0.95),
        ], 0.6)
        db.commit()
    finally:
        db.close()
    return exp_id


def test_experiment_detail(client, experiment):
    d = client.get(f"/api/experiments/{experiment}").json()
    assert d["experiment"]["video_id"] == experiment
    assert [p["label"] for p in d["people"]] == ["Person 01", "Person 02"]
    assert len(d["events"]) == 5
    assert d["workflow"]["configured"] is False
    assert client.get("/api/experiments/VID_nope").status_code == 404


def test_workflow_configuration_round_trip(client, experiment):
    r = client.put(f"/api/experiments/{experiment}/workflow",
                   json={"expected_sequence": [WALK, REACH, HANDLE]})
    assert r.status_code == 200
    body = r.json()
    assert body["configured"] and body["expected_sequence"] == [WALK, REACH, HANDLE]
    # Combined view: Person 02's Standing and the Unknown are flagged, all three steps done
    assert body["completion"] == 1.0
    assert {d["type"] for d in body["deviations"]} == {"unknown", "unexpected"}

    person1 = client.get(f"/api/experiments/{experiment}/workflow",
                         params={"person_id": f"{experiment}_Person_01"}).json()
    assert {d["type"] for d in person1["deviations"]} == {"unknown"}

    assert client.put(f"/api/experiments/{experiment}/workflow",
                      json={"expected_sequence": ["Dancing"]}).status_code == 400
    assert client.put(f"/api/experiments/{experiment}/workflow",
                      json={"expected_sequence": []}).status_code == 422
    reset = client.delete(f"/api/experiments/{experiment}/workflow").json()
    assert reset["configured"] is False


def test_report_json(client, experiment):
    r = client.get(f"/api/reports/{experiment}").json()
    assert r["report_id"] == f"REP-{experiment}"
    assert r["experiment"]["video"] == "lab run.mp4"
    assert r["participants"]["count"] == 2
    assert r["summary"]["total_events"] == 5
    assert len(r["exceptions"]["unknown_events"]) == 1
    assert [e["activity"] for e in r["exceptions"]["low_confidence_events"]] == [HANDLE]
    assert r["review_status"]["unresolved"] == 2
    assert r["workflow"]["expected_sequence"]


def test_report_excludes_rejected_events(client, experiment):
    pending = client.get(f"/api/review/events?experiment_id={experiment}").json()
    unknown = next(e for e in pending if e["activity_type"] == "Unknown")
    client.post(f"/api/review/events/{unknown['id']}", json={"action": "reject"})
    r = client.get(f"/api/reports/{experiment}").json()
    assert r["summary"]["total_events"] == 4
    assert r["review_status"]["rejected"] == 1
    assert all(e["activity"] != "Unknown" for e in r["activity_log"])


def test_report_csv(client, experiment):
    r = client.get(f"/api/reports/{experiment}/csv")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/csv")
    assert "attachment" in r.headers["content-disposition"] and ".csv" in r.headers["content-disposition"]
    text = r.content.decode("utf-8-sig")
    rows = list(csv.DictReader(io.StringIO(text)))
    assert len(rows) == 5
    assert rows[0]["video"] == "lab run.mp4" and rows[0]["experiment_id"] == experiment


def test_report_pdf(client, experiment):
    r = client.get(f"/api/reports/{experiment}/pdf")
    assert r.status_code == 200
    assert r.headers["content-type"] == "application/pdf"
    assert r.content.startswith(b"%PDF") and len(r.content) > 2000


def test_report_list_and_unfinished_experiment(client, experiment):
    listed = {x["experiment_id"]: x for x in client.get("/api/reports").json()}
    assert listed[experiment]["events"] == 5 and listed[experiment]["people"] == 2
    db = SessionLocal()
    try:
        db.add(models.Experiment(id="VID_notdone", name="x.mp4", status="uploaded"))
        db.commit()
    finally:
        db.close()
    assert client.get("/api/reports/VID_notdone").status_code == 409
    assert client.get("/api/reports/VID_missing/pdf").status_code == 404


# ── browser-playable previews ────────────────────────────────────────────────

def test_codec_detection_on_opencv_video(sample_video):
    codec = media.probe_codec(sample_video)
    assert codec == "mpeg4"
    assert media.browser_playable(sample_video, codec) is False
    assert media.browser_playable("clip.mp4", "h264") is True
    assert media.browser_playable("clip.avi", "h264") is False


@pytest.mark.skipif(not media.ffmpeg_available(), reason="ffmpeg not installed")
def test_processing_creates_h264_preview(client, sample_video):
    with open(sample_video, "rb") as f:
        up = client.post("/api/videos/upload", files={"file": ("opencv.mp4", f.read(), "video/mp4")}).json()
    assert up["codec"] == "mpeg4" and up["preview_status"] == "pending" and up["playable"] is False
    client.post(f"/api/videos/{up['video_id']}/process")
    deadline = time.time() + 120
    while time.time() < deadline:
        st = client.get(f"/api/videos/{up['video_id']}/status").json()
        if st["status"] in ("completed", "failed"):
            break
        time.sleep(0.2)
    assert st["status"] == "completed" and st["preview_status"] == "ready" and st["playable"] is True
    served = client.get(f"/api/videos/{up['video_id']}", headers={"Range": "bytes=0-3000"})
    assert served.status_code == 206
    assert b"avc1" in served.content  # H.264 sample entry in the MP4 header (faststart)
