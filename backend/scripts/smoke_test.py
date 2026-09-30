"""End-to-end smoke test against a RUNNING backend (and optionally frontend).

    cd backend
    ..\\.venv\\Scripts\\python scripts\\smoke_test.py            # cleans up what it creates
    ..\\.venv\\Scripts\\python scripts\\smoke_test.py --keep     # keep the test experiments

Covers the implementation plan's tests A-J with generated clips of real people (ultralytics'
bus.jpg with a slow pan): health/status, upload validation (MP4/AVI/MOV, bad files), background
processing, events, Unknown -> Review, multi-person tracking, analytics, reports and a live
WebSocket session. Exit code 0 only if every check passes.
"""
import argparse
import json
import os
import sys
import tempfile
import time

import cv2
import httpx
import numpy as np
import ultralytics
from websockets.sync.client import connect

BUS = os.path.join(os.path.dirname(ultralytics.__file__), "assets", "bus.jpg")
results = []


def check(test: str, name: str, ok: bool, detail: str = "") -> bool:
    results.append((test, name, ok, detail))
    print(f"  [{'PASS' if ok else 'FAIL'}] {test} {name}{' - ' + detail if detail else ''}", flush=True)
    return ok


def make_clip(path: str, fourcc: str, seconds: float = 3.0, fps: int = 12) -> None:
    img = cv2.imread(BUS)
    h, w = img.shape[:2]
    cw = int(w * 0.85)
    out = cv2.VideoWriter(path, cv2.VideoWriter_fourcc(*fourcc), fps, (cw, h))
    n = int(seconds * fps)
    for i in range(n):
        x = int((w - cw) * i / max(1, n - 1))
        out.write(np.ascontiguousarray(img[:, x:x + cw]))
    out.release()


def wait_done(api: httpx.Client, vid: str, timeout: float = 300) -> dict:
    deadline = time.time() + timeout
    while time.time() < deadline:
        st = api.get(f"/api/videos/{vid}/status").json()
        if st["status"] in ("completed", "failed"):
            return st
        time.sleep(1)
    return st


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--api", default="http://127.0.0.1:8000")
    ap.add_argument("--frontend", default="http://localhost:5173")
    ap.add_argument("--keep", action="store_true", help="keep the experiments this test creates")
    args = ap.parse_args(argv)

    api = httpx.Client(base_url=args.api, timeout=60)
    created = []
    tmp = tempfile.mkdtemp(prefix="bas_smoke_")
    t_start = time.time()
    try:
        print("Test A - backend")
        try:
            health = api.get("/health").json()
        except httpx.HTTPError as e:
            check("A", "backend reachable", False, f"{e} - start it with start-backend.ps1")
            return 1
        check("A", "/health", health == {"status": "ok"}, json.dumps(health))
        s = api.get("/api/system/status").json()
        check("A", "system status", s["database"] and s["yolo_model"] and s["model_ready"],
              f"engine={s['activity_engine']}, device={s['device']}, ffmpeg={s.get('ffmpeg')}")

        print("Test B - frontend")
        try:
            fe = httpx.get(args.frontend, timeout=5)
            check("B", "frontend serves the app", fe.status_code == 200 and "BAS AI" in fe.text, args.frontend)
        except httpx.HTTPError:
            check("B", "frontend serves the app", False, f"{args.frontend} not reachable (start-frontend.ps1)")

        print("Test C - upload validation")
        clips = {}
        for ext, fourcc in ((".mp4", "mp4v"), (".avi", "MJPG"), (".mov", "mp4v")):
            p = os.path.join(tmp, f"smoke_bus{ext}")
            make_clip(p, fourcc)
            with open(p, "rb") as fh:
                r = api.post("/api/videos/upload", files={"file": (f"smoke_test_bus{ext}", fh, "video/mp4")})
            ok = r.status_code == 201
            if ok:
                clips[ext] = r.json()["video_id"]
                created.append(clips[ext])
            check("C", f"{ext.upper()[1:]} upload", ok, r.json().get("video_id") if ok else r.text)
        r = api.post("/api/videos/upload", files={"file": ("notes.txt", b"hello", "text/plain")})
        check("C", "rejects .txt", r.status_code == 400, r.json().get("detail", ""))
        r = api.post("/api/videos/upload", files={"file": ("fake.mp4", os.urandom(4096), "video/mp4")})
        check("C", "rejects non-video .mp4", r.status_code == 400, r.json().get("detail", ""))

        print("Test D/E - processing and results")
        mp4 = clips.get(".mp4")
        for ext, vid in clips.items():
            t0 = time.time()
            api.post(f"/api/videos/{vid}/process")
            st = wait_done(api, vid)
            check("D", f"{ext.upper()[1:]} processed", st["status"] == "completed",
                  f"{st['message']} ({time.time() - t0:.0f}s, playable={st.get('playable')})")
        detail = api.get(f"/api/experiments/{mp4}").json() if mp4 else {"events": [], "people": []}
        events = detail["events"]
        fields_ok = all({"person", "activity_type", "start_time", "end_time", "duration", "confidence"} <= e.keys()
                        for e in events)
        check("E", "activity events with person/times/duration/confidence", bool(events) and fields_ok,
              "; ".join(f"{e['person']} {e['activity_type']} {e['start_time']}-{e['end_time']} {e['confidence']:.2f}"
                        for e in events[:5]))

        print("Test F - Unknown / low confidence -> Review Queue")
        pending = api.get(f"/api/review/events?experiment_id={mp4}").json() if mp4 else []
        flagged = [e for e in events if e["activity_type"] == "Unknown" or e["review_status"] == "pending"]
        check("F", "flagged events are in the Review Queue", len(pending) == len(flagged),
              f"{len(pending)} pending ({', '.join(sorted({e['activity_type'] for e in pending})) or 'none'})")
        unknowns = [e for e in events if e["activity_type"] == "Unknown"]
        check("F", "Unknown events say why", all(e.get("note") for e in unknowns),
              "; ".join(f"{e['person']}: {e.get('note')}" for e in unknowns) or "no Unknown events")

        print("Test G - multi-person tracking")
        check("G", "several people tracked", len(detail["people"]) >= 3,
              ", ".join(p["label"] for p in detail["people"]))

        print("Test H - analytics")
        a = api.get(f"/api/analytics?experiment_id={mp4}").json() if mp4 else {}
        kept = [e for e in events if e["review_status"] != "rejected"]
        check("H", "analytics match the stored events",
              a.get("total_events") == len(kept) and a.get("people_count") == len({e["person_id"] for e in kept}),
              f"{a.get('total_events')} events, {a.get('people_count')} people, avg conf {a.get('avg_confidence')}")

        print("Test I - reports")
        for fmt, path, needle in (("JSON", f"/api/reports/{mp4}", b'"report_id"'),
                                  ("CSV", f"/api/reports/{mp4}/csv", b"report_id,experiment_id"),
                                  ("PDF", f"/api/reports/{mp4}/pdf", b"%PDF")):
            r = api.get(path)
            check("I", f"{fmt} report", r.status_code == 200 and needle in r.content[:4000], f"{len(r.content)} bytes")

        print("Test J - live monitoring (camera frames over WebSocket)")
        img = cv2.resize(cv2.imread(BUS), (540, 720))
        frame = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 70])[1].tobytes()
        r = api.post("/api/live/sessions", json={"fps": 5, "name": "smoke_test live"})
        if check("J", "start live session", r.status_code == 201, r.text[:120]):
            s = r.json()
            created.append(s["experiment_id"])
            ws_url = args.api.replace("http", "ws", 1) + s["ws_path"]
            people, t0 = [], time.time()
            with connect(ws_url, max_size=2 ** 22) as ws:
                for _ in range(10):
                    ws.send(frame)
                    msg = json.loads(ws.recv())
                    people = msg.get("people", people)
                ws.send("stop")
                summary = json.loads(ws.recv())
            check("J", "live detections", len(people) >= 3,
                  f"{len(people)} people, e.g. {people[0]['person']} {people[0]['activity']} "
                  f"{round(people[0]['confidence'] * 100)}%" if people else "none")
            check("J", "session saved as experiment", summary.get("type") == "summary" and summary.get("events", 0) >= 3,
                  f"{summary.get('message')} ({time.time() - t0:.0f}s)")
    finally:
        if not args.keep:
            for vid in created:
                api.delete(f"/api/experiments/{vid}")
            print(f"Cleaned up {len(created)} test experiment(s).")
        api.close()

    failed = [r for r in results if not r[2]]
    print(f"\n{len(results) - len(failed)}/{len(results)} checks passed in {time.time() - t_start:.0f}s.")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
