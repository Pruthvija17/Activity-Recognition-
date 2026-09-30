from sqlalchemy import Column, Integer, String, Float, ForeignKey, DateTime, Text
from sqlalchemy.orm import relationship
from database import Base
from config import utcnow


class Experiment(Base):
    __tablename__ = "experiments"

    id = Column(String, primary_key=True, index=True)
    name = Column(String)
    # Lifecycle: uploaded -> queued -> processing -> completed | failed
    status = Column(String, default="uploaded")
    start_time = Column(DateTime, default=utcnow)  # created / uploaded at
    video_filename = Column(String, nullable=True)  # Original filename of the uploaded video
    video_path = Column(String, nullable=True)       # Absolute path to the uploaded file
    source = Column(String, default="upload")        # upload | camera
    file_size = Column(Integer, nullable=True)       # bytes
    duration_seconds = Column(Float, nullable=True)
    fps = Column(Float, nullable=True)
    frame_count = Column(Integer, nullable=True)
    progress = Column(Float, default=0.0)            # 0-100 while processing
    message = Column(Text, nullable=True)            # result summary or failure reason
    engine = Column(String, nullable=True)           # activity engine that produced the events
    processed_at = Column(DateTime, nullable=True)
    processing_seconds = Column(Float, nullable=True)
    codec = Column(String, nullable=True)            # e.g. h264, hevc, mpeg4
    # Browser playback: not_needed | pending | ready | failed | unavailable (no ffmpeg)
    preview_status = Column(String, nullable=True)
    preview_path = Column(String, nullable=True)

    events = relationship("ActivityEvent", back_populates="experiment")
    participants = relationship("Participant", back_populates="experiment")
    config = relationship("ExperimentConfig", back_populates="experiment", uselist=False)


class Participant(Base):
    __tablename__ = "participants"

    id = Column(String, primary_key=True, index=True)
    experiment_id = Column(String, ForeignKey("experiments.id"))
    tracked_id = Column(String)

    experiment = relationship("Experiment", back_populates="participants")
    events = relationship("ActivityEvent", back_populates="participant")


class ActivityEvent(Base):
    __tablename__ = "activity_events"

    id = Column(String, primary_key=True, index=True)
    experiment_id = Column(String, ForeignKey("experiments.id"))
    person_id = Column(String, ForeignKey("participants.id"))
    # video_id: references the experiment id (same as experiment_id) for URL construction
    video_id = Column(String, nullable=True, index=True)

    activity_type = Column(String)
    start_time = Column(String)      # HH:MM:SS string
    end_time = Column(String)        # HH:MM:SS string
    start_seconds = Column(Float, nullable=True)  # Numeric seconds for seeking
    end_seconds = Column(Float, nullable=True)
    duration = Column(Float)
    confidence = Column(Float)
    status = Column(String)          # display status: "Confirmed" | "Review" | "Rejected"
    zone = Column(String, nullable=True)
    frame_number = Column(Integer, nullable=True)  # Start frame for precise seeking
    # Review workflow: auto (accepted by the engine) | pending | confirmed | rejected | reclassified
    review_status = Column(String, default="auto", index=True)
    original_activity = Column(String, nullable=True)  # model prediction before an operator reclassified it
    reviewed_at = Column(DateTime, nullable=True)
    note = Column(String, nullable=True)  # why an event is Unknown, e.g. "only upper body visible"

    experiment = relationship("Experiment", back_populates="events")
    participant = relationship("Participant", back_populates="events")


class ExperimentConfig(Base):
    """Stores the expected activity sequence for an experiment."""
    __tablename__ = "experiment_configs"

    id = Column(String, primary_key=True, index=True)
    experiment_id = Column(String, ForeignKey("experiments.id"), unique=True)
    # JSON-encoded list of activity names in expected order
    expected_sequence = Column(Text, nullable=True)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)

    experiment = relationship("Experiment", back_populates="config")


class SystemSettings(Base):
    """Singleton row (id=1) storing pipeline calibration settings."""
    __tablename__ = "system_settings"

    id = Column(Integer, primary_key=True, default=1)  # Always row 1
    # Confidence threshold (0-100 integer, stored as int for human readability)
    confidence_threshold = Column(Integer, default=60)  # Maps to 0.60 float
    # Unknown sensitivity: 'Low' | 'Medium' | 'High'
    unknown_sensitivity = Column(String, default="Medium")
    # Active camera / source label
    camera_source = Column(String, default="")
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)
