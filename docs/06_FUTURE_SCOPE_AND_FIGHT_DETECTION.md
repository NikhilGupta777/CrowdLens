# CrowdLens — Future Scope & Fight Detection Analysis

---

## 1. CURRENT FIGHT DETECTION — DETAILED ANALYSIS

> **Status:** Implemented as a heuristic prototype (see §1.2 below). For pose-based / action-recognition upgrades, see §2.

### 1.1 What Has Been Implemented

The current fight detection in CrowdLens is a **heuristic pair-motion detector**. It does NOT use computer vision pose estimation or action recognition — it relies purely on tracking data (bounding box movements).

### 1.2 Algorithm (Current)

```python
# Pseudocode of current fight detection
for each pair (person_A, person_B) in tracked_persons:
    distance = euclidean_distance(center_A, center_B)
    speed_A = average_speed_over_5_frames(person_A)
    speed_B = average_speed_over_5_frames(person_B)
    stable_A = hit_streak(person_A) >= 3
    stable_B = hit_streak(person_B) >= 3
    
    if distance <= 180px AND speed_A >= 240px/s AND speed_B >= 240px/s AND stable_A AND stable_B:
        if this_pair persists for >= 0.8 seconds:
            emit "fight_suspected" alert
```

### 1.3 Configuration Parameters
| Parameter | Default | Description |
|-----------|---------|-------------|
| FIGHT_DETECTION_ENABLED | True | Master toggle |
| FIGHT_PROXIMITY_PX | 180 px | Max distance between pair |
| FIGHT_MIN_PAIR_SPEED | 240 px/s | Min speed for BOTH persons |
| FIGHT_PERSISTENCE_TIME | 0.8 s | How long before alert |
| FIGHT_MIN_HIT_STREAK | 3 | Track stability requirement |
| FIGHT_RESET_GRACE_TIME | 0.4 s | Tolerance for single-frame speed/proximity dips before timer resets |

### 1.4 Strengths of Current Approach
- ✅ Zero additional model overhead (uses existing tracking data)
- ✅ Works in real-time without extra inference cost
- ✅ Configurable thresholds (adjustable sensitivity)
- ✅ Quick detection (0.8s persistence is fast)
- ✅ Works with any YOLO-detected persons

### 1.5 Weaknesses / Limitations
- ❌ **High false positive rate** — Two people running past each other triggers it
- ❌ **Cannot distinguish** fighting from: playing, dancing, hugging, sports
- ❌ **No pose information** — Doesn't know if arms are raised/punching
- ❌ **No action recognition** — Cannot classify temporal movement patterns
- ❌ **Proximity requirement** — Misses fights where people separate briefly
- ❌ **Speed requirement** — Misses slow-motion grappling/choking

### 1.6 When It Works Well
- Fast, close-range altercations (both persons moving rapidly)
- Scenes with few people (less chance of coincidental proximity+speed)
- Low-density environments where high-speed close pairs are unusual

### 1.7 When It Fails
- Dense crowds (many people naturally close + moving)
- Sports areas (legitimate high-speed close-proximity movement)
- Playgrounds / social areas (roughhousing, dancing)
- Slow attacks (grabbing, pushing, choking)

---

## 2. FUTURE FIGHT DETECTION — IMPROVEMENT PATH

### 2.1 Level 1: Improved Heuristics (Short-term)
**Effort: Low | Accuracy Improvement: Modest**

Additions to current approach:
- **Relative velocity detection** — Check if persons are moving TOWARDS each other (not same direction)
- **Acceleration detection** — Sudden speed changes indicate aggressive motion
- **Oscillation detection** — Back-and-forth motion typical of fighting
- **Size change detection** — Bounding box expansion (arms spread) during fight

### 2.2 Level 2: Pose Estimation Integration (Medium-term)
**Effort: Medium | Accuracy Improvement: Significant**

Add pose estimation (MediaPipe or OpenPose) to detect:
- Raised arms (punching posture)
- Bent forward stance (aggressive posture)
- Arms extended toward another person
- Rapid limb movements in close proximity

**Models:**
- MediaPipe Pose (lightweight, real-time)
- OpenPose (multi-person, higher accuracy)
- YOLOv8-Pose (combined detection + pose)

### 2.3 Level 3: Action Recognition (Medium-long term)
**Effort: High | Accuracy Improvement: Major**

Temporal action classification using video clips:
- **SlowFast Networks** — Two-pathway (slow/fast temporal resolution)
- **I3D (Inflated 3D ConvNets)** — 3D convolutions on video clips
- **Video Swin Transformer** — Attention-based temporal modeling
- **TSN/TSM** — Temporal Segment Networks

**Training data needed:**
- Fight/violence video datasets (e.g., RWF-2000, Hockey Fight Dataset)
- Normal activity videos for negative samples
- Campus-specific footage for fine-tuning

### 2.4 Level 4: Dedicated Violence Detection Model (Long-term)
**Effort: Very High | Accuracy Improvement: Best**

Train or fine-tune a model specifically for violence/fight detection:
- Two-stream architecture (RGB + optical flow)
- Skeleton-based GCN (Graph Convolutional Networks on pose sequences)
- Attention mechanisms focusing on interacting body parts
- Ensemble of appearance + motion + pose features

---

## 3. COMPLETE FUTURE SCOPE ROADMAP

### 3.1 Phase 1 — Enhancements (1-3 months)

> **Status update:** Polygon restricted zones, loitering detection, and improved fight detection (relative-velocity heuristics, grace-time tolerance) are already implemented; see §4.1 below for the current authoritative feature matrix. The table below tracks **future** work only.

| Feature | Priority | Difficulty | Description |
|---------|----------|-----------|-------------|
| Multi-camera support | HIGH | Medium | Process 2-4 cameras simultaneously via worker processes |
| Pose-based fight detection | HIGH | Medium | Add MediaPipe / YOLOv8-Pose to disambiguate playing / sports / actual fights |
| Alert severity levels | MEDIUM | Low | Categorize alerts by severity with different responses |
| User authentication | MEDIUM | Medium | Login system for dashboard access |
| Video recording / DVR | MEDIUM | Medium | Record streams for later review |
| Telegram / Slack alerts | LOW | Low | Additional notification channels |

### 3.2 Phase 2 — Advanced Detection (3-6 months)

| Feature | Priority | Difficulty | Description |
|---------|----------|-----------|-------------|
| Pose estimation | HIGH | Medium | MediaPipe/OpenPose for posture analysis |
| Weapon detection | HIGH | Medium | Fine-tuned YOLO for knife/gun detection |
| Smoke/fire detection | MEDIUM | Medium | Dedicated detection model |
| Direction-of-travel | MEDIUM | Low | Detect wrong-way movement |
| Crowd density mapping | LOW | Medium | Heatmap history over time |
| Path analysis | LOW | High | Track movement patterns |

### 3.3 Phase 3 — Scalability (6-12 months)

| Feature | Priority | Difficulty | Description |
|---------|----------|-----------|-------------|
| Cloud deployment | HIGH | High | Kubernetes + GPU inference service |
| Multi-tenant support | HIGH | High | Multiple organizations/campuses |
| Mobile app | MEDIUM | High | React Native iOS/Android |
| License plate recognition | MEDIUM | High | ANPR at campus gates |
| Facial recognition | LOW | High | Optional identity verification |
| Edge computing | MEDIUM | High | Processing on camera hardware |

### 3.4 Phase 4 — Intelligence (12+ months)

| Feature | Priority | Difficulty | Description |
|---------|----------|-----------|-------------|
| Predictive analytics | HIGH | Very High | Predict incidents before they occur |
| Behavioural profiling | MEDIUM | High | Learn normal patterns, flag deviations |
| Action recognition | HIGH | Very High | SlowFast/I3D temporal classification |
| Federated learning | LOW | Very High | Privacy-preserving model updates |
| 3D digital twin | LOW | Very High | 3D campus visualization |
| Autonomous response | LOW | Very High | Auto-lock doors, alert police, etc. |

---

## 4. WHAT IS DONE vs WHAT IS NOT DONE

### 4.1 Complete Feature Matrix

| Category | Feature | Done? | Notes |
|----------|---------|-------|-------|
| **Detection** | Person detection | ✅ | YOLOv11m |
| | Vehicle detection | ✅ | Cars |
| | Baggage detection | ✅ | Backpack, handbag, suitcase |
| | Weapon detection | ❌ | Future - needs dedicated model |
| | Fire/smoke detection | ❌ | Future - needs dedicated model |
| | Animal detection | ❌ | Disabled but available in COCO |
| **Tracking** | Multi-object tracking | ✅ | SORT + Kalman |
| | Re-identification | ❌ | Would need appearance features (Deep SORT) |
| | Cross-camera tracking | ❌ | Future - needs multi-cam support first |
| **Anomaly** | Running | ✅ | Speed-based with body-heights/sec dual metric |
| | Overcrowding | ✅ | Spatial-cluster based (single-link), not raw count |
| | Unattended object | ✅ | Stationary + owner absent, with bag-ghost cache across SORT id churn |
| | Fall detection | ✅ | Dedicated HF model (melihuzunoglu/human-fall-detection) with NMS + IoU-association to person tracks |
| | Fight detection (heuristic) | ✅ | Pair proximity + speed + persistence with 0.4 s grace-time tolerance |
| | Fight detection (vision) | ❌ | Future — needs pose / action recognition |
| | Restricted zone | ✅ | Rectangular AND polygon zones; foot-point + bbox-overlap detection |
| | Loitering | ✅ | Anchor + hysteresis dwell timer with re-anchor factor |
| | Wrong-way movement | ❌ | Direction analysis |
| | Abandoned vehicle | ❌ | Vehicle stationary detection |
| **Input** | Browser webcam | ✅ | getUserMedia + WS relay |
| | Video file upload | ✅ | Up to 500MB |
| | RTSP stream | ✅ | FFmpeg pipe |
| | HTTP stream | ✅ | FFmpeg + MJPEG parsing |
| | Local IP camera | ✅ | Fetch-based relay |
| | Multi-camera simultaneous | ❌ | Only one source at a time |
| **Alerts** | In-app (real-time) | ✅ | WebSocket broadcast |
| | Audio alerts | ✅ | Web Audio API |
| | Browser push | ✅ | Notifications API |
| | Email (AWS SES) | ✅ | HTML formatted |
| | SMS | ❌ | Future |
| | Telegram/Slack | ❌ | Future |
| | Auto-response (door lock) | ❌ | Future IoT integration |
| **AI** | Incident reports | ✅ | GPT-generated |
| | Alert chat | ✅ | Streaming responses |
| | Scene narration | ✅ | Auto-refresh |
| | Predictive analytics | ❌ | Future - needs historical modeling |
| **Dashboard** | Live canvas | ✅ | 5 overlay styles |
| | Alert history table | ✅ | Search + filter + export |
| | Settings panel | ✅ | Live threshold tuning |
| | Analytics charts | ✅ | 10-minute bar chart |
| | Historical heatmaps | ❌ | Long-term density analysis |
| | 3D visualization | ❌ | Digital twin |
| **Infrastructure** | Single-server deploy | ✅ | Python + Node |
| | Docker container | ❌ | Not containerized yet |
| | Kubernetes | ❌ | Future scaling |
| | GPU inference service | ❌ | TensorRT/Triton |
| | Load balancing | ❌ | Single instance only |
| **Security** | SSRF protection | ✅ | URL validation |
| | Input size limits | ✅ | WS + upload caps |
| | Authentication | ❌ | No login system |
| | Role-based access | ❌ | No permissions |
| | Encryption | ❌ | No TLS by default |

### 4.2 Recently Completed (Phase A–C audit fixes)

The repo went through a deep audit pass that fixed several detection-correctness bugs and added missing tunability. The matrix above already reflects the *result*, but some changes are not feature-shaped and so don't appear there:

| Area | Change |
|------|--------|
| Tracker tuning | `MAX_AGE`, `IOU_THRESHOLD`, `TRACKER_MIN_HITS`, `OBJECT_TRACK_HOLD_FRAMES`, `BAGGAGE_*_HOLD_FRAMES`, `BAGGAGE_STRONG_CONFIDENCE`, `OBJECT_ASSOCIATION_DISTANCE_PX`, `FALL_ALERT_HOLD_TIME`, `FIGHT_RESET_GRACE_TIME` are now `PUT /api/config` tunables (no restart) |
| Anomaly correctness | Loitering / running / restricted_zone / fight no longer accumulate timers on predicted (held-over) tracks. Fight detection has 0.4 s grace-time tolerance. Sticky `restricted_zone` cards now key on `(track_id, zone_id)` so two overlapping zones produce two cards |
| Persistence | SQLite alerts table has retention cap (`DB_ALERT_RETENTION`, default 5000). `ALTER TABLE` migration adds `snapshot_url` for older DBs. `/api/alerts/clear` also wipes archive JPGs. `/api/archive/capture` rejects when mode is idle. `_alert_id_counter` is monotonic now (no reset on clear) |
| AI streaming | `/api/ai/chat` uses Gemini's `streamGenerateContent` SSE endpoint for real word-by-word streaming (was a single chunk after a 5 s wait) |
| UX | Connecting overlay surfaces `model_progress.stage` from `/api/health` (`exporting_onnx`, `warmup_gpu`, `downloading`, etc.) so the user knows what's happening during cold start. AI reports + chat now persist in `localStorage` with `{v:1}` schema versioning. Camera profiles likewise. AlertHistory shows filtered-vs-total counts |

---

## 5. KEY TECHNICAL DECISIONS & TRADE-OFFS

### 5.1 Why YOLOv11m (not v11n or v11x)?
- **v11n (nano)**: Faster but lower accuracy — misses distant/small persons
- **v11m (medium)**: Best balance of speed and accuracy for surveillance
- **v11x (extra-large)**: Too slow for real-time CPU inference

### 5.2 Why SORT (not Deep SORT or ByteTrack)?
- **SORT**: Simple, fast, sufficient for single-camera fixed scenes
- **Deep SORT**: Adds appearance model — slower, overkill for our use case
- **ByteTrack**: Uses low-confidence detections — marginal improvement, more complexity

### 5.3 Why SQLite (not PostgreSQL)?
- **SQLite**: Zero-config, embedded, sufficient for single-server
- **PostgreSQL**: Overkill for current scale; needed for multi-server future

### 5.4 Why Canvas 2D (not WebGL or Three.js)?
- **Canvas 2D**: Simple, fast enough for 2D overlays at 60fps
- **WebGL**: Overkill for bounding boxes and text
- **Three.js**: For 3D visualization (future digital twin)

### 5.5 Why FFmpeg for Streams (not OpenCV)?
- **FFmpeg**: Handles all formats, proper reconnection, stderr diagnostics
- **OpenCV VideoCapture**: Often hangs on RTSP, no clear error messages

---

*Future Scope & Fight Detection Analysis — CrowdLens Campus AI Monitor*
