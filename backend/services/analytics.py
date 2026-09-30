"""Analytics and dashboard figures computed from stored activity events.

Rejected events (operator marked them as false detections) are excluded from every figure.
"""
from collections import defaultdict
from typing import Optional

from sqlalchemy.orm import Session

import models
from services.activity.rules import ACTIVITIES, UNKNOWN

# Categorical palette validated for colour-vision deficiency in this fixed order (adjacent CVD
# delta-E >= 9.1). Colour follows the activity, never its rank. Keep in sync with
# frontend/src/lib/activityColors.ts.
ACTIVITY_COLORS = {
    "Standing": "#2a78d6",
    "Sitting": "#eb6834",
    "Walking": "#1baf7a",
    "Reaching": "#eda100",
    "Picking up an object": "#e87ba4",
    "Placing an object": "#008300",
    "Handling experimental equipment": "#4a3aa7",
    UNKNOWN: "#e34948",
}
ACTIVITY_ORDER = ACTIVITIES + [UNKNOWN]
CONFIDENCE_BUCKETS = [(0.0, 0.5, "<50%"), (0.5, 0.6, "50-60%"), (0.6, 0.7, "60-70%"),
                      (0.7, 0.8, "70-80%"), (0.8, 0.9, "80-90%"), (0.9, 1.01, "90-100%")]


def _event_rows(db: Session, experiment_id: Optional[str] = None):
    q = (
        db.query(models.ActivityEvent, models.Participant.tracked_id, models.Experiment.video_filename)
        .outerjoin(models.Participant, models.ActivityEvent.person_id == models.Participant.id)
        .join(models.Experiment, models.ActivityEvent.experiment_id == models.Experiment.id)
    )
    if experiment_id:
        q = q.filter(models.ActivityEvent.experiment_id == experiment_id)
    return q.all()


def person_label(tracked_id: Optional[str], person_id: str, filename: Optional[str], with_video: bool) -> str:
    label = tracked_id or person_id
    return f"{label} · {filename}" if with_video and filename else label


def _mean(values):
    return round(sum(values) / len(values), 4) if values else None


def compute_analytics(db: Session, experiment_id: Optional[str] = None) -> dict:
    rows = _event_rows(db, experiment_id)
    kept = [(e, tid, fn) for e, tid, fn in rows if e.review_status != "rejected"]
    events = [e for e, _, _ in kept]
    multi = experiment_id is None and len({e.experiment_id for e in events}) > 1

    by_activity = defaultdict(lambda: {"count": 0, "seconds": 0.0, "conf": []})
    for e in events:
        a = by_activity[e.activity_type]
        a["count"] += 1
        a["seconds"] += e.duration or 0.0
        a["conf"].append(e.confidence or 0.0)
    order = {name: i for i, name in enumerate(ACTIVITY_ORDER)}
    distribution = [
        {
            "name": name,
            "count": v["count"],
            "seconds": round(v["seconds"], 2),
            "avg_confidence": _mean(v["conf"]),
            "color": ACTIVITY_COLORS.get(name, "#94A3B8"),
        }
        for name, v in sorted(by_activity.items(), key=lambda kv: order.get(kv[0], 99))
    ]

    people = defaultdict(lambda: {"events": 0, "unknowns": 0, "seconds": 0.0, "conf": [],
                                  "by_activity": defaultdict(float), "experiment_id": None, "name": ""})
    for e, tracked_id, filename in kept:
        p = people[e.person_id]
        p["name"] = person_label(tracked_id, e.person_id, filename, multi)
        p["experiment_id"] = e.experiment_id
        p["events"] += 1
        p["unknowns"] += e.activity_type == UNKNOWN
        p["seconds"] += e.duration or 0.0
        p["conf"].append(e.confidence or 0.0)
        p["by_activity"][e.activity_type] += e.duration or 0.0
    person_stats = [
        {
            "person_id": pid,
            "name": v["name"],
            "experiment_id": v["experiment_id"],
            "events": v["events"],
            "unknowns": v["unknowns"],
            "active_seconds": round(v["seconds"], 2),
            "avg_confidence": _mean(v["conf"]),
            "top_activity": max(v["by_activity"], key=v["by_activity"].get) if v["by_activity"] else None,
            "seconds_by_activity": {a: round(sec, 2) for a, sec in v["by_activity"].items()},
        }
        for pid, v in sorted(people.items(), key=lambda kv: kv[1]["name"])
    ]

    histogram = [
        {"bucket": label, "count": sum(1 for e in events if lo <= (e.confidence or 0.0) < hi)}
        for lo, hi, label in CONFIDENCE_BUCKETS
    ]

    return {
        "experiment_id": experiment_id,
        "experiments_count": len({e.experiment_id for e in events}),
        "people_count": len(people),
        "total_events": len(events),
        "rejected_events": len(rows) - len(kept),
        "pending_review": sum(1 for e in events if e.review_status == "pending"),
        "reviewed_events": sum(1 for e in events if e.review_status in ("confirmed", "reclassified")),
        "unknown_events": sum(1 for e in events if e.activity_type == UNKNOWN),
        "avg_confidence": _mean([e.confidence or 0.0 for e in events]),
        "total_activity_seconds": round(sum(e.duration or 0.0 for e in events), 2),
        "activity_distribution": distribution,
        "person_stats": person_stats,
        "confidence_histogram": histogram,
    }


def dashboard_summary(db: Session, recent_limit: int = 8) -> dict:
    experiments = db.query(models.Experiment).order_by(models.Experiment.start_time.desc()).all()
    counts = defaultdict(int)
    for exp in experiments:
        counts[exp.status] += 1

    active = [e for e in experiments if e.status in ("processing", "queued")]
    active.sort(key=lambda e: (e.status != "processing", e.start_time))
    current = active[0] if active else None

    stats = compute_analytics(db)

    rows = _event_rows(db)
    kept = [(e, tid, fn) for e, tid, fn in rows if e.review_status != "rejected"]
    processed_at = {e.id: e.processed_at for e in experiments}
    kept.sort(key=lambda r: (processed_at.get(r[0].experiment_id) is not None,
                             processed_at.get(r[0].experiment_id), r[0].start_seconds or 0.0), reverse=True)
    recent = [
        {
            "id": e.id,
            "experiment_id": e.experiment_id,
            "video": fn,
            "person": person_label(tid, e.person_id, None, False),
            "activity": e.activity_type,
            "start_time": e.start_time,
            "end_time": e.end_time,
            "confidence": e.confidence,
            "review_status": e.review_status,
        }
        for e, tid, fn in kept[:recent_limit]
    ]

    return {
        "experiments": {
            "total": len(experiments),
            "active": counts["processing"] + counts["queued"],
            "completed": counts["completed"],
            "failed": counts["failed"],
            "uploaded": counts["uploaded"],
        },
        "people_detected": stats["people_count"],
        "total_events": stats["total_events"],
        "pending_review": stats["pending_review"],
        "unknown_events": stats["unknown_events"],
        "avg_confidence": stats["avg_confidence"],
        "current_job": {
            "video_id": current.id,
            "filename": current.video_filename or current.name,
            "status": current.status,
            "progress": current.progress or 0.0,
        } if current else None,
        "recent_events": recent,
    }
