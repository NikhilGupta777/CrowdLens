"""
Dedicated fall detector powered by:
https://huggingface.co/melihuzunoglu/human-fall-detection
"""

import os
import threading

import numpy as np

from backend.config import FALL_MODEL_CONFIDENCE_THRESHOLD

_fall_model = None
_fall_model_ready = False
_fall_model_error: str | None = None
_lock = threading.Lock()


def is_fall_model_ready() -> bool:
    return _fall_model_ready


def get_fall_model_error() -> str | None:
    return _fall_model_error


def _download_fall_model() -> None:
    global _fall_model, _fall_model_ready, _fall_model_error
    try:
        from huggingface_hub import hf_hub_download
        from ultralytics import YOLO

        local_override = os.environ.get("FALL_MODEL_LOCAL_PATH", "").strip()
        if local_override and os.path.exists(local_override):
            model_path = local_override
            print(f"[fall-detector] Using local fall model: {model_path}")
        else:
            model_path = hf_hub_download(
                repo_id="melihuzunoglu/human-fall-detection",
                filename="best.pt",
            )
        model = YOLO(model_path)
        dummy = np.zeros((640, 640, 3), dtype=np.uint8)
        model(dummy, conf=FALL_MODEL_CONFIDENCE_THRESHOLD, verbose=False)
        _fall_model = model
        _fall_model_ready = True
        print("[fall-detector] Fall model ready (Hugging Face YOLOv11).")
    except Exception as e:
        _fall_model_error = str(e)
        print(f"[fall-detector] Failed to load fall model: {e}")


def detect_falls(frame: np.ndarray, conf_override: float | None = None) -> list[dict]:
    """
    Returns detections for "fallen" class as:
      [{"bbox":[x1,y1,x2,y2], "confidence":float, "label":"fallen"}, ...]
    """
    if not _fall_model_ready or _fall_model is None:
        return []

    conf = (
        FALL_MODEL_CONFIDENCE_THRESHOLD
        if conf_override is None
        else float(conf_override)
    )
    with _lock:
        result = _fall_model(frame, conf=conf, verbose=False)[0]

    fallen_results: list[dict] = []
    names = result.names or {}
    for box in result.boxes:
        class_id = int(box.cls[0].cpu().numpy())
        label = str(names.get(class_id, "")).strip().lower()
        if "fallen" not in label and "fall" not in label:
            continue
        x1, y1, x2, y2 = box.xyxy[0].cpu().numpy()
        confidence = float(box.conf[0].cpu().numpy())
        fallen_results.append(
            {
                "bbox": [float(x1), float(y1), float(x2), float(y2)],
                "confidence": round(confidence, 3),
                "label": label,
            }
        )
    return fallen_results
