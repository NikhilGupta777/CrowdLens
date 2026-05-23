"""
YOLO11m Detection Module
Loads YOLO11m and runs inference via ONNX Runtime (preferred) or PyTorch.
Includes robust GPU/CPU fallback to handle driver mismatches gracefully.
"""

import os
import threading

import numpy as np
import torch

os.environ.setdefault("YOLO_CONFIG_DIR", "/tmp/Ultralytics")

from backend.config import COCO_CLASSES, CONFIDENCE_THRESHOLD, YOLO_MODEL, UNATTENDED_CLASSES, BAGGAGE_CONFIDENCE_FLOOR

MODEL_PATH     = YOLO_MODEL                           # e.g. "yolo11m.pt"
ONNX_PATH      = MODEL_PATH.replace(".pt", ".onnx")   # e.g. "yolo11m.onnx"
TARGET_CLASSES = set(COCO_CLASSES.keys())
BAGGAGE_CLASSES = set(UNATTENDED_CLASSES)
# Canonical "baggage" class id used when collapsing overlapping
# backpack/handbag/suitcase detections. Prefer 26 because the project's
# COCO_CLASSES override maps 26 → "baggage". If 26 is removed from
# UNATTENDED_CLASSES, fall back to the first member so the dedupe still works
# without being a hard literal.
if 26 in UNATTENDED_CLASSES:
    BAGGAGE_TRACK_CLASS_ID = 26
else:
    BAGGAGE_TRACK_CLASS_ID = next(iter(UNATTENDED_CLASSES), 26)
_BAGGAGE_FLOOR = max(0.05, min(0.30, BAGGAGE_CONFIDENCE_FLOOR))

_model        = None
_model_ready  = False
_model_error: str | None = None
_model_device = "cpu"
# Loading-progress stage strings published via get_loading_progress().
# Sequence: idle -> exporting_onnx -> loading_onnx -> warmup_gpu -> warmup_cpu
# -> loading_pytorch -> warmup_pytorch_gpu -> warmup_pytorch_cpu -> ready
# -> error. Used by /api/{video,stream,webcam}/status so the UI can show
# "Loading… (warmup_gpu)" instead of an indefinite spinner.
_model_stage: str = "idle"
_lock         = threading.Lock()


def is_model_ready() -> bool:
    return _model_ready


def get_model_error() -> str | None:
    return _model_error


def get_model_stage() -> str:
    return _model_stage


def get_loading_progress() -> dict:
    """Public progress payload for status endpoints."""
    return {
        "stage": _model_stage,
        "ready": _model_ready,
        "error": _model_error,
        "device": _model_device,
    }


def _try_warmup(model, label: str, device: str | None = None):
    """Run a single warm-up inference. Returns True on success."""
    dummy = np.zeros((640, 640, 3), dtype=np.uint8)
    kwargs = dict(conf=CONFIDENCE_THRESHOLD, verbose=False)
    if device:
        kwargs["device"] = device
    model(dummy, **kwargs)
    print(f"[detector] Warm-up OK → {label}")
    return True


def _box_area(box: list[float]) -> float:
    return max(1.0, float((box[2] - box[0]) * (box[3] - box[1])))


def _iou(box_a: list[float], box_b: list[float]) -> float:
    x1 = max(box_a[0], box_b[0])
    y1 = max(box_a[1], box_b[1])
    x2 = min(box_a[2], box_b[2])
    y2 = min(box_a[3], box_b[3])
    inter = max(0.0, x2 - x1) * max(0.0, y2 - y1)
    if inter <= 0:
        return 0.0
    return inter / (_box_area(box_a) + _box_area(box_b) - inter + 1e-6)


def _center_distance(box_a: list[float], box_b: list[float]) -> float:
    ax = (box_a[0] + box_a[2]) / 2.0
    ay = (box_a[1] + box_a[3]) / 2.0
    bx = (box_b[0] + box_b[2]) / 2.0
    by = (box_b[1] + box_b[3]) / 2.0
    return float(np.hypot(ax - bx, ay - by))


def _same_baggage_object(box_a: list[float], box_b: list[float]) -> bool:
    """Decide whether two baggage detections refer to the same physical object.

    YOLO COCO frequently labels the same bag with multiple sibling classes
    (backpack/handbag/suitcase) and the boxes drift between frames, so a
    pure IoU check is too tight.  The center-distance fallback exists to
    catch *partial* overlap on small bags where IoU is unreliable.

    Edge case fixed in this revision: two physically distinct small bags
    sitting side-by-side could previously satisfy the center-distance
    fallback (their centres are within ``max(35, 0.5·max_diag)``) without
    actually overlapping, and would silently merge into a single
    detection.  Adding a minimum-IoU gate to the fallback path eliminates
    that — boxes must still touch to be considered the same object.
    """
    iou = _iou(box_a, box_b)
    # Strong overlap: clearly the same object regardless of size.
    if iou >= 0.35:
        return True

    # Limit the fallback to small boxes where the YOLO bbox is most jittery.
    smaller_area = min(_box_area(box_a), _box_area(box_b))
    if smaller_area > 4000:  # ~63x63 px — not a tiny bag
        return False

    # Require *some* overlap before the proximity fallback engages. Without
    # this, two disjoint small bags sitting side by side merge into one;
    # with it, the boxes must still actually touch.
    if iou < 0.10:
        return False

    max_diag = max(np.sqrt(_box_area(box_a)), np.sqrt(_box_area(box_b)))
    return _center_distance(box_a, box_b) <= max(35.0, 0.50 * max_diag)


def _dedupe_and_canonicalize_baggage(detections: list[dict]) -> list[dict]:
    """
    YOLO COCO often labels the same bag as backpack/handbag/suitcase in the
    same frame or flips between those labels across frames. The app only needs
    a stable baggage object for unattended-object logic, so collapse overlapping
    baggage detections and track them under one canonical class.
    """
    non_baggage = [d for d in detections if d["class_id"] not in BAGGAGE_CLASSES]
    baggage = sorted(
        (d for d in detections if d["class_id"] in BAGGAGE_CLASSES),
        key=lambda d: d["confidence"],
        reverse=True,
    )

    kept: list[dict] = []
    for candidate in baggage:
        if any(_same_baggage_object(candidate["bbox"], existing["bbox"]) for existing in kept):
            continue
        merged = dict(candidate)
        merged["class_id"] = BAGGAGE_TRACK_CLASS_ID
        merged["class_name"] = "baggage"
        kept.append(merged)

    return non_baggage + kept


def _download_model():
    """
    Load YOLO11m, export to ONNX once, then reload via ONNX Runtime.
    Falls back through multiple strategies if GPU or ONNX fails:
      1. ONNX + GPU  (fastest)
      2. ONNX + CPU  (fast, portable)
      3. PyTorch + GPU
      4. PyTorch + CPU (slowest, always works)
    Runs in a background thread at startup.
    """
    global _model, _model_ready, _model_error, _model_device, _model_stage
    try:
        from ultralytics import YOLO

        _model_stage = "starting"
        has_cuda = torch.cuda.is_available()
        if has_cuda:
            gpu_name = torch.cuda.get_device_name(0)
            print(f"[detector] CUDA available — {gpu_name}")
        else:
            print("[detector] CUDA not available — will use CPU")

        # ── Export to ONNX if not already done ─────────────────────────────────
        if not os.path.exists(ONNX_PATH):
            _model_stage = "exporting_onnx"
            print(f"[detector] Exporting {MODEL_PATH} → {ONNX_PATH} (one-time ~30 s)…")
            try:
                pt_model = YOLO(MODEL_PATH)
                pt_model.export(
                    format="onnx",
                    imgsz=640,
                    simplify=True,
                    opset=17,
                )
                print(f"[detector] Export complete → {ONNX_PATH}")
            except Exception as export_err:
                print(f"[detector] ONNX export failed ({export_err}); will use .pt directly")
                if os.path.exists(ONNX_PATH):
                    os.remove(ONNX_PATH)

        # ── Strategy 1: ONNX Runtime (try GPU then CPU) ───────────────────────
        if os.path.exists(ONNX_PATH):
            _model_stage = "loading_onnx"
            print(f"[detector] Loading {ONNX_PATH} via ONNX Runtime…")
            try:
                model = YOLO(ONNX_PATH)

                # Try GPU-accelerated ONNX first
                if has_cuda:
                    try:
                        _model_stage = "warmup_onnx_gpu"
                        _try_warmup(model, "ONNX Runtime + GPU", device="0")
                        _model = model
                        _model_device = "cuda:0"
                        _model_ready = True
                        _model_stage = "ready"
                        print("[detector] ✓ Model ready via ONNX Runtime (GPU).")
                        return
                    except Exception as gpu_err:
                        print(f"[detector] ONNX GPU failed ({gpu_err}); trying ONNX CPU…")

                # Try CPU ONNX
                _model_stage = "warmup_onnx_cpu"
                _try_warmup(model, "ONNX Runtime + CPU", device="cpu")
                _model = model
                _model_device = "cpu"
                _model_ready = True
                _model_stage = "ready"
                print("[detector] ✓ Model ready via ONNX Runtime (CPU).")
                return
            except Exception as onnx_err:
                print(f"[detector] ONNX Runtime failed entirely ({onnx_err}); falling back to PyTorch")

        # ── Strategy 2: PyTorch (try GPU then CPU) ────────────────────────────
        _model_stage = "loading_pytorch"
        print(f"[detector] Loading {MODEL_PATH} via PyTorch…")
        model = YOLO(MODEL_PATH)

        if has_cuda:
            try:
                model.to("cuda:0")
                _model_stage = "warmup_pytorch_gpu"
                _try_warmup(model, "PyTorch + GPU", device="0")
                _model = model
                _model_device = "cuda:0"
                _model_ready = True
                _model_stage = "ready"
                print("[detector] ✓ Model ready via PyTorch (GPU).")
                return
            except Exception as pt_gpu_err:
                print(f"[detector] PyTorch GPU failed ({pt_gpu_err}); using CPU…")

        model.to("cpu")
        _model_stage = "warmup_pytorch_cpu"
        _try_warmup(model, "PyTorch + CPU", device="cpu")
        _model = model
        _model_device = "cpu"
        _model_ready = True
        _model_stage = "ready"
        print("[detector] ✓ Model ready via PyTorch (CPU).")

    except Exception as e:
        _model_error = str(e)
        _model_stage = "error"
        print(f"[detector] Fatal model error: {e}")


class YOLOv8Detector:
    """YOLO11m detector — uses best available backend (ONNX/PyTorch, GPU/CPU)."""

    def __init__(self):
        if not _model_ready:
            raise RuntimeError("YOLO11m model not ready yet — wait for startup")

    def detect(self, frame: np.ndarray, conf_override: float | None = None) -> list[dict]:
        """
        Run YOLO11m inference on a BGR frame.

        Uses a two-tier confidence strategy: YOLO runs at the lower baggage
        floor so low-confidence bags are not discarded internally, then
        non-baggage classes are post-filtered at the normal threshold.
        """
        normal_conf = CONFIDENCE_THRESHOLD if conf_override is None else conf_override
        yolo_floor = min(normal_conf, _BAGGAGE_FLOOR)

        with _lock:
            results = _model(frame, conf=yolo_floor, verbose=False)[0]

        detections = []
        for box in results.boxes:
            x1, y1, x2, y2 = box.xyxy[0].cpu().numpy()
            confidence = float(box.conf[0].cpu().numpy())
            class_id   = int(box.cls[0].cpu().numpy())

            if class_id not in TARGET_CLASSES:
                continue

            if class_id in BAGGAGE_CLASSES:
                if confidence < _BAGGAGE_FLOOR:
                    continue
            else:
                if confidence < normal_conf:
                    continue

            detections.append({
                "bbox":       [float(x1), float(y1), float(x2), float(y2)],
                "confidence": round(confidence, 3),
                "class_id":   class_id,
                "class_name": COCO_CLASSES.get(class_id, "unknown"),
            })
        return _dedupe_and_canonicalize_baggage(detections)
