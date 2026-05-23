"""PPE (Personal Protective Equipment) Detector — helmet detection.

Uses keremberke/yolov8n-hard-hat-detection from HuggingFace Hub.
Downloads on first run, then caches locally.

detect_ppe(frame) returns a list of dicts:
  [{"bbox": [x1, y1, x2, y2], "label": "Hardhat"|"NO-Hardhat", "confidence": float}]
"""

import threading

_model = None
_model_lock = threading.Lock()
_model_ready = False
_model_error: str | None = None
_loading_progress = 0.0


def _download_ppe_model() -> None:
    """Download the PPE YOLO model from HuggingFace Hub (background thread)."""
    global _model, _model_ready, _model_error, _loading_progress

    try:
        _loading_progress = 0.1
        from ultralytics import YOLO

        # keremberke/yolov8n-hard-hat-detection is a lightweight YOLOv8-nano
        # model (~6 MB) fine-tuned on hard-hat/no-hard-hat detection.
        # If the model is already cached, this is instant.
        model_id = "keremberke/yolov8n-hard-hat-detection"
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
                _model_error = f"Could not load PPE model: {e2}"
                print(f"[ppe] {_model_error}")
                return

        with _model_lock:
            _model = model
            _model_ready = True
            _loading_progress = 1.0
        print("[ppe] PPE (hard-hat) model loaded successfully")

    except Exception as e:
        _model_error = str(e)
        print(f"[ppe] Failed to load PPE model: {e}")


def is_ppe_model_ready() -> bool:
    return _model_ready


def get_ppe_model_error() -> str | None:
    return _model_error


def get_ppe_loading_progress() -> float:
    return _loading_progress


def detect_ppe(frame, conf_override: float = 0.40) -> list[dict]:
    """Run PPE detection on a frame. Returns list of detections.

    Each detection: {"bbox": [x1,y1,x2,y2], "label": str, "confidence": float}
    Labels: "Hardhat", "NO-Hardhat"
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
                cls_id = int(boxes.cls[i].cpu().numpy())
                label = result.names.get(cls_id, f"class_{cls_id}")

                detections.append({
                    "bbox": [float(xyxy[0]), float(xyxy[1]), float(xyxy[2]), float(xyxy[3])],
                    "label": label,
                    "confidence": round(conf, 3),
                })

        return detections

    except Exception as e:
        print(f"[ppe] Detection error: {e}")
        return []
