"""Activity labels for training: a CSV you write by hand and/or labels exported from operator reviews.

labels.csv columns:
    video       path to the video file (absolute, or relative to the CSV)
    start_s     segment start in seconds
    end_s       segment end in seconds
    activity    one of the seven activities, or "Unknown" for movements outside them
    person      optional: "Person 01", ... (numbering as shown in the app); blank = the only person

Export reviewed events from the app database:
    python -m training.labels export --out data/labels_reviewed.csv
"""
import argparse
import csv
import os
import sys
from dataclasses import dataclass
from typing import List, Optional

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.activity.rules import ACTIVITIES, UNKNOWN  # noqa: E402

VALID = set(ACTIVITIES) | {UNKNOWN}
COLUMNS = ["video", "start_s", "end_s", "activity", "person"]


@dataclass
class Label:
    video: str
    start: float
    end: float
    activity: str
    person: Optional[str] = None


def read_labels(path: str) -> List[Label]:
    base = os.path.dirname(os.path.abspath(path))
    labels, errors = [], []
    with open(path, encoding="utf-8-sig", newline="") as fh:
        for n, row in enumerate(csv.DictReader(fh), start=2):
            try:
                video = row["video"].strip()
                if not os.path.isabs(video):
                    video = os.path.normpath(os.path.join(base, video))
                start, end = float(row["start_s"]), float(row["end_s"])
                activity = row["activity"].strip()
                if activity not in VALID:
                    raise ValueError(f"unknown activity '{activity}'")
                if end <= start:
                    raise ValueError("end_s must be after start_s")
                person = (row.get("person") or "").strip() or None
                labels.append(Label(video, start, end, activity, person))
            except (KeyError, ValueError) as e:
                errors.append(f"line {n}: {e}")
    if errors:
        raise ValueError(f"{path} has invalid rows:\n  " + "\n  ".join(errors))
    return labels


def write_labels(path: str, labels: List[Label]) -> None:
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(COLUMNS)
        for lb in labels:
            w.writerow([lb.video, f"{lb.start:.3f}", f"{lb.end:.3f}", lb.activity, lb.person or ""])


def reviewed_labels(db) -> List[Label]:
    """Operator-confirmed or reclassified events whose video file still exists."""
    import models

    rows = (
        db.query(models.ActivityEvent, models.Participant.tracked_id, models.Experiment.video_path)
        .outerjoin(models.Participant, models.ActivityEvent.person_id == models.Participant.id)
        .join(models.Experiment, models.ActivityEvent.experiment_id == models.Experiment.id)
        .filter(models.ActivityEvent.review_status.in_(["confirmed", "reclassified"]))
        .all()
    )
    out = []
    for e, tracked_id, video_path in rows:
        if not video_path or not os.path.exists(video_path) or e.activity_type not in VALID:
            continue
        out.append(Label(video_path, e.start_seconds or 0.0, e.end_seconds or 0.0, e.activity_type, tracked_id))
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    ex = sub.add_parser("export", help="export operator-reviewed events as labels")
    ex.add_argument("--out", required=True)
    tpl = sub.add_parser("template", help="write an empty labels.csv with the right columns")
    tpl.add_argument("--out", required=True)
    args = ap.parse_args(argv)

    if args.cmd == "template":
        write_labels(args.out, [])
        print(f"Wrote empty template {args.out}")
        return
    from database import SessionLocal

    db = SessionLocal()
    try:
        labels = reviewed_labels(db)
    finally:
        db.close()
    write_labels(args.out, labels)
    print(f"Exported {len(labels)} reviewed segments to {args.out}")


if __name__ == "__main__":
    main()
