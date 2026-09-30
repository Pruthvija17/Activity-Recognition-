# BAS AI — Test Report

Date: 2026-09-30 · Machine: Windows 11, 12-core CPU, **no CUDA GPU** · Activity engine: rule-based pose baseline (no trained model yet)

Status legend: ✅ verified · ⚠️ partially verified (see note) · ⏳ needs the user's real footage / hardware

## How this was tested

| Layer | What | Result |
|---|---|---|
| Backend unit + API tests | `cd backend; ..\.venv\Scripts\python -m pytest tests -q` — 85 tests: upload validation, job lifecycle, activity rules on synthetic skeletons, segmentation, open-set, review workflow, analytics, workflow check, reports (JSON/CSV/PDF), previews, live WebSocket sessions with real photo frames, training pipeline end to end | **85 passed** |
| End-to-end smoke test | `..\.venv\Scripts\python scripts\smoke_test.py` against the running app (tests A–J below, clips of real people generated from a photo; cleans up after itself) | **22 / 22 checks passed** |
| Frontend | `npm run build` (type-check + production build), `npm run lint` (oxlint) | clean, no warnings |
| Browser | Every page exercised in the in-app browser against the real backend (details per milestone in `docs/IMPLEMENTATION_PLAN.md`) | ✅ |
| Real webcam | One 46 s live session with two people recorded by the user (`LIVE_06de16fa`) | see below |

## Plan §23 — tests A–J

| Test | Result | Evidence |
|---|---|---|
| A Backend | ✅ | `/health` → `{"status":"ok"}`; `/api/system/status` reports database, pose model, activity engine, ffmpeg, device; a missing package is reported instead of crashing (tested by starting from the incomplete `backend/venv`) |
| B Frontend | ✅ | builds and lints clean; header shows real Backend / Database / AI Models status; offline banner and automatic recovery verified by stopping/starting the backend |
| C Upload | ✅ | MP4, AVI and MOV accepted; `.txt`, non-video `.mp4`, empty and oversized files rejected (413); filename cannot choose the save path |
| D Processing | ✅ | background queue, live progress, queued → processing → completed; two jobs back-to-back; page reload mid-job; restart marks unfinished jobs failed |
| E Results | ✅ | events with person, activity, start/end, duration, confidence, review status |
| F Unknown | ✅ | Unknown / low-confidence events go to the Review Queue and carry a reason ("only upper body visible", "person not clearly visible", "ambiguous between activities", …) |
| G Multi-person | ✅ | 3–4 people tracked with stable IDs in real-photo clips and live frames; 2 people in the user's webcam session |
| H Analytics | ✅ | figures match stored events; rejected events excluded; experiment filter |
| I Reports | ✅ | JSON, CSV (Excel-ready) and PDF (rendered and inspected) per completed experiment |
| J Camera | ✅ / ⏳ | camera controls, permission/no-camera/in-use messages, live overlay and saved sessions verified with a stand-in camera stream and the user's own webcam session; achieved live frame rate on a visible browser window still to be read off by the user |

## Plan §24 — acceptance criteria

**Backend** — FastAPI starts without errors ✅ · `/health` ✅ · CORS (incl. Range preflights) ✅ · `/api/system/status` ✅ · model status reported ✅

**Video** — MP4 ✅ · AVI ✅ · MOV ✅ · 500 MB limit ✅ (enforced while streaming; tested with a lowered limit, not with a real 500 MB file) · invalid files rejected ✅ · processing ✅

**AI**

| Criterion | Status | Note |
|---|---|---|
| YOLO detects people | ✅ | real photos and the user's webcam session |
| Multi-person tracking | ✅ | stable IDs; very short tracks dropped; people numbered by appearance |
| Pose / features | ✅ | torso-normalised, per-second motion, jitter-smoothed; upper-body mode when hips are out of view |
| Activity classifier | ✅ | rule-based baseline with real probability distributions; trainable temporal model tooling ready (M8) |
| Seven activities recognised | ⚠️ | all seven pass on synthetic skeletons; on real footage: Standing verified; Sitting, Walking, Reaching, Picking up and Handling were produced from the user's webcam session but their correctness has not been confirmed; Placing not yet seen on real footage. **Accuracy on real BAS footage is unmeasured** until labelled clips exist |
| Unknown activity | ✅ | entropy / probability / visibility rules; prototype-distance check for trained models |
| Confidence recorded | ✅ | per event (mean probability) |
| Temporal segments | ✅ | smoothing, hysteresis, minimum duration, gap splitting |

**Live Monitor** — camera permission ✅ · preview ✅ · start ✅ · stop ✅ · live AI ✅ · errors handled ✅ (achieved fps on a visible window ⏳)

**Database** — experiments, videos, persons, activity events, Unknown events, review decisions saved ✅ · data unchanged after a backend restart ✅ (10 experiments / 28 events / 2 review decisions before and after; videos still stream)

**Frontend** — Dashboard, Live Monitor, Experiments (+ detail), Review Queue, Analytics, Reports, Settings ✅

**Production-quality behaviour**

| Criterion | Status | Note |
|---|---|---|
| No fake AI predictions | ✅ | the old database with fabricated events was retired (`bas_ai.legacy.db`); every event comes from the pipeline |
| No fake dashboard statistics | ✅ | all figures computed from stored events |
| No fake report data | ✅ | reports built from stored events |
| No dead API endpoints | ✅ | legacy `/api/upload/`, synchronous processing, `/events/`, `POST /events/`, `PUT /events/{id}`, `POST /experiments/`, the status-only `/ws/live` and old sequence/report routes removed |
| No unexplained backend errors | ✅ | structured logs; users get clean messages, never stack traces |
| No CORS errors | ✅ | explicit allowed headers (Range preflight bug fixed) |
| No persistent "Backend Offline" when running | ✅ | root causes fixed (broken `backend/venv` crash, IPv6 `localhost`) |

## Plan §30 — Definition of Done

| # | Item | Status |
|---|---|---|
| 1–4 | Start FastAPI, start frontend, open BAS AI, backend connected | ✅ |
| 5–6 | Upload and process a video | ✅ |
| 7 | Actual people detected | ✅ |
| 8 | Actual activity predictions | ✅ (rule-based baseline; accuracy on real BAS footage ⏳) |
| 9–10 | Confidence, timestamps and durations | ✅ |
| 11–12 | Unknown activities, reviewed | ✅ |
| 13 | Analytics update | ✅ |
| 14 | Generate a report | ✅ |
| 15–19 | Live Monitor: camera, live AI, stop | ✅ (user's own session saved) |
| 20 | Restart without breaking data | ✅ |

## Measured performance (CPU only)

| What | Measured |
|---|---|
| Pose inference per frame | ≈ 80 ms (idle CPU) to ≈ 240 ms (loaded) |
| 62 s video, 1,488 frames | 118–137 s (every 3rd frame analysed), while a third-party service (`altisikservice`) used ~57 % CPU; ≈ 45 s estimated on an idle CPU (was 309 s before M3) |
| 3–4 s real-people clips | 2–11 s |
| Live monitoring | server ≈ 240 ms/frame → ≈ 3 fps possible; first frame of a session ≈ 3–4 s (model warm-up) |
| H.264 preview creation | 0.3–4.4 s per clip |

## Known limitations (honest)

1. **No accuracy numbers on real BAS footage yet.** The rule baseline was tuned on synthetic poses and a few real images; `docs/TRAINING.md` explains how labelled clips turn into a trained model with a proper evaluation report.
2. **CPU only.** Processing is slower than real time on long videos; live monitoring reaches ≈ 3 fps. A CUDA GPU is used automatically if present.
3. **Webcam close-ups.** When only the upper body is visible, standing/sitting/walking/pick-place cannot be judged and are reported as Unknown with the reason "only upper body visible"; reaching and handling still work.
4. **Picking vs placing** by rules relies on context (hands together before/after); low-context cases get lower confidence and go to review. A trained model learns it from the motion order.
5. **Playback of HEVC / MPEG-4 Part 2** needs ffmpeg for the automatic preview (installed on this machine).
6. **One live session at a time** (one camera, one CPU).
