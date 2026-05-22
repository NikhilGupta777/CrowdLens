import random
import time
import math
from backend.config import FRAME_WIDTH, FRAME_HEIGHT, COCO_CLASSES, UNATTENDED_CLASSES

PERSON_W, PERSON_H = 60, 140
OBJ_W, OBJ_H = 40, 40

# Start simulation IDs at a high offset so they never collide with
# SORT tracker IDs (which start from 1 and grow).
_id_counter = 100_000


def _next_id():
    global _id_counter
    _id_counter += 1
    return _id_counter


class Entity:
    def __init__(self, class_id: int, fixed: bool = False):
        global _id_counter
        self.id = _next_id()
        self.class_id = class_id
        self.fixed = fixed

        margin = 100
        self.cx = random.randint(margin, FRAME_WIDTH - margin)
        self.cy = random.randint(margin + 50, FRAME_HEIGHT - margin)

        if fixed:
            self.vx = 0.0
            self.vy = 0.0
        else:
            speed = random.uniform(3, 8)
            angle = random.uniform(0, 2 * math.pi)
            self.vx = math.cos(angle) * speed
            self.vy = math.sin(angle) * speed

        self.w = PERSON_W if class_id == 0 else OBJ_W
        self.h = PERSON_H if class_id == 0 else OBJ_H
        self.created_at = time.time()
        self.lifetime = random.uniform(10, 30) if not fixed else random.uniform(8, 20)
        self.running = False
        self.run_timer = 0

    def tick(self, dt: float):
        if self.fixed:
            return

        now = time.time()
        if self.class_id == 0:
            self.run_timer -= dt
            if self.run_timer <= 0:
                if self.running:
                    self.running = False
                    speed = random.uniform(3, 8)
                    angle = random.uniform(0, 2 * math.pi)
                    self.vx = math.cos(angle) * speed
                    self.vy = math.sin(angle) * speed
                    self.run_timer = random.uniform(3, 8)
                else:
                    if random.random() < 0.15:
                        self.running = True
                        speed = random.uniform(25, 40)
                        angle = random.uniform(0, 2 * math.pi)
                        self.vx = math.cos(angle) * speed
                        self.vy = math.sin(angle) * speed
                        self.run_timer = random.uniform(1.5, 3)
                    else:
                        self.run_timer = random.uniform(2, 5)

        self.cx += self.vx * dt
        self.cy += self.vy * dt

        hw, hh = self.w / 2, self.h / 2
        if self.cx - hw < 10:
            self.cx = hw + 10
            self.vx = abs(self.vx)
        if self.cx + hw > FRAME_WIDTH - 10:
            self.cx = FRAME_WIDTH - hw - 10
            self.vx = -abs(self.vx)
        if self.cy - hh < 60:
            self.cy = hh + 60
            self.vy = abs(self.vy)
        if self.cy + hh > FRAME_HEIGHT - 10:
            self.cy = FRAME_HEIGHT - hh - 10
            self.vy = -abs(self.vy)

    def to_track(self) -> dict:
        hw, hh = self.w / 2, self.h / 2
        return {
            "id": self.id,
            "x1": round(self.cx - hw),
            "y1": round(self.cy - hh),
            "x2": round(self.cx + hw),
            "y2": round(self.cy + hh),
            "class_id": self.class_id,
            "class_name": COCO_CLASSES.get(self.class_id, "object"),
            "running": self.running
        }

    def is_expired(self, now: float) -> bool:
        return now - self.created_at > self.lifetime


class SimulationEngine:
    def __init__(self):
        self.entities: list[Entity] = []
        self.last_tick = time.time()
        self._spawn_initial()

    def _spawn_initial(self):
        for _ in range(random.randint(1, 3)):
            self.entities.append(Entity(class_id=0))
        for _ in range(random.randint(0, 2)):
            cls = random.choice(UNATTENDED_CLASSES)
            self.entities.append(Entity(class_id=cls, fixed=True))

    def tick(self) -> list:
        now = time.time()
        dt = min(now - self.last_tick, 0.1)
        self.last_tick = now

        self.entities = [e for e in self.entities if not e.is_expired(now)]

        for e in self.entities:
            e.tick(dt)

        if random.random() < 0.02:
            self.entities.append(Entity(class_id=0))

        if random.random() < 0.01:
            cls = random.choice(UNATTENDED_CLASSES)
            self.entities.append(Entity(class_id=cls, fixed=True))

        return [e.to_track() for e in self.entities]
