from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, declarative_base
import logging
import sqlite3
import os

from config import DB_PATH

log = logging.getLogger("bas.database")

SQLALCHEMY_DATABASE_URL = f"sqlite:///{DB_PATH}"

engine = create_engine(
    SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False}
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

def migrate_db():
    if not os.path.exists(DB_PATH):
        return

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # Check tables
    tables = [t[0] for t in cursor.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]

    if "experiments" in tables:
        cursor.execute("PRAGMA table_info(experiments)")
        exp_cols = [col[1] for col in cursor.fetchall()]
        if "video_filename" not in exp_cols:
            cursor.execute("ALTER TABLE experiments ADD COLUMN video_filename VARCHAR")
        if "video_path" not in exp_cols:
            cursor.execute("ALTER TABLE experiments ADD COLUMN video_path VARCHAR")
        for col, sql_type in [
            ("source", "VARCHAR DEFAULT 'upload'"),
            ("file_size", "INTEGER"),
            ("duration_seconds", "FLOAT"),
            ("fps", "FLOAT"),
            ("frame_count", "INTEGER"),
            ("progress", "FLOAT DEFAULT 0"),
            ("message", "TEXT"),
            ("engine", "VARCHAR"),
            ("processed_at", "DATETIME"),
            ("processing_seconds", "FLOAT"),
        ]:
            if col not in exp_cols:
                cursor.execute(f"ALTER TABLE experiments ADD COLUMN {col} {sql_type}")
        # Old status names -> current lifecycle names
        cursor.execute("UPDATE experiments SET status = 'completed' WHERE status = 'processed'")
        cursor.execute("UPDATE experiments SET status = 'uploaded' WHERE status = 'active'")

    if "activity_events" in tables:
        cursor.execute("PRAGMA table_info(activity_events)")
        evt_cols = [col[1] for col in cursor.fetchall()]
        if "video_id" not in evt_cols:
            cursor.execute("ALTER TABLE activity_events ADD COLUMN video_id VARCHAR")
        if "start_seconds" not in evt_cols:
            cursor.execute("ALTER TABLE activity_events ADD COLUMN start_seconds FLOAT")
        if "end_seconds" not in evt_cols:
            cursor.execute("ALTER TABLE activity_events ADD COLUMN end_seconds FLOAT")
        if "frame_number" not in evt_cols:
            cursor.execute("ALTER TABLE activity_events ADD COLUMN frame_number INTEGER")

        cursor.execute("UPDATE activity_events SET video_id = experiment_id WHERE video_id IS NULL")

        rows = cursor.execute("SELECT id, start_time, end_time FROM activity_events WHERE start_seconds IS NULL OR end_seconds IS NULL").fetchall()
        for row_id, start_t, end_t in rows:
            def hms_to_sec(hms):
                try:
                    parts = str(hms).strip().split(":")
                    if len(parts) == 3:
                        return int(parts[0]) * 3600 + int(parts[1]) * 60 + float(parts[2])
                    if len(parts) == 2:
                        return int(parts[0]) * 60 + float(parts[1])
                    return float(parts[0])
                except Exception:
                    return 0.0
            s_sec = hms_to_sec(start_t) if start_t else 0.0
            e_sec = hms_to_sec(end_t) if end_t else 0.0
            cursor.execute("UPDATE activity_events SET start_seconds = ?, end_seconds = ? WHERE id = ?", (s_sec, e_sec, row_id))

    conn.commit()
    conn.close()

# Run migration on import
migrate_db()


def check_db() -> bool:
    """Return True if the database answers a trivial query."""
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except Exception as e:
        log.error("Database check failed: %s", e)
        return False

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

