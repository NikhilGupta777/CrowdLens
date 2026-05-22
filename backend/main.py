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
)
from backend.detector import _download_model, is_model_ready, get_model_error
from backend.fall_detector import (
    _download_fall_model,
    detect_falls,
    get_fall_model_error,
    is_fall_model_ready,
)

# ─── Global State ─────────────────────────────────────────────────────────────

alert_history: deque = deque(maxlen=500)
connected_clients: set[WebSocket] = set()

_WS_MAX_MSG_BYTES = 1 * 1024 * 1024  # 1 MB cap per WebSocket message
_ALERT_COOLDOWN_SECS = 5.0

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
}

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
_video_anomaly_detector = AnomalyDetector()

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
    severity = "HIGH" if anomaly.get("type") in {"fall_detected", "fight_suspected", "restricted_zone"} else "MEDIUM"
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
    person_count = sum(1 for t in tracks if t["class_id"] == 0)
    object_count = sum(1 for t in tracks if t["class_id"] != 0)

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


def _apply_config():
    import backend.config as cfg

    for k, v in current_config.items():
        setattr(cfg, k.upper(), v)


async def _broadcast(message: str):
    dead = []
    for ws in connected_clients:
        try:
            await ws.send_text(message)
        except Exception:
            dead.append(ws)
    for d in dead:
        connected_clients.discard(d)


async def _cancel_active():
    global _active_task
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
    global _video_anomaly_detector
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
        tracker = Sort(
            max_age=MAX_AGE, min_hits=TRACKER_MIN_HITS, iou_threshold=IOU_THRESHOLD
        )
        _video_anomaly_detector = AnomalyDetector()
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
                _video_anomaly_detector = AnomalyDetector()
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
            anomalies = _video_anomaly_detector.update(
                tracks,
                now,
                fall_detections=fall_detections,
                fall_persistence_time=current_config["fall_persistence_time"],
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
    """
    global _video_anomaly_detector
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
        tracker = Sort(
            max_age=MAX_AGE, min_hits=TRACKER_MIN_HITS, iou_threshold=IOU_THRESHOLD
        )
        _video_anomaly_detector = AnomalyDetector()
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
        print(f"[stream] FFmpeg opened: {source_input}")
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
                        tracker = Sort(
                            max_age=MAX_AGE,
                            min_hits=TRACKER_MIN_HITS,
                            iou_threshold=IOU_THRESHOLD,
                        )
                        _video_anomaly_detector = AnomalyDetector()
                        frames_processed = 0
                        proc = await loop.run_in_executor(None, _start_proc)
                        frame_q, reader_stop, reader_thread, reader_state = (
                            _start_reader(proc)
                        )
                        print(f"[stream] FFmpeg opened: {source_input}")
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
                tracker = Sort(
                    max_age=MAX_AGE,
                    min_hits=TRACKER_MIN_HITS,
                    iou_threshold=IOU_THRESHOLD,
                )
                _video_anomaly_detector = AnomalyDetector()
                frames_processed = 0
                proc = await loop.run_in_executor(None, _start_proc)
                frame_q, reader_stop, reader_thread, reader_state = _start_reader(proc)
                print(f"[stream] FFmpeg opened: {source_input}")
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
            anomalies = _video_anomaly_detector.update(
                tracks,
                now,
                fall_detections=fall_detections,
                fall_persistence_time=current_config["fall_persistence_time"],
            )
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
    """Pulls JPEG frames from _cam_frame_queue, runs YOLO+SORT, broadcasts."""
    global _video_anomaly_detector
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
        tracker = Sort(
            max_age=MAX_AGE, min_hits=TRACKER_MIN_HITS, iou_threshold=IOU_THRESHOLD
        )
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
            tracks = _finalize_tracks(tracks, anomalies)

            payload = build_frame_payload(
                tracks, anomalies, now, "webcam", frame_for_archive=frame
            )
            payload["frame_jpeg"] = _encode_preview(frame)
            if connected_clients:
                await _broadcast(json.dumps(payload))

    except asyncio.CancelledError:
        pass
    finally:
        webcam_status["active"] = False
        print("[webcam] Webcam processing loop stopped")


# ─── Lifespan ─────────────────────────────────────────────────────────────────


@asynccontextmanager
async def lifespan(app: FastAPI):
    _apply_config()
    await _db.init_db()
    _db.load_into_deque(alert_history)
    thread = threading.Thread(target=_download_model, daemon=True)
    thread.start()
    fall_thread = threading.Thread(target=_download_fall_model, daemon=True)
    fall_thread.start()
    yield
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
    return {"status": "ok", "uptime": round(time.time() - _start_time)}


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
    global _alert_id_counter
    cleared = len(alert_history)
    alert_history.clear()
    _alert_id_counter = 0
    await _db.clear_alerts()
    return {"success": True, "cleared": cleared}


@app.get("/api/archive")
def get_archive(limit: int = 200):
    """Return alerts that have stored evidence snapshots."""
    history = [h for h in reversed(list(alert_history)) if h.get("snapshot_url")]
    return {"items": history[:limit], "total": len(history)}


@app.post("/api/archive/capture")
def capture_archive_snapshot():
    """Capture a manual evidence snapshot from the latest processed frame."""
    global _alert_id_counter
    if _latest_frame_for_snapshot is None:
        raise HTTPException(409, "No processed frame available yet")

    now = time.time()
    snapshot_url = _save_archive_snapshot(_latest_frame_for_snapshot, now)
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
    return {
        **current_config,
        "restricted_zones": RESTRICTED_ZONES,
        "frame_width": FRAME_WIDTH,
        "frame_height": FRAME_HEIGHT,
    }


class ConfigUpdate(BaseModel):
    overcrowding_threshold: int | None = None
    running_speed_threshold: float | None = None
    unattended_object_time: float | None = None
    stationary_threshold: float | None = None
    unattended_owner_proximity_px: float | None = None
    unattended_owner_grace_time: float | None = None
    fall_persistence_time: float | None = None
    fall_model_confidence_threshold: float | None = None
    restricted_zone_enabled: bool | None = None
    restricted_zone_min_dwell: float | None = None
    fight_detection_enabled: bool | None = None
    fight_proximity_px: float | None = None
    fight_min_pair_speed: float | None = None
    fight_persistence_time: float | None = None
    fight_min_hit_streak: int | None = None
    alert_cooldown_secs: float | None = None
    loitering_enabled: bool | None = None
    loitering_time_threshold: float | None = None
    loitering_radius_px: float | None = None


@app.put("/api/config")
def update_config(body: ConfigUpdate):
    global _ALERT_COOLDOWN_SECS
    if body.overcrowding_threshold is not None:
        current_config["overcrowding_threshold"] = body.overcrowding_threshold
    if body.running_speed_threshold is not None:
        current_config["running_speed_threshold"] = body.running_speed_threshold
    if body.unattended_object_time is not None:
        current_config["unattended_object_time"] = body.unattended_object_time
    if body.stationary_threshold is not None:
        current_config["stationary_threshold"] = body.stationary_threshold
    if body.unattended_owner_proximity_px is not None:
        current_config["unattended_owner_proximity_px"] = (
            body.unattended_owner_proximity_px
        )
    if body.unattended_owner_grace_time is not None:
        current_config["unattended_owner_grace_time"] = body.unattended_owner_grace_time
    if body.fall_persistence_time is not None:
        current_config["fall_persistence_time"] = max(
            0.2, min(5.0, float(body.fall_persistence_time))
        )
    if body.fall_model_confidence_threshold is not None:
        current_config["fall_model_confidence_threshold"] = max(
            0.05, min(0.95, float(body.fall_model_confidence_threshold))
        )
    if body.restricted_zone_enabled is not None:
        current_config["restricted_zone_enabled"] = body.restricted_zone_enabled
    if body.restricted_zone_min_dwell is not None:
        current_config["restricted_zone_min_dwell"] = body.restricted_zone_min_dwell
    if body.fight_detection_enabled is not None:
        current_config["fight_detection_enabled"] = body.fight_detection_enabled
    if body.fight_proximity_px is not None:
        current_config["fight_proximity_px"] = body.fight_proximity_px
    if body.fight_min_pair_speed is not None:
        current_config["fight_min_pair_speed"] = body.fight_min_pair_speed
    if body.fight_persistence_time is not None:
        current_config["fight_persistence_time"] = body.fight_persistence_time
    if body.fight_min_hit_streak is not None:
        current_config["fight_min_hit_streak"] = body.fight_min_hit_streak
    if body.alert_cooldown_secs is not None:
        _ALERT_COOLDOWN_SECS = max(0.5, float(body.alert_cooldown_secs))
        current_config["alert_cooldown_secs"] = _ALERT_COOLDOWN_SECS
    if body.loitering_enabled is not None:
        current_config["loitering_enabled"] = body.loitering_enabled
    if body.loitering_time_threshold is not None:
        current_config["loitering_time_threshold"] = max(3.0, float(body.loitering_time_threshold))
    if body.loitering_radius_px is not None:
        current_config["loitering_radius_px"] = max(30.0, float(body.loitering_radius_px))
    _apply_config()
    return current_config


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
        "fall_model_ready": is_fall_model_ready(),
        "fall_model_error": get_fall_model_error(),
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
    stream_status["url"] = url
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
        "fall_model_ready": is_fall_model_ready(),
        "fall_model_error": get_fall_model_error(),
    }


# ─── Webcam mode endpoints ────────────────────────────────────────────────────


@app.get("/api/webcam/status")
def get_webcam_status():
    return {
        **webcam_status,
        "model_ready": is_model_ready(),
        "model_error": get_model_error(),
        "fall_model_ready": is_fall_model_ready(),
        "fall_model_error": get_fall_model_error(),
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
    """SSE chat with Gemini about alert history."""

    async def stream():
        try:
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
            text = await loop.run_in_executor(
                None, lambda: _gemini_chat(system_prompt, req.messages, 2048)
            )
            yield f"data: {json.dumps({'content': text})}\n\n"
            yield f"data: {json.dumps({'done': True})}\n\n"
        except Exception as e:
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
