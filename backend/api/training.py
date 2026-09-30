"""Training-data status for the trainable activity model (training itself runs from the command line)."""
import io
import os
from collections import Counter

from fastapi import APIRouter, Depends
from fastapi.responses import Response
from sqlalchemy.orm import Session

from database import get_db
from runtime import ai_pipeline
from services.activity.rules import ACTIVITIES, UNKNOWN
from training.labels import COLUMNS, reviewed_labels
from training.train import MIN_VIDEOS_FOR_VIDEO_SPLIT

router = APIRouter(prefix="/api/training", tags=["training"])

RECOMMENDED_SEGMENTS = 20


@router.get("/summary")
def training_summary(db: Session = Depends(get_db)):
    """How much labelled data operator reviews have produced, and what model is in use."""
    labels = reviewed_labels(db)
    counts = Counter(lb.activity for lb in labels)
    videos = len({lb.video for lb in labels})
    per_activity = [{"activity": a, "segments": counts.get(a, 0)} for a in ACTIVITIES + [UNKNOWN]]
    missing = [a for a in ACTIVITIES if counts.get(a, 0) < RECOMMENDED_SEGMENTS]
    status = ai_pipeline.get_model_status()
    return {
        "labelled_segments": len(labels),
        "videos": videos,
        "per_activity": per_activity,
        "recommended_segments_per_activity": RECOMMENDED_SEGMENTS,
        "min_videos": MIN_VIDEOS_FOR_VIDEO_SPLIT,
        "ready": videos >= MIN_VIDEOS_FOR_VIDEO_SPLIT and not missing,
        "needs_more": missing,
        "engine": status["engine"],
        "trained_model": status["activity_model_info"],
        "model_error": status["activity_model_error"],
    }


@router.get("/labels.csv")
def reviewed_labels_csv(db: Session = Depends(get_db)):
    """Operator-reviewed events as a labels CSV (the input format of training/train.py)."""
    import csv

    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\r\n")
    w.writerow(COLUMNS)
    for lb in reviewed_labels(db):
        w.writerow([os.path.abspath(lb.video), f"{lb.start:.3f}", f"{lb.end:.3f}", lb.activity, lb.person or ""])
    return Response(buf.getvalue(), media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": 'attachment; filename="bas_reviewed_labels.csv"'})
