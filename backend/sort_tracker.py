"""
SORT: Simple Online and Realtime Tracking
Translated from the original SORT paper implementation.
Uses Kalman filtering (filterpy) + Hungarian algorithm (scipy).
"""
import threading

import numpy as np
from scipy.optimize import linear_sum_assignment
from filterpy.kalman import KalmanFilter

try:
    from backend.config import UNATTENDED_CLASSES
except Exception:
    UNATTENDED_CLASSES = [24, 26, 28]

BAGGAGE_TRACK_CLASSES = set(UNATTENDED_CLASSES)
OBJECT_TRACK_CLASSES = BAGGAGE_TRACK_CLASSES | {2}
OBJECT_TRACK_HOLD_FRAMES = 30
BAGGAGE_STRONG_HOLD_FRAMES = 120
BAGGAGE_WEAK_HOLD_FRAMES = 45
BAGGAGE_STRONG_CONFIDENCE = 0.20
OBJECT_ASSOCIATION_DISTANCE_PX = 95.0

# Module-level ID counter with a lock so multiple Sort instances
# (video, webcam, stream) each get globally unique track IDs and
# a reset() on one instance cannot cause ID collisions in another.
_id_lock = threading.Lock()
_id_counter = 0


def _box_to_z(bbox):
    """Convert [x1,y1,x2,y2] to Kalman state [cx, cy, area, aspect_ratio]."""
    w = bbox[2] - bbox[0]
    h = bbox[3] - bbox[1]
    cx = bbox[0] + w / 2.0
    cy = bbox[1] + h / 2.0
    s = w * h
    r = w / float(h + 1e-6)
    return np.array([[cx], [cy], [s], [r]])


def _z_to_box(x):
    """Convert Kalman state back to [x1, y1, x2, y2]."""
    w = np.sqrt(abs(x[2] * x[3]))
    h = x[2] / (w + 1e-6)
    return np.array([
        x[0] - w / 2.0,
        x[1] - h / 2.0,
        x[0] + w / 2.0,
        x[1] + h / 2.0,
    ]).flatten()


def _iou(b1, b2):
    """Compute IoU between two boxes [x1,y1,x2,y2]."""
    xx1 = max(b1[0], b2[0])
    yy1 = max(b1[1], b2[1])
    xx2 = min(b1[2], b2[2])
    yy2 = min(b1[3], b2[3])
    inter = max(0.0, xx2 - xx1) * max(0.0, yy2 - yy1)
    a1 = (b1[2] - b1[0]) * (b1[3] - b1[1])
    a2 = (b2[2] - b2[0]) * (b2[3] - b2[1])
    return inter / (a1 + a2 - inter + 1e-6)


def _center_distance(b1, b2):
    c1x = (b1[0] + b1[2]) / 2.0
    c1y = (b1[1] + b1[3]) / 2.0
    c2x = (b2[0] + b2[2]) / 2.0
    c2y = (b2[1] + b2[3]) / 2.0
    return float(np.hypot(c1x - c2x, c1y - c2y))


def _box_area(b):
    return max(1.0, float((b[2] - b[0]) * (b[3] - b[1])))


def _object_association_cost(det_box, pred_box):
    iou = _iou(det_box, pred_box)
    if iou >= 0.30:
        return 1.0 - iou

    # Small bags and distant cars often jump enough between YOLO frames that IoU
    # becomes weak or zero. A bounded center-distance fallback keeps the same ID
    # without allowing far-away objects to merge.
    det_diag = np.sqrt(_box_area(det_box))
    pred_diag = np.sqrt(_box_area(pred_box))
    max_dist = max(OBJECT_ASSOCIATION_DISTANCE_PX, 1.5 * det_diag, 1.5 * pred_diag)
    dist = _center_distance(det_box, pred_box)
    if dist <= max_dist:
        return min(0.70, (dist / max_dist) * 0.70)
    return 1.0


def _associate(detections, predictions, iou_threshold=0.3):
    """
    Match detections to existing trackers via Hungarian algorithm.
    Returns: (matches, unmatched_dets, unmatched_trks)
    """
    if len(predictions) == 0:
        return [], list(range(len(detections))), []
    if len(detections) == 0:
        return [], [], list(range(len(predictions)))

    cost = np.zeros((len(detections), len(predictions)))
    for d, det in enumerate(detections):
        for t, pred in enumerate(predictions):
            det_box, det_class = det
            pred_box, pred_class = pred
            if det_class != pred_class:
                # Keep class identity stable: do not match person<->object tracks.
                cost[d, t] = 1e6
                continue
            if det_class in OBJECT_TRACK_CLASSES:
                cost[d, t] = _object_association_cost(det_box, pred_box)
            else:
                cost[d, t] = 1.0 - _iou(det_box, pred_box)

    row_ind, col_ind = linear_sum_assignment(cost)

    matches, unmatched_d, unmatched_t = [], [], []
    matched_d, matched_t = set(), set()

    for r, c in zip(row_ind, col_ind):
        if cost[r, c] < 1.0 - iou_threshold:
            matches.append((r, c))
            matched_d.add(r)
            matched_t.add(c)

    for d in range(len(detections)):
        if d not in matched_d:
            unmatched_d.append(d)
    for t in range(len(predictions)):
        if t not in matched_t:
            unmatched_t.append(t)

    return matches, unmatched_d, unmatched_t


class KalmanBoxTracker:
    """Single object tracked with a Kalman filter. State: [cx,cy,s,r,vcx,vcy,vs]."""

    def __init__(self, bbox: list, class_id: int, confidence: float):
        self.kf = KalmanFilter(dim_x=7, dim_z=4)
        # State transition
        self.kf.F = np.array([
            [1, 0, 0, 0, 1, 0, 0],
            [0, 1, 0, 0, 0, 1, 0],
            [0, 0, 1, 0, 0, 0, 1],
            [0, 0, 0, 1, 0, 0, 0],
            [0, 0, 0, 0, 1, 0, 0],
            [0, 0, 0, 0, 0, 1, 0],
            [0, 0, 0, 0, 0, 0, 1],
        ], dtype=float)
        # Measurement matrix
        self.kf.H = np.array([
            [1, 0, 0, 0, 0, 0, 0],
            [0, 1, 0, 0, 0, 0, 0],
            [0, 0, 1, 0, 0, 0, 0],
            [0, 0, 0, 1, 0, 0, 0],
        ], dtype=float)
        self.kf.R[2:, 2:] *= 10.0
        self.kf.P[4:, 4:] *= 1000.0
        self.kf.P *= 10.0
        self.kf.Q[-1, -1] *= 0.01
        self.kf.Q[4:, 4:] *= 0.01
        self.kf.x[:4] = _box_to_z(bbox)

        global _id_counter
        with _id_lock:
            _id_counter += 1
            self.id = _id_counter

        self.class_id = class_id
        self.confidence = confidence
        self.last_bbox = np.array(bbox, dtype=float)
        self.hits = 1
        self.hit_streak = 1
        self.age = 0
        self.time_since_update = 0

    def predict(self):
        if self.kf.x[6] + self.kf.x[2] <= 0:
            self.kf.x[6] = 0.0
        self.kf.predict()
        self.age += 1
        if self.time_since_update > 0:
            self.hit_streak = 0
        self.time_since_update += 1
        return _z_to_box(self.kf.x)

    def update(self, bbox: list, class_id: int, confidence: float):
        self.time_since_update = 0
        self.hits += 1
        self.hit_streak += 1
        self.class_id = class_id
        self.confidence = confidence
        self.last_bbox = np.array(bbox, dtype=float)
        self.kf.update(_box_to_z(bbox))

    def get_box(self):
        return _z_to_box(self.kf.x)

    def get_last_box(self):
        return self.last_bbox.copy()


class Sort:
    """
    SORT multi-object tracker.
    max_age: frames to keep a tracker alive without a match.
    min_hits: min matches before reporting a track (reduces false positives).
    iou_threshold: min IoU to consider a detection-tracker match.
    """

    def __init__(self, max_age: int = 3, min_hits: int = 2, iou_threshold: float = 0.3):
        self.max_age = max_age
        self.min_hits = min_hits
        self.iou_threshold = iou_threshold
        self.trackers: list[KalmanBoxTracker] = []
        self.frame_count = 0

    def update(self, detections: list[dict]) -> list[dict]:
        """
        detections: [{"bbox": [x1,y1,x2,y2], "class_id": int, "confidence": float}]
        Returns: [{"id": int, "bbox": [x1,y1,x2,y2], "class_id": int, "confidence": float}]
        """
        self.frame_count += 1

        # Predict step
        predictions = []
        dead = []
        for i, trk in enumerate(self.trackers):
            pred = trk.predict()
            if np.any(np.isnan(pred)):
                dead.append(i)
            else:
                match_box = trk.get_last_box() if trk.class_id in BAGGAGE_TRACK_CLASSES else pred
                predictions.append((match_box.tolist(), trk.class_id))
        for i in reversed(dead):
            self.trackers.pop(i)

        det_boxes = [(d["bbox"], d["class_id"]) for d in detections]
        matches, unmatched_dets, unmatched_trks = _associate(
            det_boxes, predictions, self.iou_threshold
        )

        # Update matched
        for d_idx, t_idx in matches:
            self.trackers[t_idx].update(
                detections[d_idx]["bbox"],
                detections[d_idx]["class_id"],
                detections[d_idx]["confidence"],
            )

        # Create new trackers
        for d_idx in unmatched_dets:
            self.trackers.append(
                KalmanBoxTracker(
                    detections[d_idx]["bbox"],
                    detections[d_idx]["class_id"],
                    detections[d_idx]["confidence"],
                )
            )

        # Collect active tracks
        active = []
        for trk in self.trackers:
            recently_detected = trk.time_since_update < 1
            confirmed_now = (
                trk.hit_streak >= self.min_hits or self.frame_count <= self.min_hits
            )
            hold_limit = (
                BAGGAGE_STRONG_HOLD_FRAMES
                if trk.class_id in BAGGAGE_TRACK_CLASSES
                and trk.confidence >= BAGGAGE_STRONG_CONFIDENCE
                else BAGGAGE_WEAK_HOLD_FRAMES
                if trk.class_id in BAGGAGE_TRACK_CLASSES
                else OBJECT_TRACK_HOLD_FRAMES
                if trk.class_id in OBJECT_TRACK_CLASSES
                else 0
            )
            object_hold = (
                hold_limit > 0
                and 0 < trk.time_since_update <= hold_limit
                and (
                    trk.hits >= 1
                    if trk.class_id in BAGGAGE_TRACK_CLASSES
                    else trk.hits >= max(2, self.min_hits)
                )
            )
            if (recently_detected and confirmed_now) or object_hold:
                box_source = (
                    trk.get_last_box()
                    if trk.class_id in BAGGAGE_TRACK_CLASSES and trk.time_since_update > 0
                    else trk.get_box()
                )
                box = box_source.tolist()
                active.append({
                    "id": trk.id,
                    "bbox": box,
                    "class_id": trk.class_id,
                    "confidence": trk.confidence,
                    "hit_streak": trk.hit_streak,
                    "age": trk.age,
                    "hits": trk.hits,
                    "time_since_update": trk.time_since_update,
                    "predicted": trk.time_since_update > 0,
                })

        # Prune dead trackers — respect extended hold for object/baggage tracks.
        def _prune_limit(trk):
            if trk.class_id in BAGGAGE_TRACK_CLASSES:
                if trk.confidence >= BAGGAGE_STRONG_CONFIDENCE:
                    return BAGGAGE_STRONG_HOLD_FRAMES
                return BAGGAGE_WEAK_HOLD_FRAMES
            if trk.class_id in OBJECT_TRACK_CLASSES:
                return OBJECT_TRACK_HOLD_FRAMES
            return self.max_age

        self.trackers = [t for t in self.trackers if t.time_since_update <= _prune_limit(t)]

        return active

    def reset(self):
        self.trackers = []
        self.frame_count = 0
        # The global _id_counter is intentionally NOT reset here.
        # Resetting it could cause ID collisions between concurrent Sort
        # instances (video / webcam / stream) or across looped sessions.
