"""Extract per-person pose feature sequences from every video named in a labels file.

    python -m training.extract --labels data/labels.csv --cache data/features

Runs the same detector / tracker / feature code as the app, so training and inference see identical
inputs. Results are cached per video (keyed by path, size and modification time).
"""
import argparse
import json
import logging
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config  # noqa: E402

from training.dataset import feature_cache_path  # noqa: E402
from training.labels import read_labels  # noqa: E402

log = logging.getLogger("bas.training")


def extract(labels_path: str, cache_dir: str, force: bool = False, pipeline=None) -> dict:
    """Returns {video path: feature cache path}. `pipeline` can be injected (tests)."""
    labels = read_labels(labels_path)
    videos = sorted({lb.video for lb in labels})
    os.makedirs(cache_dir, exist_ok=True)
    if pipeline is None:
        from pipeline import AIVideoPipeline
        pipeline = AIVideoPipeline()
    if not pipeline.model_ready:
        raise RuntimeError(pipeline.load_error or "pose model not ready")

    out = {}
    for n, video in enumerate(videos, start=1):
        if not os.path.exists(video):
            log.error("[%d/%d] missing video %s - skipped", n, len(videos), video)
            continue
        path = feature_cache_path(cache_dir, video)
        if os.path.exists(path) and not force:
            log.info("[%d/%d] cached %s", n, len(videos), os.path.basename(video))
            out[video] = path
            continue
        t0 = time.monotonic()
        result = pipeline.process_video(video, collect_features=True)
        if result.get("failed") or not result.get("model_ready"):
            log.error("[%d/%d] failed %s: %s", n, len(videos), video, result.get("message"))
            continue
        with open(path, "w", encoding="utf-8") as fh:
            json.dump({"video": video, "sample_interval": result["sample_interval"],
                       "tracks": result["feature_tracks"]}, fh)
        log.info("[%d/%d] %s: %d people, %.0fs", n, len(videos), os.path.basename(video),
                 len(result["feature_tracks"]), time.monotonic() - t0)
        out[video] = path
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--labels", required=True)
    ap.add_argument("--cache", default=os.path.join(config.BASE_DIR, "data", "features"))
    ap.add_argument("--force", action="store_true", help="re-extract even if cached")
    args = ap.parse_args(argv)
    config.setup_logging()
    done = extract(args.labels, args.cache, args.force)
    print(f"Features ready for {len(done)} video(s) in {args.cache}")


if __name__ == "__main__":
    main()
