"""Structured experiment reports and their CSV / PDF renderings.

Every figure comes from stored events; rejected events are excluded from the log and totals
(their count is reported). Reports are only produced for completed experiments.
"""
import csv
import datetime
import io
from typing import Optional

from sqlalchemy.orm import Session

import models
from services.activity.rules import UNKNOWN
from services.analytics import ACTIVITY_COLORS, compute_analytics
from services.experiment_data import event_rows, workflow_result
from config import utcnow


def _iso(dt: Optional[datetime.datetime]) -> Optional[str]:
    return dt.isoformat() + "Z" if dt else None


def _clock(seconds: Optional[float]) -> str:
    if seconds is None:
        return "-"
    s = int(round(seconds))
    return f"{s // 3600:02d}:{s % 3600 // 60:02d}:{s % 60:02d}"


def build_report(db: Session, exp: models.Experiment, confidence_threshold: float) -> dict:
    rows = event_rows(db, exp.id)
    kept = [(e, tid) for e, tid in rows if e.review_status != "rejected"]
    stats = compute_analytics(db, exp.id)
    workflow = workflow_result(db, exp.id)

    def log_entry(e, tid):
        return {
            "person": tid or e.person_id,
            "activity": e.activity_type,
            "start_time": e.start_time,
            "end_time": e.end_time,
            "start_seconds": e.start_seconds,
            "end_seconds": e.end_seconds,
            "duration_seconds": e.duration,
            "confidence": round(e.confidence or 0.0, 4),
            "review_status": e.review_status,
            "original_activity": e.original_activity,
            "note": e.note,
        }

    log = [log_entry(e, tid) for e, tid in kept]
    unknown = [x for x in log if x["activity"] == UNKNOWN]
    low = [x for x in log if x["activity"] != UNKNOWN and x["confidence"] < confidence_threshold]
    review_counts = {k: sum(1 for e, _ in rows if e.review_status == k)
                     for k in ("auto", "pending", "confirmed", "reclassified", "rejected")}

    return {
        "report_id": f"REP-{exp.id}",
        "generated_at": _iso(utcnow()),
        "experiment": {
            "experiment_id": exp.id,
            "video": exp.video_filename or exp.name,
            "source": exp.source or "upload",
            "uploaded_at": _iso(exp.start_time),
            "processed_at": _iso(exp.processed_at),
            "duration_seconds": exp.duration_seconds,
            "fps": exp.fps,
            "frame_count": exp.frame_count,
            "processing_seconds": exp.processing_seconds,
            "activity_engine": exp.engine,
        },
        "participants": {
            "count": stats["people_count"],
            "people": [
                {k: p[k] for k in ("name", "events", "active_seconds", "top_activity", "unknowns", "avg_confidence")}
                for p in stats["person_stats"]
            ],
        },
        "summary": {
            "total_events": stats["total_events"],
            "total_activity_seconds": stats["total_activity_seconds"],
            "avg_confidence": stats["avg_confidence"],
            "unknown_events": len(unknown),
            "low_confidence_events": len(low),
            "confidence_threshold": confidence_threshold,
            "workflow_deviations": workflow["deviation_count"],
        },
        "activity_summary": [
            {k: d[k] for k in ("name", "count", "seconds", "avg_confidence")} for d in stats["activity_distribution"]
        ],
        "activity_log": log,
        "exceptions": {
            "unknown_events": unknown,
            "low_confidence_events": low,
            "workflow_deviations": workflow["deviations"],
        },
        "workflow": {k: workflow[k] for k in ("expected_sequence", "observed_sequence", "is_compliant", "message",
                                              "completion", "configured", "next_expected_step")},
        "review_status": {
            "auto_accepted": review_counts["auto"],
            "reviewed": review_counts["confirmed"] + review_counts["reclassified"],
            "corrected": review_counts["reclassified"],
            "rejected": review_counts["rejected"],
            "unresolved": review_counts["pending"],
        },
        "notes": [
            f"Activity labels were produced by: {exp.engine or 'unknown engine'}.",
            "Rejected events (operator-marked false detections) are excluded from the log and all totals.",
            "Workflow deviations indicate that operator review is required; they do not mean the experiment failed.",
        ],
    }


CSV_COLUMNS = ["report_id", "experiment_id", "video", "person", "activity", "start_time", "end_time",
               "start_seconds", "end_seconds", "duration_seconds", "confidence", "review_status",
               "original_activity", "note"]


def to_csv(report: dict) -> str:
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=CSV_COLUMNS, extrasaction="ignore", lineterminator="\r\n")
    w.writeheader()
    exp = report["experiment"]
    for row in report["activity_log"]:
        w.writerow({**row, "report_id": report["report_id"], "experiment_id": exp["experiment_id"],
                    "video": exp["video"]})
    # BOM so Excel opens UTF-8 correctly.
    return "﻿" + buf.getvalue()


def to_pdf(report: dict) -> bytes:
    from reportlab.graphics.shapes import Drawing, Rect, String
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    deep = colors.HexColor("#0F4C81")
    soft = colors.HexColor("#E0F2FE")
    ice = colors.HexColor("#EFF9FF")
    ink2 = colors.HexColor("#475569")
    styles = getSampleStyleSheet()
    h1 = styles["Title"].clone("h1", textColor=deep, alignment=0, fontSize=18)
    h2 = styles["Heading2"].clone("h2", textColor=deep, spaceBefore=10, spaceAfter=4)
    body = styles["BodyText"].clone("b", fontSize=9, leading=12)
    small = body.clone("s", fontSize=8, textColor=ink2)

    def table(data, widths, header=True):
        t = Table(data, colWidths=widths, repeatRows=1 if header else 0)
        style = [
            ("FONT", (0, 0), (-1, -1), "Helvetica", 8),
            ("TEXTCOLOR", (0, 0), (-1, -1), colors.HexColor("#0F172A")),
            ("LINEBELOW", (0, 0), (-1, -1), 0.25, soft),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("TOPPADDING", (0, 0), (-1, -1), 3),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ]
        if header:
            style += [("FONT", (0, 0), (-1, 0), "Helvetica-Bold", 8), ("BACKGROUND", (0, 0), (-1, 0), ice)]
        t.setStyle(TableStyle(style))
        return t

    def pct(v):
        return "-" if v is None else f"{round(v * 100)}%"

    exp, summ = report["experiment"], report["summary"]
    story = [
        Paragraph("BAS Activity Intelligence - Experiment Report", h1),
        Paragraph(f"Report {report['report_id']} · generated {report['generated_at'][:19].replace('T', ' ')} UTC", small),
        Spacer(1, 6 * mm),
        Paragraph("Experiment", h2),
        table([
            ["Experiment ID", exp["experiment_id"], "Video", exp["video"]],
            ["Uploaded (UTC)", (exp["uploaded_at"] or "-")[:19].replace("T", " "),
             "Processed (UTC)", (exp["processed_at"] or "-")[:19].replace("T", " ")],
            ["Video length", _clock(exp["duration_seconds"]), "Processing time",
             f"{exp['processing_seconds']:.1f} s" if exp["processing_seconds"] is not None else "-"],
            ["Activity engine", exp["activity_engine"] or "-", "People detected", str(report["participants"]["count"])],
        ], [32 * mm, 58 * mm, 32 * mm, 58 * mm], header=False),
        Paragraph("Summary", h2),
        table([
            ["Events", "Activity time", "Avg confidence", "Unknown", "Low confidence", "Workflow deviations"],
            [summ["total_events"], _clock(summ["total_activity_seconds"]), pct(summ["avg_confidence"]),
             summ["unknown_events"], summ["low_confidence_events"], summ["workflow_deviations"]],
        ], [30 * mm] * 6),
    ]

    acts = report["activity_summary"]
    if acts:
        story.append(Paragraph("Time per activity", h2))
        width, bar_h, gap, label_w = 180 * mm, 12, 6, 58 * mm
        max_s = max(a["seconds"] for a in acts) or 1.0
        d = Drawing(width, len(acts) * (bar_h + gap) + 4)
        for i, a in enumerate(acts):
            y = d.height - (i + 1) * (bar_h + gap)
            w = (width - label_w - 20 * mm) * a["seconds"] / max_s
            d.add(String(0, y + 3, a["name"], fontName="Helvetica", fontSize=8, fillColor=ink2))
            d.add(Rect(label_w, y, max(w, 1), bar_h, fillColor=colors.HexColor(ACTIVITY_COLORS.get(a["name"], "#94A3B8")),
                       strokeColor=None))
            d.add(String(label_w + w + 4, y + 3, _clock(a["seconds"]), fontName="Helvetica", fontSize=8, fillColor=ink2))
        story.append(d)
        story.append(table(
            [["Activity", "Events", "Time", "Avg confidence"]]
            + [[a["name"], a["count"], _clock(a["seconds"]), pct(a["avg_confidence"])] for a in acts],
            [70 * mm, 30 * mm, 35 * mm, 35 * mm]))

    people = report["participants"]["people"]
    if people:
        story.append(Paragraph("Participants", h2))
        story.append(table(
            [["Person", "Events", "Active time", "Main activity", "Unknown", "Avg confidence"]]
            + [[p["name"], p["events"], _clock(p["active_seconds"]), p["top_activity"] or "-", p["unknowns"],
                pct(p["avg_confidence"])] for p in people],
            [28 * mm, 18 * mm, 24 * mm, 62 * mm, 18 * mm, 28 * mm]))

    wf = report["workflow"]
    story.append(Paragraph("Workflow", h2))
    story.append(Paragraph(
        f"Expected{'' if wf['configured'] else ' (default)'}: {' → '.join(wf['expected_sequence'])}", body))
    story.append(Paragraph(f"Observed: {' → '.join(wf['observed_sequence']) or '-'}", body))
    story.append(Paragraph(f"<b>{wf['message']}</b> Completed {round(wf['completion'] * 100)}% of steps.", body))
    devs = report["exceptions"]["workflow_deviations"]
    if devs:
        story.append(table(
            [["Type", "Activity", "Time", "Person", "Detail"]]
            + [[d["type"].replace("_", " "), d["activity"], _clock(d["time"]), d["person"] or "-",
                Paragraph(d["detail"], small)] for d in devs],
            [22 * mm, 42 * mm, 18 * mm, 20 * mm, 78 * mm]))

    rs = report["review_status"]
    story.append(Paragraph("Review status", h2))
    story.append(table(
        [["Auto-accepted", "Reviewed", "Corrected", "Rejected", "Unresolved"],
         [rs["auto_accepted"], rs["reviewed"], rs["corrected"], rs["rejected"], rs["unresolved"]]],
        [36 * mm] * 5))

    log_rows = report["activity_log"]
    story.append(Paragraph("Activity log", h2))
    if log_rows:
        story.append(table(
            [["Person", "Activity", "Start", "End", "Duration", "Conf.", "Review"]]
            + [[r["person"], r["activity"] + (f" (was {r['original_activity']})" if r["original_activity"] else ""),
                r["start_time"], r["end_time"], f"{r['duration_seconds']:.1f} s", pct(r["confidence"]),
                r["review_status"]] for r in log_rows],
            [20 * mm, 68 * mm, 18 * mm, 18 * mm, 18 * mm, 14 * mm, 24 * mm]))
    else:
        story.append(Paragraph("No activity events.", body))

    story.append(Spacer(1, 6 * mm))
    for n in report["notes"]:
        story.append(Paragraph(n, small))

    def footer(canvas, doc):
        canvas.saveState()
        canvas.setFont("Helvetica", 7)
        canvas.setFillColor(ink2)
        canvas.drawString(15 * mm, 10 * mm, f"{report['report_id']} · BAS Activity Intelligence (SIH26174)")
        canvas.drawRightString(A4[0] - 15 * mm, 10 * mm, f"Page {doc.page}")
        canvas.restoreState()

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=15 * mm, rightMargin=15 * mm, topMargin=15 * mm,
                            bottomMargin=18 * mm, title=f"Experiment report {report['report_id']}",
                            author="BAS Activity Intelligence")
    doc.build(story, onFirstPage=footer, onLaterPages=footer)
    return buf.getvalue()
