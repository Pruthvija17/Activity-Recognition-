"""Evaluation metrics for the temporal activity model, and a markdown report.

    python -m training.evaluate --model weights/activity_gru.pt --labels data/labels.csv

By default only the model's held-out test videos (recorded in its spec) are evaluated.
"""
import argparse
import datetime
import os
import sys
from typing import List, Optional

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.activity.rules import UNKNOWN  # noqa: E402
from services.activity.unknown import OpenSetClassifier  # noqa: E402

from training.dataset import CLASSES, UNKNOWN_INDEX, Windows  # noqa: E402


def classification_metrics(y_true: List[int], y_pred: List[int], classes: List[str]) -> dict:
    k = len(classes)
    cm = [[0] * k for _ in range(k)]
    for t, p in zip(y_true, y_pred):
        cm[t][p] += 1
    per_class, f1s = {}, []
    for i, name in enumerate(classes):
        tp = cm[i][i]
        fp = sum(cm[r][i] for r in range(k)) - tp
        fn = sum(cm[i]) - tp
        support = sum(cm[i])
        prec = tp / (tp + fp) if tp + fp else 0.0
        rec = tp / (tp + fn) if tp + fn else 0.0
        f1 = 2 * prec * rec / (prec + rec) if prec + rec else 0.0
        per_class[name] = {"precision": round(prec, 4), "recall": round(rec, 4), "f1": round(f1, 4), "support": support}
        if support:
            f1s.append(f1)
    n = len(y_true)
    return {
        "windows": n,
        "accuracy": round(sum(cm[i][i] for i in range(k)) / n, 4) if n else None,
        "macro_f1": round(sum(f1s) / len(f1s), 4) if f1s else None,
        "per_class": per_class,
        "confusion_matrix": cm,  # rows = true class, columns = predicted class (classes order)
    }


def open_set_metrics(known_flagged: List[bool], unknown_flagged: List[bool]) -> dict:
    """known_flagged: known windows the open-set step called Unknown; unknown_flagged: Unknown windows caught."""
    tp = sum(unknown_flagged)
    fp = sum(known_flagged)
    fn = len(unknown_flagged) - tp
    return {
        "unknown_windows": len(unknown_flagged),
        "unknown_precision": round(tp / (tp + fp), 4) if tp + fp else None,
        "unknown_recall": round(tp / len(unknown_flagged), 4) if unknown_flagged else None,
        "false_unknown_rate": round(fp / len(known_flagged), 4) if known_flagged else None,
        "false_known_rate": round(fn / len(unknown_flagged), 4) if unknown_flagged else None,
    }


def evaluate_windows(analyze, windows: Windows, sensitivity: str = "Medium") -> dict:
    """analyze(seq) -> ({class: prob}, novelty ratio). Closed-set metrics on known windows; open-set
    metrics (entropy / probability / prototype distance, as in the live engine) on Unknown ones."""
    clf = OpenSetClassifier(sensitivity=sensitivity)
    y_true, y_pred, known_flagged, unknown_flagged = [], [], [], []
    for seq, label in zip(windows.X, windows.y):
        probs, novelty = analyze(seq)
        flagged = clf.decide(probs).label == UNKNOWN or novelty > 1.0
        if label == UNKNOWN_INDEX:
            unknown_flagged.append(flagged)
        else:
            y_true.append(label)
            y_pred.append(CLASSES.index(max(probs, key=probs.get)))
            known_flagged.append(flagged)
    result = classification_metrics(y_true, y_pred, CLASSES)
    result["open_set"] = {"sensitivity": sensitivity, **open_set_metrics(known_flagged, unknown_flagged)}
    return result


def _pct(v: Optional[float]) -> str:
    return "-" if v is None else f"{v * 100:.1f}%"


def markdown_report(spec: dict, test: dict, title: str = "Activity model evaluation") -> str:
    data = spec.get("data", {})
    lines = [
        f"# {title}",
        "",
        f"Generated {datetime.datetime.utcnow().isoformat(timespec='seconds')}Z · model trained {spec.get('trained_at', '?')}",
        "",
        f"- Split: **{data.get('split', '?')}** - train {len(data.get('train_videos', []))}, "
        f"validation {len(data.get('val_videos', []))}, test {len(data.get('test_videos', []))} video(s)",
        f"- Window: {spec.get('window')} samples at {spec.get('sample_fps')} fps "
        f"({spec.get('window', 0) / max(spec.get('sample_fps', 1), 1e-6):.1f} s)",
        f"- Test windows: {test['windows']} · **accuracy {_pct(test['accuracy'])}** · **macro F1 {_pct(test['macro_f1'])}**",
        "",
    ]
    for w in spec.get("warnings", []):
        lines.append(f"> ⚠ {w}")
    if spec.get("warnings"):
        lines.append("")
    lines += ["| Activity | Precision | Recall | F1 | Test windows |", "|---|---|---|---|---|"]
    for name, m in test["per_class"].items():
        lines.append(f"| {name} | {_pct(m['precision'])} | {_pct(m['recall'])} | {_pct(m['f1'])} | {m['support']} |")
    lines += ["", "Confusion matrix (rows = true, columns = predicted):", "",
              "| | " + " | ".join(c[:10] for c in CLASSES) + " |",
              "|---" * (len(CLASSES) + 1) + "|"]
    for name, row in zip(CLASSES, test["confusion_matrix"]):
        lines.append(f"| **{name[:18]}** | " + " | ".join(str(v) for v in row) + " |")
    o = test["open_set"]
    lines += ["", f"Unknown detection (sensitivity {o['sensitivity']}):", ""]
    if o["unknown_windows"]:
        lines += [f"- Unknown precision {_pct(o['unknown_precision'])}, recall {_pct(o['unknown_recall'])}",
                  f"- False unknown rate {_pct(o['false_unknown_rate'])}, false known rate {_pct(o['false_known_rate'])}"]
    else:
        lines += [f"- No Unknown-labelled test segments; false unknown rate on known windows: "
                  f"{_pct(o['false_unknown_rate'])}. Label some unexpected movements as `Unknown` to measure recall."]
    return "\n".join(lines) + "\n"


def main(argv=None):
    import config
    from services.activity.temporal import TemporalModel, spec_path_for
    from training.dataset import feature_cache_path, load_features, windows_for_video
    from training.labels import read_labels

    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--model", default=config.ACTIVITY_MODEL_PATH)
    ap.add_argument("--labels", required=True)
    ap.add_argument("--cache", default=os.path.join(config.BASE_DIR, "data", "features"))
    ap.add_argument("--all-videos", action="store_true", help="evaluate every labelled video, not just the test split")
    ap.add_argument("--sensitivity", default="Medium", choices=["Low", "Medium", "High"])
    ap.add_argument("--report", default=os.path.join(os.path.dirname(config.BASE_DIR), "docs", "MODEL_EVALUATION.md"))
    args = ap.parse_args(argv)

    model, err = TemporalModel.load(args.model)
    if model is None:
        sys.exit(err or f"No trained model at {args.model} ({spec_path_for(args.model)})")
    labels = read_labels(args.labels)
    wanted = None if args.all_videos else set(model.spec.get("data", {}).get("test_videos", []))
    windows = Windows()
    for video in sorted({lb.video for lb in labels}):
        if wanted is not None and video not in wanted:
            continue
        cache = feature_cache_path(args.cache, video)
        if not os.path.exists(cache):
            print(f"no extracted features for {video}; run training.extract first")
            continue
        windows.extend(windows_for_video([lb for lb in labels if lb.video == video], load_features(cache),
                                         model.window, int(model.spec.get("stride", 4))))
    if not windows.y:
        sys.exit("No evaluation windows found.")
    result = evaluate_windows(model.analyze, windows, args.sensitivity)
    with open(args.report, "w", encoding="utf-8") as fh:
        fh.write(markdown_report(model.spec, result))
    print(f"Accuracy {_pct(result['accuracy'])}, macro F1 {_pct(result['macro_f1'])} on {result['windows']} windows. "
          f"Report: {args.report}")


if __name__ == "__main__":
    main()
