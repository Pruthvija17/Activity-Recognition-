"""Test setup: isolated database and uploads folder, one app instance per test session."""
import os
import sys
import tempfile

import pytest

_TMP = tempfile.mkdtemp(prefix="bas_test_")
os.environ["BAS_DB_PATH"] = os.path.join(_TMP, "test.db")
os.environ["BAS_UPLOADS_DIR"] = os.path.join(_TMP, "uploads")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import cv2  # noqa: E402
import numpy as np  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

import main  # noqa: E402


@pytest.fixture(scope="session")
def client():
    with TestClient(main.app) as c:
        yield c


@pytest.fixture(scope="session")
def uploads_dir():
    return os.environ["BAS_UPLOADS_DIR"]


@pytest.fixture(scope="session")
def sample_video() -> str:
    """A tiny, real, decodable 2-second MP4 (no people in it)."""
    path = os.path.join(_TMP, "sample.mp4")
    writer = cv2.VideoWriter(path, cv2.VideoWriter_fourcc(*"mp4v"), 10, (160, 120))
    for i in range(20):
        frame = np.full((120, 160, 3), 240, dtype=np.uint8)
        cv2.rectangle(frame, (10 + i * 5, 40), (40 + i * 5, 80), (80, 60, 40), -1)
        writer.write(frame)
    writer.release()
    return path
