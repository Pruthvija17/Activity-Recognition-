"""Train the temporal activity model (GRU over pose feature windows).

    python -m training.train --labels data/labels.csv

Steps: extract pose features for every labelled video (cached), cut labelled segments into windows,
split train / validation / test BY VIDEO (windows from one video never appear in two splits),
train with class weighting and early stopping on validation macro-F1, evaluate on the test videos,
then write weights/activity_gru.pt + activity_gru.json and docs/MODEL_EVALUATION.md.
The backend uses the model automatically after a restart.
"""
import argparse
import datetime
import json
import logging
import os
import random
import sys
from typing import List, Optional, Tuple

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import torch  # noqa: E402
from torch import nn  # noqa: E402

import config  # noqa: E402
from services.activity.sequence import FEATURE_DIM, FEATURE_VERSION  # noqa: E402
from services.activity.temporal import ActivityGRU, novelty_ratios, spec_path_for  # noqa: E402

from training.dataset import CLASSES, UNKNOWN_INDEX, Windows  # noqa: E402
from training.evaluate import classification_metrics, evaluate_windows, markdown_report  # noqa: E402

log = logging.getLogger("bas.training")

MIN_VIDEOS_FOR_VIDEO_SPLIT = 3
RECOMMENDED_WINDOWS_PER_CLASS = 20
OPEN_SET_MARGIN = 1.25


class InsufficientData(RuntimeError):
    pass


def split_by_group(groups: List[str], seed: int, val_frac: float = 0.2, test_frac: float = 0.2,
                   allow_segment_split: bool = False, segments: Optional[List[str]] = None) -> Tuple[set, set, set, str]:
    units = sorted(set(groups))
    how = "by video"
    if len(units) < MIN_VIDEOS_FOR_VIDEO_SPLIT:
        if not allow_segment_split or not segments:
            raise InsufficientData(
                f"Only {len(units)} labelled video(s); at least {MIN_VIDEOS_FOR_VIDEO_SPLIT} are needed for an honest "
                "train/validation/test split by video. Label more footage, or pass --allow-segment-split "
                "(weaker: test windows then come from the same videos as training windows).")
        units = sorted(set(segments))
        how = "by labelled segment (WARNING: same videos in train and test - optimistic metrics)"
    rng = random.Random(seed)
    rng.shuffle(units)
    n = len(units)
    n_test = max(1, round(n * test_frac))
    n_val = max(1, round(n * val_frac))
    if n - n_test - n_val < 1:
        raise InsufficientData(f"Not enough labelled units ({n}) to form train, validation and test sets.")
    return set(units[n_test + n_val:]), set(units[n_test:n_test + n_val]), set(units[:n_test]), how


def _subset(w: Windows, keys: List[str], chosen: set) -> Windows:
    out = Windows()
    for x, y, g, k in zip(w.X, w.y, w.groups, keys):
        if k in chosen:
            out.X.append(x)
            out.y.append(y)
            out.groups.append(g)
    return out


def _known(w: Windows) -> Tuple[torch.Tensor, torch.Tensor]:
    idx = [i for i, y in enumerate(w.y) if y != UNKNOWN_INDEX]
    if not idx:
        return torch.zeros((0, 1, FEATURE_DIM)), torch.zeros((0,), dtype=torch.long)
    return torch.tensor([w.X[i] for i in idx], dtype=torch.float32), torch.tensor([w.y[i] for i in idx])


def train_model(windows: Windows, segments: List[str], *, window: int, stride: int, sample_fps: float,
                hidden: int = 64, layers: int = 1, epochs: int = 80, lr: float = 2e-3, batch_size: int = 64,
                patience: int = 12, seed: int = 0, allow_segment_split: bool = False) -> Tuple[dict, dict, dict]:
    """Returns (state_dict, spec, test_metrics)."""
    torch.manual_seed(seed)
    random.seed(seed)
    train_u, val_u, test_u, how = split_by_group(windows.groups, seed, allow_segment_split=allow_segment_split,
                                                 segments=segments)
    keys = windows.groups if how == "by video" else segments
    tr, va, te = (_subset(windows, keys, s) for s in (train_u, val_u, test_u))
    Xtr, ytr = _known(tr)
    Xva, yva = _known(va)
    if len(ytr) == 0 or len(yva) == 0:
        raise InsufficientData("Training or validation split has no labelled (non-Unknown) windows.")

    mean = Xtr.reshape(-1, FEATURE_DIM).mean(0)
    std = Xtr.reshape(-1, FEATURE_DIM).std(0).clamp_min(1e-6)
    norm = lambda x: (x - mean) / std  # noqa: E731

    counts = torch.bincount(ytr, minlength=len(CLASSES)).float()
    weights = torch.where(counts > 0, counts.sum() / (len(CLASSES) * counts.clamp_min(1)), torch.zeros_like(counts))
    net = ActivityGRU(FEATURE_DIM, len(CLASSES), hidden=hidden, layers=layers)
    opt = torch.optim.AdamW(net.parameters(), lr=lr, weight_decay=1e-4)
    loss_fn = nn.CrossEntropyLoss(weight=weights)

    best_f1, best_state, bad = -1.0, None, 0
    Xtr_n, Xva_n = norm(Xtr), norm(Xva)
    for epoch in range(epochs):
        net.train()
        perm = torch.randperm(len(ytr))
        for i in range(0, len(perm), batch_size):
            b = perm[i:i + batch_size]
            opt.zero_grad()
            loss = loss_fn(net(Xtr_n[b]), ytr[b])
            loss.backward()
            opt.step()
        net.eval()
        with torch.no_grad():
            pred = net(Xva_n).argmax(1).tolist()
        f1 = classification_metrics(yva.tolist(), pred, CLASSES)["macro_f1"] or 0.0
        if f1 > best_f1:
            best_f1, best_state, bad = f1, {k: v.clone() for k, v in net.state_dict().items()}, 0
        else:
            bad += 1
            if bad >= patience:
                log.info("Early stop at epoch %d", epoch + 1)
                break
    net.load_state_dict(best_state)
    net.eval()

    # Open-set calibration: per-class prototype (mean embedding) and a distance threshold that
    # covers ~99 % of that class's training windows, plus a safety margin.
    with torch.no_grad():
        emb = net.embed(Xtr_n)
    prototypes, thresholds = [], []
    for c in range(len(CLASSES)):
        e = emb[ytr == c]
        if len(e) == 0:
            prototypes.append(None)
            thresholds.append(None)
            continue
        proto = e.mean(0)
        d = torch.linalg.norm(e - proto, dim=1)
        prototypes.append(proto.tolist())
        thresholds.append(float(torch.quantile(d, 0.99)) * OPEN_SET_MARGIN + 1e-6)
    open_set = {"method": "distance to class prototype in GRU embedding space",
                "margin": OPEN_SET_MARGIN, "prototypes": prototypes, "thresholds": thresholds}

    def analyze(seq):
        with torch.no_grad():
            e = net.embed(norm(torch.tensor([seq], dtype=torch.float32)))
            p = torch.softmax(net.head(e), -1)
            ratio = novelty_ratios(e, p.argmax(-1), open_set)[0].item()
        return dict(zip(CLASSES, p[0].tolist())), ratio

    test_metrics = evaluate_windows(analyze, te)
    count = lambda w: w.counts()  # noqa: E731
    warnings = [f"'{c}' has only {n} training windows (recommend >= {RECOMMENDED_WINDOWS_PER_CLASS})."
                for c, n in count(tr).items() if c in CLASSES and n < RECOMMENDED_WINDOWS_PER_CLASS]
    if how != "by video":
        warnings.insert(0, "Split by labelled segment, not by video: test metrics are optimistic.")
    groups_of = lambda w: sorted(set(w.groups))  # noqa: E731
    spec = {
        "model": "ActivityGRU",
        "feature_version": FEATURE_VERSION,
        "feature_dim": FEATURE_DIM,
        "classes": CLASSES,
        "window": window,
        "stride": stride,
        "sample_fps": sample_fps,
        "hidden": hidden,
        "layers": layers,
        "mean": mean.tolist(),
        "open_set": open_set,
        "std": std.tolist(),
        "trained_at": datetime.datetime.utcnow().isoformat(timespec="seconds") + "Z",
        "metrics": {
            "val_macro_f1": round(best_f1, 4),
            "test_accuracy": test_metrics["accuracy"],
            "test_macro_f1": test_metrics["macro_f1"],
            "test_windows": test_metrics["windows"],
            "open_set": test_metrics["open_set"],
        },
        "data": {
            "split": how,
            "train_videos": groups_of(tr),
            "val_videos": groups_of(va),
            "test_videos": groups_of(te),
            "windows": {"train": count(tr), "val": count(va), "test": count(te)},
            "skipped_segments": len(windows.skipped),
        },
        "warnings": warnings,
    }
    return best_state, spec, test_metrics


def save_model(state: dict, spec: dict, out: str, force: bool = False) -> None:
    if os.path.exists(out) and not force:
        raise FileExistsError(f"{out} exists; pass --force to replace the current model.")
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    torch.save(state, out)
    with open(spec_path_for(out), "w", encoding="utf-8") as fh:
        json.dump(spec, fh, indent=2)


def build_windows(labels_path: str, cache_dir: str, window: int, stride: int) -> Tuple[Windows, List[str], float]:
    from training.dataset import feature_cache_path, load_features, windows_for_video
    from training.labels import read_labels

    labels = read_labels(labels_path)
    all_w, segments, fps = Windows(), [], None
    for video in sorted({lb.video for lb in labels}):
        cache = feature_cache_path(cache_dir, video)
        if not os.path.exists(cache):
            log.warning("No features for %s (run training.extract); skipped", video)
            continue
        feats = load_features(cache)
        fps = fps or round(1.0 / float(feats["sample_interval"]), 3)
        for n, lb in enumerate([lb for lb in labels if lb.video == video]):
            w = windows_for_video([lb], feats, window, stride)
            segments += [f"{video}#{n}"] * len(w.y)
            all_w.extend(w)
    return all_w, segments, fps or 8.0


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--labels", required=True, help="labels CSV (see training/labels.py)")
    ap.add_argument("--cache", default=os.path.join(config.BASE_DIR, "data", "features"))
    ap.add_argument("--out", default=config.ACTIVITY_MODEL_PATH)
    ap.add_argument("--report", default=os.path.join(os.path.dirname(config.BASE_DIR), "docs", "MODEL_EVALUATION.md"))
    ap.add_argument("--window", type=int, default=16, help="samples per window (16 at 8 fps = 2 s)")
    ap.add_argument("--stride", type=int, default=4)
    ap.add_argument("--epochs", type=int, default=80)
    ap.add_argument("--hidden", type=int, default=64)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--no-extract", action="store_true", help="use cached features only")
    ap.add_argument("--allow-segment-split", action="store_true")
    ap.add_argument("--force", action="store_true", help="replace an existing model")
    args = ap.parse_args(argv)
    config.setup_logging()

    if not args.no_extract:
        from training.extract import extract
        extract(args.labels, args.cache)
    windows, segments, fps = build_windows(args.labels, args.cache, args.window, args.stride)
    for s in windows.skipped:
        log.warning("Skipped segment: %s", s)
    log.info("Windows per class: %s", windows.counts())
    try:
        state, spec, test = train_model(windows, segments, window=args.window, stride=args.stride, sample_fps=fps,
                                        hidden=args.hidden, epochs=args.epochs, seed=args.seed,
                                        allow_segment_split=args.allow_segment_split)
    except InsufficientData as e:
        sys.exit(f"Not enough data: {e}")
    save_model(state, spec, args.out, force=args.force)
    os.makedirs(os.path.dirname(args.report), exist_ok=True)
    with open(args.report, "w", encoding="utf-8") as fh:
        fh.write(markdown_report(spec, test))
    print(f"Saved {args.out} (test accuracy {test['accuracy']}, macro F1 {test['macro_f1']}). "
          f"Report: {args.report}. Restart the backend to use it.")
    for w in spec["warnings"]:
        print("WARNING:", w)


if __name__ == "__main__":
    main()
