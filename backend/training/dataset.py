"""Turn labelled segments + extracted feature sequences into fixed-length training windows."""
import hashlib
import json
import logging
import os
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from services.activity.rules import ACTIVITIES, UNKNOWN

from .labels import Label

log = logging.getLogger("bas.training")

CLASSES = list(ACTIVITIES)
UNKNOWN_INDEX = -1  # windows labelled Unknown: excluded from training, used for open-set evaluation


def feature_cache_path(cache_dir: str, video: str) -> str:
    stat = os.stat(video)
    key = hashlib.sha1(f"{os.path.abspath(video)}|{stat.st_size}|{int(stat.st_mtime)}".encode()).hexdigest()[:10]
    stem = os.path.splitext(os.path.basename(video))[0][:40]
    return os.path.join(cache_dir, f"{stem}_{key}.json")


def load_features(path: str) -> dict:
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


@dataclass
class Windows:
    X: List[List[List[float]]] = field(default_factory=list)  # (n, window, dim)
    y: List[int] = field(default_factory=list)                 # class index or UNKNOWN_INDEX
    groups: List[str] = field(default_factory=list)            # video: split unit (no leakage)
    skipped: List[str] = field(default_factory=list)

    def extend(self, other: "Windows") -> None:
        self.X += other.X
        self.y += other.y
        self.groups += other.groups
        self.skipped += other.skipped

    def counts(self) -> Dict[str, int]:
        c = {name: 0 for name in CLASSES + [UNKNOWN]}
        for label in self.y:
            c[UNKNOWN if label == UNKNOWN_INDEX else CLASSES[label]] += 1
        return c


def _runs(times: List[float], idx: List[int], interval: float) -> List[List[int]]:
    """Split sample indices into contiguous runs (a gap means the track was lost)."""
    runs: List[List[int]] = []
    for i in idx:
        if runs and times[i] - times[runs[-1][-1]] <= 2.5 * interval:
            runs[-1].append(i)
        else:
            runs.append([i])
    return runs


def _pick_track(label: Label, tracks: Dict[str, dict]) -> Tuple[Optional[str], str]:
    if label.person:
        return (label.person, "") if label.person in tracks else (None, f"no track named {label.person}")
    overlapping = [name for name, tr in tracks.items()
                   if tr["t"] and tr["t"][0] <= label.end and tr["t"][-1] >= label.start]
    if len(overlapping) == 1:
        return overlapping[0], ""
    if not overlapping:
        return None, "no person tracked during the segment"
    return None, f"{len(overlapping)} people visible; add a 'person' column to say which one"


def windows_for_video(labels: List[Label], feats: dict, window: int, stride: int) -> Windows:
    out = Windows()
    interval = float(feats["sample_interval"])
    tracks = feats["tracks"]
    for lb in labels:
        where = f"{os.path.basename(lb.video)} {lb.start:.1f}-{lb.end:.1f}s {lb.activity}"
        name, why = _pick_track(lb, tracks)
        if name is None:
            out.skipped.append(f"{where}: {why}")
            continue
        tr = tracks[name]
        times, vecs = tr["t"], tr["vectors"]
        idx = [i for i, t in enumerate(times) if lb.start <= t <= lb.end]
        made = 0
        for run in _runs(times, idx, interval):
            if len(run) >= window:
                starts = range(0, len(run) - window + 1, stride)
                seqs = [[vecs[i] for i in run[s:s + window]] for s in starts]
            elif len(run) >= max(2, window // 2):
                seq = [vecs[i] for i in run]
                seqs = [[seq[0]] * (window - len(seq)) + seq]  # short action: left-pad once
            else:
                seqs = []
            for seq in seqs:
                out.X.append(seq)
                out.y.append(UNKNOWN_INDEX if lb.activity == UNKNOWN else CLASSES.index(lb.activity))
                out.groups.append(lb.video)
                made += 1
        if not made:
            out.skipped.append(f"{where}: fewer than {max(2, window // 2)} pose samples of {name}")
    return out
