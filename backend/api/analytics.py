"""Analytics and dashboard summary endpoints (all figures come from stored events)."""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

import models
from database import get_db
from runtime import ai_pipeline
from services.analytics import compute_analytics, dashboard_summary

router = APIRouter(tags=["analytics"])


@router.get("/api/analytics")
def analytics(experiment_id: Optional[str] = None, db: Session = Depends(get_db)):
    if experiment_id and db.get(models.Experiment, experiment_id) is None:
        raise HTTPException(status_code=404, detail="Experiment not found.")
    result = compute_analytics(db, experiment_id)
    result["activity_engine"] = ai_pipeline.get_model_status()["engine"]
    return result


@router.get("/api/dashboard/summary")
def dashboard(db: Session = Depends(get_db)):
    return dashboard_summary(db)
