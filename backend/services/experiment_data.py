"""Shared queries for one experiment: its events, people and workflow evaluation."""
import json
import logging
from typing import List, Optional, Tuple

from sqlalchemy.orm import Session

import models
from services.workflow import DEFAULT_WORKFLOW, ObservedStep, evaluate

log = logging.getLogger("bas.experiments")


def event_rows(db: Session, experiment_id: str, include_rejected: bool = True):
    """(event, tracked_id e.g. 'Person 01') pairs ordered by time."""
    q = (
        db.query(models.ActivityEvent, models.Participant.tracked_id)
        .outerjoin(models.Participant, models.ActivityEvent.person_id == models.Participant.id)
        .filter(models.ActivityEvent.experiment_id == experiment_id)
    )
    if not include_rejected:
        q = q.filter(models.ActivityEvent.review_status != "rejected")
    return q.order_by(models.ActivityEvent.start_seconds, models.Participant.tracked_id).all()


def expected_sequence(db: Session, experiment_id: str) -> Tuple[List[str], bool]:
    """(steps, configured). Falls back to the default workflow when none was configured."""
    cfg = db.query(models.ExperimentConfig).filter(models.ExperimentConfig.experiment_id == experiment_id).first()
    if cfg and cfg.expected_sequence:
        try:
            steps = json.loads(cfg.expected_sequence)
            if isinstance(steps, list) and steps:
                return [str(s) for s in steps], True
        except ValueError:
            log.warning("Invalid workflow config for %s; using default", experiment_id)
    return list(DEFAULT_WORKFLOW), False


def workflow_result(db: Session, experiment_id: str, person_id: Optional[str] = None) -> dict:
    steps, configured = expected_sequence(db, experiment_id)
    observed = [
        ObservedStep(e.activity_type, e.start_seconds or 0.0, e.end_seconds or 0.0, tid or e.person_id)
        for e, tid in event_rows(db, experiment_id, include_rejected=False)
        if person_id is None or e.person_id == person_id
    ]
    result = evaluate(steps, observed)
    result.update({"configured": configured, "scope": person_id or "all people"})
    return result
