from pydantic import BaseModel
from typing import List, Optional
import datetime


# ── Activity Event ────────────────────────────────────────────────────────────

class ActivityEventBase(BaseModel):
    activity_type: str
    start_time: str
    end_time: str
    duration: float
    confidence: float
    status: str
    zone: Optional[str] = None
    start_seconds: Optional[float] = None
    end_seconds: Optional[float] = None
    frame_number: Optional[int] = None
    review_status: Optional[str] = None
    original_activity: Optional[str] = None
    reviewed_at: Optional[datetime.datetime] = None


class ActivityEventCreate(ActivityEventBase):
    id: str
    experiment_id: str
    person_id: str
    video_id: Optional[str] = None


class ActivityEvent(ActivityEventBase):
    id: str
    experiment_id: str
    person_id: str
    video_id: Optional[str] = None

    class Config:
        from_attributes = True


# ── Participant ───────────────────────────────────────────────────────────────

class ParticipantBase(BaseModel):
    tracked_id: str


class ParticipantCreate(ParticipantBase):
    id: str
    experiment_id: str


class Participant(ParticipantBase):
    id: str
    experiment_id: str
    events: List[ActivityEvent] = []

    class Config:
        from_attributes = True


# ── Experiment ────────────────────────────────────────────────────────────────

class ExperimentBase(BaseModel):
    name: str


class ExperimentCreate(ExperimentBase):
    id: str


class Experiment(ExperimentBase):
    id: str
    status: str
    start_time: datetime.datetime
    video_filename: Optional[str] = None
    video_path: Optional[str] = None
    source: Optional[str] = None
    file_size: Optional[int] = None
    duration_seconds: Optional[float] = None
    fps: Optional[float] = None
    frame_count: Optional[int] = None
    progress: Optional[float] = None
    message: Optional[str] = None
    engine: Optional[str] = None
    processed_at: Optional[datetime.datetime] = None
    processing_seconds: Optional[float] = None
    participants: List[Participant] = []
    events: List[ActivityEvent] = []

    class Config:
        from_attributes = True


# ── Sequence / Config ─────────────────────────────────────────────────────────

class SequenceConfigRequest(BaseModel):
    expected_sequence: List[str]


class SequenceDeviationDetail(BaseModel):
    step_index: int
    expected: str
    observed: Optional[str]
    deviation_type: str   # "skipped" | "out_of_order" | "unexpected"


class SequenceValidationResult(BaseModel):
    experiment_id: str
    is_compliant: bool
    deviation_count: int
    deviations: List[SequenceDeviationDetail]
    observed_sequence: List[str]
    expected_sequence: List[str]
    next_expected_step: Optional[str]
    message: str


# ── Analytics ─────────────────────────────────────────────────────────────────

class ActivityCount(BaseModel):
    name: str
    value: int
    color: str


class PersonStat(BaseModel):
    name: str
    activities: int
    unknowns: int
    avg_confidence: float


class AnalyticsResponse(BaseModel):
    experiment_id: Optional[str] = None
    total_events: int
    confirmed_events: int
    unknown_events: int
    sequence_deviations: int
    avg_confidence: float
    experiment_duration_seconds: float
    activity_distribution: List[ActivityCount]
    person_stats: List[PersonStat]
    model_ready: bool


# ── Event Update ──────────────────────────────────────────────────────────────

class EventUpdateRequest(BaseModel):
    activity_type: str


# ── System Settings ───────────────────────────────────────────────────────────

class SystemSettingsBase(BaseModel):
    confidence_threshold: int = 60      # 0-100 integer
    unknown_sensitivity: str = "Medium"  # Low | Medium | High
    camera_source: str = "Camera 01 (Overhead Station)"


class SystemSettingsUpdate(SystemSettingsBase):
    pass


class SystemSettingsResponse(SystemSettingsBase):
    updated_at: Optional[datetime.datetime] = None

    class Config:
        from_attributes = True


class HardwareStatusResponse(BaseModel):
    cuda_available: bool
    cuda_device_name: Optional[str] = None
    cuda_device_count: int = 0
    backend: str           # "cuda" | "cpu"
    opencv_available: bool
    torch_available: bool
