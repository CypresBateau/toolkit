
from __future__ import annotations

from typing import Dict, Optional

from pydantic import BaseModel, Field


class PredictResponse(BaseModel):
    request_id: str
    filename: str
    object: str
    inference_time_ms: float

    anomaly_score_raw: float
    anomaly_score: float = Field(
        ...,
        description="Single-image anomaly score. This is not benchmark-normalized.",
    )

    heatmap_png_base64: Optional[str]

    model_info: Dict[str, str]


class HealthResponse(BaseModel):
    status: str
    model_loaded: bool
    active_object: str
    checkpoint: str
    device: str
    gpu_memory_mb: int = 0