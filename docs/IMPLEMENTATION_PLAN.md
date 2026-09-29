# BAS AI — Implementation Plan v2 (post-inspection)

Supersedes `implementation_plan.md` and builds on `BAS_AI_Complete_Implementation_Plan.md`.
Written 2026-09-29 after a full inspection of the codebase and a live run of the pipeline.

---

## 1. Where the project actually is

| Area | State found | Evidence |
|---|---|---|
| Backend startup | Works **only** from root `.venv`. `backend/venv` lacks cv2/ultralytics → `import cv2` in `pipeline.py` crashes startup → "Backend Offline". | Started on :8011 from `.venv`: healthy in ~4 s. |
| `requirements.txt` | Missing opencv, ultralytics, torch, numpy, lap, python-multipart. Fresh install cannot run. | File contents. |
| Processing | Synchronous inside the HTTP request. 62 s video took **309 s** on CPU; browser hangs, no progress. YOLO tracks every frame even though only every 2nd is classified. | Timed run. |
| Detection / tracking | YOLO11n-pose + ByteTrack (ultralytics). Reasonable choice. Weight sits in `backend/`, status endpoint looks in `backend/weights/` → reports "missing". | `/api/model/status`. |
| Activity classifier | Hand-written pose rules with **hardcoded** confidences (0.78/0.76/0.74…). Not a probability. `unknown_sensitivity` stored but unused. | `pipeline.py:104-143`. |
| Trained weights | None exist (`activity_cnn.pt`, `yolov8n.pt`, any `.pth/.onnx`). `model_config.json` describes models never trained. | Repo search. |
| Test data | Only video is a synthetic stick-figure cartoon → **0 detections in 1,488 frames**. 26 uploads are byte-identical copies. | Run output + md5. |
| Database | 9 fabricated events copied from PRD examples (e.g. Walking 00:01:12 @0.94 in a 62 s video). One experiment stuck in `processing`. | DB query. |
| Frontend | Compiles clean (tsc 0 errors). `localhost:8000` hardcoded ~15×. Live Monitor has no camera code. "Demo Mode" badge, dead "New Experiment" button, fake timeline axis, fake RTSP camera list. No Reject action. | Source. |
| Hardware | CPU only (no CUDA). | `torch.cuda.is_available() == False`. |

## 2. Decisions (confirmed with user)

1. **Inputs:** both webcam live monitoring *and* user-supplied recorded footage.
2. **Classifier:** improved, honestly-labeled rule baseline now → add a trainable temporal model (GRU on pose keypoint sequences) + labeling/training tooling; pipeline uses the trained model automatically when its weights exist.
3. **Housekeeping:** git initialised (done, commit `67121d2`). No deletions of DB rows, uploads, or `backend/venv` without further approval.
4. **In-scope extras:** workflow deviation check, PDF + JSON export, experiments list & detail page. Zone awareness is out of scope.

## 3. Technical choices

- **Keep YOLO11n-pose + ByteTrack** instead of YOLOv8 + DeepSORT + MediaPipe. One CPU-friendly model yields person boxes, 17 keypoints and (with ByteTrack) persistent IDs. The prior plan explicitly allows "the existing tracker". Fewer dependencies, no coordinate-system mismatch between detector and pose model.
- **SQLite + SQLAlchemy** stays; extend with the existing lightweight `migrate_db()` pattern (no Alembic).
- **Background job worker** (single thread + queue) for video processing, so the API stays responsive and CPU isn't oversubscribed.
- **Live inference over WebSocket**: browser samples ~5 fps JPEG frames → backend → JSON detections → canvas overlay.
- **PDF** via `reportlab` (new dependency, pure Python).
- One Python env: root `.venv`. `backend/venv` left in place but unused and documented as such.

## 4. Target structure (evolves existing files, no rewrite from scratch)

```
backend/
  main.py                 app, CORS, router includes, startup
  config.py               paths, env (CORS origins, thresholds, weights dir)
  database.py, models.py, schemas.py   (extended)
  api/                    system.py, videos.py, experiments.py, review.py,
                          analytics.py, reports.py, settings.py, live.py
  services/
    inference/detector.py     YOLO pose load-once + status
    activity/features.py      keypoint normalisation, window features
    activity/rules.py         rule scores for all 7 classes -> softmax
    activity/temporal.py      GRU model wrapper (optional weights)
    activity/unknown.py       threshold + entropy open-set logic
    processing/segmenter.py   smoothing, hysteresis, min-duration -> events
    processing/jobs.py        background queue, progress, states
    workflow.py               expected vs observed sequence
    reports.py                JSON / CSV / PDF builders
  training/               extract_pose.py, labels template, train_gru.py, evaluate.py
  tests/                  pytest (API + unit)
  weights/                yolo11n-pose.pt (moved), activity_gru.pt (when trained)
frontend/src/
  lib/config.ts           VITE_API_URL (single source)
  lib/api.ts              typed client for every endpoint
  hooks/useSystemStatus.ts, useCamera.ts, useLiveInference.ts
  types/                  shared API types
  pages/ExperimentDetail.tsx  (new)  + existing pages rewired
```

## 5. Milestones (in order; each ends in a verifiable state)

### M1 — Backend runs reliably (P0) — ✅ done
- Fix `requirements.txt` (pinned to versions already working in `.venv`) + `reportlab`.
- Move `yolo11n-pose.pt` → `backend/weights/`; loader checks there first.
- `GET /health` → `{"status":"ok"}`; `GET /api/system/status` → backend / pose model / activity engine (rules|gru) / database / cuda booleans + engine name. Missing component reports `false`, never crashes.
- CORS from env (default `http://localhost:5173`, `127.0.0.1:5173`); drop the `*` + credentials combo.
- Startup: mark experiments left in `processing`/`queued` as `failed: interrupted by restart`.
- Structured logging (`logging`, not `print`) for startup, model load, upload, jobs, inference, DB and API errors; users get clean messages, no stack traces.
- Start scripts: `start-backend.ps1`, `start-frontend.ps1`, README.
- **Verify:** fresh terminal → script → `/health` ok; frontend header shows Connected.
- **Result:** startup ~2 s; `/health` and `/api/system/status` verified; foreign CORS origins rejected; stuck job marked failed on restart; starting from the broken `backend/venv` now boots and reports `missing_packages: [opencv, ultralytics]` instead of crashing. Found that `localhost` resolves to `::1` first while uvicorn binds IPv4 → frontend will target `127.0.0.1:8000` (M2).

### M2 — Frontend API config (P0)
- `VITE_API_URL` in `frontend/.env` (+ `.env.example`); all fetches through `lib/api.ts`; WS URL derived from it.
- `useSystemStatus` hook polls `/api/system/status`; header shows Backend / AI engine / DB honestly. Remove "Demo Mode" badge; show "Rule-based baseline" or "Trained model" instead.
- Shared page states: backend unavailable, model missing, no data, processing failed (texts from plan §21).
- **Verify:** grep finds zero `localhost:8000` outside config; stop backend → every page shows the offline state; start → recovers without reload.

### M3 — Upload + async processing (P0)
- `POST /api/videos/upload`: mp4/avi/mov (+webm), 500 MB streaming limit, extension **and** OpenCV open check (reject corrupt/non-video), returns `{video_id, filename, file_size, status:"uploaded"}`.
- `POST /api/videos/{id}/process` → enqueue, returns `queued`. `GET /api/videos/{id}/status` → `uploaded|queued|processing|completed|failed`, `progress` 0-100, `error`.
- Performance: `vid_stride` so inference runs only at ~8 fps effective, `imgsz=640`, model loaded once. Target ≥4× faster than the current 309 s for the 62 s clip; record actual numbers.
- Frontend: XHR upload with % progress, then polling progress bar, then "View results" → detail page.
- **Verify:** upload a real clip; UI shows upload %, queued, processing %, completed; a `.txt` renamed `.mp4` is rejected; >500 MB rejected.

### M4 — Activity engine v1: honest rules + temporal + unknown (P1)
- Features per track per sample: normalised keypoints (hip-centred, torso-scaled), joint angles, wrist height/extension, centre velocity over a ~1 s window.
- Rules produce a **score for every class** → softmax → real distribution. Confidence = max prob; entropy computed.
- Unknown: `max_prob < threshold` OR `entropy > sensitivity_threshold` (Low 2.5 / Medium 1.75 / High 1.0 — matching the Settings copy, which becomes true). Also "unknown" when pose keypoints are too incomplete.
- Temporal: sliding-window majority vote, hysteresis (new label must persist N samples), min event duration 1.0 s, merge same-label gaps < 0.5 s. Per-track, so multiple people stay separate.
- Tracking hygiene: drop tracks shorter than `min_track_length`; person labels renumbered 01, 02… per experiment in order of appearance.
- Events store `start/end seconds`, frame numbers, confidence (mean prob of chosen class), `review_status`.
- Unit tests on synthetic prediction streams for segmenter + unknown logic.
- **Verify:** on the user's recorded clips, events have plausible labels, start/end within ~1 s of what a human marks, unknown gestures land in Review Queue.

### M5 — Data model, review, dashboard, analytics (P1/P2)
- Migrations: experiments get `source` (upload|camera), `progress`, `error_message`, `processed_at`, `duration_seconds`, `fps`, `people_count`, `engine`; events get `review_status` (pending|confirmed|rejected|reclassified|auto), `original_activity`, `reviewed_at`.
- Review: `GET /api/review/events?experiment_id=` (unknown + below-threshold, pending); `POST /api/review/events/{id}` with `confirm | reject | reclassify(activity)`. Original prediction preserved for future training data.
- Review UI: clip player seeks to event (existing code, fixed), Confirm / Reject / Reclassify, keyboard-friendly.
- `GET /api/dashboard/summary`: experiments (total/active/completed), people detected (sum of distinct tracks per experiment — not global participant-row count), unknown pending, avg confidence, recent events, current job progress.
- Analytics: `GET /api/analytics/summary|activity-distribution|person-statistics?experiment_id=` incl. durations per activity, counts, avg confidence, unknown count. Rejected events excluded. Frontend adds experiment filter, duration chart, confidence stats.
- **Verify:** reclassify an event → Review count drops, Analytics distribution changes, survives backend restart.

### M6 — Experiments list/detail, workflow, reports (P2)
- Experiments page: list of all experiments (status, source, duration, people, events) + upload panel; "New Experiment" button becomes the upload flow (dead button removed).
- `/experiments/:id` detail: video player, per-person timeline with a real time axis scaled to video duration, event table (click → seek), workflow panel.
- Workflow: fix sequence validator (currently orders by HH:MM:SS *string* and mixes people) → order by `start_seconds`, per-person or combined toggle, ignore rejected; expected sequence editable in the detail page; wording "Observed sequence deviates from expected workflow — operator review required."
- Reports: `GET /api/reports/{id}` JSON (experiment info, video, date, people, activity summary, durations, confidence, unknowns, person stats, workflow result, review status), `.csv` (real `text/csv` download), `.pdf` (reportlab). Reports list only for completed experiments.
- **Verify:** download all three formats for a processed clip; numbers match Analytics for that experiment.

### M7 — Live Monitor with webcam (P2)
- `useCamera`: `getUserMedia`, device list via `enumerateDevices` (replaces fake RTSP dropdown in Settings), START/STOP CAMERA; handles NotAllowedError, NotFoundError, NotReadableError (in use), unsupported browser.
- START/STOP AI MONITORING: creates a `camera` experiment; frames sampled at 5 fps (configurable 1-10), JPEG q≈0.7, one in flight at a time (no queue build-up).
- `WS /ws/live/{experiment_id}`: separate YOLO instance with `persist=True` tracking; same feature/rules/temporal/unknown code as offline; returns `{person, box, activity, confidence, unknown}` + measured latency/FPS.
- Canvas overlay: boxes + "Person 1 — Walking — 89%", "⚠ Unknown Activity". Live event feed from the segmenter; events persisted to DB so Review/Analytics/Reports work for live sessions too.
- Backend unavailable during monitoring → overlay stops, clear message, camera preview keeps running.
- **Verify:** allow camera → preview; start monitoring → labelled overlay at ≥3 fps on this CPU; stop → experiment appears with events.

### M8 — Trainable temporal model (P1, needs labelled footage)
- `training/extract_pose.py`: runs the same detector/tracker, dumps per-track keypoint sequences.
- Label format: `labels.csv` → `video, start_s, end_s, activity[, person]` (template + instructions provided).
- `training/train_gru.py`: small GRU over 32-frame windows, **split by video/subject** (PRD §28, avoids leakage), class weights; saves `weights/activity_gru.pt` + `activity_gru.json` (classes, window, feature spec, metrics).
- `training/evaluate.py`: accuracy, per-class P/R/F1, confusion matrix, unknown precision/recall with held-out "other" clips.
- Pipeline picks GRU automatically when weights + matching spec exist; UI shows which engine produced each experiment.
- **Verify:** evaluation report generated on held-out videos; results shown honestly even if accuracy is modest.

### M9 — End-to-end tests, polish, demo
- `pytest` API tests (TestClient, temp DB, tiny generated video) covering health, status, upload validation, job lifecycle, review actions, analytics, reports.
- Manual acceptance run of plan §23 tests A–J and §30 Definition of Done with the user's footage; results written to `docs/TEST_REPORT.md`.
- Frontend: fix oxlint `set-state-in-effect` warnings, page title "BAS AI — Activity Intelligence", loading/empty states, remove unused `App.css`/assets.
- README: setup, run, recording guidelines, architecture, limitations (CPU speed, rule baseline accuracy).
- Demo script following plan §29.

## 6. What I need from you along the way

| When | What |
|---|---|
| Before M4 verification | 3–5 real clips (phone/webcam, fixed position, full body visible, each activity held 5–10 s, include one clip with 2 people and one with "unexpected" moves). |
| Before M8 | More clips (ideally ≥20 short instances per activity, several people) + `labels.csv` (I'll provide a template), or ~30 min to label with the tool. |
| M7 | Allowing camera access in the browser when testing. |

## 7. Legacy data — resolved

Approved 2026-09-29: `bas_ai.db` renamed to `bas_ai.legacy.db` (kept on disk, unused); the backend starts with a clean database. Duplicate uploads and `backend/venv` remain untouched.

## 8. Explicit non-goals / honesty rules

No hardcoded or random predictions, no fake stats, "Connected" only from real `/health`, missing models reported not hidden, Unknown class and multi-person tracking kept, models loaded once, camera frames sampled not streamed wholesale. The rule baseline is labelled as such everywhere it appears.
