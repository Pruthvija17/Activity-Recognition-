"""Request/response models for the settings and hardware endpoints (other routers return plain dicts)."""
import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict


class SystemSettingsBase(BaseModel):
    confidence_threshold: int = 60      # 0-100; events below it go to the Review Queue
    unknown_sensitivity: str = "Medium"  # Low | Medium | High (entropy threshold for Unknown)
    camera_source: str = ""


class SystemSettingsUpdate(SystemSettingsBase):
    pass


class SystemSettingsResponse(SystemSettingsBase):
    model_config = ConfigDict(from_attributes=True)

    updated_at: Optional[datetime.datetime] = None


class HardwareStatusResponse(BaseModel):
    cuda_available: bool
    cuda_device_name: Optional[str] = None
    cuda_device_count: int = 0
    backend: str           # "cuda" | "cpu"
    opencv_available: bool
    torch_available: bool
