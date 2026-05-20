import numpy as np
from backend.config import (
    OVERCROWDING_THRESHOLD, RUNNING_SPEED_THRESHOLD,
    RUNNING_PERSISTENCE_TIME, RUNNING_MIN_HIT_STREAK,
    UNATTENDED_OBJECT_TIME, STATIONARY_THRESHOLD, UNATTENDED_CLASSES,
    UNATTENDED_OWNER_PROXIMITY_PX, UNATTENDED_OWNER_GRACE_TIME,
    FALL_PERSISTENCE_TIME,
    RESTRICTED_ZONE_ENABLED, RESTRICTED_ZONE_MIN_DWELL, RESTRICTED_ZONES,
    FIGHT_DETECTION_ENABLED, FIGHT_PROXIMITY_PX, FIGHT_MIN_PAIR_SPEED,
    FIGHT_PERSISTENCE_TIME, FIGHT_MIN_HIT_STREAK,
    FRAME_WIDTH, FRAME_HEIGHT,
)


class AnomalyDetector:
    def __init__(self):
        self.track_history: dict = {}
        self.running_candidate_since: dict[int, float] = {}
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

    @staticmethod
    def _bbox_center(track: dict) -> tuple[float, float]:
        return (
            (float(track["x1"]) + float(track["x2"])) / 2.0,
            (float(track["y1"]) + float(track["y2"])) / 2.0,
        )

    @staticmethod
    def _distance_point_to_bbox(px: float, py: float, box: dict) -> float:
        bx1 = float(box["x1"])
        by1 = float(box["y1"])
        bx2 = float(box["x2"])
        by2 = float(box["y2"])
        nx = min(max(px, bx1), bx2)
        ny = min(max(py, by1), by2)
        return float(np.hypot(px - nx, py - ny))

    def _distance_object_to_person(self, obj_track: dict, person_track: dict) -> float:
        ox, oy = self._bbox_center(obj_track)
        px, _ = self._bbox_center(person_track)
        feet_y = float(person_track["y2"])
        # Use both bbox distance and foot distance. Bags are usually near feet,
        # while bbox overlap handles seated/near-camera people.
        return min(
            self._distance_point_to_bbox(ox, oy, person_track),
            float(np.hypot(ox - px, oy - feet_y)),
        )

    @staticmethod
    def _is_stationary(history: list, threshold: float) -> bool:
        if len(history) < 4:
            return False
        recent = history[-12:]
        xs = [p[0] for p in recent]
        ys = [p[1] for p in recent]
        spread = float(np.hypot(max(xs) - min(xs), max(ys) - min(ys)))
        return spread <= threshold

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

        if not self._is_stationary(history, STATIONARY_THRESHOLD):
            self.object_stationary_since.pop(track_id, None)
            self.owner_absent_since.pop(track_id, None)
            self.object_alert_active_until.pop(track_id, None)
            self.object_alert_payload.pop(track_id, None)
            return None

        if track_id not in self.object_stationary_since:
            self.object_stationary_since[track_id] = current_time

        nearest_person = None
        nearest_distance = float("inf")
        for person in person_tracks:
            distance = self._distance_object_to_person(track, person)
            if distance < nearest_distance:
                nearest_distance = distance
                nearest_person = person

        owner_id = self.object_owner_id.get(track_id)
        if owner_id is None and nearest_person is not None and nearest_distance <= UNATTENDED_OWNER_PROXIMITY_PX:
            owner_id = int(nearest_person["id"])
            self.object_owner_id[track_id] = owner_id
            self.object_owner_last_near[track_id] = current_time
            self.owner_absent_since.pop(track_id, None)
            return None

        owner_track = next((p for p in person_tracks if int(p["id"]) == owner_id), None) if owner_id is not None else None
        owner_near = False
        if owner_track is not None:
            owner_distance = self._distance_object_to_person(track, owner_track)
            owner_near = owner_distance <= UNATTENDED_OWNER_PROXIMITY_PX

        if owner_near:
            self.object_owner_last_near[track_id] = current_time
            self.owner_absent_since.pop(track_id, None)
            return None

        # If no owner was ever seen, still allow alerting after the object has
        # been stationary and isolated long enough. This covers clips that start
        # after the bag was abandoned.
        if track_id not in self.owner_absent_since:
            self.owner_absent_since[track_id] = current_time
            return None

        stationary_time = current_time - self.object_stationary_since.get(track_id, current_time)
        owner_absent_time = current_time - self.owner_absent_since[track_id]
        if stationary_time < UNATTENDED_OBJECT_TIME or owner_absent_time < UNATTENDED_OWNER_GRACE_TIME:
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
            "bbox": [
                int(track["x1"]),
                int(track["y1"]),
                int(track["x2"]),
                int(track["y2"]),
            ],
        }
        if owner_id is not None:
            anomaly["owner_track_id"] = owner_id
        self.object_alert_active_until[track_id] = current_time + 4.0
        self.object_alert_payload[track_id] = dict(anomaly)
        return anomaly

    def _emit_fall_anomalies(
        self,
        tracks: list,
        current_time: float,
        fall_detections: list[dict],
        fall_persistence_time: float = FALL_PERSISTENCE_TIME,
    ) -> list[dict]:
        anomalies: list[dict] = []

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
        min_area = FRAME_WIDTH * FRAME_HEIGHT * 0.012

        for det in fall_detections:
            fx1, fy1, fx2, fy2 = det["bbox"]
            fbox = [float(fx1), float(fy1), float(fx2), float(fy2)]
            confidence = float(det.get("confidence", 0.0))
            fw = max(1.0, float(fx2) - float(fx1))
            fh = max(1.0, float(fy2) - float(fy1))
            area = fw * fh
            # Keep HF model as the source of truth, but reject tiny / high / very
            # vertical boxes that frequently cause false positives (wall objects).
            if float(fy2) < FRAME_HEIGHT * 0.38:
                continue
            if area < min_area:
                continue
            if (fw / fh) < 0.50:
                continue

            fcx = (fx1 + fx2) / 2.0
            fcy = (fy1 + fy2) / 2.0
            candidate_key: object = ("fall_region", int(fcx // 96), int(fcy // 96))
            best_track_id = None

            # Reuse an existing candidate key when overlap is strong, so
            # persistence survives slight box movement between frames.
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

        # Keep a confirmed fall active for a short hold window so alerts do not
        # flicker off/on when the detector briefly misses a few frames.
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
            anomalies.append(
                {
                    "type": "fall_detected",
                    "duration": round(max(0.0, current_time - since), 1),
                    "confidence": payload.get("confidence", 0.0),
                    "position": payload.get("position"),
                    "bbox": payload.get("bbox"),
                    "note": "hf_fall_model_confirmed",
                }
            )

        stale_fall_keys = [
            k
            for k in self.fall_candidate_since
            if (
                k not in active_fall_keys
                and (current_time - self.fall_last_seen_at.get(k, 0.0)) > 2.0
                and k not in self.fall_active_until
            )
        ]
        for k in stale_fall_keys:
            self.fall_candidate_since.pop(k, None)
            self.fall_candidate_boxes.pop(k, None)
            self.fall_last_seen_at.pop(k, None)

        return anomalies

    def update(
        self,
        tracks: list,
        current_time: float,
        fall_detections: list[dict] | None = None,
        fall_persistence_time: float = FALL_PERSISTENCE_TIME,
    ) -> list:
        anomalies = []

        person_tracks = [t for t in tracks if t["class_id"] == 0]
        person_positions = [self._bbox_center(t) for t in person_tracks]

        person_count = len(person_positions)
        if person_count > OVERCROWDING_THRESHOLD:
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
                recent = history[-5:]
                dist = 0
                for i in range(1, len(recent)):
                    dist += np.hypot(recent[i][0] - recent[i-1][0], recent[i][1] - recent[i-1][1])
                avg_speed = dist / len(recent)
                person_motion[track_id] = {
                    "cx": cx,
                    "cy": cy,
                    "avg_speed": float(avg_speed),
                    "hit_streak": hit_streak,
                }

                # Require stable track age and persistence window to reduce
                # false running alerts from brief SORT ID switches/jitter.
                if hit_streak >= RUNNING_MIN_HIT_STREAK and avg_speed > RUNNING_SPEED_THRESHOLD:
                    if track_id not in self.running_candidate_since:
                        self.running_candidate_since[track_id] = current_time
                    elif current_time - self.running_candidate_since[track_id] >= RUNNING_PERSISTENCE_TIME:
                        anomalies.append({
                            "type": "running",
                            "track_id": track_id,
                            "avg_speed": round(avg_speed, 1),
                            "position": [cx, cy]
                        })
                else:
                    self.running_candidate_since.pop(track_id, None)

                # Digital fencing: unauthorized person in restricted zone.
                if RESTRICTED_ZONE_ENABLED:
                    frame_w = max(1, int(track.get("frame_width", FRAME_WIDTH)))
                    frame_h = max(1, int(track.get("frame_height", FRAME_HEIGHT)))
                    sx = frame_w / FRAME_WIDTH
                    sy = frame_h / FRAME_HEIGHT
                    for zone in RESTRICTED_ZONES:
                        zone_id = zone["id"]
                        zx1 = zone["x1"] * sx
                        zx2 = zone["x2"] * sx
                        zy1 = zone["y1"] * sy
                        zy2 = zone["y2"] * sy
                        inside = (
                            zx1 <= cx <= zx2
                            and zy1 <= cy <= zy2
                        )
                        key = (track_id, zone_id)
                        if inside:
                            if key not in self.zone_entry_since:
                                self.zone_entry_since[key] = current_time
                            dwell = current_time - self.zone_entry_since[key]
                            if dwell >= RESTRICTED_ZONE_MIN_DWELL:
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

            elif class_id in UNATTENDED_CLASSES:
                unattended = self._emit_unattended_object(
                    track,
                    current_time,
                    history,
                    person_tracks,
                )
                if unattended:
                    anomalies.append(unattended)

        if FIGHT_DETECTION_ENABLED and len(person_motion) >= 2:
            active_fight_pairs: set[tuple[int, int]] = set()
            person_ids = sorted(person_motion.keys())
            for i in range(len(person_ids)):
                for j in range(i + 1, len(person_ids)):
                    id1 = person_ids[i]
                    id2 = person_ids[j]
                    p1 = person_motion[id1]
                    p2 = person_motion[id2]
                    pair_key = (id1, id2)

                    close_enough = np.hypot(p1["cx"] - p2["cx"], p1["cy"] - p2["cy"]) <= FIGHT_PROXIMITY_PX
                    fast_both = (
                        p1["avg_speed"] >= FIGHT_MIN_PAIR_SPEED
                        and p2["avg_speed"] >= FIGHT_MIN_PAIR_SPEED
                    )
                    stable_tracks = (
                        p1["hit_streak"] >= FIGHT_MIN_HIT_STREAK
                        and p2["hit_streak"] >= FIGHT_MIN_HIT_STREAK
                    )

                    if close_enough and fast_both and stable_tracks:
                        active_fight_pairs.add(pair_key)
                        if pair_key not in self.fight_candidate_since:
                            self.fight_candidate_since[pair_key] = current_time
                            continue

                        persisted = current_time - self.fight_candidate_since[pair_key]
                        if persisted >= FIGHT_PERSISTENCE_TIME:
                            last_alert = self.fight_last_alert_at.get(pair_key, 0.0)
                            # Keep signal visible while avoiding frame-by-frame alert spam.
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

        active_ids = {t["id"] for t in tracks}
        stale = [k for k in self.track_history if k not in active_ids]
        for k in stale:
            del self.track_history[k]
            self.running_candidate_since.pop(k, None)
            self.fall_candidate_since.pop(k, None)
            self.owner_absent_since.pop(k, None)
            self.object_owner_id.pop(k, None)
            self.object_owner_last_near.pop(k, None)
            self.object_stationary_since.pop(k, None)
            self.object_alert_active_until.pop(k, None)
            self.object_alert_payload.pop(k, None)

        stale_zone_keys = [k for k in self.zone_entry_since if k[0] not in active_ids]
        for k in stale_zone_keys:
            del self.zone_entry_since[k]

        stale_fight_keys = [k for k in self.fight_candidate_since if k[0] not in active_ids or k[1] not in active_ids]
        for k in stale_fight_keys:
            self.fight_candidate_since.pop(k, None)
            self.fight_last_alert_at.pop(k, None)

        if fall_detections:
            anomalies.extend(
                self._emit_fall_anomalies(
                    tracks,
                    current_time,
                    fall_detections,
                    fall_persistence_time=fall_persistence_time,
                )
            )

        return anomalies
