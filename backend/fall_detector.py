"""
Dedicated fall detector powered by:
https://huggingface.co/melihuzunoglu/human-fall-detection

Detects "fallen" class bounding boxes and applies lightweight NMS + sanity
filtering before returning results to the anomaly engine.
"""

import os
import threading

import numpy as np

from backend.config import (
    FALL_MODEL_CONFIDENCE_THRESHOLD,
    FRAME_WIDTH,
    FRAME_HEIGHT,
)

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
        # Assign model first, then set ready flag (memory ordering safety)
        _fall_model = model
        _fall_model_ready = True
        print("[fall-detector] Fall model ready (Hugging Face YOLOv11).")
    except Exception as e:
        _fall_model_error = str(e)
        print(f"[fall-detector] Failed to load fall model: {e}")



def _iou(a: list[float], b: list[float]) -> float:
    """Intersection-over-Union for two [x1,y1,x2,y2] boxes."""
    ix1 = max(a[0], b[0])
    iy1 = max(a[1], b[1])
    ix2 = min(a[2], b[2])
    iy2 = min(a[3], b[3])
    inter = max(0.0, ix2 - ix1) * max(0.0, iy2 - iy1)
    if inter <= 0:
        return 0.0
    area_a = max(0.0, a[2] - a[0]) * max(0.0, a[3] - a[1])
    area_b = max(0.0, b[2] - b[0]) * max(0.0, b[3] - b[1])
    return inter / (area_a + area_b - inter + 1e-6)


def _nms_fall_detections(detections: list[dict], iou_thresh: float = 0.45) -> list[dict]:
    """
    Simple greedy NMS: keep highest-confidence detection, suppress overlapping.
    Prevents duplicate persistence timers in anomaly.py for the same fall event.
    """
    if len(detections) <= 1:
        return detections
    sorted_dets = sorted(detections, key=lambda d: d["confidence"], reverse=True)
    kept: list[dict] = []
    for det in sorted_dets:
        if any(_iou(det["bbox"], k["bbox"]) >= iou_thresh for k in kept):
            continue
        kept.append(det)
    return kept


def detect_falls(frame: np.ndarray, conf_override: float | None = None) -> list[dict]:
    """
    Returns detections for "fallen" class as:
      [{"bbox":[x1,y1,x2,y2], "confidence":float, "label":"fallen"}, ...]

    Applies:
      1. Confidence threshold
      2. Sanity filters (min area, reject top-of-frame)
      3. NMS to deduplicate overlapping fall boxes
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

    # Get frame dimensions from the actual input (may differ from config)
    fh, fw = frame.shape[:2] if frame.ndim >= 2 else (FRAME_HEIGHT, FRAME_WIDTH)

    fallen_results: list[dict] = []
    names = result.names or {}
    for box in result.boxes:
        class_id = int(box.cls[0].cpu().numpy())
        label = str(names.get(class_id, "")).strip().lower()
        if "fallen" not in label and "fall" not in label:
            continue
        x1, y1, x2, y2 = box.xyxy[0].cpu().numpy()
        confidence = float(box.conf[0].cpu().numpy())

        # Sanity filter 1: reject tiny boxes (noise / artifacts)
        box_w = max(1.0, float(x2 - x1))
        box_h = max(1.0, float(y2 - y1))
        box_area = box_w * box_h
        frame_area = fw * fh
        if box_area < frame_area * 0.004:  # < 0.4% of frame
            continue

        # Sanity filter 2: reject boxes entirely in top 20% of frame
        # (ceiling/wall/sign misclassifications)
        if float(y2) < fh * 0.20:
            continue

        fallen_results.append({
            "bbox": [float(x1), float(y1), float(x2), float(y2)],
            "confidence": round(confidence, 3),
            "label": label,
        })

    # Deduplicate overlapping detections
    return _nms_fall_detections(fallen_results)
