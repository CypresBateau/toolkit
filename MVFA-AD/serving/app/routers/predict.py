"""POST /api/v1/predict — 上传图片，返回 anomaly score 和 heatmap。"""

from __future__ import annotations

import os
import time
import uuid

from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from ..inference import run_inference
from ..model_singleton import ModelSingleton, VALID_OBJECTS
from ..schemas import PredictResponse


router = APIRouter()

@router.post("/predict", response_model=PredictResponse, tags=["predict"])
@router.post("/api/v1/predict", response_model=PredictResponse, tags=["predict"])
async def predict(
    file: UploadFile = File(..., description="医学图像文件，支持 JPG / JPEG / PNG"),
    obj: str = Form(
        default=None,
        description="Brain/Liver/Chest/Retina_RESC/Retina_OCT2017/Histopathology",
    ),
    return_heatmap: bool = Form(default=True, description="是否返回 base64 PNG heatmap"),
) -> PredictResponse:
    sg = ModelSingleton.get()

    if not sg.loaded:
        raise HTTPException(status_code=503, detail="Model is still loading, please retry.")

    target_obj = obj or os.environ.get("MVFA_DEFAULT_OBJECT", "Brain")

    if target_obj not in VALID_OBJECTS:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid obj={target_obj}. Valid: {VALID_OBJECTS}",
        )

    max_bytes = int(os.environ.get("MAX_FILE_SIZE_MB", 20)) * 1024 * 1024

    data = await file.read()

    if len(data) > max_bytes:
        raise HTTPException(
            status_code=413,
            detail=f"File too large ({len(data) // 1024} KB). "
                   f"Max allowed: {max_bytes // 1024 // 1024} MB.",
        )

    filename = file.filename or "upload.png"
    lower = filename.lower()

    if not any(lower.endswith(ext) for ext in (".jpg", ".jpeg", ".png")):
        raise HTTPException(
            status_code=415,
            detail="Unsupported file type. Accepted: jpg, jpeg, png.",
        )

    t0 = time.perf_counter()

    try:
        result = run_inference(
            image_bytes=data,
            filename=filename,
            singleton=sg,
            obj=target_obj,
            return_heatmap=return_heatmap,
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))

    elapsed_ms = (time.perf_counter() - t0) * 1000

    return PredictResponse(
        request_id=str(uuid.uuid4()),
        filename=filename,
        object=target_obj,
        inference_time_ms=round(elapsed_ms, 2),
        anomaly_score_raw=round(float(result["anomaly_score_raw"]), 6),
        anomaly_score=round(float(result["anomaly_score"]), 6),
        heatmap_png_base64=result["heatmap_png_base64"],
        model_info={
            "checkpoint": sg.checkpoint_name,
            "active_object": sg.active_object,
            "model_name": sg.model_name,
            "img_size": str(sg.img_size),
            "device": str(sg.device),
        },
    )