# CrowdLens — Complete Feature List & Module Breakdown

---

## MODULE 1: OBJECT DETECTION ENGINE

### Files: `backend/detector.py`, `backend/config.py`

| Feature | Status | Description |
|---------|--------|-------------|
| YOLOv11m model loading | ✅ Done | Multi-strategy (ONNX GPU → ONNX CPU → PyTorch GPU → PyTorch CPU) |
| ONNX export (one-time) | ✅ Done | Auto-exports .pt → .onnx for faster inference |
| GPU auto-detection | ✅ Done | Detects CUDA availability, uses if possible |
| Warm-up inference | ✅ Done | Runs dummy frame on load to pre-allocate memory |
| Person detection | ✅ Done | Class 0, confidence ≥ mode-specific threshold |
| Vehicle detection | ✅ Done | Class 2 (car) |
| Baggage detection | ✅ Done | Classes 24, 26, 28 (backpack, handbag, suitcase) |
| Baggage deduplication | ✅ Done | Merges overlapping bag detections to one "baggage" entity |
| Two-tier confidence | ✅ Done | Baggage floor (0.10) + normal threshold per mode |
| Thread-safe inference | ✅ Done | Global lock prevents concurrent model access |

---

## MODULE 2: MULTI-OBJECT TRACKING

### Files: `backend/sort_tracker.py`

| Feature | Status | Description |
|---------|--------|-------------|
| Kalman Filter prediction | ✅ Done | 7D state vector per tracker |
| Hungarian algorithm matching | ✅ Done | Optimal assignment via scipy.linear_sum_assignment |
| IoU-based cost (persons) | ✅ Done | Standard bounding box overlap |
| Center-distance cost (bags) | ✅ Done | Fallback for small/jumping objects |
| Class-aware matching | ✅ Done | Person tracks cannot match object detections |
| Track creation | ✅ Done | New tracker for unmatched detections |
| Track pruning | ✅ Done | Remove trackers exceeding hold limit |
| Extended hold (baggage) | ✅ Done | 120 frames (strong) / 45 frames (weak) |
| Extended hold (objects) | ✅ Done | 30 frames for vehicles |
| Global ID counter | ✅ Done | Thread-safe, never resets (prevents collisions) |
| Predicted box output | ✅ Done | Returns predicted position when detection missed |

---

## MODULE 3: ANOMALY DETECTION

### Files: `backend/anomaly.py`

| Feature | Status | Description |
|---------|--------|-------------|
| Running detection | ✅ Done | Speed history + threshold + persistence |
| Overcrowding detection | ✅ Done | Person count exceeds threshold |
| Unattended object detection | ✅ Done | Stationary bag + owner absent |
| Owner identification | ✅ Done | Nearest person within proximity radius |
| Owner absence tracking | ✅ Done | Grace period before alerting |
| Fall detection integration | ✅ Done | Dedicated model + temporal persistence |
| Fall false-positive filtering | ✅ Done | Area, position, aspect ratio checks |
| Fight suspicion (heuristic) | ✅ Done | Pair proximity + pair speed + persistence |
| Restricted zone detection | ✅ Done | Point-in-rectangle + dwell time |
| Track history management | ✅ Done | 20-frame position history per track |
| Stale track cleanup | ✅ Done | Remove history for disappeared tracks |

---

## MODULE 4: FALL DETECTION

### Files: `backend/fall_detector.py`

| Feature | Status | Description |
|---------|--------|-------------|
| HuggingFace model download | ✅ Done | Auto-downloads melihuzunoglu/human-fall-detection |
| Local model override | ✅ Done | FALL_MODEL_LOCAL_PATH env var |
| Source-resolution inference | ✅ Done | Better posture detection than downscaled |
| "Fallen" class filtering | ✅ Done | Only considers "fallen"/"fall" labels |
| Thread-safe inference | ✅ Done | Lock-protected model access |
| Confidence threshold | ✅ Done | Configurable (default 0.35) |

---

## MODULE 5: SIMULATION ENGINE

### Files: `backend/simulation.py`

| Feature | Status | Description |
|---------|--------|-------------|
| Entity spawning | ✅ Done | Random persons + objects |
| Movement simulation | ✅ Done | Velocity-based with boundary bouncing |
| Running behavior | ✅ Done | Random speed bursts (15% chance) |
| Entity lifecycle | ✅ Done | 10-30s lifetime with auto-removal |
| Stationary objects | ✅ Done | Fixed-position baggage entities |
| Boundary enforcement | ✅ Done | Entities stay within frame bounds |

---

## MODULE 6: DATABASE & PERSISTENCE

### Files: `backend/database.py`

| Feature | Status | Description |
|---------|--------|-------------|
| SQLite with WAL mode | ✅ Done | Concurrent read/write performance |
| Thread-local connections | ✅ Done | Thread safety |
| Async wrappers | ✅ Done | asyncio.to_thread for non-blocking |
| Alert insertion | ✅ Done | Stores anomaly JSON + metadata |
| Alert loading (paginated) | ✅ Done | Ordered by timestamp DESC |
| Alert clearing | ✅ Done | Delete all records |
| Startup hydration | ✅ Done | Load DB into in-memory deque |
| Indexed queries | ✅ Done | Index on timestamp DESC |

---

## MODULE 7: API & WEBSOCKET

### Files: `backend/main.py`

| Feature | Status | Description |
|---------|--------|-------------|
| Health check endpoint | ✅ Done | GET /api/health |
| Stats endpoint | ✅ Done | GET /api/stats |
| Alert history endpoint | ✅ Done | GET /api/alerts/history |
| Alert clear endpoint | ✅ Done | POST /api/alerts/clear |
| Config get/put endpoints | ✅ Done | GET/PUT /api/config |
| Video upload endpoint | ✅ Done | POST /api/video/upload (500MB limit) |
| Video start/stop | ✅ Done | POST /api/video/start, /api/video/stop |
| Video status | ✅ Done | GET /api/video/status |
| Stream start/stop | ✅ Done | POST /api/stream/start, /api/stream/stop |
| Stream status | ✅ Done | GET /api/stream/status |
| Webcam start/stop | ✅ Done | POST /api/webcam/start, /api/webcam/stop |
| WebSocket broadcast (/ws) | ✅ Done | Server → all connected clients |
| WebSocket camera (/ws/cam) | ✅ Done | Client → server (JPEG frames) |
| Archive endpoints | ✅ Done | GET/POST /api/archive/* |
| Notification endpoints | ✅ Done | GET/POST /api/notify/* |
| AI endpoints | ✅ Done | POST /api/ai/report, /api/ai/chat, /api/ai/narrate |
| CORS middleware | ✅ Done | Allow all origins |
| SSRF validation | ✅ Done | Stream URL safety check |
| Video processing loop | ✅ Done | Async task with frame-accurate playback |
| Stream processing loop | ✅ Done | FFmpeg pipe + reader thread |
| Webcam processing loop | ✅ Done | Queue-based frame processing |

---

## MODULE 8: NOTIFICATION SYSTEM

### Files: `backend/main.py` (notification section)

| Feature | Status | Description |
|---------|--------|-------------|
| Alert cooldown (5s) | ✅ Done | Per (type, track_id) deduplication |
| Email alerts (AWS SES) | ✅ Done | HTML-formatted via aws cli |
| Email cooldown (45s) | ✅ Done | File-based cross-process lock |
| Email metrics tracking | ✅ Done | attempts, sent, suppressed, failed |
| Test email endpoint | ✅ Done | POST /api/notify/test |
| Evidence snapshots | ✅ Done | JPEG capture on alert |
| Archive retention (7 days) | ✅ Done | Auto-cleanup of old snapshots |
| Manual snapshot capture | ✅ Done | POST /api/archive/capture |

---

## MODULE 9: FRONTEND — DASHBOARD PAGE

### Files: `artifacts/company-ai/src/pages/Dashboard.tsx`

| Feature | Status | Description |
|---------|--------|-------------|
| Live surveillance canvas | ✅ Done | 1280×720 Canvas 2D |
| Metric pills (4 stats) | ✅ Done | Persons, objects, anomalies, tracks |
| Sound toggle | ✅ Done | Enable/disable audio alerts |
| Browser notification toggle | ✅ Done | Web Notifications API |
| Webcam panel (USB) | ✅ Done | getUserMedia + device selection |
| Webcam panel (local network) | ✅ Done | MJPEG/snapshot relay |
| Video upload panel | ✅ Done | Drag-drop, progress, start/stop |
| Stream panel | ✅ Done | URL input, camera profiles |
| Camera profile saving | ✅ Done | localStorage persistence |
| Evidence snapshot button | ✅ Done | Manual capture |
| Restricted zone toggle | ✅ Done | Enable/disable with API call |
| Critical alert title badge | ✅ Done | Page title shows alert count |
| Source mode indicators | ✅ Done | Mode-specific UI states |
| Multi-camera device selector | ✅ Done | enumerateDevices() |

---

## MODULE 10: FRONTEND — CANVAS RENDERING

### Files: `artifacts/company-ai/src/components/SimulationCanvas.tsx`

| Feature | Status | Description |
|---------|--------|-------------|
| Corner brackets style | ✅ Done | L-shaped markers with labels |
| Glowing dots style | ✅ Done | Foot-position dots with glow |
| Density heatmap style | ✅ Done | Radial gradient overlays |
| ID chips style | ✅ Done | Floating labels only |
| Auto style (adaptive) | ✅ Done | Switches based on crowd count |
| Bounding box smoothing | ✅ Done | Exponential interpolation |
| Anomaly overlays | ✅ Done | Pulsing circles/boxes per type |
| Restricted zone rendering | ✅ Done | Dashed rectangle + name label |
| Video frame background | ✅ Done | Base64 JPEG decoding + drawImage |
| Webcam background | ✅ Done | Direct video element drawImage |
| Mode HUD badges | ✅ Done | YOLO·VIDEO / WEBCAM / STREAM |
| Idle state display | ✅ Done | Dark gradient + instructions |
| Loading state display | ✅ Done | Grid pattern + loading text |
| Performance memoization | ✅ Done | Custom memo comparator |

---

## MODULE 11: FRONTEND — ALERT HISTORY

### Files: `artifacts/company-ai/src/pages/AlertHistory.tsx`

| Feature | Status | Description |
|---------|--------|-------------|
| Data table | ✅ Done | Time, type, severity, details, position, source, evidence |
| Summary cards | ✅ Done | Per-type count with colors |
| Bar chart (Recharts) | ✅ Done | 10-minute trend visualization |
| Type filtering | ✅ Done | Click filter buttons |
| Text search | ✅ Done | Search by type, track, zone, source |
| CSV export | ✅ Done | Full data export with escaping |
| JSON export | ✅ Done | Full data export |
| Auto-refresh (3s) | ✅ Done | Background polling |
| Clear all (with confirm) | ✅ Done | Two-click confirmation |
| Evidence thumbnails | ✅ Done | Inline snapshot preview |
| Chart toggle | ✅ Done | Show/hide bar chart |

---

## MODULE 12: FRONTEND — AI ASSISTANT

### Files: `artifacts/company-ai/src/pages/AIPanel.tsx`

| Feature | Status | Description |
|---------|--------|-------------|
| Live Narrator tab | ✅ Done | Scene description from current frame |
| Auto-refresh narration (10s) | ✅ Done | Periodic AI scene updates |
| Incident Reports tab | ✅ Done | Per-alert AI report generation |
| Alert Chat tab | ✅ Done | Natural-language querying |
| Streaming responses (SSE) | ✅ Done | Progressive text display |
| Suggestion prompts | ✅ Done | Pre-built query suggestions |
| Context injection | ✅ Done | Last 50 alerts sent to GPT |
| Loading states | ✅ Done | Spinner + disabled buttons |

---

## MODULE 13: FRONTEND — SETTINGS

### Files: `artifacts/company-ai/src/pages/Settings.tsx`

| Feature | Status | Description |
|---------|--------|-------------|
| Overlay style selector | ✅ Done | Visual cards with SVG previews |
| Box smoothing slider | ✅ Done | Real-time canvas update |
| Overcrowding threshold | ✅ Done | Premium slider UI |
| Running speed threshold | ✅ Done | Premium slider UI |
| Unattended object time | ✅ Done | Premium slider UI |
| Stationary threshold | ✅ Done | Premium slider UI |
| Owner proximity radius | ✅ Done | Premium slider UI |
| Owner absence grace | ✅ Done | Premium slider UI |
| Fall model confidence | ✅ Done | Premium slider UI |
| Fall persistence time | ✅ Done | Premium slider UI |
| Restricted zone toggle | ✅ Done | Toggle card |
| Restricted zone dwell | ✅ Done | Premium slider UI |
| Fight detection toggle | ✅ Done | Toggle card |
| Fight proximity | ✅ Done | Premium slider UI |
| Fight pair speed | ✅ Done | Premium slider UI |
| Fight persistence | ✅ Done | Premium slider UI |
| Fight hit streak | ✅ Done | Premium slider UI |
| Alert cooldown | ✅ Done | Premium slider UI |
| Live apply (PUT /api/config) | ✅ Done | Instant backend update |
| Config polling (sync) | ✅ Done | Keeps UI in sync |

---

## MODULE 14: FRONTEND — CORE HOOKS

### Files: `artifacts/company-ai/src/hooks/`

| Hook | File | Purpose |
|------|------|---------|
| useSimulation | useSimulation.ts | WebSocket connection + frame state |
| useCamProcessor | useCamProcessor.ts | Webcam JPEG capture → /ws/cam |
| useLocalCamRelay | useLocalCamRelay.ts | Network camera MJPEG/snapshot relay |
| useAlertSound | useAlertSound.ts | Web Audio API alert tones |
| useNotifications | useNotifications.ts | Browser push notifications |
| useStickyAnomalies | useStickyAnomalies.ts | Anomaly display persistence (8s) |
| useTheme | useTheme.ts | Dark/Light mode toggle |
| useIsMobile | use-mobile.tsx | Responsive breakpoint detection |

---

## MODULE 15: FRONTEND — LAYOUT & NAVIGATION

### Files: `artifacts/company-ai/src/components/Layout.tsx`

| Feature | Status | Description |
|---------|--------|-------------|
| Sidebar navigation rail | ✅ Done | Icon buttons for 4 pages |
| Mobile drawer | ✅ Done | Slide-in sidebar on mobile |
| Header with clock | ✅ Done | Live time + branding |
| Threat level indicator | ✅ Done | Secure / Warning / Critical |
| Connection status | ✅ Done | WebSocket connected indicator |
| Dark/Light mode toggle | ✅ Done | Sun/Moon button in header |
| Responsive layout | ✅ Done | Mobile-first with breakpoints |

---

## SUMMARY: TOTAL FEATURE COUNT

| Category | Count |
|----------|-------|
| Backend Detection Features | 10 |
| Tracking Features | 11 |
| Anomaly Detection Features | 11 |
| Fall Detection Features | 6 |
| Database Features | 8 |
| API/WebSocket Features | 24 |
| Notification Features | 8 |
| Dashboard Features | 14 |
| Canvas Rendering Features | 14 |
| Alert History Features | 11 |
| AI Assistant Features | 8 |
| Settings Features | 18 |
| Hook Features | 8 |
| Layout Features | 7 |
| **TOTAL** | **~158 features** |

---

*Feature List & Module Breakdown — CrowdLens Campus AI Monitor*
