"""Face Detector — uses OpenCV's built-in Haar Cascade.

Zero extra downloads required: haarcascade_frontalface_default.xml ships
with every OpenCV install (including opencv-python-headless).

detect_faces(frame) returns a list of dicts:
  [{"bbox": [x1, y1, x2, y2], "confidence": float}]

The confidence is a synthetic 0-1 value derived from the number of
neighbours that confirmed the face (higher = more reliable).
"""

import os
import threading

import cv2
import numpy as np

_cascade = None
_model_ready = False
_model_error: str | None = None


def _load_face_cascade() -> None:
    """Load the Haar cascade classifier (instant, no download)."""
    global _cascade, _model_ready, _model_error

    try:
        cascade_path = cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
        if not os.path.exists(cascade_path):
            _model_error = f"Cascade file not found at {cascade_path}"
            print(f"[face] {_model_error}")
            return

        _cascade = cv2.CascadeClassifier(cascade_path)
        if _cascade.empty():
            _model_error = "Failed to load Haar cascade (empty classifier)"
            print(f"[face] {_model_error}")
            return

        _model_ready = True
        print("[face] Haar cascade face detector loaded")

    except Exception as e:
        _model_error = str(e)
        print(f"[face] Failed to load face cascade: {e}")


def is_face_model_ready() -> bool:
    return _model_ready


def get_face_model_error() -> str | None:
    return _model_error


def detect_faces(
    frame,
    scale_factor: float = 1.3,
    min_neighbors: int = 5,
    min_size: tuple[int, int] = (30, 30),
) -> list[dict]:
    """Detect faces in a frame using the Haar cascade.

    Returns list of dicts with bbox [x1,y1,x2,y2] and confidence (0-1).
    """
    if not _model_ready or _cascade is None:
        return []

    try:
        # Convert to grayscale for cascade
        if len(frame.shape) == 3:
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        else:
            gray = frame

        # Histogram equalization for better detection in varied lighting
        gray = cv2.equalizeHist(gray)

        # detectMultiScale returns (x, y, w, h) rects and reject levels
        faces, reject_levels, level_weights = _cascade.detectMultiScale3(
            gray,
            scaleFactor=scale_factor,
            minNeighbors=min_neighbors,
            minSize=min_size,
            flags=cv2.CASCADE_SCALE_IMAGE,
            outputRejectLevels=True,
        )

        detections = []
        if faces is not None and len(faces) > 0:
            for i, (x, y, w, h) in enumerate(faces):
                # Synthetic confidence from level_weights (higher = more reliable)
                weight = float(level_weights[i]) if level_weights is not None and i < len(level_weights) else 1.0
                # Normalize to 0-1 range (weights typically range 0-5+)
                confidence = min(1.0, max(0.0, weight / 5.0))

                detections.append({
                    "bbox": [int(x), int(y), int(x + w), int(y + h)],
                    "confidence": round(confidence, 3),
                })

        return detections

    except Exception as e:
        print(f"[face] Detection error: {e}")
        return []
