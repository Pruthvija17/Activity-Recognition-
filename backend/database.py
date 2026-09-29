from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(__file__), "bas_ai.db")
SQLALCHEMY_DATABASE_URL = f"sqlite:///{DB_PATH}"

engine = create_engine(
    SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False}
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

def migrate_db():
    db_path = os.path.join(os.path.dirname(__file__), "bas_ai.db")
    if not os.path.exists(db_path):
        return

    conn = sqlite3.connect(db_path)
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

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

