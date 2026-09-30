import os
import time

from api import videos as videos_api


def _upload(client, name, data, content_type="video/mp4"):
    return client.post("/api/videos/upload", files={"file": (name, data, content_type)})


def _wait_for_terminal_state(client, video_id, timeout=120):
    deadline = time.time() + timeout
    seen = set()
    while time.time() < deadline:
        body = client.get(f"/api/videos/{video_id}/status").json()
        seen.add(body["status"])
        if body["status"] in ("completed", "failed"):
            return body, seen
        time.sleep(0.2)
    raise AssertionError(f"job did not finish in {timeout}s (states seen: {seen})")


def test_health(client):
    assert client.get("/health").json() == {"status": "ok"}


def test_system_status_reports_components(client):
    s = client.get("/api/system/status").json()
    for key in ("backend", "database", "yolo_model", "activity_model", "model_ready", "activity_engine"):
        assert key in s
    assert s["backend"] is True and s["database"] is True


def test_rejects_wrong_extension(client):
    r = _upload(client, "notes.txt", b"hello", "text/plain")
    assert r.status_code == 400
    assert "Invalid file format" in r.json()["detail"]


def test_rejects_non_video_with_video_extension(client, uploads_dir):
    before = set(os.listdir(uploads_dir))
    r = _upload(client, "fake.mp4", os.urandom(4096))
    assert r.status_code == 400
    assert "could not be read as a video" in r.json()["detail"]
    assert set(os.listdir(uploads_dir)) == before, "rejected file must be deleted"


def test_rejects_empty_file(client):
    r = _upload(client, "empty.mp4", b"")
    assert r.status_code == 400


def test_rejects_oversized_file(client, monkeypatch, uploads_dir):
    monkeypatch.setattr(videos_api, "MAX_FILE_SIZE", 1024)
    before = set(os.listdir(uploads_dir))
    r = _upload(client, "big.mp4", os.urandom(4096))
    assert r.status_code == 413
    assert set(os.listdir(uploads_dir)) == before


def test_filename_cannot_escape_uploads_dir(client, sample_video, uploads_dir):
    with open(sample_video, "rb") as f:
        r = _upload(client, "../../evil name.mp4", f.read())
    assert r.status_code == 201
    saved = [n for n in os.listdir(uploads_dir) if n.startswith(r.json()["video_id"])]
    assert saved == [f"{r.json()['video_id']}_evil_name.mp4"]


def test_upload_process_lifecycle(client, sample_video):
    with open(sample_video, "rb") as f:
        r = _upload(client, "sample.mp4", f.read())
    assert r.status_code == 201
    up = r.json()
    assert up["status"] == "uploaded"
    assert up["file_size"] > 0
    assert abs(up["duration_seconds"] - 2.0) < 0.2
    vid = up["video_id"]

    r = client.post(f"/api/videos/{vid}/process")
    assert r.status_code == 202
    assert r.json()["status"] == "queued"

    final, seen = _wait_for_terminal_state(client, vid)
    assert final["status"] == "completed", final
    assert final["progress"] == 100.0
    assert final["events_count"] == 0
    assert "no people were detected" in final["message"]
    assert final["processed_at"] and final["processed_at"].endswith("Z")

    listed = {v["video_id"]: v for v in client.get("/api/videos").json()}
    assert listed[vid]["status"] == "completed"

    # Re-processing is allowed once finished
    assert client.post(f"/api/videos/{vid}/process").status_code == 202
    final, _ = _wait_for_terminal_state(client, vid)
    assert final["status"] == "completed"


def test_process_twice_while_active_is_rejected(client, sample_video):
    with open(sample_video, "rb") as f:
        vid = _upload(client, "twice.mp4", f.read()).json()["video_id"]
    assert client.post(f"/api/videos/{vid}/process").status_code == 202
    second = client.post(f"/api/videos/{vid}/process")
    # The tiny video may already be done; otherwise the second request must be refused.
    assert second.status_code in (202, 409)
    if second.status_code == 409:
        assert "already" in second.json()["detail"]
    _wait_for_terminal_state(client, vid)


def test_process_unknown_video_404(client):
    assert client.post("/api/videos/VID_nope/process").status_code == 404
    assert client.get("/api/videos/VID_nope/status").status_code == 404


def test_serve_video_supports_range(client, sample_video):
    with open(sample_video, "rb") as f:
        vid = _upload(client, "play.mp4", f.read()).json()["video_id"]
    full = client.get(f"/api/videos/{vid}")
    assert full.status_code == 200
    assert full.headers["content-type"] == "video/mp4"
    part = client.get(f"/api/videos/{vid}", headers={"Range": "bytes=0-99"})
    assert part.status_code == 206
    assert len(part.content) == 100


def test_pipeline_crash_marks_job_failed(client, sample_video, monkeypatch):
    import runtime

    def boom(path, progress_cb=None):
        raise RuntimeError("simulated inference crash")

    monkeypatch.setattr(runtime.ai_pipeline, "process_video", boom)
    with open(sample_video, "rb") as f:
        vid = _upload(client, "crash.mp4", f.read()).json()["video_id"]
    assert client.post(f"/api/videos/{vid}/process").status_code == 202
    final, _ = _wait_for_terminal_state(client, vid)
    assert final["status"] == "failed"
    assert "Check backend logs" in final["message"]
    assert "simulated" not in final["message"], "internal error details must not leak to the UI"


def test_processing_refused_when_model_not_ready(client, sample_video, monkeypatch):
    import runtime

    monkeypatch.setattr(runtime.ai_pipeline, "model_ready", False)
    with open(sample_video, "rb") as f:
        vid = _upload(client, "nomodel.mp4", f.read()).json()["video_id"]
    r = client.post(f"/api/videos/{vid}/process")
    assert r.status_code == 503
    assert "model is missing" in r.json()["detail"]
    assert client.get(f"/api/videos/{vid}/status").json()["status"] == "uploaded"


def test_cors_preflight_allows_range_for_video_seeking(client):
    r = client.options(
        "/api/videos/anything",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "range",
        },
    )
    assert r.status_code == 200
    assert "range" in r.headers.get("access-control-allow-headers", "").lower()
    assert r.headers["access-control-allow-origin"] == "http://localhost:5173"


def test_video_responses_must_be_revalidated(client, sample_video):
    with open(sample_video, "rb") as f:
        vid = client.post("/api/videos/upload", files={"file": ("cache.mp4", f.read(), "video/mp4")}).json()["video_id"]
    r = client.get(f"/api/videos/{vid}", headers={"Range": "bytes=0-9"})
    assert r.headers["cache-control"] == "no-cache" and r.headers.get("etag")
