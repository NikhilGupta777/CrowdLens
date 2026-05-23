import numpy as np
import backend.config as _cfg

# Re-export for any external code that references these as module attributes.
UNATTENDED_CLASSES = _cfg.UNATTENDED_CLASSES


class AnomalyDetector:
    def __init__(self):
        self.track_history: dict = {}
        self.running_candidate_since: dict[int, float] = {}
        self.running_last_fast_at: dict[int, float] = {}
        self.fall_candidate_since: dict[object, float] = {}
        self.zone_entry_since: dict[tuple[int, str], float] = {}
        self.fight_candidate_since: dict[tuple[int, int], float] = {}
        self.fight_last_alert_at: dict[tuple[int, int], float] = {}
        # Last frame in which a pair satisfied close+fast+stable. Used by the
        # fight grace-time tolerance so a single-frame dip doesn't wipe
        # accumulated persistence (mirrors RUNNING_RESET_GRACE_TIME).
        self.fight_last_qualifying_at: dict[tuple[int, int], float] = {}
        self.owner_absent_since: dict[int, float] = {}
        self.object_owner_id: dict[int, int] = {}
        self.object_owner_last_near: dict[int, float] = {}
        self.object_stationary_since: dict[int, float] = {}
        self.object_alert_active_until: dict[int, float] = {}
        self.object_alert_payload: dict[int, dict] = {}
        self.fall_candidate_boxes: dict[object, list[float]] = {}
        self.fall_last_seen_at: dict[object, float] = {}
        self.fall_active_until: dict[object, float] = {}
        self.fall_active_payload: dict[object, dict] = {}
        self.loiter_first_seen: dict[int, float] = {}
        self.loiter_anchor: dict[int, tuple[float, float]] = {}
        # Last bbox + class observed for each baggage track; used to seed the
        # ghost cache when a track is pruned. Person tracks are not stored here.
        self.object_last_bbox: dict[int, tuple[int, list[float]]] = {}
        # Spatial-cell ghost cache for baggage tracks that just died.
        # Key: (cell_x, cell_y) using UNATTENDED_GHOST_CELL_PX.
        # Value: {"expires_at", "stationary_since", "owner_id",
        #         "owner_absent_since", "bbox", "class_id"}.
        self.baggage_ghost_cache: dict[tuple[int, int], dict] = {}

    # ── Helpers ──────────────────────────────────────────────────────────────

    @staticmethod
    def _iou(a: list[float], b: list[float]) -> float:
        """Intersection-over-Union for two [x1, y1, x2, y2] boxes."""
        ax1, ay1, ax2, ay2 = a
        bx1, by1, bx2, by2 = b
        ix1 = max(ax1, bx1)
        iy1 = max(ay1, by1)
        ix2 = min(ax2, bx2)
        iy2 = min(ay2, by2)
        iw = max(0.0, ix2 - ix1)
        ih = max(0.0, iy2 - iy1)
        inter = iw * ih
        if inter <= 0:
            return 0.0
        area_a = max(0.0, ax2 - ax1) * max(0.0, ay2 - ay1)
        area_b = max(0.0, bx2 - bx1) * max(0.0, by2 - by1)
        union = area_a + area_b - inter
        return inter / union if union > 0 else 0.0

    @staticmethod
    def _point_in_polygon(px: float, py: float, points: list) -> bool:
        """Ray-casting point-in-polygon test for an arbitrary polygon."""
        if not points or len(points) < 3:
            return False
        inside = False
        j = len(points) - 1
        for i in range(len(points)):
            xi, yi = float(points[i][0]), float(points[i][1])
            xj, yj = float(points[j][0]), float(points[j][1])
            intersect = ((yi > py) != (yj > py)) and (
                px < (xj - xi) * (py - yi) / (yj - yi + 1e-12) + xi
            )
            if intersect:
                inside = not inside
            j = i
        return inside


    @staticmethod
    def _bbox_center(track: dict) -> tuple[float, float]:
        return (
            (float(track["x1"]) + float(track["x2"])) / 2.0,
            (float(track["y1"]) + float(track["y2"])) / 2.0,
        )

    @staticmethod
    def _bbox_foot(track: dict) -> tuple[float, float]:
        """Foot point = bottom center of bbox."""
        cx = (float(track["x1"]) + float(track["x2"])) / 2.0
        return (cx, float(track["y2"]))

    @staticmethod
    def _distance_point_to_bbox(px: float, py: float, box: dict) -> float:
        bx1 = float(box["x1"])
        by1 = float(box["y1"])
        bx2 = float(box["x2"])
        by2 = float(box["y2"])
        nx = min(max(px, bx1), bx2)
        ny = min(max(py, by1), by2)
        return float(np.hypot(px - nx, py - ny))

    @staticmethod
    def _bbox_overlaps_rect(track: dict, rx1: float, ry1: float, rx2: float, ry2: float) -> bool:
        """Check if a track bbox overlaps the given rectangle."""
        tx1 = float(track["x1"])
        ty1 = float(track["y1"])
        tx2 = float(track["x2"])
        ty2 = float(track["y2"])
        return tx1 < rx2 and tx2 > rx1 and ty1 < ry2 and ty2 > ry1


    def _distance_object_to_person(self, obj_track: dict, person_track: dict) -> float:
        ox, oy = self._bbox_center(obj_track)
        px, _ = self._bbox_center(person_track)
        feet_y = float(person_track["y2"])
        return min(
            self._distance_point_to_bbox(ox, oy, person_track),
            float(np.hypot(ox - px, oy - feet_y)),
        )

    @staticmethod
    def _is_stationary(history: list, threshold: float | None = None) -> bool:
        if len(history) < 4:
            return False
        if threshold is None:
            threshold = _cfg.STATIONARY_THRESHOLD
        recent = history[-12:]
        xs = [p[0] for p in recent]
        ys = [p[1] for p in recent]
        spread = float(np.hypot(max(xs) - min(xs), max(ys) - min(ys)))
        return spread <= threshold

    # ── Running Detection (fixed: dual-metric + grace time) ──────────────────


    def _check_running(self, track_id: int, track: dict, history: list,
                       current_time: float) -> dict | None:
        """
        Dual-metric running detection with anti-jitter floor:
          1. Raw pixel speed > RUNNING_SPEED_THRESHOLD (legacy fallback)
          2. Body-heights/sec > RUNNING_BODY_HEIGHTS_PER_SEC AND
             raw pixel speed > RUNNING_PIXEL_FLOOR (anti-jitter)
        Either path triggers running. The pixel floor on the body-heights
        path prevents tiny bboxes (e.g. distant figures) from producing
        huge body-heights/sec from a few pixels of YOLO jitter.

        The legacy raw-speed path still scales naturally because tracks
        coming in here have already been normalised to the canonical
        FRAME_WIDTH x FRAME_HEIGHT canvas in main._build_tracks_from_yolo.
        Uses grace time so a 1-frame speed dip doesn't reset persistence.
        """
        hit_streak = int(track.get("hit_streak", 0))
        if hit_streak < _cfg.RUNNING_MIN_HIT_STREAK:
            # Not enough confirmed frames — reset
            self.running_candidate_since.pop(track_id, None)
            self.running_last_fast_at.pop(track_id, None)
            return None

        recent = history[-5:]
        time_span = recent[-1][2] - recent[0][2]
        if time_span < 0.01:
            return None

        dist = 0.0
        for i in range(1, len(recent)):
            dist += np.hypot(recent[i][0] - recent[i-1][0],
                             recent[i][1] - recent[i-1][1])
        avg_speed = dist / time_span

        # Body-heights/sec: average height from recent history entries
        heights = [entry[4] for entry in recent if len(entry) >= 5]
        avg_height = sum(heights) / len(heights) if heights else 1.0
        body_heights_per_sec = avg_speed / max(avg_height, 1.0)

        pixel_floor = float(getattr(_cfg, "RUNNING_PIXEL_FLOOR", 60.0))
        is_fast_raw = avg_speed > _cfg.RUNNING_SPEED_THRESHOLD
        is_fast_relative = (
            body_heights_per_sec > _cfg.RUNNING_BODY_HEIGHTS_PER_SEC
            and avg_speed > pixel_floor
        )
        is_fast = is_fast_raw or is_fast_relative

        if is_fast:
            self.running_last_fast_at[track_id] = current_time
            if track_id not in self.running_candidate_since:
                self.running_candidate_since[track_id] = current_time
        else:
            # Grace time: tolerate brief dips without resetting
            last_fast = self.running_last_fast_at.get(track_id, 0.0)
            grace = getattr(_cfg, "RUNNING_RESET_GRACE_TIME", 0.4)
            if (current_time - last_fast) > grace:
                self.running_candidate_since.pop(track_id, None)
                self.running_last_fast_at.pop(track_id, None)
                return None

        candidate_start = self.running_candidate_since.get(track_id)
        if candidate_start is None:
            return None
        elapsed = current_time - candidate_start
        if elapsed >= _cfg.RUNNING_PERSISTENCE_TIME:
            cx, cy = self._bbox_center(track)
            # Confidence reflects how much the metrics exceed their thresholds.
            speed_ratio = avg_speed / max(_cfg.RUNNING_SPEED_THRESHOLD, 1.0)
            relative_ratio = body_heights_per_sec / max(_cfg.RUNNING_BODY_HEIGHTS_PER_SEC, 0.1)
            score = max(speed_ratio, relative_ratio)
            confidence = float(min(1.0, max(0.0, (score - 0.9) / 0.6)))
            return {
                "type": "running",
                "track_id": track_id,
                "avg_speed": round(float(avg_speed), 1),
                "body_heights_per_sec": round(float(body_heights_per_sec), 2),
                "confidence": round(confidence, 2),
                "position": [cx, cy],
            }
        return None


    # ── Unattended Object (fixed: bystander-attends + ghost cache) ──────────

    @staticmethod
    def _ghost_cell_key(cx: float, cy: float) -> tuple[int, int]:
        """Spatial-cell key for ghost cache lookups."""
        cell_px = max(16, int(getattr(_cfg, "UNATTENDED_GHOST_CELL_PX", 96)))
        return (int(cx // cell_px), int(cy // cell_px))

    def _save_baggage_ghost(self, track_id: int, current_time: float) -> None:
        """Snapshot the unattended-tracker state of a baggage track that is
        about to be deleted, so a re-detected track in the same area can
        resume the stationary timer instead of restarting from zero."""
        last = self.object_last_bbox.get(track_id)
        if not last:
            return
        class_id, bbox = last
        # Ignore if no useful state has accumulated.
        stationary = self.object_stationary_since.get(track_id)
        if stationary is None:
            return
        cx = (bbox[0] + bbox[2]) / 2.0
        cy = (bbox[1] + bbox[3]) / 2.0
        key = self._ghost_cell_key(cx, cy)
        ttl = float(getattr(_cfg, "UNATTENDED_GHOST_TTL", 8.0))
        self.baggage_ghost_cache[key] = {
            "expires_at": current_time + ttl,
            "stationary_since": stationary,
            "owner_id": self.object_owner_id.get(track_id),
            "owner_absent_since": self.owner_absent_since.get(track_id),
            "owner_last_near": self.object_owner_last_near.get(track_id),
            "bbox": [float(b) for b in bbox],
            "class_id": int(class_id),
        }

    def _try_restore_bag_ghost(self, track_id: int, track: dict,
                               current_time: float) -> bool:
        """If a baggage track in the same spatial cell recently died with an
        accumulated stationary timer, transplant that state to this new track
        so SORT ID churn does not erase the unattended progress."""
        if track_id in self.object_stationary_since:
            return False  # already initialised
        cx, cy = self._bbox_center(track)
        key = self._ghost_cell_key(cx, cy)
        ghost = self.baggage_ghost_cache.get(key)
        if not ghost:
            return False
        if ghost["expires_at"] < current_time:
            self.baggage_ghost_cache.pop(key, None)
            return False
        if int(ghost.get("class_id", -1)) != int(track["class_id"]):
            return False
        # Confirm spatial match against the stored bbox to reject coincidental
        # cell collisions between two unrelated bags.
        cur_bbox = [float(track["x1"]), float(track["y1"]),
                    float(track["x2"]), float(track["y2"])]
        if self._iou(cur_bbox, ghost["bbox"]) < 0.10:
            # No overlap: cells matched but boxes drifted; skip restore.
            return False
        self.object_stationary_since[track_id] = float(ghost["stationary_since"])
        if ghost.get("owner_id") is not None:
            self.object_owner_id[track_id] = int(ghost["owner_id"])
        if ghost.get("owner_absent_since") is not None:
            self.owner_absent_since[track_id] = float(ghost["owner_absent_since"])
        if ghost.get("owner_last_near") is not None:
            self.object_owner_last_near[track_id] = float(ghost["owner_last_near"])
        self.baggage_ghost_cache.pop(key, None)
        return True

    def _emit_unattended_object(
        self,
        track: dict,
        current_time: float,
        history: list,
        person_tracks: list[dict],
    ) -> dict | None:
        track_id = int(track["id"])
        class_name = track.get("class_name", "object")
        cx, cy = self._bbox_center(track)

        # Remember last bbox so the ghost cache can persist this track's
        # state if it dies in the cleanup loop later in this update().
        self.object_last_bbox[track_id] = (
            int(track["class_id"]),
            [float(track["x1"]), float(track["y1"]),
             float(track["x2"]), float(track["y2"])],
        )

        if not self._is_stationary(history, _cfg.STATIONARY_THRESHOLD):
            self.object_stationary_since.pop(track_id, None)
            self.owner_absent_since.pop(track_id, None)
            self.object_alert_active_until.pop(track_id, None)
            self.object_alert_payload.pop(track_id, None)
            return None

        # Try to inherit accumulated stationary state from a recently-killed
        # baggage track in the same spatial cell. Without this, SORT ID churn
        # (occlusion > MAX_AGE then re-detection) restarts the unattended
        # timer from zero and a 5+ second abandonment never reaches threshold.
        self._try_restore_bag_ghost(track_id, track, current_time)

        if track_id not in self.object_stationary_since:
            self.object_stationary_since[track_id] = current_time

        # Find nearest person and check bystander proximity
        nearest_person = None
        nearest_distance = float("inf")
        any_person_near = False
        for person in person_tracks:
            distance = self._distance_object_to_person(track, person)
            if distance < nearest_distance:
                nearest_distance = distance
                nearest_person = person
            if distance <= _cfg.UNATTENDED_OWNER_PROXIMITY_PX:
                any_person_near = True

        # Bystander-attends: if ANY person is near, the object is attended
        bystander_attends = getattr(_cfg, "UNATTENDED_BYSTANDER_ATTENDS", False)

        owner_id = self.object_owner_id.get(track_id)
        if owner_id is None and nearest_person is not None and nearest_distance <= _cfg.UNATTENDED_OWNER_PROXIMITY_PX:
            owner_id = int(nearest_person["id"])
            self.object_owner_id[track_id] = owner_id
            self.object_owner_last_near[track_id] = current_time
            self.owner_absent_since.pop(track_id, None)
            return None


        owner_track = next((p for p in person_tracks if int(p["id"]) == owner_id), None) if owner_id is not None else None
        owner_near = False
        if owner_track is not None:
            owner_distance = self._distance_object_to_person(track, owner_track)
            owner_near = owner_distance <= _cfg.UNATTENDED_OWNER_PROXIMITY_PX

        # If the assigned owner's track disappeared, re-assign to nearest person
        if owner_id is not None and owner_track is None:
            if nearest_person is not None and nearest_distance <= _cfg.UNATTENDED_OWNER_PROXIMITY_PX:
                owner_id = int(nearest_person["id"])
                self.object_owner_id[track_id] = owner_id
                self.object_owner_last_near[track_id] = current_time
                self.owner_absent_since.pop(track_id, None)
                return None

        # Object is attended if owner is near OR (bystander mode) any person is near
        if owner_near or (bystander_attends and any_person_near):
            self.object_owner_last_near[track_id] = current_time
            self.owner_absent_since.pop(track_id, None)
            return None

        if track_id not in self.owner_absent_since:
            self.owner_absent_since[track_id] = current_time
            return None

        stationary_time = current_time - self.object_stationary_since.get(track_id, current_time)
        owner_absent_time = current_time - self.owner_absent_since[track_id]
        if stationary_time < _cfg.UNATTENDED_OBJECT_TIME or owner_absent_time < _cfg.UNATTENDED_OWNER_GRACE_TIME:
            active_payload = self.object_alert_payload.get(track_id)
            if self.object_alert_active_until.get(track_id, 0.0) > current_time and active_payload:
                return dict(active_payload)
            return None

        anomaly = {
            "type": "unattended_object",
            "track_id": track_id,
            "class_name": class_name,
            "duration": round(stationary_time, 1),
            "owner_absent": round(owner_absent_time, 1),
            "position": [cx, cy],
            "bbox": [int(track["x1"]), int(track["y1"]), int(track["x2"]), int(track["y2"])],
        }
        # Confidence scales with how far past the unattended thresholds we are.
        # 1.0 == twice the configured stationary time, capped.
        stationary_score = min(1.0, max(0.0, stationary_time / max(0.1, _cfg.UNATTENDED_OBJECT_TIME)))
        absent_score = min(1.0, max(0.0, owner_absent_time / max(0.1, _cfg.UNATTENDED_OWNER_GRACE_TIME)))
        anomaly["confidence"] = round(min(1.0, 0.5 * stationary_score + 0.5 * absent_score), 2)
        if owner_id is not None:
            anomaly["owner_track_id"] = owner_id
        self.object_alert_active_until[track_id] = current_time + 4.0
        self.object_alert_payload[track_id] = dict(anomaly)
        return anomaly


    # ── Fall Detection (fixed: uses config thresholds properly) ──────────────

    def _emit_fall_anomalies(
        self,
        tracks: list,
        current_time: float,
        fall_detections: list[dict],
        fall_persistence_time: float | None = None,
    ) -> list[dict]:
        anomalies: list[dict] = []
        if fall_persistence_time is None:
            fall_persistence_time = _cfg.FALL_PERSISTENCE_TIME

        frame_area = _cfg.FRAME_WIDTH * _cfg.FRAME_HEIGHT
        min_area_ratio = getattr(_cfg, "FALL_MIN_AREA_RATIO", 0.005)
        aspect_ratio_min = getattr(_cfg, "FALL_ASPECT_RATIO_MIN", 0.40)
        person_iou_min = float(getattr(_cfg, "FALL_PERSON_IOU_MIN", 0.20))
        min_area = frame_area * min_area_ratio

        # Collect person track bboxes once for IoU association.
        person_boxes: list[tuple[int, list[float]]] = []
        for t in tracks:
            if t.get("class_id") == 0:
                person_boxes.append((
                    int(t["id"]),
                    [float(t["x1"]), float(t["y1"]),
                     float(t["x2"]), float(t["y2"])],
                ))

        # Use class-level _iou helper (also used by the ghost cache).
        _iou = self._iou

        active_fall_keys: set[object] = set()
        emitted_keys: set[object] = set()

        for det in fall_detections:
            fx1, fy1, fx2, fy2 = det["bbox"]
            fbox = [float(fx1), float(fy1), float(fx2), float(fy2)]
            confidence = float(det.get("confidence", 0.0))
            fw = max(1.0, float(fx2) - float(fx1))
            fh = max(1.0, float(fy2) - float(fy1))
            area = fw * fh

            # Reject: top-of-frame (ceiling/wall objects)
            if float(fy2) < _cfg.FRAME_HEIGHT * 0.25:
                continue
            # Reject: too small (uses config FALL_MIN_AREA_RATIO)
            if area < min_area:
                continue
            # Reject: clearly upright (uses config FALL_ASPECT_RATIO_MIN)
            if (fw / fh) < aspect_ratio_min:
                continue


            fcx = (fx1 + fx2) / 2.0
            fcy = (fy1 + fy2) / 2.0
            candidate_key: object = ("fall_region", int(fcx // 128), int(fcy // 128))

            # Associate this fall with the best-overlapping person track so the
            # cooldown bucket and downstream alert payload reference the actual
            # person who fell, not a coarse spatial cell. Without this, two
            # simultaneous falls within the same 128 px cell collapse into
            # one alert because they share the same cooldown key.
            best_track_id = None
            best_track_iou = 0.0
            for tid, pbox in person_boxes:
                score = _iou(fbox, pbox)
                if score > best_track_iou:
                    best_track_iou = score
                    best_track_id = tid
            if best_track_iou < person_iou_min:
                best_track_id = None
            if best_track_id is not None:
                # Use the person track id as the cooldown key to keep simultaneous
                # falls separate, while still allowing the spatial-cell fallback
                # below for model-only events without an associated person.
                candidate_key = ("fall_track", int(best_track_id))

            # Reuse existing candidate key when overlap is strong
            best_existing_key = None
            best_existing_iou = 0.0
            for k, prev_box in self.fall_candidate_boxes.items():
                score = _iou(fbox, prev_box)
                if score > best_existing_iou:
                    best_existing_iou = score
                    best_existing_key = k
            if best_existing_key is not None and best_existing_iou >= 0.30:
                candidate_key = best_existing_key

            active_fall_keys.add(candidate_key)
            self.fall_candidate_boxes[candidate_key] = fbox
            self.fall_last_seen_at[candidate_key] = current_time
            if candidate_key not in self.fall_candidate_since:
                self.fall_candidate_since[candidate_key] = current_time
                continue
            elapsed = current_time - self.fall_candidate_since[candidate_key]
            if elapsed >= fall_persistence_time:
                cx = (fx1 + fx2) / 2.0
                cy = (fy1 + fy2) / 2.0
                anomaly = {
                    "type": "fall_detected",
                    "duration": round(elapsed, 1),
                    "confidence": float(round(confidence, 3)),
                    "position": [cx, cy],
                    "bbox": [int(fx1), int(fy1), int(fx2), int(fy2)],
                }
                if best_track_id is not None:
                    anomaly["track_id"] = best_track_id
                else:
                    anomaly["note"] = "hf_fall_model_confirmed"
                anomalies.append(anomaly)
                emitted_keys.add(candidate_key)
                self.fall_active_until[candidate_key] = current_time + float(
                    getattr(_cfg, "FALL_ALERT_HOLD_TIME", 3.0)
                )
                active_payload = {
                    "position": [cx, cy],
                    "bbox": [int(fx1), int(fy1), int(fx2), int(fy2)],
                    "confidence": max(
                        float(round(confidence, 3)),
                        float(self.fall_active_payload.get(candidate_key, {}).get("confidence", 0.0)),
                    ),
                }
                if best_track_id is not None:
                    active_payload["track_id"] = int(best_track_id)
                self.fall_active_payload[candidate_key] = active_payload


        # Keep confirmed falls active during hold window
        for k, until_ts in list(self.fall_active_until.items()):
            if until_ts < current_time:
                self.fall_active_until.pop(k, None)
                self.fall_active_payload.pop(k, None)
                continue
            if k in emitted_keys:
                continue
            payload = self.fall_active_payload.get(k)
            if not payload:
                continue
            since = self.fall_candidate_since.get(k, current_time)
            held = {
                "type": "fall_detected",
                "duration": round(max(0.0, current_time - since), 1),
                "confidence": payload.get("confidence", 0.0),
                "position": payload.get("position"),
                "bbox": payload.get("bbox"),
                "note": "hf_fall_model_confirmed",
            }
            held_track_id = payload.get("track_id")
            if held_track_id is not None:
                held["track_id"] = held_track_id
            anomalies.append(held)

        # Clean up stale fall candidates
        stale_fall_keys = [
            k for k in self.fall_candidate_since
            if (k not in active_fall_keys
                and (current_time - self.fall_last_seen_at.get(k, 0.0)) > 2.0
                and k not in self.fall_active_until)
        ]
        for k in stale_fall_keys:
            self.fall_candidate_since.pop(k, None)
            self.fall_candidate_boxes.pop(k, None)
            self.fall_last_seen_at.pop(k, None)

        return anomalies


    # ── Restricted Zone (fixed: feet-point + bbox overlap + polygon) ────────

    def _check_restricted_zone(self, track: dict, track_id: int,
                               current_time: float) -> list[dict]:
        anomalies = []
        if not _cfg.RESTRICTED_ZONE_ENABLED:
            return anomalies

        cx, cy = self._bbox_center(track)
        foot_x, foot_y = self._bbox_foot(track)
        frame_w = max(1, int(track.get("frame_width", _cfg.FRAME_WIDTH)))
        frame_h = max(1, int(track.get("frame_height", _cfg.FRAME_HEIGHT)))
        sx = frame_w / _cfg.FRAME_WIDTH
        sy = frame_h / _cfg.FRAME_HEIGHT
        use_feet = getattr(_cfg, "RESTRICTED_ZONE_USE_FEET", True)

        for zone in _cfg.RESTRICTED_ZONES:
            zone_id = zone.get("id")
            if not zone_id:
                continue
            shape = str(zone.get("shape", "rect")).lower()

            if shape == "polygon":
                raw_points = zone.get("points") or []
                # Scale polygon points from canonical 1280x720 to track frame.
                scaled = [(float(p[0]) * sx, float(p[1]) * sy)
                          for p in raw_points if len(p) >= 2]
                if len(scaled) < 3:
                    continue
                center_inside = self._point_in_polygon(cx, cy, scaled)
                feet_inside = (
                    self._point_in_polygon(foot_x, foot_y, scaled)
                    if use_feet else False
                )
                # Bbox-overlap heuristic: cheaper than a full bbox-poly clip,
                # treat the bbox corners as additional sample points so a
                # person whose feet are inside but center is outside still
                # triggers (and vice-versa for tight near-edge cases).
                bbox_overlap = any(
                    self._point_in_polygon(px, py, scaled)
                    for px, py in (
                        (float(track["x1"]), float(track["y1"])),
                        (float(track["x2"]), float(track["y1"])),
                        (float(track["x1"]), float(track["y2"])),
                        (float(track["x2"]), float(track["y2"])),
                    )
                )
                inside = center_inside or feet_inside or bbox_overlap
            else:
                # Rectangle (default + backwards compat)
                zx1 = float(zone.get("x1", 0)) * sx
                zx2 = float(zone.get("x2", 0)) * sx
                zy1 = float(zone.get("y1", 0)) * sy
                zy2 = float(zone.get("y2", 0)) * sy
                if zx2 <= zx1 or zy2 <= zy1:
                    continue
                center_inside = (zx1 <= cx <= zx2 and zy1 <= cy <= zy2)
                feet_inside = (
                    zx1 <= foot_x <= zx2 and zy1 <= foot_y <= zy2
                ) if use_feet else False
                bbox_overlap = self._bbox_overlaps_rect(track, zx1, zy1, zx2, zy2)
                inside = center_inside or feet_inside or bbox_overlap

            key = (track_id, zone_id)
            if inside:
                if key not in self.zone_entry_since:
                    self.zone_entry_since[key] = current_time
                dwell = current_time - self.zone_entry_since[key]
                if dwell >= _cfg.RESTRICTED_ZONE_MIN_DWELL:
                    # Confidence rises as dwell time exceeds the configured
                    # threshold, capped at 1.0 once the person has dwelled
                    # for ~3x the trigger time.
                    base = max(0.1, _cfg.RESTRICTED_ZONE_MIN_DWELL)
                    conf = min(1.0, max(0.0, (dwell - base) / (2.0 * base) + 0.5))
                    anomalies.append({
                        "type": "restricted_zone",
                        "track_id": track_id,
                        "zone_id": zone_id,
                        "zone_name": zone.get("name", zone_id),
                        "duration": round(dwell, 1),
                        "confidence": round(float(conf), 2),
                        "position": [cx, cy],
                    })
            else:
                self.zone_entry_since.pop(key, None)

        return anomalies


    # ── Loitering (fixed: hysteresis re-anchor) ──────────────────────────────

    def _check_loitering(self, track: dict, track_id: int,
                         current_time: float) -> dict | None:
        if not _cfg.LOITERING_ENABLED:
            return None
        cx, cy = self._bbox_center(track)
        reanchor_factor = getattr(_cfg, "LOITERING_REANCHOR_FACTOR", 1.5)

        if track_id in self.loiter_anchor:
            ax, ay = self.loiter_anchor[track_id]
            dist_from_anchor = float(np.hypot(cx - ax, cy - ay))

            # Hysteresis: only reset if moved beyond radius * reanchor_factor
            # This prevents jitter near the edge from resetting the timer
            if dist_from_anchor > _cfg.LOITERING_RADIUS_PX * reanchor_factor:
                self.loiter_anchor[track_id] = (cx, cy)
                self.loiter_first_seen[track_id] = current_time
            elif dist_from_anchor <= _cfg.LOITERING_RADIUS_PX:
                # Still within anchor radius — check dwell time
                dwell = current_time - self.loiter_first_seen.get(track_id, current_time)
                if dwell >= _cfg.LOITERING_TIME_THRESHOLD:
                    return {
                        "type": "loitering",
                        "track_id": track_id,
                        "duration": round(dwell, 1),
                        "position": [cx, cy],
                    }
            # Between radius and radius*factor: in hysteresis band, do nothing
        else:
            self.loiter_anchor[track_id] = (cx, cy)
            self.loiter_first_seen[track_id] = current_time

        return None


    # ── Main update ──────────────────────────────────────────────────────────

    def _cluster_persons(
        self, person_tracks: list[dict],
    ) -> list[dict]:
        """Single-link spatial clustering of persons.

        Two persons belong to the same cluster if they are within
        OVERCROWDING_CLUSTER_DISTANCE_PX of any cluster member. Returns one
        dict per cluster:
          - ``size``      : member count
          - ``centroid``  : (cx, cy) of the cluster centroid
          - ``bbox``      : (x1, y1, x2, y2) tight axis-aligned bounding
                            box of all member bboxes (NOT just centres)
          - ``area_px2``  : area of that bbox, used downstream for the
                            density-per-area metric.

        ``bbox`` and ``area_px2`` are required by the overcrowding emitter
        to compute a density score (people per 1000 px²).  Sample-based
        density (count / cluster_bbox_area) means a tight crowd at a
        doorway scores higher than the same headcount spread across a
        plaza, which is exactly the operator signal we want.
        """
        if not person_tracks:
            return []
        max_dist = float(getattr(
            _cfg, "OVERCROWDING_CLUSTER_DISTANCE_PX", 200.0,
        ))
        max_dist_sq = max_dist * max_dist
        n = len(person_tracks)
        # Union-find by index
        parent = list(range(n))

        def _find(i: int) -> int:
            while parent[i] != i:
                parent[i] = parent[parent[i]]
                i = parent[i]
            return i

        def _union(a: int, b: int) -> None:
            ra, rb = _find(a), _find(b)
            if ra != rb:
                parent[ra] = rb

        centers = [self._bbox_center(t) for t in person_tracks]
        for i in range(n):
            cx_i, cy_i = centers[i]
            for j in range(i + 1, n):
                cx_j, cy_j = centers[j]
                dx = cx_i - cx_j
                dy = cy_i - cy_j
                if dx * dx + dy * dy <= max_dist_sq:
                    _union(i, j)

        groups: dict[int, list[int]] = {}
        for i in range(n):
            r = _find(i)
            groups.setdefault(r, []).append(i)

        clusters: list[dict] = []
        for members in groups.values():
            cx = sum(centers[i][0] for i in members) / len(members)
            cy = sum(centers[i][1] for i in members) / len(members)
            # Tight bbox over ALL member bboxes (full body extents, not
            # just centres) so density reflects actual physical occupancy.
            x1 = min(float(person_tracks[i]["x1"]) for i in members)
            y1 = min(float(person_tracks[i]["y1"]) for i in members)
            x2 = max(float(person_tracks[i]["x2"]) for i in members)
            y2 = max(float(person_tracks[i]["y2"]) for i in members)
            area = max(1.0, (x2 - x1) * (y2 - y1))
            clusters.append({
                "size": len(members),
                "centroid": (float(cx), float(cy)),
                "bbox": (x1, y1, x2, y2),
                "area_px2": area,
            })
        return clusters

    def update(
        self,
        tracks: list,
        current_time: float,
        fall_detections: list[dict] | None = None,
        fall_persistence_time: float | None = None,
    ) -> list:
        anomalies = []

        person_tracks = [t for t in tracks if t["class_id"] == 0]

        # ── Overcrowding via spatial clustering ──────────────────────────────
        # Each cluster is a tight group of persons; alert when a SINGLE cluster
        # exceeds the configured threshold. This avoids the old failure mode
        # where 5 people scattered across a wide plaza falsely alerted, and
        # also catches the opposite case (5 people jammed at a doorway in an
        # otherwise empty scene that the old centroid logic would have missed
        # because the headcount in the frame was 5 but the cluster was tight).
        threshold = max(2, int(_cfg.OVERCROWDING_THRESHOLD))
        min_cluster = max(2, int(getattr(
            _cfg, "OVERCROWDING_MIN_CLUSTER_SIZE", threshold,
        )))
        for cluster in self._cluster_persons(person_tracks):
            if cluster["size"] >= max(threshold, min_cluster):
                cx, cy = cluster["centroid"]
                bx1, by1, bx2, by2 = cluster["bbox"]
                area_px2 = float(cluster["area_px2"])
                # Density expressed as people per 1000 px² of the cluster
                # bbox.  Picked so a tight 4-person huddle inside a 200x200
                # box scores ~0.10 while 4 people spread across the whole
                # 1280x720 frame scores ~0.004 — three orders of magnitude
                # lower, which is the right operator signal.
                density_per_kpx2 = round(
                    cluster["size"] * 1000.0 / area_px2, 4
                )
                anomalies.append({
                    "type": "overcrowding",
                    "count": cluster["size"],
                    "cluster_size": cluster["size"],
                    "cluster_bbox": [
                        int(bx1), int(by1), int(bx2), int(by2),
                    ],
                    "cluster_area_px2": int(area_px2),
                    "density_per_kpx2": density_per_kpx2,
                    "position": [cx, cy],
                    "confidence": round(
                        min(1.0, cluster["size"] / max(threshold, 1) / 2.0 + 0.5),
                        2,
                    ),
                })

        person_motion: dict[int, dict] = {}

        for track in tracks:
            track_id = track["id"]
            class_id = track["class_id"]
            cx = (track["x1"] + track["x2"]) / 2.0
            cy = (track["y1"] + track["y2"]) / 2.0

            if track_id not in self.track_history:
                self.track_history[track_id] = []

            w = max(1.0, float(track["x2"] - track["x1"]))
            h = max(1.0, float(track["y2"] - track["y1"]))
            self.track_history[track_id].append((cx, cy, current_time, w, h))
            self.track_history[track_id] = self.track_history[track_id][-20:]
            history = self.track_history[track_id]

            if class_id == 0 and len(history) >= 5:
                hit_streak = int(track.get("hit_streak", 0))
                # Skip behavioural timers for predicted (held-over) tracks.
                # SORT keeps person tracks alive for up to MAX_AGE = 30 frames
                # after detection is lost; without this guard, loitering/zone
                # dwell/running timers keep accumulating wall-clock time even
                # though the person already left the frame, producing false
                # alerts when the next real detection re-arrives.
                is_predicted = bool(track.get("predicted", False))

                # Compute motion for fight detection
                recent = history[-5:]
                time_span = recent[-1][2] - recent[0][2]
                dist = 0.0
                for i in range(1, len(recent)):
                    dist += np.hypot(recent[i][0] - recent[i-1][0],
                                     recent[i][1] - recent[i-1][1])
                avg_speed = dist / time_span if time_span > 0.01 else 0.0
                # Predicted tracks contribute 0 speed to fight pairing too:
                # they have no fresh detection so any apparent motion is
                # purely Kalman extrapolation.
                person_motion[track_id] = {
                    "cx": cx, "cy": cy,
                    "avg_speed": 0.0 if is_predicted else float(avg_speed),
                    "hit_streak": hit_streak,
                    "predicted": is_predicted,
                }

                if is_predicted:
                    # Don't run loitering / zone / running on phantom tracks,
                    # but keep history so when the real detection returns we
                    # have continuity for body-heights/sec calculations.
                    continue

                # Running detection (dual-metric with grace)
                running_anomaly = self._check_running(track_id, track, history, current_time)
                if running_anomaly:
                    anomalies.append(running_anomaly)

                # Restricted zone (feet + bbox overlap)
                zone_anomalies = self._check_restricted_zone(track, track_id, current_time)
                anomalies.extend(zone_anomalies)

                # Loitering (hysteresis)
                loiter = self._check_loitering(track, track_id, current_time)
                if loiter:
                    anomalies.append(loiter)

            elif class_id in _cfg.UNATTENDED_CLASSES:
                unattended = self._emit_unattended_object(
                    track, current_time, history, person_tracks,
                )
                if unattended:
                    anomalies.append(unattended)


        # ── Fight detection ──────────────────────────────────────────────────
        if _cfg.FIGHT_DETECTION_ENABLED and len(person_motion) >= 2:
            # Tolerate brief speed dips / proximity blips before resetting
            # the fight candidate timer. Mirrors RUNNING_RESET_GRACE_TIME.
            # Without this, a single-frame stutter wipes accumulated
            # persistence and the alert never fires for borderline pairs.
            fight_grace = float(getattr(_cfg, "FIGHT_RESET_GRACE_TIME", 0.4))
            if not hasattr(self, "fight_last_qualifying_at"):
                self.fight_last_qualifying_at = {}

            active_fight_pairs: set[tuple[int, int]] = set()
            person_ids = sorted(person_motion.keys())
            for i in range(len(person_ids)):
                for j in range(i + 1, len(person_ids)):
                    id1 = person_ids[i]
                    id2 = person_ids[j]
                    p1 = person_motion[id1]
                    p2 = person_motion[id2]
                    pair_key = (id1, id2)

                    # Skip pairs where either track is predicted — pair speed
                    # was already zeroed for predicted tracks above, but we
                    # also want them out of the active set so cleanup logic
                    # doesn't preserve a phantom timer indefinitely.
                    if p1.get("predicted") or p2.get("predicted"):
                        continue

                    close_enough = np.hypot(p1["cx"] - p2["cx"], p1["cy"] - p2["cy"]) <= _cfg.FIGHT_PROXIMITY_PX
                    fast_both = (
                        p1["avg_speed"] >= _cfg.FIGHT_MIN_PAIR_SPEED
                        and p2["avg_speed"] >= _cfg.FIGHT_MIN_PAIR_SPEED
                    )
                    stable_tracks = (
                        p1["hit_streak"] >= _cfg.FIGHT_MIN_HIT_STREAK
                        and p2["hit_streak"] >= _cfg.FIGHT_MIN_HIT_STREAK
                    )

                    qualifies = close_enough and fast_both and stable_tracks
                    if qualifies:
                        self.fight_last_qualifying_at[pair_key] = current_time
                        active_fight_pairs.add(pair_key)
                        if pair_key not in self.fight_candidate_since:
                            self.fight_candidate_since[pair_key] = current_time
                            continue
                        persisted = current_time - self.fight_candidate_since[pair_key]
                        if persisted >= _cfg.FIGHT_PERSISTENCE_TIME:
                            last_alert = self.fight_last_alert_at.get(pair_key, 0.0)
                            if current_time - last_alert >= 1.5:
                                mid_x = (p1["cx"] + p2["cx"]) / 2.0
                                mid_y = (p1["cy"] + p2["cy"]) / 2.0
                                anomalies.append({
                                    "type": "fight_suspected",
                                    "track_id": id1,
                                    "track_ids": [id1, id2],
                                    "avg_pair_speed": round((p1["avg_speed"] + p2["avg_speed"]) / 2.0, 1),
                                    "distance": float(round(np.hypot(p1["cx"] - p2["cx"], p1["cy"] - p2["cy"]), 1)),
                                    "duration": round(persisted, 1),
                                    "position": [mid_x, mid_y],
                                })
                                self.fight_last_alert_at[pair_key] = current_time
                    else:
                        # Did not qualify this frame — apply grace-time tolerance.
                        last_qualified = self.fight_last_qualifying_at.get(pair_key)
                        if last_qualified is not None and (current_time - last_qualified) <= fight_grace:
                            # Still inside grace window — keep the candidate alive
                            # so a 1-frame stutter doesn't reset persistence.
                            active_fight_pairs.add(pair_key)
                        else:
                            # Out of grace — drop the timer.
                            self.fight_candidate_since.pop(pair_key, None)
                            self.fight_last_alert_at.pop(pair_key, None)
                            self.fight_last_qualifying_at.pop(pair_key, None)

            stale_fights = [k for k in self.fight_candidate_since if k not in active_fight_pairs]
            for k in stale_fights:
                self.fight_candidate_since.pop(k, None)
                self.fight_last_alert_at.pop(k, None)
                self.fight_last_qualifying_at.pop(k, None)


        # ── Cleanup stale tracks ─────────────────────────────────────────────
        active_ids = {t["id"] for t in tracks}
        # Identify the class of each currently-active track so we can save
        # baggage ghost state before purging the per-track buckets.
        active_classes = {int(t["id"]): int(t["class_id"]) for t in tracks}
        baggage_classes = set(getattr(_cfg, "UNATTENDED_CLASSES", []))

        stale = [k for k in self.track_history if k not in active_ids]
        for k in stale:
            # Only baggage tracks need ghost preservation: person tracks are
            # tied to running/loitering/zone state we explicitly want to drop.
            last = self.object_last_bbox.get(k)
            if last is not None and int(last[0]) in baggage_classes:
                self._save_baggage_ghost(int(k), current_time)
            del self.track_history[k]
            self.running_candidate_since.pop(k, None)
            self.running_last_fast_at.pop(k, None)
            self.owner_absent_since.pop(k, None)
            self.object_owner_id.pop(k, None)
            self.object_owner_last_near.pop(k, None)
            self.object_stationary_since.pop(k, None)
            self.object_alert_active_until.pop(k, None)
            self.object_alert_payload.pop(k, None)
            self.object_last_bbox.pop(k, None)
            self.loiter_first_seen.pop(k, None)
            self.loiter_anchor.pop(k, None)

        # Drop stale last-bbox entries even when track_history was not held
        # for them (e.g. edge case where ghost was already saved).
        for k in [tid for tid in self.object_last_bbox if tid not in active_ids]:
            self.object_last_bbox.pop(k, None)

        # Prune expired baggage ghosts.
        expired_ghosts = [
            k for k, g in self.baggage_ghost_cache.items()
            if g["expires_at"] < current_time
        ]
        for k in expired_ghosts:
            self.baggage_ghost_cache.pop(k, None)

        stale_zone_keys = [k for k in self.zone_entry_since if k[0] not in active_ids]
        for k in stale_zone_keys:
            del self.zone_entry_since[k]

        stale_fight_keys = [k for k in self.fight_candidate_since if k[0] not in active_ids or k[1] not in active_ids]
        for k in stale_fight_keys:
            self.fight_candidate_since.pop(k, None)
            self.fight_last_alert_at.pop(k, None)
            self.fight_last_qualifying_at.pop(k, None)

        # ── Fall detection ───────────────────────────────────────────────────
        if fall_detections:
            anomalies.extend(
                self._emit_fall_anomalies(
                    tracks, current_time, fall_detections,
                    fall_persistence_time=fall_persistence_time,
                )
            )

        return anomalies
