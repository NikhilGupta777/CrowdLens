import asyncio
import base64
import ipaddress
import json
import math
import os
import queue
import shutil
import subprocess
import tempfile
import time
import threading
from collections import deque
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from urllib.parse import urlsplit
from dotenv import load_dotenv
load_dotenv()

import numpy as np
from fastapi import (
    FastAPI,
    WebSocket,
    WebSocketDisconnect,
    UploadFile,
    File,
    HTTPException,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, FileResponse
from pydantic import BaseModel

from backend.anomaly import AnomalyDetector
import backend.database as _db
from backend.config import (
    OVERCROWDING_THRESHOLD,
    RUNNING_SPEED_THRESHOLD,
    UNATTENDED_OBJECT_TIME,
    STATIONARY_THRESHOLD,
    COCO_CLASSES,
    UNATTENDED_OWNER_PROXIMITY_PX,
    UNATTENDED_OWNER_GRACE_TIME,
    FALL_PERSISTENCE_TIME,
    FALL_MODEL_CONFIDENCE_THRESHOLD,
    RESTRICTED_ZONE_ENABLED,
    RESTRICTED_ZONE_MIN_DWELL,
    FIGHT_DETECTION_ENABLED,
    FIGHT_PROXIMITY_PX,
    FIGHT_MIN_PAIR_SPEED,
    FIGHT_PERSISTENCE_TIME,
    FIGHT_MIN_HIT_STREAK,
    LOITERING_ENABLED,
    LOITERING_TIME_THRESHOLD,
    LOITERING_RADIUS_PX,
    RESTRICTED_ZONES,
    FRAME_WIDTH,
    FRAME_HEIGHT,
    STREAM_FRAME_WIDTH,
    STREAM_FRAME_HEIGHT,
    STREAM_TARGET_FPS,
    STREAM_DETECTION_CONFIDENCE,
    VIDEO_DETECTION_CONFIDENCE,
    WEBCAM_DETECTION_CONFIDENCE,
    TRACKER_MIN_HITS,
    INFER_WIDTH,
    INFER_HEIGHT,
    MAX_AGE,
    IOU_THRESHOLD,
    ALERT_ESCALATION_SECS,
)
from backend.config import (
    PPE_DETECTION_ENABLED,
    PPE_CONFIDENCE_THRESHOLD,
    FACE_DETECTION_ENABLED,
    FACE_SCALE_FACTOR,
    FACE_MIN_NEIGHBORS,
    LPR_DETECTION_ENABLED,
    LPR_CONFIDENCE_THRESHOLD,
)
from backend.detector import (
    _download_model,
    is_model_ready,
    get_model_error,
    get_loading_progress as _yolo_progress,
)
from backend.fall_detector import (
    _download_fall_model,
    detect_falls,
    get_fall_model_error,
    is_fall_model_ready,
    get_fall_loading_progress as _fall_progress,
)
from backend.ppe_detector import (
    _download_ppe_model,
    detect_ppe,
    is_ppe_model_ready,
    get_ppe_model_error,
    get_ppe_loading_progress as _ppe_progress,
)
from backend.face_detector import (
    _load_face_cascade,
    detect_faces as detect_faces_cv,
    is_face_model_ready,
    get_face_model_error,
)
from backend.lpr_detector import (
    _download_lpr_model,
    detect_plates,
    is_lpr_model_ready,
    get_lpr_model_error,
    get_lpr_loading_progress as _lpr_progress,
)

# ─── Global State ─────────────────────────────────────────────────────────────

alert_history: deque = deque(maxlen=500)
connected_clients: set[WebSocket] = set()

_WS_MAX_MSG_BYTES = 1 * 1024 * 1024  # 1 MB cap per WebSocket message
_ALERT_COOLDOWN_SECS = 5.0

# Informational detection types: still recorded to the alert log / history so
# the operator can review them, but they are NOT security incidents. Face and
# plate detections fire on virtually every frame, so emailing or escalating
# them would bury genuine safety alerts (falls, fights, restricted-zone,
# PPE violations) and spam the operator's inbox. Manual snapshots are operator
# actions, not incidents, so they should not escalate either.
_INFO_ALERT_TYPES = {"face_detected", "lpr_detected", "manual_snapshot"}

current_config = {
    "overcrowding_threshold": OVERCROWDING_THRESHOLD,
    "running_speed_threshold": RUNNING_SPEED_THRESHOLD,
    "unattended_object_time": UNATTENDED_OBJECT_TIME,
    "stationary_threshold": STATIONARY_THRESHOLD,
    "unattended_owner_proximity_px": UNATTENDED_OWNER_PROXIMITY_PX,
    "unattended_owner_grace_time": UNATTENDED_OWNER_GRACE_TIME,
    "fall_persistence_time": FALL_PERSISTENCE_TIME,
    "fall_model_confidence_threshold": FALL_MODEL_CONFIDENCE_THRESHOLD,
    "restricted_zone_enabled": RESTRICTED_ZONE_ENABLED,
    "restricted_zone_min_dwell": RESTRICTED_ZONE_MIN_DWELL,
    "fight_detection_enabled": FIGHT_DETECTION_ENABLED,
    "fight_proximity_px": FIGHT_PROXIMITY_PX,
    "fight_min_pair_speed": FIGHT_MIN_PAIR_SPEED,
    "fight_persistence_time": FIGHT_PERSISTENCE_TIME,
    "fight_min_hit_streak": FIGHT_MIN_HIT_STREAK,
    "alert_cooldown_secs": _ALERT_COOLDOWN_SECS,
    "loitering_enabled": LOITERING_ENABLED,
    "loitering_time_threshold": LOITERING_TIME_THRESHOLD,
    "loitering_radius_px": LOITERING_RADIUS_PX,
    # ── Tracker tuning (Phase B) ─────────────────────────────────────────────
    # Surfaced via /api/config so they can be tweaked without a restart.
    # Keys are lowercase versions of the actual cfg attribute name so
    # _apply_config's k.upper() round-trips correctly.
    "max_age": MAX_AGE,                          # cfg.MAX_AGE
    "iou_threshold": IOU_THRESHOLD,              # cfg.IOU_THRESHOLD
    "tracker_min_hits": TRACKER_MIN_HITS,        # cfg.TRACKER_MIN_HITS
    "object_track_hold_frames": 30,
    "baggage_strong_hold_frames": 120,
    "baggage_weak_hold_frames": 45,
    "baggage_strong_confidence": 0.20,
    "object_association_distance_px": 95.0,
    "fall_alert_hold_time": 3.0,
    "db_alert_retention": 5000,
    "alert_escalation_secs": ALERT_ESCALATION_SECS,
    # ── PPE / Face / LPR detection ──────────────────────────────────────────
    "ppe_detection_enabled": PPE_DETECTION_ENABLED,
    "ppe_confidence_threshold": PPE_CONFIDENCE_THRESHOLD,
    "face_detection_enabled": FACE_DETECTION_ENABLED,
    "face_scale_factor": FACE_SCALE_FACTOR,
    "face_min_neighbors": FACE_MIN_NEIGHBORS,
    "lpr_detection_enabled": LPR_DETECTION_ENABLED,
    "lpr_confidence_threshold": LPR_CONFIDENCE_THRESHOLD,
}

# Allowlist of cfg attribute names that _apply_config is permitted to write.
# Computed once at import time from the current_config keys plus the extra
# tunables added in the deep audit. Anything not on this list is rejected
# with a logged warning so typos cannot silently set unused attributes.
_CONFIG_ALLOWED_ATTRS = frozenset(
    [k.upper() for k in current_config.keys()] + [
        "RUNNING_BODY_HEIGHTS_PER_SEC",
        "RUNNING_PIXEL_FLOOR",
        "RUNNING_RESET_GRACE_TIME",
        "RUNNING_MIN_HIT_STREAK",
        "FALL_MIN_AREA_RATIO",
        "FALL_ASPECT_RATIO_MIN",
        "FALL_PERSON_IOU_MIN",
        "RESTRICTED_ZONE_USE_FEET",
        "UNATTENDED_BYSTANDER_ATTENDS",
        "UNATTENDED_GHOST_TTL",
        "UNATTENDED_GHOST_CELL_PX",
        "OVERCROWDING_CLUSTER_DISTANCE_PX",
        "OVERCROWDING_MIN_CLUSTER_SIZE",
        "BAGGAGE_CONFIDENCE_FLOOR",
        "LOITERING_REANCHOR_FACTOR",
        "FIGHT_RESET_GRACE_TIME",
        # Phase B — tracker tuning + retention
        "OBJECT_TRACK_HOLD_FRAMES",
        "BAGGAGE_STRONG_HOLD_FRAMES",
        "BAGGAGE_WEAK_HOLD_FRAMES",
        "BAGGAGE_STRONG_CONFIDENCE",
        "OBJECT_ASSOCIATION_DISTANCE_PX",
        "FALL_ALERT_HOLD_TIME",
        "DB_ALERT_RETENTION",
        "ALERT_ESCALATION_SECS",
        # Phase 5 — PPE / Face / LPR
        "PPE_DETECTION_ENABLED",
        "PPE_CONFIDENCE_THRESHOLD",
        "FACE_DETECTION_ENABLED",
        "FACE_SCALE_FACTOR",
        "FACE_MIN_NEIGHBORS",
        "LPR_DETECTION_ENABLED",
        "LPR_CONFIDENCE_THRESHOLD",
    ]
)

stats_snapshot = {
    "person_count": 0,
    "object_count": 0,
    "anomaly_count": 0,
    "fps": 0,
    "uptime_seconds": 0,
}

_start_time = time.time()
_frame_times: deque = deque(maxlen=30)
_alert_cooldowns: dict = {}
_COOLDOWN_MAX_AGE = 300.0  # seconds — entries older than this are evicted
_email_cooldowns: dict = {}
# Set of alert IDs that have already been escalated (emailed + flagged).
# Cleared on /api/alerts/clear so a fresh session starts clean.
_escalated_alert_ids: set[int] = set()
_escalation_email_cooldowns: dict = {}
_EMAIL_COOLDOWN_SECS = float(os.environ.get("ALERT_EMAIL_COOLDOWN_SECS", "45"))
_ALERT_EMAIL_TO = os.environ.get("ALERT_EMAIL_TO", "2022a1r090@mietjammu.in")
_ALERT_EMAIL_FROM = os.environ.get("ALERT_EMAIL_FROM", _ALERT_EMAIL_TO).strip()
_EMAIL_COOLDOWN_PATH = os.path.join(tempfile.gettempdir(), "crowdlens_email_cooldowns.json")
_EMAIL_COOLDOWN_LOCK_PATH = f"{_EMAIL_COOLDOWN_PATH}.lock"
_AWS_CLI_BIN = (
    os.environ.get("AWS_CLI_BIN", "").strip()
    or shutil.which("aws")
    or r"C:\Program Files\Amazon\AWSCLIV2\aws.exe"
)
_email_metrics = {
    "attempts": 0,
    "sent": 0,
    "suppressed": 0,
    "failed": 0,
    "last_error": None,
    "last_message_id": None,
    "last_attempt_at": None,
    "last_sent_at": None,
}

# Thread pool for async DB writes — avoids spawning a new thread per alert.
_db_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="crowdlens_db")
_notify_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="crowdlens_notify")
_alert_id_counter = 0
_archive_dir = os.path.join(os.path.dirname(__file__), "archive")
_archive_retention_seconds = 7 * 24 * 60 * 60
_last_archive_cleanup = 0.0
_latest_frame_for_snapshot = None

os.makedirs(_archive_dir, exist_ok=True)

# ─── Processing mode state ────────────────────────────────────────────────────
# Modes: "idle" | "video" | "webcam" | "stream"

VIDEO_UPLOAD_PATH = os.path.join(tempfile.gettempdir(), "crowdlens_upload.mp4")
_processing_mode = "idle"
_active_task: asyncio.Task | None = None
# Note: _video_anomaly_detector is intentionally NOT a module-level singleton
# anymore. video_processing_loop, stream_processing_loop, and
# webcam_processing_loop each construct their own AnomalyDetector so per-loop
# state (track history, ghost cache, fall persistence buckets) cannot bleed
# across modes. Previously a stale stream loop could mutate the same instance
# the new mode just reset to.

# Lock that protects _latest_frame_for_snapshot from racing reads/writes
# between the active processing loop (writer) and POST /api/archive/capture
# (reader). Without this, capture can observe a torn frame mid-copy.
_snapshot_frame_lock = threading.Lock()

video_status = {
    "mode": "idle",
    "filename": None,
    "progress": 0.0,
    "total_frames": 0,
    "current_frame": 0,
    "error": None,
}

stream_status = {
    "active": False,
    "url": None,
    "error": None,
}

webcam_status = {
    "active": False,
    "error": None,
}

# Shared queue for webcam frames arriving over WebSocket
_cam_frame_queue: asyncio.Queue = asyncio.Queue(maxsize=4)


# ─── Helpers ──────────────────────────────────────────────────────────────────


def _get_zone(cx: float, frame_width: int) -> str:
    if cx < frame_width / 3:
        return "A"
    if cx < 2 * frame_width / 3:
        return "B"
    return "C"


def _redact_url(url: str | None) -> str | None:
    """Replace the password component of a URL with '***'.

    Used to strip credentials from logs and from any payload that flows back
    to the frontend (e.g. ``stream_status["url"]``). The username, scheme,
    host, port, path, and query are preserved so the operator can still
    recognise their own stream configuration in the UI / log output. URLs
    without credentials pass through unchanged.

    Examples
    --------
    >>> _redact_url("rtsp://admin:secret@cam.example.com/stream")
    'rtsp://admin:***@cam.example.com/stream'
    >>> _redact_url("http://192.168.1.10:4747/video")
    'http://192.168.1.10:4747/video'
    >>> _redact_url(None)
    None
    """
    if not url:
        return url
    try:
        parsed = urlsplit(url)
    except ValueError:
        return url
    if parsed.password is None:
        return url
    user = parsed.username or ""
    # Reassemble. urlsplit/SplitResult is read-only, so build the netloc by hand.
    host = parsed.hostname or ""
    port = f":{parsed.port}" if parsed.port else ""
    netloc = f"{user}:***@{host}{port}" if user else f":***@{host}{port}"
    return f"{parsed.scheme}://{netloc}{parsed.path}" + (
        f"?{parsed.query}" if parsed.query else ""
    ) + (f"#{parsed.fragment}" if parsed.fragment else "")


def _evict_stale_cooldowns(now: float) -> None:
    """Remove cooldown entries older than _COOLDOWN_MAX_AGE to bound dict size."""
    if len(_alert_cooldowns) < 500:
        return
    stale = [k for k, t in _alert_cooldowns.items() if now - t > _COOLDOWN_MAX_AGE]
    for k in stale:
        _alert_cooldowns.pop(k, None)


def _should_record_alert(anomaly: dict, now: float) -> bool:
    _evict_stale_cooldowns(now)
    track_id = anomaly.get("track_id")
    if track_id is not None:
        key = (anomaly.get("type"), track_id)
    else:
        # For model-only falls or alerts without track IDs, avoid over-grouping
        # all events under a single cooldown bucket.
        pos = anomaly.get("position") or [0, 0]
        cell_x = int(float(pos[0]) // 120)
        cell_y = int(float(pos[1]) // 120)
        key = (anomaly.get("type"), anomaly.get("note"), cell_x, cell_y)
    if now - _alert_cooldowns.get(key, 0) >= _ALERT_COOLDOWN_SECS:
        _alert_cooldowns[key] = now
        return True
    return False


def _should_send_email(entry: dict, now: float) -> bool:
    anomaly = entry.get("anomaly", {}) if isinstance(entry, dict) else {}
    alert_type = str(anomaly.get("type", "unknown"))
    source = str(entry.get("source", "unknown"))
    # Keep dedupe coarse and stable so one real-world incident does not spam
    # email because of track-id swaps, bbox jitter, or multiple backend processes.
    key = f"{_ALERT_EMAIL_TO}|{source}|{alert_type}"

    lock_fd = None
    lock_started = time.time()
    while lock_fd is None:
        try:
            lock_fd = os.open(
                _EMAIL_COOLDOWN_LOCK_PATH,
                os.O_CREAT | os.O_EXCL | os.O_RDWR,
            )
        except FileExistsError:
            try:
                if time.time() - os.path.getmtime(_EMAIL_COOLDOWN_LOCK_PATH) > 10:
                    os.unlink(_EMAIL_COOLDOWN_LOCK_PATH)
                    continue
            except FileNotFoundError:
                continue
            if time.time() - lock_started > 3:
                # Don't drop the email silently — surface the cause via metrics
                # and a log line so a wedged lock can be diagnosed.
                _email_metrics["suppressed"] += 1
                _email_metrics["last_error"] = (
                    f"email lockfile contention (>3 s waiting on "
                    f"{_EMAIL_COOLDOWN_LOCK_PATH}); alert "
                    f"{alert_type}/{source} dropped"
                )
                print(f"[notify-email] {_email_metrics['last_error']}")
                return False
            time.sleep(0.02)

    try:
        shared_cooldowns = {}
        try:
            with open(_EMAIL_COOLDOWN_PATH, "r", encoding="utf-8") as f:
                shared_cooldowns = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            shared_cooldowns = {}

        # Drop old keys so the local demo file does not grow forever.
        max_age = max(_EMAIL_COOLDOWN_SECS * 4, 300.0)
        shared_cooldowns = {
            k: float(v)
            for k, v in shared_cooldowns.items()
            if now - float(v) <= max_age
        }

        last = float(shared_cooldowns.get(key, 0.0))
        if now - last < _EMAIL_COOLDOWN_SECS:
            _email_cooldowns[key] = last
            _email_metrics["suppressed"] += 1
            return False

        shared_cooldowns[key] = now
        _email_cooldowns[key] = now
        with open(_EMAIL_COOLDOWN_PATH, "w", encoding="utf-8") as f:
            json.dump(shared_cooldowns, f)
        return True
    finally:
        if lock_fd is not None:
            try:
                os.close(lock_fd)
            except Exception:
                pass
        try:
            os.unlink(_EMAIL_COOLDOWN_LOCK_PATH)
        except FileNotFoundError:
            pass


def _send_alert_email_sync(entry: dict) -> None:
    _email_metrics["attempts"] += 1
    _email_metrics["last_attempt_at"] = time.time()
    if not _ALERT_EMAIL_TO or not _ALERT_EMAIL_FROM:
        _email_metrics["failed"] += 1
        _email_metrics["last_error"] = "email from/to not configured"
        return
    if not _AWS_CLI_BIN or not os.path.exists(_AWS_CLI_BIN):
        print("[notify-email] aws cli binary not found; set AWS_CLI_BIN env var.")
        _email_metrics["failed"] += 1
        _email_metrics["last_error"] = "aws cli binary not found"
        return
    anomaly = entry.get("anomaly", {})
    alert_type = str(anomaly.get("type", "alert")).replace("_", " ").title()
    severity = "HIGH" if anomaly.get("type") in {"fall_detected", "fight_suspected", "restricted_zone", "ppe_violation"} else "MEDIUM"
    subject = f"[CrowdLens Campus Alert] {alert_type} - {severity}"
    position = anomaly.get("position")
    details = []
    if anomaly.get("track_id") is not None:
        details.append(f"Track ID: #{anomaly.get('track_id')}")
    if position:
        details.append(f"Position: ({int(position[0])}, {int(position[1])})")
    details.append(f"Source: {str(entry.get('source', 'unknown')).upper()}")
    details.append(f"Time (UTC): {entry.get('iso', '')}")
    if entry.get("id") is not None:
        details.append(f"Alert ID: {entry.get('id')}")

    body = (
        "CrowdLens Campus AI Monitor - Alert Notification\n\n"
        f"Alert Type : {alert_type}\n"
        f"Severity   : {severity}\n"
        + "\n".join(details)
        + "\n\nThis is an automated notification from your CrowdLens project."
    )
    html_items = "".join([f"<li>{d}</li>" for d in details])
    html_body = f"""
    <html>
      <body style="font-family: Arial, sans-serif; color:#111827;">
        <div style="max-width:640px; margin:0 auto; border:1px solid #e5e7eb; border-radius:12px; overflow:hidden;">
          <div style="background:#0f172a; color:white; padding:14px 18px; font-size:18px; font-weight:700;">
            CrowdLens Campus AI Monitor
          </div>
          <div style="padding:18px;">
            <p style="margin:0 0 8px 0; font-size:16px;"><strong>Alert:</strong> {alert_type}</p>
            <p style="margin:0 0 14px 0; font-size:15px;"><strong>Severity:</strong> {severity}</p>
            <ul style="padding-left:18px; margin:0 0 14px 0;">
              {html_items}
            </ul>
            <p style="margin:0; color:#4b5563; font-size:13px;">
              This is an automated notification from your CrowdLens project.
            </p>
          </div>
        </div>
      </body>
    </html>
    """.strip()
    payload = {
        "FromEmailAddress": _ALERT_EMAIL_FROM,
        "Destination": {"ToAddresses": [_ALERT_EMAIL_TO]},
        "Content": {
            "Simple": {
                "Subject": {"Data": subject, "Charset": "UTF-8"},
                "Body": {
                    "Text": {"Data": body, "Charset": "UTF-8"},
                    "Html": {"Data": html_body, "Charset": "UTF-8"},
                },
            }
        },
    }
    with tempfile.NamedTemporaryFile(delete=False, suffix=".json", mode="w", encoding="utf-8") as tmp:
        json.dump(payload, tmp)
        payload_path = tmp.name
    try:
        result = subprocess.run(
            [_AWS_CLI_BIN, "sesv2", "send-email", "--region", "us-east-1", "--cli-input-json", f"file://{payload_path}"],
            check=True,
            capture_output=True,
            text=True,
            timeout=15,
        )
        if result.stdout:
            print(f"[notify-email] sent: {result.stdout.strip()}")
            try:
                out = json.loads(result.stdout)
                _email_metrics["last_message_id"] = out.get("MessageId")
            except Exception:
                pass
        _email_metrics["sent"] += 1
        _email_metrics["last_sent_at"] = time.time()
        _email_metrics["last_error"] = None
    except Exception as e:
        print(f"[notify-email] send failed: {e}")
        _email_metrics["failed"] += 1
        _email_metrics["last_error"] = str(e)
    finally:
        try:
            os.unlink(payload_path)
        except Exception:
            pass


def _queue_alert_email(entry: dict, now: float) -> None:
    atype = str(entry.get("anomaly", {}).get("type", ""))
    if atype in _INFO_ALERT_TYPES:
        # Informational detections never trigger email notifications.
        return
    if not _should_send_email(entry, now):
        return
    _notify_executor.submit(_send_alert_email_sync, entry)


def _email_status_payload() -> dict:
    return {
        **_email_metrics,
        "to": _ALERT_EMAIL_TO,
        "from": _ALERT_EMAIL_FROM,
        "cooldown_seconds": _EMAIL_COOLDOWN_SECS,
    }


def _reset_fps_window():
    """Reset rolling FPS window and live counters when switching source modes."""
    _frame_times.clear()
    stats_snapshot.update(
        {
            "person_count": 0,
            "object_count": 0,
            "anomaly_count": 0,
            "fps": 0,
            "uptime_seconds": round(time.time() - _start_time),
        }
    )


def _cleanup_archive(now: float):
    """Delete old snapshot files to keep archive bounded for local demo use."""
    global _last_archive_cleanup
    if now - _last_archive_cleanup < 3600:
        return
    _last_archive_cleanup = now

    try:
        for fn in os.listdir(_archive_dir):
            p = os.path.join(_archive_dir, fn)
            try:
                if (
                    os.path.isfile(p)
                    and now - os.path.getmtime(p) > _archive_retention_seconds
                ):
                    os.unlink(p)
            except Exception:
                continue
    except Exception:
        pass


def _save_archive_snapshot(frame, now: float) -> str | None:
    """Persist a JPEG snapshot for incident evidence and return a fetchable URL."""
    try:
        import cv2

        _cleanup_archive(now)
        ts = time.strftime("%Y%m%d_%H%M%S", time.localtime(now))
        ms = int((now - int(now)) * 1000)
        filename = f"alert_{ts}_{ms:03d}.jpg"
        path = os.path.join(_archive_dir, filename)
        # Keep evidence readable while controlling disk footprint.
        snapshot = frame
        h, w = snapshot.shape[:2]
        if w > 1280:
            scale = 1280 / max(1, w)
            snapshot = cv2.resize(snapshot, (1280, int(h * scale)))
        ok = cv2.imwrite(path, snapshot, [cv2.IMWRITE_JPEG_QUALITY, 82])
        if not ok:
            return None
        return f"/api/archive/image/{filename}"
    except Exception:
        return None


def build_frame_payload(
    tracks: list,
    anomalies: list,
    now: float,
    mode: str | None = None,
    frame_for_archive=None,
) -> dict:
    global _latest_frame_for_snapshot
    # Exclude tracks the SORT tracker is "predicting" (held over after the
    # detection has gone away). Without this filter the PERSONS card would
    # count up to MAX_AGE = 30 frames worth of phantom people after they
    # leave the frame, briefly inflating the live occupancy number.
    person_count = sum(1 for t in tracks if t["class_id"] == 0 and not t.get("predicted"))
    object_count = sum(1 for t in tracks if t["class_id"] != 0 and not t.get("predicted"))

    _frame_times.append(now)
    fps = 0
    if len(_frame_times) >= 2:
        elapsed = _frame_times[-1] - _frame_times[0]
        fps = round((len(_frame_times) - 1) / elapsed) if elapsed > 0 else 0

    stats_snapshot.update(
        {
            "person_count": person_count,
            "object_count": object_count,
            "anomaly_count": len(anomalies),
            "fps": fps,
            "uptime_seconds": round(now - _start_time),
        }
    )

    serializable_anomalies = []
    for a in anomalies:
        sa = dict(a)
        if sa.get("position") is not None:
            pos = sa["position"]
            sa["position"] = [float(pos[0]), float(pos[1])]
        serializable_anomalies.append(sa)

    global _alert_id_counter
    effective_mode = mode or _processing_mode
    recordable_anomalies = [
        a for a in serializable_anomalies if _should_record_alert(a, now)
    ]
    if frame_for_archive is not None:
        with _snapshot_frame_lock:
            _latest_frame_for_snapshot = frame_for_archive.copy()
    snapshot_url = None
    if recordable_anomalies and frame_for_archive is not None:
        snapshot_url = _save_archive_snapshot(frame_for_archive, now)

    for a in recordable_anomalies:
        _alert_id_counter += 1
        entry = {
            "id": _alert_id_counter,
            "anomaly": a,
            "timestamp": now,
            "iso": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now)),
            "source": effective_mode,
            "snapshot_url": snapshot_url,
            "acked": 0,
            "acked_at": None,
            "escalated": False,
        }
        alert_history.append(entry)
        _db_executor.submit(_db._insert_alert_sync, entry)
        _queue_alert_email(entry, now)

    return {
        "tracks": tracks,
        "anomalies": serializable_anomalies,
        "stats": stats_snapshot.copy(),
        "timestamp": now,
        "mode": effective_mode,
    }


def _apply_config() -> list[str]:
    """Push current_config values into backend.config module attributes.

    Validates every key against a known allowlist so a typo in current_config
    or a stray key from a /api/config PUT cannot silently set a nonexistent
    cfg attribute (which previously did nothing useful but masked real bugs).

    Returns the list of unknown keys that were ignored. Callers that handle
    a user-facing PUT can include this list in their response so the user
    sees the typo in the API response rather than only in the server log.
    """
    import backend.config as cfg

    unknown: list[str] = []
    for k, v in current_config.items():
        attr = k.upper()
        if attr not in _CONFIG_ALLOWED_ATTRS:
            print(f"[config] ignoring unknown config key: {k!r}")
            unknown.append(k)
            continue
        setattr(cfg, attr, v)
    return unknown


def _release_gpu_memory() -> None:
    """Release CUDA cached memory after a processing loop ends.

    Each mode (video / stream / webcam) constructs its own YOLOv8Detector
    proxy, but the underlying _model and CUDA tensors live in module-level
    state inside detector.py. Without an explicit cache empty between mode
    switches, long sessions can creep on VRAM as activations from previous
    inference passes are held by PyTorch's allocator.
    """
    try:
        import torch
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
    except Exception:
        # Never let GPU cleanup take down the API; missing CUDA, missing
        # torch in some environments, etc. should all silently no-op.
        pass


def _build_tracker():
    """Construct a Sort instance using live current_config values.

    Centralised so the 5 mode-specific processing loops all pick up runtime
    config changes (PUT /api/config) without each loop re-reading the same
    config keys. The Sort instance is per-session: it captures these at
    construction, so changes only take effect at the next start.
    """
    from backend.sort_tracker import Sort
    return Sort(
        max_age=int(current_config.get("max_age", MAX_AGE)),
        min_hits=int(current_config.get("tracker_min_hits", TRACKER_MIN_HITS)),
        iou_threshold=float(current_config.get("iou_threshold", IOU_THRESHOLD)),
    )


async def _broadcast(message: str):
    dead = []
    for ws in list(connected_clients):  # snapshot: avoid RuntimeError if set mutates during await
        try:
            await ws.send_text(message)
        except Exception:
            dead.append(ws)
    for d in dead:
        connected_clients.discard(d)


async def _cancel_active():
    global _active_task, _latest_frame_for_snapshot
    task = _active_task
    _active_task = None
    if task and not task.done():
        task.cancel()
        try:
            await asyncio.wait_for(task, timeout=2.0)
        except (asyncio.CancelledError, asyncio.TimeoutError):
            pass
        except Exception:
            pass
    # Clear the snapshot frame buffer when the active loop is cancelled so
    # /api/archive/capture cannot return a stale frame from a previous mode
    # (could be hours old after the user goes idle and comes back).
    with _snapshot_frame_lock:
        _latest_frame_for_snapshot = None
    # Free CUDA cached memory between mode switches so long sessions do not
    # accumulate VRAM that PyTorch's allocator would otherwise hold for reuse.
    _release_gpu_memory()


def _build_tracks_from_yolo(
    raw_tracks: list, frame_width: int, frame_height: int
) -> list:
    # Scale bbox coordinates from inference resolution to the fixed 1280×720 canvas
    # space so the frontend always receives consistent coordinates regardless of
    # what resolution YOLO inference was run at.
    scale_x = FRAME_WIDTH / max(1, frame_width)
    scale_y = FRAME_HEIGHT / max(1, frame_height)
    tracks = []
    for t in raw_tracks:
        rx1, ry1, rx2, ry2 = t["bbox"]
        x1 = max(0, int(rx1 * scale_x))
        y1 = max(0, int(ry1 * scale_y))
        x2 = min(FRAME_WIDTH, int(rx2 * scale_x))
        y2 = min(FRAME_HEIGHT, int(ry2 * scale_y))
        cx = (x1 + x2) / 2
        tracks.append(
            {
                "id": t["id"],
                "x1": x1,
                "y1": y1,
                "x2": x2,
                "y2": y2,
                "class_id": t["class_id"],
                "class_name": COCO_CLASSES.get(t["class_id"], "object"),
                "running": False,
                "confidence": round(t.get("confidence", 0), 2),
                "zone": _get_zone(cx, FRAME_WIDTH),
                "hit_streak": int(t.get("hit_streak", 0)),
                "hits": int(t.get("hits", 0)),
                "time_since_update": int(t.get("time_since_update", 0)),
                "predicted": bool(t.get("predicted", False)),
                "frame_width": FRAME_WIDTH,
                "frame_height": FRAME_HEIGHT,
            }
        )
    return tracks


def _scale_fall_detections_to_canvas(
    fall_detections: list[dict], frame_width: int, frame_height: int
) -> list[dict]:
    """Scale fall detector boxes to the same 1280x720 canvas as person tracks."""
    scale_x = FRAME_WIDTH / max(1, frame_width)
    scale_y = FRAME_HEIGHT / max(1, frame_height)
    scaled: list[dict] = []
    for d in fall_detections:
        x1, y1, x2, y2 = d.get("bbox", [0, 0, 0, 0])
        sx1 = max(0, int(float(x1) * scale_x))
        sy1 = max(0, int(float(y1) * scale_y))
        sx2 = min(FRAME_WIDTH, int(float(x2) * scale_x))
        sy2 = min(FRAME_HEIGHT, int(float(y2) * scale_y))
        if sx2 <= sx1 or sy2 <= sy1:
            continue
        nd = dict(d)
        nd["bbox"] = [sx1, sy1, sx2, sy2]
        scaled.append(nd)
    return scaled


def _finalize_tracks(tracks: list, anomalies: list) -> list:
    running_ids = {a.get("track_id") for a in anomalies if a["type"] == "running"}
    for t in tracks:
        t["running"] = t["id"] in running_ids
    return tracks


def _run_extra_detectors_sync(frame) -> dict:
    """Run PPE / face / LPR detectors on a frame. Returns dict of results.

    Called from thread pool executor so each detector can block without
    stalling the asyncio event loop. Only enabled detectors are invoked.
    """
    results: dict = {"ppe": [], "faces": [], "plates": []}

    if current_config.get("ppe_detection_enabled") and is_ppe_model_ready():
        conf = float(current_config.get("ppe_confidence_threshold", 0.40))
        results["ppe"] = detect_ppe(frame, conf_override=conf)

    if current_config.get("face_detection_enabled") and is_face_model_ready():
        scale = float(current_config.get("face_scale_factor", 1.3))
        neighbors = int(current_config.get("face_min_neighbors", 5))
        results["faces"] = detect_faces_cv(frame, scale_factor=scale, min_neighbors=neighbors)

    if current_config.get("lpr_detection_enabled") and is_lpr_model_ready():
        conf = float(current_config.get("lpr_confidence_threshold", 0.40))
        results["plates"] = detect_plates(frame, conf_override=conf)

    return results


def _build_extra_anomalies(extra: dict, frame_width: int, frame_height: int) -> list[dict]:
    """Convert PPE/face/LPR detections into anomaly dicts for the alert pipeline.

    Scales bboxes to the canonical 1280x720 canvas space.
    """
    anomalies: list[dict] = []
    scale_x = FRAME_WIDTH / max(1, frame_width)
    scale_y = FRAME_HEIGHT / max(1, frame_height)

    # PPE violations: only "NO-Hardhat" detections trigger an alert
    for det in extra.get("ppe", []):
        label = det.get("label", "")
        if "no" in label.lower():
            x1, y1, x2, y2 = det["bbox"]
            sx1 = int(x1 * scale_x)
            sy1 = int(y1 * scale_y)
            sx2 = int(x2 * scale_x)
            sy2 = int(y2 * scale_y)
            cx = (sx1 + sx2) / 2.0
            cy = (sy1 + sy2) / 2.0
            anomalies.append({
                "type": "ppe_violation",
                "ppe_label": label,
                "confidence": det["confidence"],
                "position": [cx, cy],
                "bbox": [sx1, sy1, sx2, sy2],
            })

    # Face detections
    for det in extra.get("faces", []):
        x1, y1, x2, y2 = det["bbox"]
        sx1 = int(x1 * scale_x)
        sy1 = int(y1 * scale_y)
        sx2 = int(x2 * scale_x)
        sy2 = int(y2 * scale_y)
        cx = (sx1 + sx2) / 2.0
        cy = (sy1 + sy2) / 2.0
        anomalies.append({
            "type": "face_detected",
            "confidence": det["confidence"],
            "position": [cx, cy],
            "bbox": [sx1, sy1, sx2, sy2],
        })

    # License plate detections
    for det in extra.get("plates", []):
        x1, y1, x2, y2 = det["bbox"]
        sx1 = int(x1 * scale_x)
        sy1 = int(y1 * scale_y)
        sx2 = int(x2 * scale_x)
        sy2 = int(y2 * scale_y)
        cx = (sx1 + sx2) / 2.0
        cy = (sy1 + sy2) / 2.0
        anomalies.append({
            "type": "lpr_detected",
            "confidence": det["confidence"],
            "position": [cx, cy],
            "bbox": [sx1, sy1, sx2, sy2],
        })

    return anomalies


def _encode_preview(frame) -> str:
    """Encode a cv2 frame as a base64 JPEG for WebSocket transmission."""
    import cv2

    h, w = frame.shape[:2]
    # Only resize if not already at the target resolution — avoids a redundant
    # copy when stream frames are already piped at 640×360.
    if w != 640 or h != 360:
        frame = cv2.resize(frame, (640, 360))
    _, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
    return base64.b64encode(buf.tobytes()).decode("ascii")


# ─── Video processing loop ────────────────────────────────────────────────────


async def video_processing_loop():
    """Process the uploaded video file and broadcast detection frames.

    Owns its own AnomalyDetector instance: the bag ghost cache, per-track
    history, and fall persistence buckets are loop-scoped so a stop/start
    cycle gets a clean slate, and a stream loop running concurrently (e.g.
    in error-recovery scenarios) cannot mutate this loop's state.
    """
    import cv2

    video_status["error"] = None

    try:
        from backend.detector import YOLOv8Detector
        from backend.sort_tracker import Sort
    except Exception as e:
        video_status["error"] = f"Failed to load detector: {e}"
        return

    try:
        detector = YOLOv8Detector()
        tracker = _build_tracker()
        anomaly_detector = AnomalyDetector()
    except Exception as e:
        video_status["error"] = f"Detector init failed: {e}"
        return

    cap = cv2.VideoCapture(VIDEO_UPLOAD_PATH)
    if not cap.isOpened():
        video_status["error"] = "Could not open video file"
        return

    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    native_fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    native_fps = max(1.0, min(60.0, native_fps))
    frame_interval = 1.0 / native_fps

    video_status["total_frames"] = total
    frame_num = 0
    loop = asyncio.get_event_loop()

    # Wall-clock anchor for playback pacing
    playback_start = time.time()

    def _detect_sync(f):
        return detector.detect(f, conf_override=VIDEO_DETECTION_CONFIDENCE)

    def _fall_detect_sync(f):
        return detect_falls(
            f, conf_override=current_config["fall_model_confidence_threshold"]
        )

    try:
        while True:
            ret, frame = cap.read()
            if not ret:
                # Loop the video back to the start
                cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                frame_num = 0
                tracker.reset()
                anomaly_detector = AnomalyDetector()
                playback_start = time.time()
                continue

            frame_num += 1
            video_status["current_frame"] = frame_num
            video_status["progress"] = (
                round((frame_num / total * 100), 1) if total > 0 else 0
            )

            # Target wall-clock time for this frame based on native video FPS
            target_time = playback_start + frame_num * frame_interval
            now = time.time()
            drift = now - target_time

            # If we are running behind by more than one frame interval,
            # skip this frame (grab-only, no decode cost) to catch up.
            if drift > frame_interval:
                frames_to_skip = min(int(drift / frame_interval), 15)
                for _ in range(frames_to_skip):
                    if not cap.grab():
                        break
                    frame_num += 1
                video_status["current_frame"] = frame_num
                video_status["progress"] = (
                    round((frame_num / total * 100), 1) if total > 0 else 0
                )
                await asyncio.sleep(0)
                continue

            # Wait until it is time to display this frame
            wait = target_time - time.time()
            if wait > 0.001:
                await asyncio.sleep(wait)

            frame_resized = cv2.resize(frame, (INFER_WIDTH, INFER_HEIGHT))

            # Run YOLO in thread pool — keeps the asyncio event loop responsive
            detections = await loop.run_in_executor(None, _detect_sync, frame_resized)
            # Run fall model on source-resolution frame for better posture fidelity.
            fall_detections = await loop.run_in_executor(
                None, _fall_detect_sync, frame
            )
            fall_detections = _scale_fall_detections_to_canvas(
                fall_detections, frame.shape[1], frame.shape[0]
            )
            raw_tracks = tracker.update(detections)

            now = time.time()
            tracks = _build_tracks_from_yolo(raw_tracks, INFER_WIDTH, INFER_HEIGHT)
            anomalies = anomaly_detector.update(
                tracks,
                now,
                fall_detections=fall_detections,
                fall_persistence_time=current_config["fall_persistence_time"],
            )
            # PPE / Face / LPR detections (run in thread pool)
            extra = await loop.run_in_executor(
                None, _run_extra_detectors_sync, frame_resized
            )
            anomalies.extend(
                _build_extra_anomalies(extra, INFER_WIDTH, INFER_HEIGHT)
            )
            tracks = _finalize_tracks(tracks, anomalies)

            payload = build_frame_payload(
                tracks, anomalies, now, "video", frame_for_archive=frame_resized
            )
            payload["frame_jpeg"] = _encode_preview(frame_resized)
            if connected_clients:
                await _broadcast(json.dumps(payload))

            await asyncio.sleep(0)

    except asyncio.CancelledError:
        pass
    except Exception as e:
        # Surface unexpected failures (decode errors, OOM, etc.) instead of
        # dying as an unretrieved task exception that leaves the UI stuck on
        # "Video Running". Flipping mode off "processing" lets the frontend
        # status poll auto-reset to idle.
        video_status["error"] = f"Video processing stopped unexpectedly: {e}"
        video_status["mode"] = "ready"
        print(f"[video] processing loop error: {e}")
    finally:
        cap.release()
        video_status["progress"] = 0


# ─── Stream processing loop (RTSP / HTTP / IP camera) ─────────────────────────


async def stream_processing_loop(url: str):
    """Use an FFmpeg subprocess to pipe raw BGR frames.

    Advantages over cv2.VideoCapture(url):
    - Handles HTTP MP4 progressive downloads correctly (loops when finished)
    - Works for MJPEG HTTP streams, HLS, and most container formats
    - Gives readable stderr so we can surface a clear error for blocked ports

    Owns its own AnomalyDetector instance for the same isolation reason as
    video_processing_loop: ghost cache, fall persistence, and track history
    must not bleed across modes.
    """
    import subprocess
    from urllib.parse import urlsplit
    from urllib.request import Request, urlopen

    # Stream decode/render dimensions (tuned for real-time laptop inference).
    W, H = STREAM_FRAME_WIDTH, STREAM_FRAME_HEIGHT
    FRAME_BYTES = W * H * 3

    stream_status["error"] = None
    stream_status["active"] = True

    try:
        from backend.detector import YOLOv8Detector
        from backend.sort_tracker import Sort
    except Exception as e:
        stream_status["error"] = f"Failed to load detector: {e}"
        stream_status["active"] = False
        return

    try:
        detector = YOLOv8Detector()
        tracker = _build_tracker()
        anomaly_detector = AnomalyDetector()
    except Exception as e:
        stream_status["error"] = f"Detector init failed: {e}"
        stream_status["active"] = False
        return

    # Write FFmpeg stderr to a temp file to avoid pipe deadlock
    # (stderr fills the pipe buffer -> FFmpeg blocks -> stdout stalls).
    # mkstemp atomically creates the file (unlike the deprecated mktemp).
    _stderr_fd, _stderr_path = tempfile.mkstemp(suffix=".ffmpeg_err.txt")
    os.close(_stderr_fd)
    downloaded_file_path: str | None = None
    source_input = url
    tried_http_file_fallback = False

    # Target output rate from ffmpeg. Keep this conservative on CPU.
    STREAM_FPS = STREAM_TARGET_FPS
    STREAM_CONFIDENCE = max(0.01, min(0.99, STREAM_DETECTION_CONFIDENCE))
    FIRST_FRAME_TIMEOUT_SECS = 30
    REMOTE_FILE_MAX_BYTES = 750 * 1024 * 1024
    REMOTE_FILE_EXTENSIONS = {".mp4", ".mov", ".mkv", ".avi", ".webm", ".m4v"}

    def _is_http_file_source(u: str) -> bool:
        parsed = urlsplit(u)
        if parsed.scheme.lower() not in {"http", "https"}:
            return False
        p = parsed.path.lower()
        # DroidCam uses /video path which is a live stream, not a file
        if "/video" in p or "/mjpeg" in p or "/stream" in p:
            return False
        return any(p.endswith(ext) for ext in REMOTE_FILE_EXTENSIONS)

    def _download_http_file(u: str) -> str:
        parsed = urlsplit(u)
        suffix = os.path.splitext(parsed.path)[1] or ".mp4"
        fd, tmp_path = tempfile.mkstemp(prefix="crowdlens_stream_", suffix=suffix)
        os.close(fd)
        req = Request(
            u,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0 Safari/537.36"
                ),
                "Accept": "*/*",
            },
        )
        total = 0
        with urlopen(req, timeout=30) as resp, open(tmp_path, "wb") as out:
            while True:
                chunk = resp.read(256 * 1024)
                if not chunk:
                    break
                total += len(chunk)
                if total > REMOTE_FILE_MAX_BYTES:
                    raise RuntimeError(
                        "Remote file is too large (max 750 MB for URL file fallback)"
                    )
                out.write(chunk)
        if total == 0:
            raise RuntimeError("Remote URL returned an empty file")
        return tmp_path

    def _build_cmd() -> list[str]:
        cmd = ["ffmpeg", "-y", "-loglevel", "error"]
        if source_input.lower().startswith("rtsp://"):
            # RTSP sources can hang and buffer deeply; use low-latency settings.
            # probesize: 131072 bytes (128 KB) — enough for H.264/H.265 codec
            #   detection from Hikvision, Dahua, Axis, and most campus cameras.
            #   32 bytes (old value) was too small and caused codec init failures.
            # analyzeduration: 2 s — gives SDP negotiation time to complete on
            #   cameras that are slow to send the first RTP packet.
            cmd += [
                "-fflags",
                "nobuffer",
                "-flags",
                "low_delay",
                "-analyzeduration",
                "2000000",
                "-probesize",
                "131072",
                "-rtsp_transport",
                "tcp",
                "-timeout",
                "10000000",
                "-rw_timeout",
                "10000000",
            ]
        elif source_input.lower().startswith(("http://", "https://")):
            # Detect potential DroidCam or MJPEG streams to force format
            is_mjpeg = "/video" in source_input.lower() or "mjpeg" in source_input.lower()
            if is_mjpeg:
                cmd += ["-f", "mjpeg"]

            cmd += [
                "-user_agent",
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "-timeout",
                "5000000",
                "-fflags",
                "nobuffer+genpts+igndts",
                "-flags",
                "low_delay",
                "-reconnect",
                "1",
                "-reconnect_streamed",
                "1",
                "-reconnect_on_network_error",
                "1",
                "-reconnect_at_eof",
                "1",
                "-reconnect_delay_max",
                "2",
                "-rw_timeout",
                "5000000",
                "-analyzeduration",
                "500000",
                "-probesize",
                "500000",
            ]
        cmd += [
            "-i",
            source_input,
            "-f",
            "rawvideo",
            "-pix_fmt",
            "bgr24",
            "-vsync",
            "drop",
            "-vf",
            f"scale={W}:{H},fps={STREAM_FPS}",
            "-",
        ]
        return cmd

    def _start_proc():
        stderr_fh = open(_stderr_path, "wb")
        # bufsize=-1 (default) wraps stdout in BufferedReader so that
        # read(n) returns exactly n bytes.
        return subprocess.Popen(
            _build_cmd(),
            stdout=subprocess.PIPE,
            stderr=stderr_fh,
        )

    def _read_exactly(pipe, n: int) -> bytes:
        """Read exactly n bytes from pipe, or fewer if the pipe closes."""
        buf = bytearray()
        while len(buf) < n:
            chunk = pipe.read(n - len(buf))
            if not chunk:
                break
            buf.extend(chunk)
        return bytes(buf)

    def _read_stderr() -> str:
        try:
            with open(_stderr_path, "r", errors="replace") as fh:
                return fh.read()
        except Exception:
            return ""

    def _start_reader(process):
        frame_q: queue.Queue = queue.Queue(maxsize=1)
        stop_evt = threading.Event()
        state = {"eof": False}

        def _reader():
            while not stop_evt.is_set():
                raw = _read_exactly(process.stdout, FRAME_BYTES)
                if len(raw) < FRAME_BYTES:
                    state["eof"] = True
                    break
                # Keep only the latest frame so inference does not drift behind live time.
                try:
                    frame_q.put_nowait(raw)
                except queue.Full:
                    try:
                        frame_q.get_nowait()
                    except queue.Empty:
                        pass
                    try:
                        frame_q.put_nowait(raw)
                    except queue.Full:
                        pass

        thread = threading.Thread(target=_reader, daemon=True)
        thread.start()
        return frame_q, stop_evt, thread, state

    def _stop_reader(stop_evt, thread_obj):
        if stop_evt is not None:
            stop_evt.set()
        if thread_obj is not None and thread_obj.is_alive():
            thread_obj.join(timeout=1.0)

    loop = asyncio.get_event_loop()
    proc = None
    frame_q = None
    reader_stop = None
    reader_thread = None
    reader_state = {"eof": False}

    try:
        proc = await loop.run_in_executor(None, _start_proc)
        frame_q, reader_stop, reader_thread, reader_state = _start_reader(proc)
        print(f"[stream] FFmpeg opened: {_redact_url(source_input)}")
        frames_processed = 0

        while True:
            timeout_secs = FIRST_FRAME_TIMEOUT_SECS if frames_processed == 0 else 30
            raw = None
            try:
                raw = await loop.run_in_executor(None, frame_q.get, True, timeout_secs)
            except queue.Empty:
                raw = None

            if raw is None:
                stderr_str = _read_stderr()
                low = stderr_str.lower()

                stream_ended = reader_state.get("eof") or (
                    proc is not None and proc.poll() is not None
                )

                if proc is not None and proc.poll() is None:
                    proc.kill()
                    proc.wait()
                _stop_reader(reader_stop, reader_thread)

                # Fallback: direct HTTP file URL can fail in ffmpeg network demux on some hosts.
                if (
                    frames_processed == 0
                    and not tried_http_file_fallback
                    and source_input == url
                    and _is_http_file_source(url)
                ):
                    tried_http_file_fallback = True
                    try:
                        downloaded_file_path = await loop.run_in_executor(
                            None, _download_http_file, url
                        )
                        source_input = downloaded_file_path
                        print(
                            f"[stream] Download fallback ready: {downloaded_file_path}"
                        )
                        tracker = _build_tracker()
                        anomaly_detector = AnomalyDetector()
                        frames_processed = 0
                        proc = await loop.run_in_executor(None, _start_proc)
                        frame_q, reader_stop, reader_thread, reader_state = (
                            _start_reader(proc)
                        )
                        print(f"[stream] FFmpeg opened: {_redact_url(source_input)}")
                        continue
                    except Exception as dl_err:
                        stream_status["error"] = (
                            f"Failed to download URL file: {dl_err}"
                        )
                        break

                if frames_processed == 0:
                    if source_input.lower().startswith("rtsp://"):
                        stream_status["error"] = (
                            "Timed out waiting for the first RTSP frame. "
                            "Check URL, credentials, camera reachability, and network/port access."
                        )
                    elif "connection to tcp://" in low or "error number -138" in low:
                        stream_status["error"] = (
                            "Network cannot reach this stream host/port from this machine. "
                            "Try another source or verify firewall/ISP/network access."
                        )
                    elif (
                        "403" in stderr_str
                        or "forbidden" in low
                        or "connection refused" in low
                    ):
                        stream_status["error"] = (
                            "Connection refused. For RTSP, verify camera reachability and port access; "
                            "otherwise try an HTTP/MJPEG/HLS URL."
                        )
                    elif "timed out" in low or "i/o timeout" in low:
                        stream_status["error"] = (
                            "Connection timed out before receiving frames. "
                            "Verify stream URL, credentials, and network access."
                        )
                    elif (
                        "nothing was written into output file" in low
                        or "received no packets" in low
                    ):
                        stream_status["error"] = (
                            "No video packets received from this URL. "
                            "Use a direct MJPEG/HLS/RTSP stream, or upload/download the file first."
                        )
                    elif stream_ended:
                        last_line = (
                            stderr_str.strip().split("\n")[-1]
                            if stderr_str.strip()
                            else ""
                        )
                        stream_status["error"] = (
                            last_line[:250]
                            or "Could not open stream source. Verify URL format, credentials, and camera/network reachability."
                        )
                    else:
                        stream_status["error"] = (
                            "Timed out waiting for the first video frame. "
                            "URL may not be a direct stream/video source."
                        )
                    break

                if not stream_ended:
                    stream_status["error"] = "Stream stalled while reading frames."
                    break

                # Had frames and source ended (e.g. finite HTTP MP4) -> loop automatically.
                print(f"[stream] Video ended after {frames_processed} frames; looping")
                tracker = _build_tracker()
                anomaly_detector = AnomalyDetector()
                frames_processed = 0
                proc = await loop.run_in_executor(None, _start_proc)
                frame_q, reader_stop, reader_thread, reader_state = _start_reader(proc)
                print(f"[stream] FFmpeg opened: {_redact_url(source_input)}")
                continue

            frames_processed += 1
            frame = np.frombuffer(raw, dtype=np.uint8).reshape((H, W, 3)).copy()
            detections = await loop.run_in_executor(
                None, detector.detect, frame, STREAM_CONFIDENCE
            )
            fall_detections = await loop.run_in_executor(
                None,
                lambda f=frame: detect_falls(
                    f, conf_override=current_config["fall_model_confidence_threshold"]
                ),
            )
            fall_detections = _scale_fall_detections_to_canvas(fall_detections, W, H)
            raw_tracks = tracker.update(detections)

            now = time.time()
            tracks = _build_tracks_from_yolo(raw_tracks, W, H)
            anomalies = anomaly_detector.update(
                tracks,
                now,
                fall_detections=fall_detections,
                fall_persistence_time=current_config["fall_persistence_time"],
            )
            # PPE / Face / LPR detections (run in thread pool)
            extra = await loop.run_in_executor(
                None, _run_extra_detectors_sync, frame
            )
            anomalies.extend(_build_extra_anomalies(extra, W, H))
            tracks = _finalize_tracks(tracks, anomalies)

            payload = build_frame_payload(
                tracks, anomalies, now, "stream", frame_for_archive=frame
            )
            payload["frame_jpeg"] = _encode_preview(frame)
            if connected_clients:
                await _broadcast(json.dumps(payload))

            await asyncio.sleep(0)

    except asyncio.CancelledError:
        pass
    except Exception as e:
        # Surface unexpected failures instead of dying as an unretrieved task
        # exception. The finally block clears active/url so the frontend poll
        # (resets on error && !active) returns the UI to idle.
        stream_status["error"] = f"Stream processing stopped unexpectedly: {e}"
        print(f"[stream] processing loop error: {e}")
    finally:
        if proc and proc.poll() is None:
            proc.kill()
            proc.wait()
        _stop_reader(reader_stop, reader_thread)
        if downloaded_file_path and os.path.exists(downloaded_file_path):
            try:
                os.unlink(downloaded_file_path)
            except Exception:
                pass
        try:
            os.unlink(_stderr_path)
        except Exception:
            pass
        stream_status["active"] = False
        stream_status["url"] = None
        print("[stream] Stream processing stopped")


# â”€â”€â”€ Webcam frame processing loop â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
async def webcam_processing_loop():
    """Pulls JPEG frames from _cam_frame_queue, runs YOLO+SORT, broadcasts.

    Owns its own AnomalyDetector for the same isolation reason as the video
    and stream loops: track history, ghost cache, and fall persistence are
    per-loop state and must not be shared across mode switches.
    """
    import cv2

    webcam_status["error"] = None
    webcam_status["active"] = True

    try:
        from backend.detector import YOLOv8Detector
        from backend.sort_tracker import Sort
    except Exception as e:
        webcam_status["error"] = f"Failed to load detector: {e}"
        webcam_status["active"] = False
        print(f"[webcam] Failed to load detector: {e}")
        return

    try:
        detector = YOLOv8Detector()
        tracker = _build_tracker()
        anomaly_detector = AnomalyDetector()
    except Exception as e:
        webcam_status["error"] = f"Detector init failed: {e}"
        webcam_status["active"] = False
        print(f"[webcam] Detector init failed: {e}")
        return

    print("[webcam] Webcam processing loop started")
    loop = asyncio.get_event_loop()

    try:
        while True:
            try:
                jpeg_bytes = await asyncio.wait_for(_cam_frame_queue.get(), timeout=5.0)
            except asyncio.TimeoutError:
                # Keep waiting if still in webcam mode
                if _processing_mode == "webcam":
                    continue
                break

            if _processing_mode != "webcam":
                break

            arr = np.frombuffer(jpeg_bytes, dtype=np.uint8)
            frame = cv2.imdecode(arr, cv2.IMREAD_COLOR)
            if frame is None:
                continue

            src_frame = frame
            frame = cv2.resize(frame, (INFER_WIDTH, INFER_HEIGHT))
            # Run YOLO in thread pool — keeps the asyncio event loop responsive.
            # Without this the entire server freezes for ~200 ms every frame,
            # blocking WebSocket sends and making all modes choppy.
            detections = await loop.run_in_executor(
                None, lambda f=frame: detector.detect(f, conf_override=WEBCAM_DETECTION_CONFIDENCE)
            )
            fall_detections = await loop.run_in_executor(
                None,
                lambda f=src_frame: detect_falls(
                    f, conf_override=current_config["fall_model_confidence_threshold"]
                ),
            )
            fall_detections = _scale_fall_detections_to_canvas(
                fall_detections, src_frame.shape[1], src_frame.shape[0]
            )
            raw_tracks = tracker.update(detections)

            now = time.time()
            tracks = _build_tracks_from_yolo(raw_tracks, INFER_WIDTH, INFER_HEIGHT)
            anomalies = anomaly_detector.update(
                tracks,
                now,
                fall_detections=fall_detections,
                fall_persistence_time=current_config["fall_persistence_time"],
            )
            # PPE / Face / LPR detections (run in thread pool)
            extra = await loop.run_in_executor(
                None, _run_extra_detectors_sync, frame
            )
            anomalies.extend(
                _build_extra_anomalies(extra, INFER_WIDTH, INFER_HEIGHT)
            )
            tracks = _finalize_tracks(tracks, anomalies)

            payload = build_frame_payload(
                tracks, anomalies, now, "webcam", frame_for_archive=frame
            )
            payload["frame_jpeg"] = _encode_preview(frame)
            if connected_clients:
                await _broadcast(json.dumps(payload))

    except asyncio.CancelledError:
        pass
    except Exception as e:
        # Surface unexpected failures instead of dying as an unretrieved task
        # exception that silently freezes the webcam view.
        webcam_status["error"] = f"Webcam processing stopped unexpectedly: {e}"
        print(f"[webcam] processing loop error: {e}")
    finally:
        webcam_status["active"] = False
        print("[webcam] Webcam processing loop stopped")


# ─── Lifespan ─────────────────────────────────────────────────────────────────


async def _alert_escalation_loop():
    """Background task: scan unacked alerts every 10 s.

    If an alert has not been acknowledged within ALERT_ESCALATION_SECS
    it is flagged escalated=True in the in-memory deque and DB, and a
    follow-up email is dispatched (with its own per-type cooldown so a
    single incident doesn't produce email spam if the operator is away).
    """
    global _escalated_alert_ids
    while True:
        await asyncio.sleep(10)
        esc_secs = float(current_config.get("alert_escalation_secs", ALERT_ESCALATION_SECS))
        if esc_secs <= 0:
            continue
        now = time.time()
        newly_escalated = []
        for entry in list(alert_history):
            aid = entry.get("id")
            if aid is None:
                continue
            if entry.get("acked", 0):
                continue
            if str(entry.get("anomaly", {}).get("type", "")) in _INFO_ALERT_TYPES:
                # Informational detections (faces, plates, manual snapshots)
                # are not incidents and must never escalate.
                continue
            if aid in _escalated_alert_ids:
                continue
            age = now - entry.get("timestamp", now)
            if age >= esc_secs:
                entry["escalated"] = True
                _escalated_alert_ids.add(aid)
                newly_escalated.append(entry)
                # Persist escalated flag to DB asynchronously
                _db_executor.submit(_mark_escalated_sync, aid)

        if newly_escalated:
            # Broadcast escalation event so the AlertHistory UI updates live
            esc_payload = json.dumps({
                "type": "escalation",
                "escalated_ids": [e["id"] for e in newly_escalated],
            })
            await _broadcast(esc_payload)
            # Send follow-up emails (rate-limited per type)
            for entry in newly_escalated:
                _queue_escalation_email(entry, now)


def _mark_escalated_sync(alert_id: int) -> None:
    """Persist escalated=1 to SQLite (no acked change)."""
    try:
        conn = _db._get_conn()
        conn.execute(
            "UPDATE alerts SET escalated = 1 WHERE alert_id = ?",
            (alert_id,),
        )
        conn.commit()
    except Exception as e:
        print(f"[escalation] DB mark failed for alert {alert_id}: {e}")


def _queue_escalation_email(entry: dict, now: float) -> None:
    """Send a follow-up escalation email with its own cooldown bucket."""
    anomaly = entry.get("anomaly", {})
    alert_type = str(anomaly.get("type", "unknown"))
    key = f"esc|{alert_type}"
    last = _escalation_email_cooldowns.get(key, 0.0)
    cooldown = max(60.0, float(_EMAIL_COOLDOWN_SECS))
    if now - last < cooldown:
        return
    _escalation_email_cooldowns[key] = now
    esc_entry = dict(entry)
    esc_entry["anomaly"] = dict(entry.get("anomaly", {}))
    esc_entry["anomaly"]["note"] = (
        f"[ESCALATED — not acknowledged within "
        f"{int(current_config.get('alert_escalation_secs', ALERT_ESCALATION_SECS))}s] "
        + str(esc_entry["anomaly"].get("note", ""))
    ).strip()
    _notify_executor.submit(_send_alert_email_sync, esc_entry)


@asynccontextmanager
async def lifespan(app: FastAPI):
    _apply_config()
    _load_zones_from_disk()
    await _db.init_db()
    _db.load_into_deque(alert_history)
    # Restore acked/escalated state from DB into the in-memory deque entries.
    # load_into_deque already includes acked/acked_at from the DB query;
    # rebuild _escalated_alert_ids from entries that were escalated previously.
    for entry in alert_history:
        if entry.get("escalated"):
            _escalated_alert_ids.add(entry["id"])
    # Resume the alert-id counter past the highest persisted id. Without this
    # it restarts from 0 every launch and new alerts reuse ids already present
    # in the loaded history — colliding in the deque, the DB, and the React
    # `key` of the AlertHistory table (so ack/escalation can target the wrong
    # row).
    global _alert_id_counter
    if alert_history:
        _alert_id_counter = max(int(e.get("id") or 0) for e in alert_history)
    thread = threading.Thread(target=_download_model, daemon=True)
    thread.start()
    fall_thread = threading.Thread(target=_download_fall_model, daemon=True)
    fall_thread.start()
    # PPE / Face / LPR model loading
    ppe_thread = threading.Thread(target=_download_ppe_model, daemon=True)
    ppe_thread.start()
    face_thread = threading.Thread(target=_load_face_cascade, daemon=True)
    face_thread.start()
    lpr_thread = threading.Thread(target=_download_lpr_model, daemon=True)
    lpr_thread.start()
    escalation_task = asyncio.create_task(_alert_escalation_loop())
    yield
    escalation_task.cancel()
    try:
        await escalation_task
    except asyncio.CancelledError:
        pass
    await _cancel_active()


# ─── App ──────────────────────────────────────────────────────────────────────

app = FastAPI(title="CrowdLens API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ─── REST Endpoints ───────────────────────────────────────────────────────────


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    connected_clients.add(websocket)
    try:
        while True:
            msg = await websocket.receive_text()
            if len(msg) > _WS_MAX_MSG_BYTES:
                await websocket.close(code=1009)  # 1009 = message too large
                break
    except WebSocketDisconnect:
        pass
    finally:
        connected_clients.discard(websocket)


@app.websocket("/ws/cam")
async def websocket_cam_endpoint(websocket: WebSocket):
    """Dedicated WebSocket for inbound camera frames only.
    Not added to connected_clients — never receives broadcast data."""
    await websocket.accept()
    try:
        while True:
            data = await websocket.receive_bytes()
            if _processing_mode == "webcam" and data:
                try:
                    _cam_frame_queue.put_nowait(data)
                except asyncio.QueueFull:
                    try:
                        _cam_frame_queue.get_nowait()
                        _cam_frame_queue.put_nowait(data)
                    except:
                        pass
    except WebSocketDisconnect:
        pass


@app.get("/api/health")
def health():
    return {
        "status": "ok",
        "uptime": round(time.time() - _start_time),
        "model_progress": _yolo_progress(),
        "fall_model_progress": _fall_progress(),
    }


@app.get("/api/stats")
def get_stats():
    return stats_snapshot


@app.get("/api/alerts/history")
def get_alert_history(limit: int = 200):
    history = list(alert_history)
    history.reverse()
    return {"alerts": history[:limit], "total": len(history)}


@app.get("/api/notify/status")
def get_notify_status():
    return _email_status_payload()


@app.post("/api/notify/test")
def send_notify_test(force: bool = False):
    now = time.time()
    test_entry = {
        "id": -1,
        "anomaly": {
            "type": "fall_detected",
            "track_id": 0,
            "position": [640, 360],
            "note": "manual_test",
        },
        "timestamp": now,
        "iso": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now)),
        "source": "manual",
    }
    if force:
        _send_alert_email_sync(test_entry)
    else:
        _queue_alert_email(test_entry, now)
    return {"ok": True, "status": _email_status_payload()}


@app.post("/api/alerts/clear")
async def clear_alert_history():
    """Clear in-memory alert deque, SQLite alerts table, AND archive snapshots."""
    global _escalated_alert_ids
    cleared = len(alert_history)
    alert_history.clear()
    _escalated_alert_ids = set()
    await _db.clear_alerts()
    # Also clear archive JPGs so /api/alerts/clear has a single, consistent
    # post-condition: the DB, the deque, AND the on-disk evidence are gone.
    archive_removed = 0
    try:
        for fn in os.listdir(_archive_dir):
            p = os.path.join(_archive_dir, fn)
            try:
                if os.path.isfile(p):
                    os.remove(p)
                    archive_removed += 1
            except Exception:
                pass
    except Exception:
        pass
    return {"success": True, "cleared": cleared, "archive_removed": archive_removed}


@app.post("/api/alerts/{alert_id}/ack")
async def ack_alert(alert_id: int):
    """Acknowledge a single alert by its alert_id.

    Marks acked=1, acked_at=now in the DB and updates the in-memory deque
    so the UI reflects the change immediately without a page refresh.
    """
    now = time.time()
    # Update in-memory deque
    found = False
    for entry in alert_history:
        if entry.get("id") == alert_id:
            entry["acked"] = 1
            entry["acked_at"] = now
            found = True
            break
    if not found:
        raise HTTPException(404, f"Alert {alert_id} not found")
    # Persist to DB (fire-and-forget; failure is non-fatal for the UI)
    await _db.ack_alert(alert_id, now)
    return {"success": True, "alert_id": alert_id, "acked_at": now}


@app.post("/api/alerts/ack-all")
async def ack_all_alerts():
    """Acknowledge all currently unacked alerts."""
    now = time.time()
    count = 0
    for entry in alert_history:
        if not entry.get("acked", 0):
            entry["acked"] = 1
            entry["acked_at"] = now
            count += 1
    await _db.ack_all_alerts(now)
    return {"success": True, "acknowledged": count}


@app.get("/api/archive")
def get_archive(limit: int = 200):
    """Return alerts that have stored evidence snapshots."""
    history = [h for h in reversed(list(alert_history)) if h.get("snapshot_url")]
    return {"items": history[:limit], "total": len(history)}


@app.post("/api/archive/capture")
def capture_archive_snapshot():
    """Capture a manual evidence snapshot from the latest processed frame.

    Refuses to fire when no detection mode is active. Without this guard,
    clicking Snapshot after stopping a session previously returned the last
    frame from the prior session (could be hours old) — operators briefly
    saw historical footage tagged with the current timestamp, which is a
    forensic-evidence problem.
    """
    global _alert_id_counter

    if _processing_mode == "idle":
        raise HTTPException(409, "No active detection session — start video / webcam / stream first")

    # Take a deterministic copy of the latest frame under lock so the
    # processing loop cannot mutate the buffer while we are saving it.
    # Without this lock, fast clicks could observe a torn or stale frame.
    with _snapshot_frame_lock:
        if _latest_frame_for_snapshot is None:
            raise HTTPException(409, "No processed frame available yet")
        frame_copy = _latest_frame_for_snapshot.copy()

    now = time.time()
    snapshot_url = _save_archive_snapshot(frame_copy, now)
    if not snapshot_url:
        raise HTTPException(500, "Failed to save snapshot")

    _alert_id_counter += 1
    alert_history.append(
        {
            "id": _alert_id_counter,
            "anomaly": {
                "type": "manual_snapshot",
                "track_id": None,
                "position": None,
                "note": "Manual evidence capture",
            },
            "timestamp": now,
            "iso": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now)),
            "source": _processing_mode,
            "snapshot_url": snapshot_url,
            "acked": 0,
            "acked_at": None,
            "escalated": False,
        }
    )
    return {"success": True, "snapshot_url": snapshot_url}


@app.get("/api/archive/image/{filename}")
def get_archive_image(filename: str):
    # Basic path traversal guard for local file serving.
    if "/" in filename or "\\" in filename or ".." in filename:
        raise HTTPException(400, "Invalid filename")
    path = os.path.join(_archive_dir, filename)
    if not os.path.exists(path):
        raise HTTPException(404, "Snapshot not found")
    return FileResponse(path, media_type="image/jpeg")


@app.post("/api/archive/clear")
def clear_archive():
    removed = 0
    for fn in os.listdir(_archive_dir):
        p = os.path.join(_archive_dir, fn)
        try:
            if os.path.isfile(p):
                os.remove(p)
                removed += 1
        except Exception:
            # Keep cleanup resilient for demo use.
            pass
    return {"success": True, "removed": removed}


@app.get("/api/config")
def get_config():
    import backend.config as cfg
    return {
        **current_config,
        # Use the live cfg.RESTRICTED_ZONES list so CRUD edits via the zones
        # endpoints are reflected in /api/config without needing a restart.
        "restricted_zones": cfg.RESTRICTED_ZONES,
        "frame_width": FRAME_WIDTH,
        "frame_height": FRAME_HEIGHT,
    }


# ─── PPE / Face / LPR status endpoints ─────────────────────────────────────────


@app.get("/api/ppe/status")
def get_ppe_status():
    return {
        "enabled": bool(current_config.get("ppe_detection_enabled")),
        "model_ready": is_ppe_model_ready(),
        "model_error": get_ppe_model_error(),
        "model_progress": _ppe_progress(),
        "confidence_threshold": current_config.get("ppe_confidence_threshold", 0.40),
    }


@app.get("/api/face/status")
def get_face_status():
    return {
        "enabled": bool(current_config.get("face_detection_enabled")),
        "model_ready": is_face_model_ready(),
        "model_error": get_face_model_error(),
        "scale_factor": current_config.get("face_scale_factor", 1.3),
        "min_neighbors": current_config.get("face_min_neighbors", 5),
    }


@app.get("/api/lpr/status")
def get_lpr_status():
    return {
        "enabled": bool(current_config.get("lpr_detection_enabled")),
        "model_ready": is_lpr_model_ready(),
        "model_error": get_lpr_model_error(),
        "model_progress": _lpr_progress(),
        "confidence_threshold": current_config.get("lpr_confidence_threshold", 0.40),
    }


# ─── Restricted zones CRUD ────────────────────────────────────────────────────

_ZONES_PATH = os.path.join(os.path.dirname(__file__), "zones.json")
_zones_lock = threading.Lock()
_VALID_ZONE_SHAPES = {"rect", "polygon"}


class ZoneRequest(BaseModel):
    id: str | None = None
    name: str | None = None
    shape: str | None = None  # "rect" or "polygon"
    x1: float | None = None
    y1: float | None = None
    x2: float | None = None
    y2: float | None = None
    points: list | None = None  # for polygon: [[x, y], ...]


def _validate_and_normalise_zone(body: ZoneRequest, existing_id: str | None = None) -> dict:
    """Coerce incoming zone payloads into the canonical dict the detector expects.

    Raises HTTPException with a precise message if the payload is invalid.
    """
    shape = (body.shape or "rect").lower()
    if shape not in _VALID_ZONE_SHAPES:
        raise HTTPException(400, f"Invalid shape {shape!r}; must be one of {sorted(_VALID_ZONE_SHAPES)}")

    zone: dict = {
        "id": existing_id or (body.id and str(body.id).strip()) or f"RZ{int(time.time() * 1000) % 100000}",
        "name": (body.name or "Restricted Zone").strip()[:64],
        "shape": shape,
    }

    if shape == "rect":
        if None in (body.x1, body.y1, body.x2, body.y2):
            raise HTTPException(400, "Rectangle zones require x1, y1, x2, y2")
        x1, y1, x2, y2 = float(body.x1), float(body.y1), float(body.x2), float(body.y2)
        # Normalise so x2 > x1 and y2 > y1 — the detector assumes it.
        x1, x2 = min(x1, x2), max(x1, x2)
        y1, y2 = min(y1, y2), max(y1, y2)
        # Clamp to canonical canvas bounds; we draw / detect against
        # FRAME_WIDTH x FRAME_HEIGHT.
        x1 = max(0.0, min(float(FRAME_WIDTH), x1))
        x2 = max(0.0, min(float(FRAME_WIDTH), x2))
        y1 = max(0.0, min(float(FRAME_HEIGHT), y1))
        y2 = max(0.0, min(float(FRAME_HEIGHT), y2))
        if x2 - x1 < 4 or y2 - y1 < 4:
            raise HTTPException(400, "Rectangle zone must be at least 4×4 pixels")
        zone.update({"x1": x1, "y1": y1, "x2": x2, "y2": y2})
    else:  # polygon
        pts = body.points or []
        if not isinstance(pts, list) or len(pts) < 3:
            raise HTTPException(400, "Polygon zones require at least 3 points")
        clean: list[list[float]] = []
        for p in pts:
            if not (isinstance(p, (list, tuple)) and len(p) >= 2):
                raise HTTPException(400, f"Invalid polygon point: {p!r}")
            px = max(0.0, min(float(FRAME_WIDTH), float(p[0])))
            py = max(0.0, min(float(FRAME_HEIGHT), float(p[1])))
            clean.append([px, py])
        zone["points"] = clean

    return zone


def _save_zones_to_disk() -> None:
    import backend.config as cfg
    try:
        with _zones_lock:
            data = list(cfg.RESTRICTED_ZONES)
        with open(_ZONES_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
    except Exception as e:
        print(f"[zones] Failed to save zones to {_ZONES_PATH}: {e}")


def _load_zones_from_disk() -> None:
    """Load persisted zones at startup, replacing the seed RESTRICTED_ZONES."""
    import backend.config as cfg
    if not os.path.exists(_ZONES_PATH):
        return
    try:
        with open(_ZONES_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, list):
            with _zones_lock:
                cfg.RESTRICTED_ZONES.clear()
                cfg.RESTRICTED_ZONES.extend([z for z in data if isinstance(z, dict) and z.get("id")])
            print(f"[zones] Loaded {len(cfg.RESTRICTED_ZONES)} zone(s) from {_ZONES_PATH}")
    except Exception as e:
        print(f"[zones] Failed to load zones from {_ZONES_PATH}: {e}")


@app.get("/api/zones")
def list_zones():
    import backend.config as cfg
    return {"zones": list(cfg.RESTRICTED_ZONES)}


@app.post("/api/zones")
def create_zone(body: ZoneRequest):
    import backend.config as cfg
    zone = _validate_and_normalise_zone(body)
    with _zones_lock:
        if any(z.get("id") == zone["id"] for z in cfg.RESTRICTED_ZONES):
            raise HTTPException(409, f"Zone id {zone['id']!r} already exists")
        cfg.RESTRICTED_ZONES.append(zone)
    _save_zones_to_disk()
    return {"zone": zone}


@app.put("/api/zones/{zone_id}")
def update_zone(zone_id: str, body: ZoneRequest):
    import backend.config as cfg
    zone = _validate_and_normalise_zone(body, existing_id=zone_id)
    with _zones_lock:
        for i, existing in enumerate(cfg.RESTRICTED_ZONES):
            if existing.get("id") == zone_id:
                cfg.RESTRICTED_ZONES[i] = zone
                _save_zones_to_disk()
                return {"zone": zone}
    raise HTTPException(404, f"Zone {zone_id!r} not found")


@app.delete("/api/zones/{zone_id}")
def delete_zone(zone_id: str):
    import backend.config as cfg
    with _zones_lock:
        before = len(cfg.RESTRICTED_ZONES)
        cfg.RESTRICTED_ZONES[:] = [
            z for z in cfg.RESTRICTED_ZONES if z.get("id") != zone_id
        ]
        if len(cfg.RESTRICTED_ZONES) == before:
            raise HTTPException(404, f"Zone {zone_id!r} not found")
    _save_zones_to_disk()
    return {"success": True, "id": zone_id}


class ConfigUpdate(BaseModel):
    # Keep unknown keys on the model so the PUT response can surface
    # typos to the caller. Without extra="allow" Pydantic silently drops
    # them and the user only sees the missing change in behaviour.
    model_config = {"extra": "allow"}

    overcrowding_threshold: int | None = None
    running_speed_threshold: float | None = None
    running_body_heights_per_sec: float | None = None
    running_pixel_floor: float | None = None
    unattended_object_time: float | None = None
    stationary_threshold: float | None = None
    unattended_owner_proximity_px: float | None = None
    unattended_owner_grace_time: float | None = None
    unattended_bystander_attends: bool | None = None
    unattended_ghost_ttl: float | None = None
    overcrowding_cluster_distance_px: float | None = None
    overcrowding_min_cluster_size: int | None = None
    fall_persistence_time: float | None = None
    fall_model_confidence_threshold: float | None = None
    fall_person_iou_min: float | None = None
    fall_alert_hold_time: float | None = None
    restricted_zone_enabled: bool | None = None
    restricted_zone_min_dwell: float | None = None
    fight_detection_enabled: bool | None = None
    fight_proximity_px: float | None = None
    fight_min_pair_speed: float | None = None
    fight_persistence_time: float | None = None
    fight_min_hit_streak: int | None = None
    fight_reset_grace_time: float | None = None
    alert_cooldown_secs: float | None = None
    loitering_enabled: bool | None = None
    loitering_time_threshold: float | None = None
    loitering_radius_px: float | None = None
    # Phase B — tracker tuning
    max_age: int | None = None
    iou_threshold: float | None = None
    tracker_min_hits: int | None = None
    object_track_hold_frames: int | None = None
    baggage_strong_hold_frames: int | None = None
    baggage_weak_hold_frames: int | None = None
    baggage_strong_confidence: float | None = None
    object_association_distance_px: float | None = None
    db_alert_retention: int | None = None
    alert_escalation_secs: float | None = None
    # Phase 5 — PPE / Face / LPR
    ppe_detection_enabled: bool | None = None
    ppe_confidence_threshold: float | None = None
    face_detection_enabled: bool | None = None
    face_scale_factor: float | None = None
    face_min_neighbors: int | None = None
    lpr_detection_enabled: bool | None = None
    lpr_confidence_threshold: float | None = None


def _clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, float(value)))


@app.put("/api/config")
def update_config(body: ConfigUpdate):
    global _ALERT_COOLDOWN_SECS
    if body.overcrowding_threshold is not None:
        current_config["overcrowding_threshold"] = int(_clamp(body.overcrowding_threshold, 1, 200))
    if body.running_speed_threshold is not None:
        current_config["running_speed_threshold"] = _clamp(body.running_speed_threshold, 30.0, 1500.0)
    if body.running_body_heights_per_sec is not None:
        current_config["running_body_heights_per_sec"] = _clamp(body.running_body_heights_per_sec, 0.4, 6.0)
    if body.running_pixel_floor is not None:
        current_config["running_pixel_floor"] = _clamp(body.running_pixel_floor, 0.0, 500.0)
    if body.unattended_object_time is not None:
        current_config["unattended_object_time"] = _clamp(body.unattended_object_time, 1.0, 600.0)
    if body.stationary_threshold is not None:
        current_config["stationary_threshold"] = _clamp(body.stationary_threshold, 5.0, 1000.0)
    if body.unattended_owner_proximity_px is not None:
        current_config["unattended_owner_proximity_px"] = _clamp(body.unattended_owner_proximity_px, 20.0, 1500.0)
    if body.unattended_owner_grace_time is not None:
        current_config["unattended_owner_grace_time"] = _clamp(body.unattended_owner_grace_time, 0.1, 60.0)
    if body.unattended_bystander_attends is not None:
        current_config["unattended_bystander_attends"] = bool(body.unattended_bystander_attends)
    if body.unattended_ghost_ttl is not None:
        current_config["unattended_ghost_ttl"] = _clamp(body.unattended_ghost_ttl, 0.0, 60.0)
    if body.overcrowding_cluster_distance_px is not None:
        current_config["overcrowding_cluster_distance_px"] = _clamp(body.overcrowding_cluster_distance_px, 30.0, 800.0)
    if body.overcrowding_min_cluster_size is not None:
        current_config["overcrowding_min_cluster_size"] = int(_clamp(body.overcrowding_min_cluster_size, 2, 200))
    if body.fall_persistence_time is not None:
        current_config["fall_persistence_time"] = _clamp(body.fall_persistence_time, 0.2, 5.0)
    if body.fall_model_confidence_threshold is not None:
        current_config["fall_model_confidence_threshold"] = _clamp(body.fall_model_confidence_threshold, 0.05, 0.95)
    if body.fall_person_iou_min is not None:
        current_config["fall_person_iou_min"] = _clamp(body.fall_person_iou_min, 0.0, 0.95)
    if body.restricted_zone_enabled is not None:
        current_config["restricted_zone_enabled"] = bool(body.restricted_zone_enabled)
    if body.restricted_zone_min_dwell is not None:
        current_config["restricted_zone_min_dwell"] = _clamp(body.restricted_zone_min_dwell, 0.1, 60.0)
    if body.fight_detection_enabled is not None:
        current_config["fight_detection_enabled"] = bool(body.fight_detection_enabled)
    if body.fight_proximity_px is not None:
        current_config["fight_proximity_px"] = _clamp(body.fight_proximity_px, 30.0, 1000.0)
    if body.fight_min_pair_speed is not None:
        current_config["fight_min_pair_speed"] = _clamp(body.fight_min_pair_speed, 30.0, 1500.0)
    if body.fight_persistence_time is not None:
        current_config["fight_persistence_time"] = _clamp(body.fight_persistence_time, 0.2, 10.0)
    if body.fight_min_hit_streak is not None:
        current_config["fight_min_hit_streak"] = int(_clamp(body.fight_min_hit_streak, 1, 30))
    if body.alert_cooldown_secs is not None:
        _ALERT_COOLDOWN_SECS = _clamp(body.alert_cooldown_secs, 0.5, 600.0)
        current_config["alert_cooldown_secs"] = _ALERT_COOLDOWN_SECS
    if body.loitering_enabled is not None:
        current_config["loitering_enabled"] = bool(body.loitering_enabled)
    if body.loitering_time_threshold is not None:
        current_config["loitering_time_threshold"] = _clamp(body.loitering_time_threshold, 3.0, 600.0)
    if body.loitering_radius_px is not None:
        current_config["loitering_radius_px"] = _clamp(body.loitering_radius_px, 30.0, 1500.0)
    # ── Phase B: tracker tuning + retention ──────────────────────────────
    if body.fight_reset_grace_time is not None:
        current_config["fight_reset_grace_time"] = _clamp(body.fight_reset_grace_time, 0.0, 5.0)
    if body.fall_alert_hold_time is not None:
        current_config["fall_alert_hold_time"] = _clamp(body.fall_alert_hold_time, 0.5, 30.0)
    if body.max_age is not None:
        current_config["max_age"] = int(_clamp(body.max_age, 1, 300))
    if body.iou_threshold is not None:
        current_config["iou_threshold"] = _clamp(body.iou_threshold, 0.05, 0.95)
    if body.tracker_min_hits is not None:
        current_config["tracker_min_hits"] = int(_clamp(body.tracker_min_hits, 1, 20))
    if body.object_track_hold_frames is not None:
        current_config["object_track_hold_frames"] = int(_clamp(body.object_track_hold_frames, 1, 600))
    if body.baggage_strong_hold_frames is not None:
        current_config["baggage_strong_hold_frames"] = int(_clamp(body.baggage_strong_hold_frames, 1, 1200))
    if body.baggage_weak_hold_frames is not None:
        current_config["baggage_weak_hold_frames"] = int(_clamp(body.baggage_weak_hold_frames, 1, 600))
    if body.baggage_strong_confidence is not None:
        current_config["baggage_strong_confidence"] = _clamp(body.baggage_strong_confidence, 0.05, 0.95)
    if body.object_association_distance_px is not None:
        current_config["object_association_distance_px"] = _clamp(body.object_association_distance_px, 5.0, 500.0)
    if body.db_alert_retention is not None:
        # 0 disables retention pruning entirely; useful for forensic captures.
        current_config["db_alert_retention"] = int(_clamp(body.db_alert_retention, 0, 1_000_000))
    if body.alert_escalation_secs is not None:
        # 0 disables escalation entirely.
        current_config["alert_escalation_secs"] = _clamp(body.alert_escalation_secs, 0.0, 3600.0)
    # ── Phase 5: PPE / Face / LPR ────────────────────────────────────────
    if body.ppe_detection_enabled is not None:
        current_config["ppe_detection_enabled"] = bool(body.ppe_detection_enabled)
    if body.ppe_confidence_threshold is not None:
        current_config["ppe_confidence_threshold"] = _clamp(body.ppe_confidence_threshold, 0.1, 0.95)
    if body.face_detection_enabled is not None:
        current_config["face_detection_enabled"] = bool(body.face_detection_enabled)
    if body.face_scale_factor is not None:
        current_config["face_scale_factor"] = _clamp(body.face_scale_factor, 1.05, 2.0)
    if body.face_min_neighbors is not None:
        current_config["face_min_neighbors"] = int(_clamp(body.face_min_neighbors, 1, 20))
    if body.lpr_detection_enabled is not None:
        current_config["lpr_detection_enabled"] = bool(body.lpr_detection_enabled)
    if body.lpr_confidence_threshold is not None:
        current_config["lpr_confidence_threshold"] = _clamp(body.lpr_confidence_threshold, 0.1, 0.95)
    unknown_from_apply = _apply_config()
    # Surface unknown / typo'd keys back to the caller so the user sees the
    # mistake in the API response, not just in the server log. Two sources:
    # (1) keys present in the PUT body that aren't in ConfigUpdate's typed
    #     fields (model_extra is populated because we set extra="allow"); and
    # (2) keys already in current_config that aren't in the cfg allowlist
    #     (defensive — shouldn't happen unless something manually mutated it).
    typo_keys = sorted({*(body.model_extra or {}).keys(), *unknown_from_apply})
    response: dict = {**current_config}
    if typo_keys:
        response["unknown_keys"] = typo_keys
    return response


# ─── Video endpoints ──────────────────────────────────────────────────────────


@app.post("/api/video/upload")
async def upload_video(file: UploadFile = File(...)):
    if not file.filename:
        raise HTTPException(400, "No file provided")
    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in {".mp4", ".avi", ".mov", ".mkv", ".webm"}:
        raise HTTPException(400, "Unsupported video format")

    max_bytes = 500 * 1024 * 1024
    total_size = 0
    chunk_size = 1024 * 1024  # 1 MB

    try:
        with open(VIDEO_UPLOAD_PATH, "wb") as f:
            while True:
                chunk = await file.read(chunk_size)
                if not chunk:
                    break
                total_size += len(chunk)
                if total_size > max_bytes:
                    raise HTTPException(400, "File too large (max 500 MB)")
                f.write(chunk)
    except HTTPException:
        if os.path.exists(VIDEO_UPLOAD_PATH):
            try:
                os.remove(VIDEO_UPLOAD_PATH)
            except Exception:
                pass
        raise

    if total_size == 0:
        raise HTTPException(400, "Uploaded file is empty")

    video_status["filename"] = file.filename
    video_status["mode"] = "ready"
    video_status["progress"] = 0
    return {
        "success": True,
        "filename": file.filename,
        "size_mb": round(total_size / 1e6, 1),
    }


@app.post("/api/video/start")
async def start_video():
    global _processing_mode, _active_task
    if not os.path.exists(VIDEO_UPLOAD_PATH):
        raise HTTPException(400, "No video uploaded yet")
    if not is_model_ready():
        raise HTTPException(503, "YOLO11m model is still loading, please wait")
    if not is_fall_model_ready():
        raise HTTPException(503, "Fall detection model is still loading, please wait")

    await _cancel_active()
    _reset_fps_window()
    _processing_mode = "video"
    video_status["mode"] = "processing"
    _active_task = asyncio.create_task(video_processing_loop())
    return {"success": True}


@app.post("/api/video/stop")
async def stop_video():
    global _processing_mode
    await _cancel_active()
    _reset_fps_window()
    _processing_mode = "idle"
    video_status["mode"] = "ready"
    video_status["progress"] = 0
    return {"success": True}


@app.get("/api/video/status")
def get_video_status():
    return {
        **video_status,
        "model_ready": is_model_ready(),
        "model_error": get_model_error(),
        "model_progress": _yolo_progress(),
        "fall_model_ready": is_fall_model_ready(),
        "fall_model_error": get_fall_model_error(),
        "fall_model_progress": _fall_progress(),
    }


# ─── Stream endpoints ─────────────────────────────────────────────────────────


class StreamRequest(BaseModel):
    url: str


_ALLOWED_STREAM_SCHEMES = {"rtsp", "rtsps", "http", "https"}
_PRIVATE_HOSTNAMES = {"localhost", "localho.st"}

# Set ALLOW_LOCAL_STREAMS=true when running locally to connect campus/home
# IP cameras (192.168.x.x, 10.x.x.x, rtsp://local-ip, etc.).
# Never set this in cloud/production — it disables the SSRF guard.
_ALLOW_LOCAL_STREAMS = os.environ.get("ALLOW_LOCAL_STREAMS", "true").lower() in {
    "1",
    "true",
    "yes",
}


def _validate_stream_url(url: str) -> str | None:
    """Return an error string if the URL is unsafe (SSRF guard), else None."""
    # Always allow the built-in test stream served by our own process.
    _TEST_STREAM_PATHS = {
        "http://localhost:8080/api/stream/test-feed",
        "http://127.0.0.1:8080/api/stream/test-feed",
    }
    if url in _TEST_STREAM_PATHS:
        return None
    try:
        parsed = urlsplit(url)
    except Exception:
        return "Malformed URL"
    if parsed.scheme.lower() not in _ALLOWED_STREAM_SCHEMES:
        return f"Scheme '{parsed.scheme}' is not allowed; use rtsp://, rtsps://, http://, or https://"
    host = (parsed.hostname or "").lower().rstrip(".")
    if not host:
        return "URL has no host"
    # If running locally, skip private IP restrictions so campus/home cameras work.
    if _ALLOW_LOCAL_STREAMS:
        return None
    if host in _PRIVATE_HOSTNAMES or host.endswith(".local"):
        return "Stream URL targets a local address"
    try:
        addr = ipaddress.ip_address(host)
        if (
            addr.is_loopback
            or addr.is_private
            or addr.is_link_local
            or addr.is_multicast
        ):
            return "Stream URL targets a private or internal network address"
    except ValueError:
        pass  # Not a raw IP — hostname is fine
    return None


@app.post("/api/stream/start")
async def start_stream(body: StreamRequest):
    global _processing_mode, _active_task
    if not is_model_ready():
        raise HTTPException(503, "YOLO11m model not ready yet — please wait")
    if not is_fall_model_ready():
        raise HTTPException(503, "Fall detection model not ready yet — please wait")
    url = body.url.strip()
    if not url:
        raise HTTPException(400, "Stream URL is required")
    ssrf_error = _validate_stream_url(url)
    if ssrf_error:
        raise HTTPException(400, f"Invalid stream URL: {ssrf_error}")

    await _cancel_active()
    _reset_fps_window()
    _processing_mode = "stream"
    # Store the redacted URL in the public status payload so the frontend
    # never echoes the password back via /api/stream/status. The full URL
    # is still passed to the processing loop, just kept out of the API
    # surface and any logs that consume stream_status["url"].
    stream_status["url"] = _redact_url(url)
    stream_status["error"] = None
    _active_task = asyncio.create_task(stream_processing_loop(url))
    return {"success": True}


@app.post("/api/stream/stop")
async def stop_stream():
    global _processing_mode
    await _cancel_active()
    _reset_fps_window()
    _processing_mode = "idle"
    stream_status["active"] = False
    stream_status["url"] = None
    return {"success": True}


@app.get("/api/stream/status")
def get_stream_status():
    return {
        **stream_status,
        "model_ready": is_model_ready(),
        "model_error": get_model_error(),
        "model_progress": _yolo_progress(),
        "fall_model_ready": is_fall_model_ready(),
        "fall_model_error": get_fall_model_error(),
        "fall_model_progress": _fall_progress(),
    }


# ─── Webcam mode endpoints ────────────────────────────────────────────────────


@app.get("/api/webcam/status")
def get_webcam_status():
    return {
        **webcam_status,
        "model_ready": is_model_ready(),
        "model_error": get_model_error(),
        "model_progress": _yolo_progress(),
        "fall_model_ready": is_fall_model_ready(),
        "fall_model_error": get_fall_model_error(),
        "fall_model_progress": _fall_progress(),
    }


@app.post("/api/webcam/start")
async def start_webcam():
    global _processing_mode, _active_task
    if not is_model_ready():
        raise HTTPException(503, "YOLO11m model not ready yet — please wait")
    if not is_fall_model_ready():
        raise HTTPException(503, "Fall detection model not ready yet — please wait")

    await _cancel_active()
    _reset_fps_window()
    _processing_mode = "webcam"
    webcam_status["error"] = None
    webcam_status["active"] = False  # set True when loop starts
    # Drain old frames
    while not _cam_frame_queue.empty():
        try:
            _cam_frame_queue.get_nowait()
        except Exception:
            break
    _active_task = asyncio.create_task(webcam_processing_loop())
    return {"success": True}


@app.post("/api/webcam/stop")
async def stop_webcam():
    global _processing_mode
    await _cancel_active()
    _reset_fps_window()
    _processing_mode = "idle"
    webcam_status["active"] = False
    return {"success": True}


# ─── Built-in test MJPEG stream ───────────────────────────────────────────────


async def _test_frame_generator():
    """Generates synthetic MJPEG frames that cv2.VideoCapture can read.
    Renders a dark scene with moving coloured rectangles at ~12 fps
    so the stream pipeline can be tested without an external camera."""
    import cv2

    W, H = 1280, 720
    fps_interval = 1 / 12

    while True:
        t = time.time()
        frame = np.zeros((H, W, 3), dtype=np.uint8)

        # Grid background
        for x in range(0, W, 80):
            cv2.line(frame, (x, 0), (x, H), (20, 30, 50), 1)
        for y in range(0, H, 80):
            cv2.line(frame, (0, y), (W, y), (20, 30, 50), 1)

        # Three animated "people" (tall rectangles)
        for i, (base_x, spd, col) in enumerate(
            [
                (200, 1.2, (80, 180, 80)),
                (600, 0.9, (180, 80, 80)),
                (1000, 1.5, (80, 80, 180)),
            ]
        ):
            cx = int(base_x + 180 * math.sin(t * spd + i * 2))
            cy = int(H // 2 + 60 * math.cos(t * 0.7 + i))
            cv2.rectangle(frame, (cx - 30, cy - 70), (cx + 30, cy + 70), col, -1)
            cv2.putText(
                frame,
                f"test-{i + 1}",
                (cx - 28, cy - 78),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.45,
                col,
                1,
            )

        # Timestamp overlay
        ts = time.strftime("%H:%M:%S", time.localtime(t))
        cv2.putText(
            frame,
            f"CrowdLens TEST STREAM  {ts}",
            (20, 36),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.7,
            (100, 180, 255),
            2,
        )

        _, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
        yield (b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + buf.tobytes() + b"\r\n")
        await asyncio.sleep(fps_interval)


@app.get("/api/stream/test-feed")
async def test_feed():
    """MJPEG stream endpoint for local pipeline testing.
    Paste  http://localhost:8080/api/stream/test-feed  into the stream URL box."""
    return StreamingResponse(
        _test_frame_generator(),
        media_type="multipart/x-mixed-replace; boundary=frame",
    )


# ─── AI Assistant routes ───────────────────────────────────────────────────────


_GEMINI_MODEL = "gemini-2.5-flash"


def _gemini_url(endpoint: str) -> str:
    base = os.environ.get("AI_INTEGRATIONS_GEMINI_BASE_URL", "").rstrip("/")
    return f"{base}/models/{_GEMINI_MODEL}:{endpoint}"


def _gemini_headers() -> dict:
    return {
        "Content-Type": "application/json",
        "x-goog-api-key": os.environ.get("AI_INTEGRATIONS_GEMINI_API_KEY", "dummy"),
    }


def _gemini_call(system: str, user: str, max_tokens: int = 512) -> str:
    """Blocking non-streaming Gemini call. Returns the response text."""
    import urllib.request as _req

    body = json.dumps({
        "system_instruction": {"parts": [{"text": system}]},
        "contents": [{"role": "user", "parts": [{"text": user}]}],
        "generationConfig": {"maxOutputTokens": max_tokens},
    }).encode()
    req = _req.Request(_gemini_url("generateContent"), data=body, headers=_gemini_headers())
    with _req.urlopen(req, timeout=30) as resp:
        data = json.loads(resp.read())
    return data["candidates"][0]["content"]["parts"][0]["text"]


def _gemini_chat(system: str, messages: list[dict], max_tokens: int = 512) -> str:
    """Blocking non-streaming Gemini multi-turn chat. Returns the response text."""
    import urllib.request as _req

    contents = []
    for m in messages:
        role = "model" if m.get("role") == "assistant" else m.get("role", "user")
        contents.append({"role": role, "parts": [{"text": m.get("content", "")}]})
    body = json.dumps({
        "system_instruction": {"parts": [{"text": system}]},
        "contents": contents,
        "generationConfig": {"maxOutputTokens": max_tokens},
    }).encode()
    req = _req.Request(_gemini_url("generateContent"), data=body, headers=_gemini_headers())
    with _req.urlopen(req, timeout=30) as resp:
        data = json.loads(resp.read())
    return data["candidates"][0]["content"]["parts"][0]["text"]


def _gemini_chat_stream(system: str, messages: list[dict], max_tokens: int = 2048):
    """Generator that yields incremental text chunks from Gemini's
    streamGenerateContent endpoint. Each yielded value is a string fragment
    of the assistant's reply.

    The Gemini SSE format sends `data: <json>` lines where each JSON has
    candidates[0].content.parts[0].text containing the *new* text fragment
    (cumulative deltas, not the full message). We extract those deltas and
    let the caller concat or stream them to the client.
    """
    import urllib.request as _req

    contents = []
    for m in messages:
        role = "model" if m.get("role") == "assistant" else m.get("role", "user")
        contents.append({"role": role, "parts": [{"text": m.get("content", "")}]})
    body = json.dumps({
        "system_instruction": {"parts": [{"text": system}]},
        "contents": contents,
        "generationConfig": {"maxOutputTokens": max_tokens},
    }).encode()
    # streamGenerateContent with alt=sse gives us one Server-Sent-Events
    # frame per generation step (typically one chunk per few tokens).
    url = _gemini_url("streamGenerateContent") + "?alt=sse"
    req = _req.Request(url, data=body, headers=_gemini_headers())
    with _req.urlopen(req, timeout=60) as resp:
        # Read line-by-line; each SSE record starts with "data: " and is
        # terminated by a blank line. We don't need to handle multi-line
        # events because Gemini sends each JSON on a single data line.
        for raw_line in resp:
            line = raw_line.decode("utf-8", errors="replace").strip()
            if not line or not line.startswith("data:"):
                continue
            payload = line[len("data:"):].strip()
            if payload == "[DONE]":
                break
            try:
                obj = json.loads(payload)
            except json.JSONDecodeError:
                continue
            try:
                parts = obj["candidates"][0]["content"]["parts"]
            except (KeyError, IndexError, TypeError):
                continue
            for p in parts:
                txt = p.get("text") if isinstance(p, dict) else None
                if txt:
                    yield txt


class AIReportRequest(BaseModel):
    alert: dict


class AIChatRequest(BaseModel):
    messages: list[dict]
    alert_history: list[dict] = []


class AINarrateRequest(BaseModel):
    tracks: list[dict] = []
    anomalies: list[dict] = []
    person_count: int = 0
    object_count: int = 0
    source_mode: str = "idle"


def _format_alert_for_ai(alert: dict) -> str:
    from datetime import datetime

    a = alert.get("anomaly", {})
    ts = alert.get("timestamp", 0)
    t = datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M:%S") if ts else "unknown"
    parts = [
        f"Time: {t}",
        f"Type: {a.get('type', 'unknown')}",
        f"Source: {alert.get('source', 'live')}",
    ]
    if a.get("track_id") is not None:
        parts.append(f"Track ID: #{a['track_id']}")
    if a.get("track_ids") and len(a["track_ids"]) >= 2:
        parts.append(f"Track Pair: #{a['track_ids'][0]} & #{a['track_ids'][1]}")
    if a.get("count") is not None:
        parts.append(f"People count: {a['count']}")
    if a.get("avg_speed") is not None:
        parts.append(f"Speed: {a['avg_speed']} px/frame")
    if a.get("avg_pair_speed"):
        parts.append(f"Pair speed: {a['avg_pair_speed']} px/frame")
    if a.get("distance"):
        parts.append(f"Distance between pair: {a['distance']} px")
    if a.get("duration"):
        parts.append(f"Duration: {a['duration']}s")
    if a.get("zone_name"):
        parts.append(f"Zone: {a['zone_name']}")
    if a.get("position"):
        parts.append(f"Position: {tuple(round(v) for v in a['position'])}")
    if a.get("note"):
        parts.append(f"Note: {a['note']}")
    return "\n".join(parts)


@app.post("/api/ai/report")
async def generate_ai_report(req: AIReportRequest):
    """Generate a professional incident report for a single alert."""
    try:
        alert_text = _format_alert_for_ai(req.alert)
        system = (
            "You are a professional security operations analyst for a campus AI monitoring system. "
            "Write concise, clear incident reports in plain English. "
            "Use a professional tone. Structure the report as: "
            "1) Incident Summary (2-3 sentences), "
            "2) Detection Details (bullet points), "
            "3) Recommended Action (1-2 sentences). "
            "Do not use markdown headers — use plain text with labels."
        )
        user = f"Generate an incident report for the following detection:\n\n{alert_text}"
        loop = asyncio.get_event_loop()
        report = await loop.run_in_executor(None, lambda: _gemini_call(system, user, 2048))
        return {"report": report}
    except Exception as e:
        raise HTTPException(status_code=500, detail="Failed to generate report. The AI service may be unavailable.")


@app.post("/api/ai/chat")
async def ai_chat(req: AIChatRequest):
    """SSE chat with Gemini about alert history.

    Uses Gemini's streamGenerateContent endpoint so the client sees text
    appear word-by-word instead of all-at-once after a 5-second wait.
    The blocking urllib reader runs in a worker thread; chunks are pushed
    into an asyncio.Queue and forwarded as SSE `data:` frames.
    """

    async def stream():
        history_text = ""
        if req.alert_history:
            lines = [_format_alert_for_ai(a) for a in req.alert_history[:50]]
            history_text = "\n\n---\n\n".join(lines)

        system_prompt = (
            "You are an intelligent security assistant for CrowdLens, an AI-powered crowd monitoring system. "
            "You help operators understand and analyse surveillance alert data. "
            "Be concise, professional, and factual. "
            "If you reference track IDs, quote them with #. "
        )
        if history_text:
            system_prompt += f"\n\nCurrent alert history ({len(req.alert_history)} events):\n\n{history_text}"
        else:
            system_prompt += "\n\nNo alert history is available yet."

        loop = asyncio.get_event_loop()
        # Bridge the blocking generator to async via a queue. Sentinel marks
        # end-of-stream; the JSON {error: ...} marker is used for failures
        # so the SSE consumer can show a friendly message.
        chunk_q: asyncio.Queue = asyncio.Queue(maxsize=64)
        SENTINEL_DONE = object()

        def _producer():
            try:
                for chunk in _gemini_chat_stream(system_prompt, req.messages, 2048):
                    if not chunk:
                        continue
                    asyncio.run_coroutine_threadsafe(chunk_q.put(chunk), loop).result()
            except Exception as err:
                try:
                    asyncio.run_coroutine_threadsafe(
                        chunk_q.put({"__error__": str(err)}), loop
                    ).result()
                except Exception:
                    pass
            finally:
                try:
                    asyncio.run_coroutine_threadsafe(
                        chunk_q.put(SENTINEL_DONE), loop
                    ).result()
                except Exception:
                    pass

        loop.run_in_executor(None, _producer)

        try:
            while True:
                item = await chunk_q.get()
                if item is SENTINEL_DONE:
                    break
                if isinstance(item, dict) and "__error__" in item:
                    yield f"data: {json.dumps({'error': 'AI service error. Please try again.'})}\n\n"
                    break
                # Forward the text fragment to the client. Frontend already
                # appends payload.content to the assistant message, so each
                # chunk lands as it arrives — true streaming.
                yield f"data: {json.dumps({'content': item})}\n\n"
            yield f"data: {json.dumps({'done': True})}\n\n"
        except Exception:
            yield f"data: {json.dumps({'error': 'AI service error. Please try again.'})}\n\n"

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.post("/api/ai/narrate")
async def ai_narrate(req: AINarrateRequest):
    """Generate a plain-English scene description from current detection data."""
    try:
        track_lines = []
        for t in req.tracks[:20]:
            name = t.get("class_name", "person")
            tid = t.get("id", "?")
            conf = t.get("confidence", 0)
            run = " (running)" if t.get("running") else ""
            track_lines.append(
                f"  - Track #{tid}: {name}, conf={int(conf * 100)}%{run}"
            )

        anomaly_lines = []
        for a in req.anomalies[:10]:
            anomaly_lines.append(f"  - {a.get('type', 'unknown')}: {a}")

        scene_text = (
            f"Source mode: {req.source_mode}\n"
            f"People detected: {req.person_count}\n"
            f"Objects detected: {req.object_count}\n"
            f"Active tracks ({len(req.tracks)}):\n"
            + ("\n".join(track_lines) or "  none")
            + "\n"
            f"Active anomalies ({len(req.anomalies)}):\n"
            + ("\n".join(anomaly_lines) or "  none")
        )

        system = (
            "You are a security analyst narrating a live surveillance scene for an operator. "
            "Write 2-4 sentences describing what is currently happening in the scene. "
            "Be specific about people counts, anomalies, and threat level. "
            "Keep it concise and clear — this is a live ops summary."
        )
        loop = asyncio.get_event_loop()
        narration = await loop.run_in_executor(
            None, lambda: _gemini_call(system, f"Describe this live scene:\n\n{scene_text}", 2048)
        )
        return {"narration": narration}
    except Exception as e:
        raise HTTPException(status_code=500, detail="Failed to generate narration. The AI service may be unavailable.")


# ─── SPA static file serving (production) ─────────────────────────────────────

from pathlib import Path
from fastapi.staticfiles import StaticFiles

_static_dir = (
    Path(__file__).parent.parent / "artifacts" / "company-ai" / "dist" / "public"
)

if _static_dir.exists():
    app.mount("/", StaticFiles(directory=str(_static_dir), html=True), name="spa")
