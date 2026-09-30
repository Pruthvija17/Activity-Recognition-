"""Experiment detail and workflow configuration."""
import json
import logging
import os
import uuid
from collections import OrderedDict
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

import models
from api.review import event_dict
from api.videos import video_info
from database import get_db
from services.activity.rules import ACTIVITIES, UNKNOWN
from services.experiment_data import event_rows, workflow_result
from config import utcnow

log = logging.getLogger("bas.experiments")

router = APIRouter(prefix="/api/experiments", tags=["experiments"])


class WorkflowConfig(BaseModel):
    expected_sequence: List[str] = Field(min_length=1, max_length=30)


def _experiment(db: Session, experiment_id: str) -> models.Experiment:
    exp = db.get(models.Experiment, experiment_id)
    if exp is None:
        raise HTTPException(status_code=404, detail="Experiment not found.")
    return exp


@router.get("/{experiment_id}")
def experiment_detail(experiment_id: str, db: Session = Depends(get_db)):
    """Everything the detail page needs: video info, people, all events and the workflow check."""
    exp = _experiment(db, experiment_id)
    rows = event_rows(db, experiment_id)
    people: "OrderedDict[str, dict]" = OrderedDict()
    for e, tid in rows:
        p = people.setdefault(e.person_id, {"person_id": e.person_id, "label": tid or e.person_id,
                                            "events": 0, "first_seen": e.start_seconds})
        if e.review_status != "rejected":
            p["events"] += 1
    return {
        "experiment": video_info(exp, events_count=len(rows)),
        "people": sorted(people.values(), key=lambda p: p["label"]),
        "events": [event_dict(e, tid, exp.video_filename) for e, tid in rows],
        "workflow": workflow_result(db, experiment_id),
    }


@router.get("/{experiment_id}/workflow")
def get_workflow(experiment_id: str, person_id: Optional[str] = None, db: Session = Depends(get_db)):
    _experiment(db, experiment_id)
    return workflow_result(db, experiment_id, person_id)


@router.put("/{experiment_id}/workflow")
def set_workflow(experiment_id: str, body: WorkflowConfig, db: Session = Depends(get_db)):
    _experiment(db, experiment_id)
    allowed = ACTIVITIES + [UNKNOWN]
    bad = [s for s in body.expected_sequence if s not in allowed]
    if bad:
        raise HTTPException(status_code=400, detail=f"Unknown activities in workflow: {', '.join(bad)}.")
    cfg = db.query(models.ExperimentConfig).filter(models.ExperimentConfig.experiment_id == experiment_id).first()
    if cfg is None:
        cfg = models.ExperimentConfig(id=str(uuid.uuid4()), experiment_id=experiment_id)
        db.add(cfg)
    cfg.expected_sequence = json.dumps(body.expected_sequence)
    cfg.updated_at = utcnow()
    db.commit()
    return workflow_result(db, experiment_id)


@router.delete("/{experiment_id}/workflow")
def reset_workflow(experiment_id: str, db: Session = Depends(get_db)):
    """Go back to the default workflow."""
    _experiment(db, experiment_id)
    db.query(models.ExperimentConfig).filter(models.ExperimentConfig.experiment_id == experiment_id).delete()
    db.commit()
    return workflow_result(db, experiment_id)


@router.delete("/{experiment_id}")
def delete_experiment(experiment_id: str, db: Session = Depends(get_db)):
    """Permanently delete an experiment: its events, people, workflow and video files."""
    exp = _experiment(db, experiment_id)
    if exp.status in ("queued", "processing", "live"):
        raise HTTPException(status_code=409, detail=f"Cannot delete while the experiment is {exp.status}.")
    files = [p for p in (exp.video_path, exp.preview_path) if p]
    db.query(models.ActivityEvent).filter(models.ActivityEvent.experiment_id == experiment_id).delete()
    db.query(models.Participant).filter(models.Participant.experiment_id == experiment_id).delete()
    db.query(models.ExperimentConfig).filter(models.ExperimentConfig.experiment_id == experiment_id).delete()
    db.delete(exp)
    db.commit()
    removed = 0
    for path in files:
        try:
            if os.path.exists(path):
                os.remove(path)
                removed += 1
        except OSError as e:
            log.warning("Could not remove %s: %s", path, e)
    log.info("Deleted experiment %s (%d file(s) removed)", experiment_id, removed)
    return {"deleted": experiment_id, "files_removed": removed}
