# Training the activity model

Out of the box, BAS AI labels activities with **transparent pose rules** (`services/activity/rules.py`).
With your own labelled footage you can train a **temporal model** (a small GRU over ~2 s of pose
history). The backend uses it automatically after a restart; the header, Dashboard and Settings show
which engine is active and the model's test metrics.

A trained model can learn things rules cannot, e.g. telling *picking up* from *placing* an object by
the order of the movement. It is only as good as the footage it was trained on.

## 1. Record footage

- Fixed camera, whole body in view, good light, H.264 MP4 if possible (see README).
- Several people and sessions: **at least 3 videos** (more is much better), because the test set must
  come from videos the model never saw.
- Aim for **≥ 20 labelled segments per activity**, each 2–10 s: Standing, Sitting, Walking, Reaching,
  Picking up an object, Placing an object, Handling experimental equipment.
- Also record some movements that are *none* of these (stretching, waving, bending to tie a shoe…)
  and label them `Unknown`; they are used to measure Unknown detection.

## 2. Label it (two ways, combinable)

**A. In the app (easiest).** Upload and process the videos, then go through the Review Queue:
every event you **confirm** or **reclassify** becomes a label. Settings → *Activity Model & Training
Data* shows progress per activity. Export them:

```powershell
cd backend
..\.venv\Scripts\python -m training.labels export --out data\labels.csv
```

(or use the *labels CSV* link in Settings).

**B. By hand.** `..\.venv\Scripts\python -m training.labels template --out data\labels.csv` writes the
columns; one row per segment:

| video | start_s | end_s | activity | person |
|---|---|---|---|---|
| D:\footage\session1.mp4 | 12.0 | 17.5 | Reaching | Person 01 |

`person` uses the app's numbering (as shown on the experiment page); leave it blank when only one
person is in view. Paths may be relative to the CSV.

## 3. Train

```powershell
cd backend
..\.venv\Scripts\python -m training.train --labels data\labels.csv
```

This extracts pose features for every labelled video (cached in `data/features`, using exactly the
app's detector/tracker/features), cuts labelled segments into 2 s windows, splits
**train / validation / test by video**, trains with class weighting and early stopping, calibrates
Unknown detection, evaluates on the held-out videos and writes:

- `weights/activity_gru.pt` + `weights/activity_gru.json` (spec, normalisation, metrics, split)
- `docs/MODEL_EVALUATION.md` (accuracy, per-class precision/recall/F1, confusion matrix, Unknown detection)

It refuses to train with fewer than 3 videos (`--allow-segment-split` overrides this, but test
metrics are then optimistic and the report says so) and warns about activities with little data.
It will not replace an existing model without `--force`.

Restart the backend to use the new model. To go back to the rules, move `activity_gru.pt` away and restart.

## 4. Evaluate again later

```powershell
..\.venv\Scripts\python -m training.evaluate --labels data\labels.csv            # held-out test videos
..\.venv\Scripts\python -m training.evaluate --labels data\new_labels.csv --all-videos
```

## How Unknown works with a trained model

A sample becomes Unknown when (1) the class distribution is too flat (entropy above the Settings
sensitivity), (2) the best probability is below 40 %, (3) the pose isn't visible, or (4) the model's
internal representation is further from the predicted activity's training examples than ~99 % of
them (prototype distance, calibrated at training time). (4) matters because a classifier trained on
seven activities otherwise confidently forces unseen movements into one of them.

## Notes and limits

- Features are recorded at the app's sampling rate (8 fps for videos). Live monitoring at a different
  rate stretches the 2 s window in time; choose **8 fps** in the Live Monitor for the closest match.
- The feature layout is versioned; after code changes that alter it, an old model is refused (with a
  clear message) and the rules are used until you retrain.
- `data/` (feature cache, label files) is not committed to git.
