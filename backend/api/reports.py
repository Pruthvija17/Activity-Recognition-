"""Experiment reports: list, JSON, CSV and PDF."""
import re

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse, Response
from sqlalchemy.orm import Session

import models
from database import get_db
from runtime import ai_pipeline
from services.analytics import compute_analytics
from services.experiment_data import workflow_result
from services.reports import build_report, to_csv, to_pdf

router = APIRouter(prefix="/api/reports", tags=["reports"])


def _completed(db: Session, experiment_id: str) -> models.Experiment:
    exp = db.get(models.Experiment, experiment_id)
    if exp is None:
        raise HTTPException(status_code=404, detail="Experiment not found.")
    if exp.status != "completed":
        raise HTTPException(status_code=409, detail=f"No report yet: the experiment is {exp.status}.")
    return exp


def _filename(exp: models.Experiment, ext: str) -> str:
    stem = re.sub(r"[^A-Za-z0-9_-]+", "_", (exp.video_filename or exp.id).rsplit(".", 1)[0])[:60]
    return f"BAS_report_{exp.id}_{stem}.{ext}"


def _attachment(name: str) -> dict:
    return {"Content-Disposition": f'attachment; filename="{name}"'}


@router.get("")
def list_reports(db: Session = Depends(get_db)):
    """One entry per completed experiment, newest first."""
    out = []
    for exp in (db.query(models.Experiment).filter(models.Experiment.status == "completed")
                .order_by(models.Experiment.processed_at.desc()).all()):
        stats = compute_analytics(db, exp.id)
        wf = workflow_result(db, exp.id)
        out.append({
            "report_id": f"REP-{exp.id}",
            "experiment_id": exp.id,
            "video": exp.video_filename or exp.name,
            "processed_at": exp.processed_at.isoformat() + "Z" if exp.processed_at else None,
            "duration_seconds": exp.duration_seconds,
            "events": stats["total_events"],
            "people": stats["people_count"],
            "unknown_events": stats["unknown_events"],
            "pending_review": stats["pending_review"],
            "avg_confidence": stats["avg_confidence"],
            "workflow_deviations": wf["deviation_count"],
            "workflow_compliant": wf["is_compliant"],
        })
    return out


@router.get("/{experiment_id}")
def report_json(experiment_id: str, download: bool = False, db: Session = Depends(get_db)):
    exp = _completed(db, experiment_id)
    report = build_report(db, exp, ai_pipeline.confidence_threshold)
    headers = _attachment(_filename(exp, "json")) if download else None
    return JSONResponse(report, headers=headers)


@router.get("/{experiment_id}/csv")
def report_csv(experiment_id: str, db: Session = Depends(get_db)):
    exp = _completed(db, experiment_id)
    body = to_csv(build_report(db, exp, ai_pipeline.confidence_threshold))
    return Response(body, media_type="text/csv; charset=utf-8", headers=_attachment(_filename(exp, "csv")))


@router.get("/{experiment_id}/pdf")
def report_pdf(experiment_id: str, db: Session = Depends(get_db)):
    exp = _completed(db, experiment_id)
    body = to_pdf(build_report(db, exp, ai_pipeline.confidence_threshold))
    return Response(body, media_type="application/pdf", headers=_attachment(_filename(exp, "pdf")))
