# CrowdLens — PPT Slide Content
## Presentation Guide (15-20 slides)

---

## SLIDE 1: TITLE SLIDE

**Title:** CrowdLens: AI-Powered Real-Time Campus Surveillance & Anomaly Detection System

**Subtitle:** Leveraging YOLOv11m + SORT Tracking + Behavioural Analysis for Intelligent Security Monitoring

**Author:** CrowdLens Open-Source Team
**Domain:** Computer Vision & AI Security Systems
**Department:** Intelligent Surveillance Systems Group
**Institution:** Campus AI Surveillance & Computer Vision Research Group

---

## SLIDE 2: PROBLEM STATEMENT

### The Challenge of Campus Security

**Problems with Traditional Surveillance:**
- 🔴 **Human fatigue** — Guards cannot monitor 10+ camera feeds 24/7
- 🔴 **Reactive approach** — Incidents discovered only during post-event review
- 🔴 **No automated alerts** — Critical events go unnoticed in real-time
- 🔴 **No analytics** — Raw footage provides no metrics or trends
- 🔴 **Single-source limitation** — Cannot integrate diverse camera types

**Statistics:**
- Security operators miss ~95% of events after 22 minutes of monitoring
- Average incident response time: 7-15 minutes without automation
- Campus security budgets: 60-80% spent on personnel

---

## SLIDE 3: PROPOSED SOLUTION

### CrowdLens — Intelligent Surveillance Platform

**An AI-first approach to campus security:**

1. **Automatic Detection** — YOLOv11m detects all persons and objects in real-time
2. **Persistent Tracking** — SORT maintains identity across frames
3. **Behavioural Analysis** — 6 anomaly types detected automatically
4. **Instant Alerts** — Email + browser + audio notifications
5. **AI Assistant** — Natural-language incident querying

**Key Differentiator:** No GPU required — runs on standard laptop hardware

---

## SLIDE 4: OBJECTIVES

### Project Objectives

**Primary:**
1. Real-time person/object detection using deep learning
2. Multi-object tracking with ID persistence
3. Automatic anomaly detection (6 types)
4. Instant automated alerting
5. Intuitive web-based monitoring dashboard

**Secondary:**
1. Multi-source support (webcam, video, RTSP, HTTP)
2. AI-powered reporting and analysis
3. Configurable detection parameters
4. Evidence archival with snapshots
5. CPU-efficient operation

---

## SLIDE 5: TECHNOLOGY STACK

### Tech Stack Overview

| Layer | Technology |
|-------|-----------|
| **AI/ML** | YOLOv11m, ONNX Runtime, HuggingFace Fall Model |
| **Backend** | Python 3.11, FastAPI, Uvicorn, WebSockets |
| **Tracking** | SORT Algorithm, Kalman Filter, Hungarian Algorithm |
| **Frontend** | React 19, Vite 7, TailwindCSS, Canvas 2D |
| **Database** | SQLite (WAL mode) |
| **Notifications** | AWS SES, Web Notifications API, Web Audio API |
| **Streaming** | FFmpeg (RTSP/HTTP), WebSocket binary frames |
| **AI Assistant** | OpenAI GPT API |

---

## SLIDE 6: SYSTEM ARCHITECTURE

### High-Level Architecture Diagram

```
[Camera/Video] → [Frame Capture] → [YOLOv11m Detection]
                                          ↓
[WebSocket Broadcast] ← [Alert System] ← [SORT Tracking]
        ↓                                     ↓
[React Dashboard]                    [Anomaly Detection]
(Canvas 2D Rendering)                (6 algorithms)
```

**Communication:**
- WebSocket /ws → Real-time frame data (server→client)
- WebSocket /ws/cam → Webcam frames (client→server)
- REST API → Configuration, uploads, history

---

## SLIDE 7: DETECTION ENGINE

### YOLOv11m Object Detection

**Model:** YOLOv11m (Medium) — 20M parameters
**Input:** 640×640 RGB image
**Output:** Bounding boxes + class IDs + confidence scores

**Detected Classes:**
- Person (class 0) — primary target
- Car (class 2) — vehicle monitoring
- Backpack (class 24) — baggage detection
- Handbag/Baggage (class 26) — unattended object
- Suitcase (class 28) — baggage detection

**Inference Strategy:**
1. ONNX Runtime + GPU (fastest)
2. ONNX Runtime + CPU (portable)
3. PyTorch + GPU
4. PyTorch + CPU (always works)

---

## SLIDE 8: TRACKING ENGINE

### SORT Multi-Object Tracker

**Algorithm Components:**
1. **Kalman Filter** — Predicts next position (7D state vector)
2. **Hungarian Algorithm** — Optimal detection-to-tracker matching
3. **IoU Metric** — Overlap-based similarity cost

**Key Features:**
- Global thread-safe ID counter
- Extended hold for baggage (120 frames vs 3 for persons)
- Center-distance fallback for small/distant objects
- Class-aware matching (person≠object)

**State Vector:** [center_x, center_y, area, aspect_ratio, v_cx, v_cy, v_area]

---

## SLIDE 9: ANOMALY DETECTION

### 6 Types of Anomaly Detection

| # | Anomaly | Method | Default Threshold |
|---|---------|--------|-------------------|
| 1 | **Running** | Speed > threshold for 0.8s | 270 px/s |
| 2 | **Overcrowding** | Person count > N | 4 people |
| 3 | **Unattended Object** | Bag stationary + owner absent | 5s + 2s grace |
| 4 | **Fall Detection** | Dedicated HF model + persistence | 1.2s confirm |
| 5 | **Fight Suspected** | Pair proximity + high speed | 180px + 240px/s |
| 6 | **Restricted Zone** | Person in forbidden area | 0.6s dwell |

---

## SLIDE 10: FALL DETECTION DETAIL

### Dedicated Fall Detection Model

**Model:** HuggingFace — melihuzunoglu/human-fall-detection
**Architecture:** YOLOv11 fine-tuned on fall dataset

**Pipeline:**
1. Run fall model on **source-resolution** frame (not downscaled)
2. Filter false positives:
   - Reject boxes in top 38% of frame (ceiling objects)
   - Reject boxes with width/height < 0.65 (standing people)
   - Reject tiny boxes (< 1.2% of frame area)
3. Track persistence via IoU matching across frames
4. Confirm only after 1.2 seconds of continuous detection
5. Hold confirmed falls for 3 seconds (prevent flicker)

---

## SLIDE 11: FRONTEND DASHBOARD

### React Dashboard Features

**Live Surveillance Canvas (1280×720):**
- HTML5 Canvas 2D rendering at 60fps
- 5 overlay styles: Corners, Dots, Heatmap, Chips, Auto
- Bounding box smoothing (exponential interpolation)
- Anomaly warning overlays (pulsing animations)

**Dashboard Controls:**
- Sound toggle (Web Audio tones per anomaly type)
- Browser push notifications
- Webcam / Video Upload / Stream buttons
- Evidence snapshot capture
- Restricted zone toggle

**Pages:** Dashboard | Alert History | AI Assistant | Settings

---

## SLIDE 12: ALERT SYSTEM

### Multi-Channel Alert Notifications

```
Anomaly Detected
    │
    ├── Audio Alert (Web Audio API, different tones per type)
    │
    ├── Browser Push Notification (Web Notifications API)
    │
    ├── Email Alert (AWS SES, HTML-formatted)
    │   └── Cooldown: 45s per type+source
    │
    ├── Evidence Snapshot (JPEG saved, 7-day retention)
    │
    └── Database Record (SQLite, persistent)
```

**Alert Cooldown Logic:**
- 5-second cooldown per (anomaly_type, track_id) pair
- Prevents alert flooding while maintaining responsiveness

---

## SLIDE 13: AI ASSISTANT

### GPT-Powered Intelligence

**Three Modes:**

1. **Incident Reports** — Per-alert AI-generated analysis
   - Generates detailed incident reports for any recorded alert
   - Includes context, severity assessment, recommendations

2. **Alert Chat** — Natural-language querying
   - "How many fights were detected today?"
   - "Which zone has the most intrusions?"
   - Context: last 50 alerts provided to GPT

3. **Live Narrator** — Real-time scene description
   - Describes what's currently happening
   - Auto-refresh every 10 seconds
   - Includes entity counts and anomaly status

---

## SLIDE 14: INPUT SOURCES

### Multi-Source Camera Support

| Source | How It Works |
|--------|-------------|
| **Browser Webcam** | getUserMedia → capture frames at 5fps → send JPEG via /ws/cam → YOLO on server |
| **Video Upload** | File upload (≤500MB) → server loops video → YOLO at native FPS |
| **RTSP Stream** | FFmpeg opens RTSP URL → pipes raw frames → YOLO at 15fps |
| **HTTP Stream** | FFmpeg or fetch() → MJPEG parsing → YOLO processing |
| **Local IP Camera** | Browser fetch() → MJPEG/snapshot relay → /ws/cam → YOLO |

**Special Features:**
- Camera profile saving (localStorage)
- Multi-camera USB device selection
- SSRF protection (configurable for campus use)

---

## SLIDE 15: RESULTS & PERFORMANCE

### System Performance

| Metric | Value |
|--------|-------|
| Detection FPS (CPU) | 5-8 FPS |
| Detection FPS (GPU) | 15-25 FPS |
| WebSocket latency | <100 ms |
| End-to-end latency | 200-400 ms |
| Model loading | 10-30 seconds |
| Memory usage | ~2-4 GB |

### Detection Accuracy (YOLO11m on COCO)
- Person detection mAP: ~55% (mAP50-95)
- Baggage detection mAP: ~45% (mAP50-95)

---

## SLIDE 16: DEMO SCREENSHOTS

### Key Interfaces

1. **Live Dashboard** — Canvas with tracking overlays + metric pills
2. **Alert History** — Table with chart + filtering + export
3. **Settings Page** — Threshold sliders with live preview
4. **AI Assistant** — Chat interface with streaming responses

*(Include actual screenshots from running application)*

---

## SLIDE 17: COMPARISON WITH EXISTING SYSTEMS

### Why CrowdLens is Superior

| Feature | Commercial NVR | OpenCV Basic | **CrowdLens** |
|---------|---------------|-------------|---------------|
| Cost | $$$$ | Free | Free |
| Deep Learning | Some | ❌ | ✅ YOLOv11m |
| Multi-object tracking | Limited | ❌ | ✅ SORT+Kalman |
| Anomaly types | 1-2 | ❌ | ✅ 6 types |
| AI reports | ❌ | ❌ | ✅ GPT |
| Web dashboard | ❌ | ❌ | ✅ React |
| Open source | ❌ | ✅ | ✅ |
| GPU optional | Some | ✅ | ✅ |
| Real-time config | ❌ | ❌ | ✅ |

---

## SLIDE 18: FUTURE SCOPE

### Planned Enhancements

**Short-term:**
- Multi-camera simultaneous processing
- Pose estimation for improved fight/fall detection
- Advanced crowd density analytics

**Medium-term:**
- Weapon detection model integration
- Smoke/fire detection
- License plate recognition (ANPR)
- Mobile application (React Native)

**Long-term:**
- Cloud-hosted scalable deployment (Kubernetes)
- Federated learning for privacy-preserving model improvement
- Predictive analytics (incident prediction before occurrence)
- Digital twin campus visualization (3D)

---

## SLIDE 19: CHALLENGES & LIMITATIONS

### Current Limitations

1. **Single source at a time** — Only one camera/video processes simultaneously
2. **Fight detection accuracy** — Heuristic-only, not vision-based
3. **CPU performance** — 5-8 FPS on CPU (adequate but not real-time 30fps)
4. **No authentication** — Open dashboard (suitable for internal campus use)
5. **Fall detection edge cases** — May false-positive on crouching/bending

### Challenges Overcome
- ONNX export failures → multi-strategy model loading
- WebSocket backpressure → frame dropping + bufferedAmount check
- Camera CORS issues → raw fetch() MJPEG parsing (no canvas taint)
- Track ID flickering → extended hold windows for baggage
- FFmpeg pipe deadlock → stderr to file + reader thread

---

## SLIDE 20: CONCLUSION

### Summary

**CrowdLens successfully demonstrates:**

✅ Real-time AI-powered surveillance is achievable with open-source tools
✅ Deep learning (YOLO) + tracking (SORT) provides robust person monitoring
✅ Multiple anomaly types can be detected simultaneously
✅ Modern web technologies enable rich, responsive monitoring dashboards
✅ The system operates on commodity hardware without GPU requirement
✅ AI assistants add natural-language intelligence to security operations

**Key Contribution:**
A complete, working, end-to-end intelligent surveillance system that bridges the gap between expensive commercial solutions and basic motion-detection approaches.

---

## SLIDE 21: THANK YOU + Q&A

**Thank You!**

**Questions?**

**Links:**
- Repository: github.com/NikhilGupta777/CrowdLens
- Tech: Python 3.11 + FastAPI + React 19 + YOLOv11m + SORT

---

*PPT Content Guide — CrowdLens Campus AI Monitor*
