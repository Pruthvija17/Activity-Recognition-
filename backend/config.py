"""Central backend configuration. Values can be overridden with environment variables."""
import logging
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
WEIGHTS_DIR = os.path.join(BASE_DIR, "weights")
UPLOADS_DIR = os.environ.get("BAS_UPLOADS_DIR", os.path.join(BASE_DIR, "uploads"))
OUTPUTS_DIR = os.path.join(BASE_DIR, "outputs")
DB_PATH = os.environ.get("BAS_DB_PATH", os.path.join(BASE_DIR, "bas_ai.db"))
MODEL_CONFIG_PATH = os.path.join(WEIGHTS_DIR, "model_config.json")

POSE_WEIGHTS_NAME = os.environ.get("BAS_POSE_WEIGHTS", "yolo11n-pose.pt")
POSE_WEIGHTS_PATH = os.path.join(WEIGHTS_DIR, POSE_WEIGHTS_NAME)

CORS_ORIGINS = [
    o.strip()
    for o in os.environ.get(
        "BAS_CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173"
    ).split(",")
    if o.strip()
]

LOG_LEVEL = os.environ.get("BAS_LOG_LEVEL", "INFO").upper()

for _d in (WEIGHTS_DIR, UPLOADS_DIR, OUTPUTS_DIR):
    os.makedirs(_d, exist_ok=True)


def setup_logging() -> None:
    logging.basicConfig(
        level=LOG_LEVEL,
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
