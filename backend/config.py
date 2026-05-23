FRAME_WIDTH = 1280
FRAME_HEIGHT = 720

# YOLO11m — Medium model for accurate crowd analysis.
YOLO_MODEL = "yolo11m.pt"
CONFIDENCE_THRESHOLD = 0.25

# Inference resolution for video / webcam modes.
# YOLO was trained at 640px; running at native 640x360 avoids the internal
# downsample from 1280x720, cutting inference time by ~4×.
INFER_WIDTH = 640
INFER_HEIGHT = 360

# Stream mode tuning:
# Use inference resolution directly — 4× less raw data piped from FFmpeg,
# eliminates the redundant resize before YOLO, and cuts pipe backlog.
STREAM_FRAME_WIDTH = 640
STREAM_FRAME_HEIGHT = 360
STREAM_TARGET_FPS = 15
STREAM_DETECTION_CONFIDENCE = 0.25

# Detection confidence overrides per mode.
# Lower thresholds catch more crowd members (small/distant/partially occluded).
VIDEO_DETECTION_CONFIDENCE = 0.18
WEBCAM_DETECTION_CONFIDENCE = 0.20

# Tracker confirmation policy.
# 1 = show tracks immediately (better for fast occlusion recovery).
TRACKER_MIN_HITS = 1

# SORT tracker tuning.
# Higher max_age keeps IDs alive through brief occlusions (crowded scenes).
# Lower IOU threshold accepts larger positional shifts between frames.
MAX_AGE = 30
IOU_THRESHOLD = 0.25

# Anomaly detection settings
OVERCROWDING_THRESHOLD = 4
# Spatial clustering for overcrowding: two persons belong to the same cluster
# if they are within this many pixels (single-link chain). The threshold then
# applies per cluster, so a tight crowd at a doorway triggers an alert even
# when total scene count is low, and a wide plaza with people scattered
# across it does not falsely alert just because the headcount is high.
OVERCROWDING_CLUSTER_DISTANCE_PX = 200.0
OVERCROWDING_MIN_CLUSTER_SIZE = 4        # min cluster size to emit an alert

# ── Running detection ────────────────────────────────────────────────────────
# Running uses BOTH:
#   1. Body-heights/sec (relative to bbox height) — primary, distance-invariant
#   2. Raw pixel speed floor (RUNNING_PIXEL_FLOOR) — anti-jitter guard against
#      tiny/stuttering bboxes producing huge body-heights/sec from noise
# A track is flagged as running when body-heights/sec >= threshold AND raw
# pixel speed >= RUNNING_PIXEL_FLOOR. The legacy raw-speed-only path is
# preserved as a fallback for very wide camera setups (RUNNING_SPEED_THRESHOLD).
RUNNING_SPEED_THRESHOLD = 270.0          # px/sec at 1280×720 canvas (legacy fallback)
RUNNING_BODY_HEIGHTS_PER_SEC = 1.6       # ~1.6 body heights/sec ≈ jogging+
# Anti-jitter floor. A tiny bbox (e.g. 30 px tall) can produce 2 body-heights
# /sec from a few pixels of YOLO jitter; the floor rejects those false positives.
RUNNING_PIXEL_FLOOR = 60.0               # px/sec absolute minimum
RUNNING_PERSISTENCE_TIME = 0.6
RUNNING_MIN_HIT_STREAK = 3
# Tolerate brief speed dips (single-frame stutter, momentary YOLO miss) before
# resetting the candidate timer. Without this, a 1-frame slowdown wipes
# accumulated persistence and running is repeatedly missed.
RUNNING_RESET_GRACE_TIME = 0.4

# ── Unattended object ────────────────────────────────────────────────────────
UNATTENDED_OBJECT_TIME = 5.0
STATIONARY_THRESHOLD = 110.0             # px spread over recent history
UNATTENDED_OWNER_PROXIMITY_PX = 180.0
UNATTENDED_OWNER_GRACE_TIME = 2.0
# When True, ANY tracked person within UNATTENDED_OWNER_PROXIMITY_PX of the
# object counts as a guardian (not just the originally-assigned owner). This
# prevents false-positives in busy areas where the owner walks away but a
# different person is standing right next to the bag.
UNATTENDED_BYSTANDER_ATTENDS = True
# Ghost cache: when a baggage SORT track dies (occluded > MAX_AGE), cache its
# state for this many seconds in a spatial-cell map. If a new baggage track
# appears in the same cell within the TTL, restore stationary_since /
# owner_id / owner_absent_since so the unattended timer is not reset by SORT
# ID churn. Required to detect bags abandoned for 4+ seconds with brief
# occlusions, which previously kept restarting the 5-second stationary timer.
UNATTENDED_GHOST_TTL = 8.0
UNATTENDED_GHOST_CELL_PX = 96            # spatial bucket size for ghost lookup

# ── Fall detection ───────────────────────────────────────────────────────────
FALL_PERSISTENCE_TIME = 1.2
FALL_MODEL_CONFIDENCE_THRESHOLD = 0.35
# Sanity filters on top of the HF fall model. The model itself classifies
# "fallen" — these checks reject obvious false positives without rejecting
# valid forward-collapse / kneeling falls.
FALL_MIN_AREA_RATIO = 0.005              # min bbox area / frame area (~0.5%)
FALL_ASPECT_RATIO_MIN = 0.40             # min width/height of a fallen box
# Minimum IoU between a fall bbox and a person track bbox to associate the
# fall with that track id. Helps distinguish concurrent falls and avoids
# all falls falling back to spatial-cell cooldown buckets (which previously
# merged two simultaneous falls within the same 128 px cell into one alert).
FALL_PERSON_IOU_MIN = 0.20

# ── Restricted zone ──────────────────────────────────────────────────────────
RESTRICTED_ZONE_ENABLED = True
RESTRICTED_ZONE_MIN_DWELL = 0.6
# Trigger if the foot point (cx, y2) is in the zone OR if the person bbox
# overlaps the zone rectangle. Center-only checks miss people walking along
# the zone edge whose feet are inside but center is outside.
RESTRICTED_ZONE_USE_FEET = True

# ── Fight detection ──────────────────────────────────────────────────────────
FIGHT_DETECTION_ENABLED = True
FIGHT_PROXIMITY_PX = 180.0
FIGHT_MIN_PAIR_SPEED = 240.0
FIGHT_PERSISTENCE_TIME = 0.8
FIGHT_MIN_HIT_STREAK = 3

# ── Loitering detection ──────────────────────────────────────────────────────
# A loiterer remains within a small region for an extended time. The radius
# defines that region. Re-anchoring uses hysteresis (1.5× radius) so jitter
# inside the region does not reset the timer.
LOITERING_ENABLED = True
LOITERING_TIME_THRESHOLD = 15.0
LOITERING_RADIUS_PX = 180.0
LOITERING_REANCHOR_FACTOR = 1.5

# Baggage-specific confidence floor. YOLO runs at this threshold so low-confidence
# bags are not discarded internally; non-baggage classes are post-filtered at the
# per-mode threshold (VIDEO/WEBCAM/STREAM_DETECTION_CONFIDENCE).
BAGGAGE_CONFIDENCE_FLOOR = 0.10

# Classes treated as baggage for unattended-object detection.
# Keep this narrow: bags only. Bottles, animals, phones, books, etc. remain off.
UNATTENDED_CLASSES = [24, 26, 28]

# Rectangular or polygon digital-fence areas in absolute frame coordinates
# (1280x720). Each zone has a "shape" field: "rect" (uses x1/y1/x2/y2) or
# "polygon" (uses points: [[x,y], ...]). Existing rectangle-only zones still
# work without an explicit "shape" key — they're treated as rectangles.
RESTRICTED_ZONES = [
    {"id": "RZ1", "name": "Restricted Zone A", "shape": "rect",
     "x1": 920, "y1": 80, "x2": 1240, "y2": 520},
]

# Active detection classes. Keep this intentionally narrow for reliability.
# Other COCO classes remain available in code and can be re-enabled later.
COCO_CLASSES = {
    0: "person",
    2: "car",
    24: "backpack",
    26: "baggage",
    28: "suitcase",
}

# Disabled but intentionally kept for easy re-enable later.
DISABLED_COCO_CLASSES = {
    1: "bicycle", 3: "motorcycle", 5: "bus", 7: "truck",
    15: "cat", 16: "dog", 17: "horse", 18: "sheep", 19: "cow",
    39: "bottle", 41: "cup", 67: "cell phone", 73: "book",
}
