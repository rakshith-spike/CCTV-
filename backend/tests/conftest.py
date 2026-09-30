import os
import tempfile
from pathlib import Path

# Never open the application's live Qdrant directory from test processes.
os.environ["CCTV_DATA_DIR"] = tempfile.mkdtemp(prefix="cctv-test-")
os.environ.setdefault(
    "CCTV_MODEL_DIR", str(Path(__file__).resolve().parents[2] / "data" / "models")
)
import pytest
from backend.storage import db


@pytest.fixture(autouse=True)
def database():
    db.init_db()
    from backend.forensics.service import init
    init()
    with db.connection() as c:
        for table in (
            "forensic_searches", "forensic_reports", "forensic_events", "forensic_recovery", "forensic_custody", "forensic_evidence", "forensic_cases",
            "search_history",
            "clips",
            "alerts",
            "video_segments",
            "processing_jobs",
            "videos",
            "cameras",
        ):
            c.execute(f"DELETE FROM {table}")
    yield


@pytest.fixture
def client():
    from fastapi.testclient import TestClient
    from backend.main import app

    with TestClient(app) as client:
        yield client


@pytest.fixture
def sample_video(tmp_path):
    from demo.generate_sample_video import generate

    path = tmp_path / "real-photograph.mp4"
    generate(path, seconds=3)
    return path
