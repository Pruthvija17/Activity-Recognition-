# BAS AI — Activity Intelligence (SIH26174)

AI human-activity recognition for on-board BAS experiments: person detection, multi-person tracking, activity recognition with Unknown detection, operator review, analytics and reports.

- **Backend:** FastAPI + SQLite + Ultralytics YOLO11-pose (ByteTrack) — `backend/`
- **Frontend:** React + Vite + Tailwind — `frontend/`
- **Plan / status:** [`docs/IMPLEMENTATION_PLAN.md`](docs/IMPLEMENTATION_PLAN.md)

## First-time setup (Windows)

```powershell
python -m venv .venv
.venv\Scripts\python -m pip install -r backend\requirements.txt
cd frontend; npm install; cd ..
```

Use only the project-root `.venv`. (`backend/venv` is an old, incomplete environment and is not used.)

## Run

Two terminals, from the project root:

```powershell
powershell -ExecutionPolicy Bypass -File .\start-backend.ps1    # http://127.0.0.1:8000
powershell -ExecutionPolicy Bypass -File .\start-frontend.ps1   # http://localhost:5173
```

`start-backend.ps1 -Reload` enables auto-reload while developing.

## Check it is working

| URL | Expected |
|---|---|
| http://127.0.0.1:8000/health | `{"status":"ok"}` |
| http://127.0.0.1:8000/api/system/status | `database`, `yolo_model`, `model_ready` all `true` |
| http://127.0.0.1:8000/docs | Interactive API docs |

If a component is not ready, `/api/system/status` says why (`model_error`, `missing_packages`) and the backend log prints the same at startup.

> Use `127.0.0.1` rather than `localhost` for the backend: on this Windows setup `localhost` resolves to IPv6 `::1` first, while the backend listens on IPv4.

## Tests

```powershell
cd backend; ..\.venv\Scripts\python -m pytest tests -q
```

Tests use a temporary database and uploads folder, never the real ones.

## Recording test footage

Fixed camera, whole body in view, good light. Hold each activity for 5–10 s. Record as **H.264 MP4** where possible: iPhones default to HEVC, which Chrome on Windows usually cannot play back in the Review Queue (analysis still works). On iPhone: Settings → Camera → Formats → *Most Compatible*.

## Processing videos

Experiments → drop or select a video → **Upload & Process**. Upload progress, queue position and processing progress are shown live; jobs run one at a time in the background and survive page reloads. A backend restart marks unfinished jobs as failed (use **Retry**).

## Backend configuration (environment variables)

| Variable | Default |
|---|---|
| `BAS_CORS_ORIGINS` | `http://localhost:5173,http://127.0.0.1:5173` |
| `BAS_DB_PATH` | `backend/bas_ai.db` |
| `BAS_UPLOADS_DIR` | `backend/uploads` |
| `BAS_POSE_WEIGHTS` | `yolo11n-pose.pt` (in `backend/weights/`) |
| `BAS_LOG_LEVEL` | `INFO` |

## Honest status of the AI

Activity labels currently come from a **rule-based baseline** on YOLO pose keypoints; no trained activity model exists yet (planned in milestone M8). The UI and API label results accordingly. Processing runs on CPU when no CUDA GPU is available.

`backend/bas_ai.legacy.db` holds the previous database (which contained fabricated example events); it is kept for reference and not used.
