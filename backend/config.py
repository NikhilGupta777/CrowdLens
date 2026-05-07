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
RUNNING_SPEED_THRESHOLD = 18.0
RUNNING_PERSISTENCE_TIME = 0.8
RUNNING_MIN_HIT_STREAK = 4
UNATTENDED_OBJECT_TIME = 5.0
STATIONARY_THRESHOLD = 150.0
UNATTENDED_OWNER_PROXIMITY_PX = 180.0
UNATTENDED_OWNER_GRACE_TIME = 2.0
FALL_PERSISTENCE_TIME = 0.4
FALL_MODEL_CONFIDENCE_THRESHOLD = 0.18
RESTRICTED_ZONE_ENABLED = True
RESTRICTED_ZONE_MIN_DWELL = 0.6
FIGHT_DETECTION_ENABLED = True
FIGHT_PROXIMITY_PX = 180.0
FIGHT_MIN_PAIR_SPEED = 16.0
FIGHT_PERSISTENCE_TIME = 0.8
FIGHT_MIN_HIT_STREAK = 3

# Unattended object detection is disabled for now. Keep the code path intact,
# but do not track bottles/bags/books/phones until the project needs them again.
UNATTENDED_CLASSES = []

# Rectangular digital-fence areas in absolute frame coordinates (1280x720).
RESTRICTED_ZONES = [
    {"id": "RZ1", "name": "Restricted Zone A", "x1": 920, "y1": 80, "x2": 1240, "y2": 520},
]

# Active detection classes. Keep this intentionally narrow for reliability.
# Other COCO classes remain available in code and can be re-enabled later.
COCO_CLASSES = {
    0: "person",
    2: "car",
}

# Disabled but intentionally kept for easy re-enable later.
DISABLED_COCO_CLASSES = {
    1: "bicycle", 3: "motorcycle", 5: "bus", 7: "truck",
    15: "cat", 16: "dog", 17: "horse", 18: "sheep", 19: "cow",
    24: "backpack", 26: "handbag", 28: "suitcase",
    39: "bottle", 41: "cup", 67: "cell phone", 73: "book",
}
