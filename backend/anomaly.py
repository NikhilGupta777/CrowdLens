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

    # ── Helpers ──────────────────────────────────────────────────────────────


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
        Dual-metric running detection:
          1. Raw pixel speed > RUNNING_SPEED_THRESHOLD
          2. Body-heights/sec > RUNNING_BODY_HEIGHTS_PER_SEC
        Either metric alone triggers running. Uses grace time so a 1-frame
        speed dip doesn't reset the persistence timer.
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

        is_fast = (avg_speed > _cfg.RUNNING_SPEED_THRESHOLD or
                   body_heights_per_sec > _cfg.RUNNING_BODY_HEIGHTS_PER_SEC)

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
            return {
                "type": "running",
                "track_id": track_id,
                "avg_speed": round(float(avg_speed), 1),
                "body_heights_per_sec": round(float(body_heights_per_sec), 2),
                "position": [cx, cy],
            }
        return None


    # ── Unattended Object (fixed: bystander-attends logic) ───────────────────

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

        if not self._is_stationary(history, _cfg.STATIONARY_THRESHOLD):
            self.object_stationary_since.pop(track_id, None)
            self.owner_absent_since.pop(track_id, None)
            self.object_alert_active_until.pop(track_id, None)
            self.object_alert_payload.pop(track_id, None)
            return None

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
        min_area = frame_area * min_area_ratio

        def _iou(a: list[float], b: list[float]) -> float:
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
            best_track_id = None

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
                self.fall_active_until[candidate_key] = current_time + 3.0
                self.fall_active_payload[candidate_key] = {
                    "position": [cx, cy],
                    "bbox": [int(fx1), int(fy1), int(fx2), int(fy2)],
                    "confidence": max(
                        float(round(confidence, 3)),
                        float(self.fall_active_payload.get(candidate_key, {}).get("confidence", 0.0)),
                    ),
                }


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
            anomalies.append({
                "type": "fall_detected",
                "duration": round(max(0.0, current_time - since), 1),
                "confidence": payload.get("confidence", 0.0),
                "position": payload.get("position"),
                "bbox": payload.get("bbox"),
                "note": "hf_fall_model_confirmed",
            })

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


    # ── Restricted Zone (fixed: feet-point + bbox overlap) ───────────────────

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
            zone_id = zone["id"]
            zx1 = zone["x1"] * sx
            zx2 = zone["x2"] * sx
            zy1 = zone["y1"] * sy
            zy2 = zone["y2"] * sy

            # Check: center inside zone
            center_inside = (zx1 <= cx <= zx2 and zy1 <= cy <= zy2)
            # Check: foot point inside zone
            feet_inside = (zx1 <= foot_x <= zx2 and zy1 <= foot_y <= zy2) if use_feet else False
            # Check: bbox overlaps zone
            bbox_overlap = self._bbox_overlaps_rect(track, zx1, zy1, zx2, zy2)

            inside = center_inside or feet_inside or bbox_overlap

            key = (track_id, zone_id)
            if inside:
                if key not in self.zone_entry_since:
                    self.zone_entry_since[key] = current_time
                dwell = current_time - self.zone_entry_since[key]
                if dwell >= _cfg.RESTRICTED_ZONE_MIN_DWELL:
                    anomalies.append({
                        "type": "restricted_zone",
                        "track_id": track_id,
                        "zone_id": zone_id,
                        "zone_name": zone.get("name", zone_id),
                        "duration": round(dwell, 1),
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

    def update(
        self,
        tracks: list,
        current_time: float,
        fall_detections: list[dict] | None = None,
        fall_persistence_time: float | None = None,
    ) -> list:
        anomalies = []

        person_tracks = [t for t in tracks if t["class_id"] == 0]
        person_positions = [self._bbox_center(t) for t in person_tracks]

        person_count = len(person_positions)
        if person_count > _cfg.OVERCROWDING_THRESHOLD:
            crowd_x = sum(p[0] for p in person_positions) / person_count
            crowd_y = sum(p[1] for p in person_positions) / person_count
            anomalies.append({"type": "overcrowding", "count": person_count, "position": [crowd_x, crowd_y]})

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
                # Compute motion for fight detection
                recent = history[-5:]
                time_span = recent[-1][2] - recent[0][2]
                dist = 0.0
                for i in range(1, len(recent)):
                    dist += np.hypot(recent[i][0] - recent[i-1][0],
                                     recent[i][1] - recent[i-1][1])
                avg_speed = dist / time_span if time_span > 0.01 else 0.0
                person_motion[track_id] = {
                    "cx": cx, "cy": cy,
                    "avg_speed": float(avg_speed),
                    "hit_streak": hit_streak,
                }

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
            active_fight_pairs: set[tuple[int, int]] = set()
            person_ids = sorted(person_motion.keys())
            for i in range(len(person_ids)):
                for j in range(i + 1, len(person_ids)):
                    id1 = person_ids[i]
                    id2 = person_ids[j]
                    p1 = person_motion[id1]
                    p2 = person_motion[id2]
                    pair_key = (id1, id2)

                    close_enough = np.hypot(p1["cx"] - p2["cx"], p1["cy"] - p2["cy"]) <= _cfg.FIGHT_PROXIMITY_PX
                    fast_both = (
                        p1["avg_speed"] >= _cfg.FIGHT_MIN_PAIR_SPEED
                        and p2["avg_speed"] >= _cfg.FIGHT_MIN_PAIR_SPEED
                    )
                    stable_tracks = (
                        p1["hit_streak"] >= _cfg.FIGHT_MIN_HIT_STREAK
                        and p2["hit_streak"] >= _cfg.FIGHT_MIN_HIT_STREAK
                    )

                    if close_enough and fast_both and stable_tracks:
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
                        self.fight_candidate_since.pop(pair_key, None)
                        self.fight_last_alert_at.pop(pair_key, None)

            stale_fights = [k for k in self.fight_candidate_since if k not in active_fight_pairs]
            for k in stale_fights:
                self.fight_candidate_since.pop(k, None)
                self.fight_last_alert_at.pop(k, None)


        # ── Cleanup stale tracks ─────────────────────────────────────────────
        active_ids = {t["id"] for t in tracks}
        stale = [k for k in self.track_history if k not in active_ids]
        for k in stale:
            del self.track_history[k]
            self.running_candidate_since.pop(k, None)
            self.running_last_fast_at.pop(k, None)
            self.owner_absent_since.pop(k, None)
            self.object_owner_id.pop(k, None)
            self.object_owner_last_near.pop(k, None)
            self.object_stationary_since.pop(k, None)
            self.object_alert_active_until.pop(k, None)
            self.object_alert_payload.pop(k, None)
            self.loiter_first_seen.pop(k, None)
            self.loiter_anchor.pop(k, None)

        stale_zone_keys = [k for k in self.zone_entry_since if k[0] not in active_ids]
        for k in stale_zone_keys:
            del self.zone_entry_since[k]

        stale_fight_keys = [k for k in self.fight_candidate_since if k[0] not in active_ids or k[1] not in active_ids]
        for k in stale_fight_keys:
            self.fight_candidate_since.pop(k, None)
            self.fight_last_alert_at.pop(k, None)

        # ── Fall detection ───────────────────────────────────────────────────
        if fall_detections:
            anomalies.extend(
                self._emit_fall_anomalies(
                    tracks, current_time, fall_detections,
                    fall_persistence_time=fall_persistence_time,
                )
            )

        return anomalies
