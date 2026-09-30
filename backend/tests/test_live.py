"""Live monitoring over the WebSocket, using a real photo of people as camera frames."""
import os
import time

import cv2
import pytest
import ultralytics

from runtime import live

BUS = os.path.join(os.path.dirname(ultralytics.__file__), "assets", "bus.jpg")


@pytest.fixture(scope="module")
def frame_jpeg() -> bytes:
    img = cv2.imread(BUS)
    ok, buf = cv2.imencode(".jpg", cv2.resize(img, (540, 720)), [cv2.IMWRITE_JPEG_QUALITY, 70])
    assert ok
    return buf.tobytes()


@pytest.fixture(autouse=True)
def no_leftover_session():
    yield
    if live.current is not None and not live.current.finished:
        live.stop(live.current.experiment_id)


def _start(client, fps=5):
    r = client.post("/api/live/sessions", json={"fps": fps, "name": "test camera"})
    assert r.status_code == 201, r.text
    return r.json()


def test_live_session_end_to_end(client, frame_jpeg):
    s = _start(client)
    exp_id = s["experiment_id"]
    assert client.post("/api/live/sessions", json={"fps": 5}).status_code == 409
    assert client.get("/api/live/sessions/current").json()["experiment_id"] == exp_id

    with client.websocket_connect(s["ws_path"]) as ws:
        results = []
        t_first = time.monotonic()
        for _ in range(12):
            ws.send_bytes(frame_jpeg)
            results.append(ws.receive_json())
        elapsed = time.monotonic() - t_first
        ws.send_bytes(b"not an image")
        err = ws.receive_json()
        ws.send_text("stop")
        summary = ws.receive_json()

    assert all(r["type"] == "result" for r in results)
    last = results[-1]
    assert len(last["people"]) >= 3
    for p in last["people"]:
        assert p["person"].startswith("Person ")
        assert all(0.0 <= v <= 1.0 for v in p["box"])
        assert 0.0 <= p["confidence"] <= 1.0
    # Identities are stable across frames.
    assert {p["track_id"] for p in results[5]["people"]} == {p["track_id"] for p in last["people"]}
    assert err["type"] == "error"

    assert summary["type"] == "summary" and summary["frames"] == 12
    assert summary["people"] >= 3 and summary["events"] >= 3
    assert client.get("/api/live/sessions/current").json() is None

    status = client.get(f"/api/videos/{exp_id}/status").json()
    assert status["status"] == "completed" and status["source"] == "camera"
    # Session time is real elapsed time (inference on CPU is slower than the requested 5 fps).
    assert status["duration_seconds"] == pytest.approx(elapsed, abs=0.6)
    assert status["file_exists"]

    detail = client.get(f"/api/experiments/{exp_id}").json()
    live_names = {p["person"] for p in last["people"]}
    assert {p["label"] for p in detail["people"]} <= live_names  # same names as shown live


def test_disconnect_without_stop_still_saves(client, frame_jpeg):
    s = _start(client)
    with client.websocket_connect(s["ws_path"]) as ws:
        for _ in range(8):
            ws.send_bytes(frame_jpeg)
            ws.receive_json()
    deadline = time.time() + 10
    while time.time() < deadline and client.get("/api/live/sessions/current").json() is not None:
        time.sleep(0.1)
    status = client.get(f"/api/videos/{s['experiment_id']}/status").json()
    assert status["status"] == "completed" and status["frame_count"] >= 8


def test_slow_frames_keep_real_time(client, frame_jpeg):
    """3 frames sent >1 s apart at a requested 5 fps: the session lasts real time, not 3 / 5 s."""
    s = _start(client, fps=5)
    with client.websocket_connect(s["ws_path"]) as ws:
        ts = []
        t_first = time.monotonic()
        for i in range(3):
            if i:
                time.sleep(1.0)
            ws.send_bytes(frame_jpeg)
            ts.append(ws.receive_json()["t"])
        elapsed = time.monotonic() - t_first
        ws.send_text("stop")
        summary = ws.receive_json()
    assert summary["frames"] == 3
    assert summary["duration_seconds"] == pytest.approx(elapsed, abs=0.6)
    assert ts[1] - ts[0] >= 0.8 and ts[2] - ts[1] >= 0.8


def test_session_without_frames(client):
    s = _start(client)
    summary = client.post(f"/api/live/sessions/{s['experiment_id']}/stop").json()
    assert summary["frames"] == 0 and summary["events"] == 0
    status = client.get(f"/api/videos/{s['experiment_id']}/status").json()
    assert status["status"] == "completed" and "No camera frames" in status["message"]


def test_unknown_session(client):
    assert client.post("/api/live/sessions/LIVE_nope/stop").status_code == 404
    with client.websocket_connect("/ws/live/LIVE_nope") as ws:
        assert ws.receive_json()["type"] == "error"


def test_fps_is_bounded(client):
    assert client.post("/api/live/sessions", json={"fps": 30}).status_code == 422


def test_live_refused_when_model_not_ready(client, monkeypatch):
    import runtime

    monkeypatch.setattr(runtime.ai_pipeline, "model_ready", False)
    assert client.post("/api/live/sessions", json={"fps": 5}).status_code == 503


def test_frames_faster_than_requested_rate_do_not_stretch_time(client, frame_jpeg):
    """Sending as fast as possible (faster than 2 fps) must not make the recording longer than real time."""
    s = _start(client, fps=2)
    with client.websocket_connect(s["ws_path"]) as ws:
        t_first = time.monotonic()
        for _ in range(10):
            ws.send_bytes(frame_jpeg)
            ws.receive_json()
        elapsed = time.monotonic() - t_first
        ws.send_text("stop")
        summary = ws.receive_json()
    assert summary["frames"] == 10
    assert summary["duration_seconds"] <= elapsed + 0.6
