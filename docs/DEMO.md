# SIH26174 demo script — BAS AI

Target: 8–10 minutes, following the chain **Input → AI → Detection → Recognition → Logging → Review → Analytics → Report** (plan §29).

## The day before

- [ ] Record 2–3 short clips (30–90 s) in a lab-like setting: fixed camera, whole body in view, good light, H.264 MP4. Include standing, walking, reaching, picking up and placing an object, handling equipment, sitting — and one clip with **two people**, and a few seconds of an "unexpected" movement (stretching, waving).
- [ ] Upload and process them once (Experiments), review a couple of events, and set an expected workflow on one of them, so Analytics, Reports and the workflow panel have real content.
- [ ] Delete old test experiments you don't want to show (experiment page → Delete).
- [ ] Plug in / test the webcam in **Chrome or Edge at http://localhost:5173** (the in-app browser pane blocks the camera).

## 15 minutes before

```powershell
powershell -ExecutionPolicy Bypass -File .\start-backend.ps1
powershell -ExecutionPolicy Bypass -File .\start-frontend.ps1
cd backend; ..\.venv\Scripts\python scripts\smoke_test.py      # expect "22/22 checks passed"
```

- Close Teams/Zoom/other camera apps; close heavy programs (processing is CPU-bound).
- Open http://localhost:5173 in Chrome, full screen; zoom 90–100 %.

## Script

| # | Screen | Do | Say |
|---|---|---|---|
| 1 | Dashboard | point at the header | "Backend, database and AI models are live-checked, not hard-coded. It tells us exactly which engine produced the results and that we're on CPU." |
| 2 | Experiments | drop a prepared clip → **Upload & Process** | "Upload with progress, then background processing: YOLO pose detects people, ByteTrack keeps identities, pose features feed the activity engine." |
| 3 | Experiment detail (a processed clip) | play; click a timeline segment; click an event row | "Every person gets their own timeline. Events have start, end, duration and confidence; clicking jumps the video to that moment." |
| 4 | Workflow panel | show steps/deviations; **Edit steps** briefly | "We compare the observed sequence with the expected experiment workflow and flag missing, out-of-order and unexpected steps with timestamps — for operator review, never an automatic 'fail'." |
| 5 | Review Queue | show the reason on an Unknown event; press `1`–`8`, `Enter`; `X` on a false detection | "The system doesn't force every movement into seven classes. Unknown and low-confidence events come here with the reason; the operator's decision is stored and the model's original prediction kept — that's future training data." |
| 6 | Analytics | switch the experiment filter | "Time per activity, per-person breakdown and confidence distribution, all from stored events; rejected detections are excluded." |
| 7 | Reports | open the PDF | "One-click structured report: experiment info, participants, activity log, exceptions, workflow result, review status. Also CSV and JSON." |
| 8 | Live Monitor | **Start camera** → **Start AI monitoring**; stand, sit, reach; **Stop** | "Live frames are analysed a few times per second with the same engine; stopping saves the session as a normal experiment, recording included." |
| 9 | Settings | sensitivity + training panel | "Unknown sensitivity is configurable. And every reviewed event becomes a label: with enough footage, one command trains a temporal model that the app picks up automatically." |

## If something goes wrong

| Symptom | Fix |
|---|---|
| "Backend Offline" | start `start-backend.ps1`; the page reconnects by itself |
| Camera "permission denied" | Chrome address bar → site settings → Camera → Allow; reload |
| Camera "in use" | close Teams/Zoom/other tabs using it |
| Video won't play | it's HEVC/MPEG-4; check `ffmpeg` is on PATH (Settings/Status) and re-process once |
| Processing slow | show a pre-processed experiment instead; mention CPU-only |
| Only "Unknown" live | step back so hips and legs are in view (upper-body-only is reported as such) |

## Honest answers to likely questions

- *Accuracy?* "The rule baseline hasn't been measured on real BAS footage yet; the training tool produces an accuracy / F1 / confusion-matrix report as soon as we have labelled clips, split by video to avoid leakage."
- *Why not a deep model already?* "No labelled BAS data existed. We built the pipeline so every operator review creates labels, and a temporal GRU trains from them with one command."
- *GPU?* "Not required; used automatically when present."
