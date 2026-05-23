"""License Plate Detector — uses keremberke/yolov8n-license-plate-detection.

Downloads from HuggingFace Hub on first run, then caches locally.
No OCR — just detects the plate bounding box and emits an alert.

detect_plates(frame) returns a list of dicts:
  [{"bbox": [x1, y1, x2, y2], "confidence": float}]
"""

import threading

_model = None
_model_lock = threading.Lock()
_model_ready = False
_model_error: str | None = None
_loading_progress = 0.0


def _download_lpr_model() -> None:
    """Download the license plate YOLO model from HuggingFace Hub (background thread)."""
    global _model, _model_ready, _model_error, _loading_progress

    try:
        _loading_progress = 0.1
        from ultralytics import YOLO

        model_id = "keremberke/yolov8n-license-plate-detection"
        _loading_progress = 0.3

        try:
            model = YOLO(model_id)
            _loading_progress = 0.9
        except Exception:
            # Fallback: try downloading with huggingface_hub directly
            try:
                from huggingface_hub import hf_hub_download
                model_path = hf_hub_download(
                    repo_id=model_id,
                    filename="best.pt",
                )
                model = YOLO(model_path)
                _loading_progress = 0.9
            except Exception as e2:
                _model_error = f"Could not load LPR model: {e2}"
                print(f"[lpr] {_model_error}")
                return

        with _model_lock:
            _model = model
            _model_ready = True
            _loading_progress = 1.0
        print("[lpr] License plate detection model loaded successfully")

    except Exception as e:
        _model_error = str(e)
        print(f"[lpr] Failed to load LPR model: {e}")


def is_lpr_model_ready() -> bool:
    return _model_ready


def get_lpr_model_error() -> str | None:
    return _model_error


def get_lpr_loading_progress() -> float:
    return _loading_progress


def detect_plates(frame, conf_override: float = 0.40) -> list[dict]:
    """Run license plate detection on a frame.

    Returns list of dicts: {"bbox": [x1,y1,x2,y2], "confidence": float}
    """
    if not _model_ready or _model is None:
        return []

    try:
        # Serialize inference: ultralytics models are not thread-safe, and the
        # extra detectors run in a shared thread-pool executor where a stale
        # processing loop could overlap with a newly-started one during a mode
        # switch. Mirrors the lock in detector.py / fall_detector.py.
        with _model_lock:
            results = _model.predict(
                source=frame,
                conf=conf_override,
                verbose=False,
                imgsz=640,
            )

        detections = []
        for result in results:
            boxes = result.boxes
            if boxes is None:
                continue
            for i in range(len(boxes)):
                xyxy = boxes.xyxy[i].cpu().numpy()
                conf = float(boxes.conf[i].cpu().numpy())

                detections.append({
                    "bbox": [float(xyxy[0]), float(xyxy[1]), float(xyxy[2]), float(xyxy[3])],
                    "confidence": round(conf, 3),
                })

        return detections

    except Exception as e:
        print(f"[lpr] Detection error: {e}")
        return []
