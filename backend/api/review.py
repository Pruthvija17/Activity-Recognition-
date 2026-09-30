"""Human-in-the-loop review of Unknown and low-confidence events."""
import datetime
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

import models
from database import get_db
from services.activity.rules import ACTIVITIES, UNKNOWN
from services.analytics import person_label
from config import utcnow

router = APIRouter(prefix="/api/review", tags=["review"])

REVIEWABLE_LABELS = ACTIVITIES + [UNKNOWN]


class ReviewAction(BaseModel):
    action: Literal["confirm", "reject", "reclassify"]
    activity: Optional[str] = None


def _iso(dt: Optional[datetime.datetime]) -> Optional[str]:
    return dt.isoformat() + "Z" if dt else None


def event_dict(e: models.ActivityEvent, tracked_id: Optional[str], filename: Optional[str]) -> dict:
    return {
        "id": e.id,
        "experiment_id": e.experiment_id,
        "video_id": e.video_id or e.experiment_id,
        "video": filename,
        "person_id": e.person_id,
        "person": person_label(tracked_id, e.person_id, None, False),
        "activity_type": e.activity_type,
        "original_activity": e.original_activity,
        "note": e.note,
        "start_time": e.start_time,
        "end_time": e.end_time,
        "start_seconds": e.start_seconds,
        "end_seconds": e.end_seconds,
        "duration": e.duration,
        "confidence": e.confidence,
        "status": e.status,
        "review_status": e.review_status,
        "reviewed_at": _iso(e.reviewed_at),
    }


def _rows(db: Session):
    return (
        db.query(models.ActivityEvent, models.Participant.tracked_id, models.Experiment.video_filename)
        .outerjoin(models.Participant, models.ActivityEvent.person_id == models.Participant.id)
        .join(models.Experiment, models.ActivityEvent.experiment_id == models.Experiment.id)
    )


@router.get("/events")
def review_events(
    experiment_id: Optional[str] = None,
    status: Literal["pending", "reviewed", "all"] = "pending",
    db: Session = Depends(get_db),
):
    """Events that need (or received) an operator decision, oldest video first, then by time."""
    q = _rows(db)
    if experiment_id:
        q = q.filter(models.ActivityEvent.experiment_id == experiment_id)
    if status == "pending":
        q = q.filter(models.ActivityEvent.review_status == "pending")
    elif status == "reviewed":
        q = q.filter(models.ActivityEvent.review_status.in_(["confirmed", "rejected", "reclassified"]))
    else:
        q = q.filter(models.ActivityEvent.review_status != "auto")
    q = q.order_by(models.Experiment.start_time, models.ActivityEvent.start_seconds)
    return [event_dict(e, tid, fn) for e, tid, fn in q.all()]


@router.get("/summary")
def review_summary(db: Session = Depends(get_db)):
    counts = {k: 0 for k in ("pending", "confirmed", "rejected", "reclassified", "auto")}
    for (status,) in db.query(models.ActivityEvent.review_status).all():
        counts[status or "auto"] = counts.get(status or "auto", 0) + 1
    return counts


@router.post("/events/{event_id}")
def review_event(event_id: str, body: ReviewAction, db: Session = Depends(get_db)):
    """Record an operator decision. The model's original label is kept when reclassifying."""
    row = _rows(db).filter(models.ActivityEvent.id == event_id).first()
    if row is None:
        raise HTTPException(status_code=404, detail="Event not found.")
    e, tracked_id, filename = row

    if body.action == "confirm":
        e.review_status, e.status = "confirmed", "Confirmed"
    elif body.action == "reject":
        e.review_status, e.status = "rejected", "Rejected"
    else:
        if body.activity not in REVIEWABLE_LABELS:
            raise HTTPException(
                status_code=400,
                detail=f"Unknown activity '{body.activity}'. Choose one of: {', '.join(REVIEWABLE_LABELS)}.",
            )
        if body.activity == e.activity_type:
            e.review_status = "confirmed"
        else:
            if e.original_activity is None:
                e.original_activity = e.activity_type
            e.activity_type = body.activity
            e.review_status = "reclassified"
        e.status = "Confirmed"
    e.reviewed_at = utcnow()
    db.commit()
    return event_dict(e, tracked_id, filename)
