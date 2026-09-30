# BAS AI — Model Weights

Model files are loaded once at backend startup from this directory. Weight files are not committed to git.

| Component | File | Status | Purpose |
| :--- | :--- | :--- | :--- |
| Person detector + pose + tracking | `yolo11n-pose.pt` | **In use** | Ultralytics YOLO11 pose: person boxes, 17 COCO keypoints; IDs via ByteTrack |
| Activity classifier (default) | — | **Rule-based baseline** | Transparent rules on pose keypoints (`services/activity/rules.py`); used whenever no compatible trained model is present |
| Trained temporal classifier | `activity_gru.pt` + `activity_gru.json` | Optional | GRU over ~2 s of pose features; created by `python -m training.train` (see docs/TRAINING.md) and used automatically when present and compatible |

If `yolo11n-pose.pt` is missing, the backend attempts a one-time download of the official Ultralytics weights into this folder. If that fails (offline), `/api/system/status` reports `yolo_model: false` with the reason, and processing is refused instead of producing fabricated results.

## Activity classes

1. `Standing`
2. `Sitting`
3. `Walking`
4. `Reaching`
5. `Picking up an object`
6. `Placing an object`
7. `Handling experimental equipment`

Plus `Unknown` for detections the engine cannot confidently assign; these go to the Review Queue.

`model_config.json` holds the sampling, tracking, open-set and event-segmentation parameters used by the engine.
