"""Trainable temporal activity model: a small GRU over a window of per-frame pose feature vectors.

Weights live next to a JSON spec (feature layout version, window length, normalisation, classes,
evaluation metrics). Loading refuses a spec that doesn't match the current feature layout.
"""
import json
import logging
import os
from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence, Tuple

import torch
from torch import nn

from .sequence import FEATURE_DIM, FEATURE_VERSION

log = logging.getLogger("bas.temporal")


class ActivityGRU(nn.Module):
    def __init__(self, input_dim: int, num_classes: int, hidden: int = 64, layers: int = 1, dropout: float = 0.2):
        super().__init__()
        self.gru = nn.GRU(input_dim, hidden, num_layers=layers, batch_first=True,
                          dropout=dropout if layers > 1 else 0.0)
        self.drop = nn.Dropout(dropout)
        self.head = nn.Linear(hidden, num_classes)

    def embed(self, x: torch.Tensor) -> torch.Tensor:  # x: (batch, time, features) -> (batch, hidden)
        _, h = self.gru(x)
        return h[-1]

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.head(self.drop(self.embed(x)))


def novelty_ratios(emb: torch.Tensor, pred: torch.Tensor, open_set: Optional[dict]) -> torch.Tensor:
    """Distance of each embedding to the predicted class prototype, relative to that class's threshold.

    > 1 means further from the class than (almost) every training example: an unfamiliar movement.
    """
    ratios = torch.zeros(len(pred))
    if not open_set:
        return ratios
    for i, c in enumerate(pred.tolist()):
        proto, thr = open_set["prototypes"][c], open_set["thresholds"][c]
        if proto is not None and thr:
            ratios[i] = torch.dist(emb[i], torch.tensor(proto)) / thr
    return ratios


def spec_path_for(weights_path: str) -> str:
    return os.path.splitext(weights_path)[0] + ".json"


@dataclass
class TemporalModel:
    net: ActivityGRU
    spec: dict
    mean: torch.Tensor
    std: torch.Tensor

    @property
    def classes(self) -> List[str]:
        return list(self.spec["classes"])

    @property
    def window(self) -> int:
        return int(self.spec["window"])

    @property
    def min_window(self) -> int:
        """Samples needed before the model is trusted (the rest is left-padded)."""
        return max(2, self.window // 2)

    @classmethod
    def load(cls, weights_path: str) -> Tuple[Optional["TemporalModel"], Optional[str]]:
        """(model, None) or (None, reason). A missing file is not an error: reason is None."""
        spec_path = spec_path_for(weights_path)
        if not os.path.exists(weights_path) or not os.path.exists(spec_path):
            return None, None
        try:
            with open(spec_path, encoding="utf-8") as fh:
                spec = json.load(fh)
            if spec.get("feature_version") != FEATURE_VERSION or spec.get("feature_dim") != FEATURE_DIM:
                return None, (f"Trained model uses feature layout v{spec.get('feature_version')} "
                              f"({spec.get('feature_dim')} values) but this code expects v{FEATURE_VERSION} "
                              f"({FEATURE_DIM}); retrain it.")
            net = ActivityGRU(FEATURE_DIM, len(spec["classes"]), hidden=int(spec["hidden"]), layers=int(spec["layers"]))
            net.load_state_dict(torch.load(weights_path, map_location="cpu", weights_only=True))
            net.eval()
            mean = torch.tensor(spec["mean"], dtype=torch.float32)
            std = torch.tensor(spec["std"], dtype=torch.float32).clamp_min(1e-6)
            return cls(net, spec, mean, std), None
        except Exception as e:
            log.exception("Could not load trained activity model %s", weights_path)
            return None, f"Trained activity model could not be loaded: {e}"

    @torch.no_grad()
    def analyze(self, vectors: Sequence[Sequence[float]]) -> Tuple[Dict[str, float], float]:
        """(class probabilities, novelty ratio) for the most recent window of feature vectors."""
        seq = list(vectors)[-self.window:]
        if len(seq) < self.window:
            seq = [seq[0]] * (self.window - len(seq)) + seq
        x = ((torch.tensor(seq, dtype=torch.float32) - self.mean) / self.std).unsqueeze(0)
        emb = self.net.embed(x)
        probs = torch.softmax(self.net.head(emb), dim=-1)
        ratio = novelty_ratios(emb, probs.argmax(-1), self.spec.get("open_set"))[0].item()
        return dict(zip(self.classes, probs[0].tolist())), ratio

    def predict(self, vectors: Sequence[Sequence[float]]) -> Dict[str, float]:
        return self.analyze(vectors)[0]
