from __future__ import annotations

import math
import random
from dataclasses import dataclass
from typing import Any

import pymunk

from config import SimulationConfig
from models import TeamRecord


@dataclass
class RoundEntry:
    team: TeamRecord
    body: pymunk.Body
    shape: pymunk.Circle
    slot_index: int = -1
    slot_value: int = 0
    exit_time: float = 0.0
    exited: bool = False
    stall_timer: float = 0.0
    nudge_count: int = 0
    last_x: float = 0.0
    last_y: float = 0.0


class GrandPrixEngine:
    TARGET_HOLE_COUNT = 12
    DEFAULT_HOLE_TEMPLATE = (-5, -3, -2, -1, 0, 1, 2, 3, 4, 5, 7, 10)

    def __init__(
        self,
        cfg: SimulationConfig,
        *,
        title: str,
        teams: list[TeamRecord],
        hole_values: list[int],
        round_count: int,
        role: str = "grand_prix",
        round_duration_seconds: float = 22.0,
        random_seed: int = 0,
        vertical: bool = False,
    ) -> None:
        self.cfg = cfg
        self.title = str(title or "Grand Prix")
        self.teams = list(teams)
        self.round_count = int(round_count)
        self.random_seed = int(random_seed)
        self.rng = random.Random(self.random_seed)

        self.hole_values = self._coerce_hole_values(hole_values)
        self.hole_count = len(self.hole_values)

        self.round_duration_seconds = max(12.0, float(round_duration_seconds))
        self.intro_duration_seconds = 2.8
        self.summary_duration_seconds = 2.3
        self.action_timeout_seconds = max(8.0, self.round_duration_seconds - self.summary_duration_seconds)
        self.final_duration_seconds = 4.2
        self.is_vertical = vertical

        if self.is_vertical:
            self.board_rect = {
                "x": 40,
                "y": 80,
                "width": 1000,
                "height": 1300,
            }
            self.side_panel_rect = {
                "x": 40,
                "y": 1420,
                "width": 1000,
                "height": 450,
            }
        else:
            self.board_rect = {
                "x": 78,
                "y": 46,
                "width": 1080,
                "height": 988,
            }
            self.side_panel_rect = {
                "x": 1190,
                "y": 46,
                "width": 650,
                "height": 988,
            }

        self.ball_radius = max(13, int(self.cfg.physics.ball_radius * 0.55))
        self.ball_mass = max(0.7, float(self.cfg.physics.ball_mass))
        self.ball_elasticity = 0.75
        self.ball_friction = 0.30  # Sürtünmeyi 0.30'a ayarladık (kullanıcı talebi)
        self.peg_radius = max(7, int(self.cfg.physics.peg_radius * 0.65))

        self.bottom_row_pegs: list[tuple[float, float]] = []
        self.peg_positions = self._build_peg_positions()
        self.slot_rects = self._build_slot_rects()
        if self.slot_rects:
            self.exit_capture_y = max(float(slot["y"]) + float(slot["height"]) + 6.0 for slot in self.slot_rects)
        else:
            board_bottom = self.board_rect["y"] + self.board_rect["height"]
            self.exit_capture_y = board_bottom + 22.0

        self.space = pymunk.Space()
        self.space.gravity = (0.0, float(self.cfg.physics.gravity_y) * 0.72)
        self.space.iterations = max(24, int(self.cfg.physics.space_iterations))
        self.space.damping = 0.9985
        self._build_static_world()

        self.team_points: dict[str, int] = {team.team_key: 0 for team in self.teams}
        self.round_history: list[dict[str, Any]] = []

        self.current_round = 0
        self.completed_rounds = 0
        self.phase = "intro"
        self.phase_elapsed = 0.0
        self.final_elapsed = 0.0
        self.current_entries: list[RoundEntry] = []
        self.current_round_results: list[dict[str, Any]] = []
        self.latest_completed_round_results: list[dict[str, Any]] = []
        self._round_awarded = False
        self._pending_round_payloads: list[dict[str, Any]] = []
        self._pending_audio_cues: list[str] = []
        self._final_audio_sent = False
        self._collision_sparks: list[dict[str, Any]] = []

    def update(self, dt: float) -> None:
        if self.phase == "finished":
            return

        delta = max(0.0, float(dt))

        if self.phase in {"intro", "action", "summary"}:
            self.phase_elapsed += delta

        if self.phase == "intro":
            if self.phase_elapsed >= self.intro_duration_seconds:
                self._start_next_round()
        elif self.phase == "action":
            self._advance_action_phase(delta)
            if self._all_entries_exited():
                self._complete_action_phase()
        elif self.phase == "summary":
            if self.phase_elapsed >= self.summary_duration_seconds:
                if self.current_round >= self.round_count:
                    self.phase = "final"
                    self.final_elapsed = 0.0
                    if not self._final_audio_sent:
                        self._pending_audio_cues.append("whistle_end")
                        self._final_audio_sent = True
                else:
                    self._start_next_round()
        elif self.phase == "final":
            self.final_elapsed += delta
            if self.final_elapsed >= self.final_duration_seconds:
                self.phase = "finished"

    def is_finished(self) -> bool:
        return self.phase == "finished"

    def drain_audio_cues(self) -> list[str]:
        cues = list(self._pending_audio_cues)
        self._pending_audio_cues = []
        return cues

    def drain_completed_round_payloads(self) -> list[dict[str, Any]]:
        payloads = list(self._pending_round_payloads)
        self._pending_round_payloads = []
        return payloads

    def get_collision_sparks(self, since: float) -> list[dict[str, Any]]:
        return [dict(s) for s in self._collision_sparks if float(s.get("time", 0.0)) >= since]

    def get_snapshot(self) -> dict[str, Any]:
        active_balls = []
        for entry in self.current_entries:
            if entry.exited:
                continue
            x = float(entry.body.position.x)
            y = float(entry.body.position.y)
            active_balls.append(
                {
                    "team_key": entry.team.team_key,
                    "team_name": entry.team.name,
                    "team_short_name": entry.team.short_name,
                    "badge_file": entry.team.badge_file,
                    "color_seed": self._color_seed(entry.team.team_key),
                    "x": x,
                    "y": y,
                    "radius": self.ball_radius,
                }
            )

        champion_key = None
        if self.phase in {"final", "finished"}:
            standings = self._build_standings()
            champion_key = str(standings[0]["team_key"]) if standings else None
        round_display = self.current_round if self.current_round > 0 else 1
        intro_remaining = max(0.0, self.intro_duration_seconds - self.phase_elapsed)

        return {
            "title": self.title,
            "phase": self.phase,
            "current_round": round_display,
            "round_count": self.round_count,
            "completed_rounds": self.completed_rounds,
            "is_vertical": getattr(self, "is_vertical", False),
            "board_rect": dict(self.board_rect),
            "side_panel_rect": dict(self.side_panel_rect),
            "peg_positions": list(self.peg_positions),
            "peg_radius": int(self.peg_radius),
            "slot_rects": list(self.slot_rects),
            "hole_values": [
                {
                    "slot_index": slot_index,
                    "points": int(self.hole_values[slot_index]),
                    "rect": dict(self.slot_rects[slot_index]),
                }
                for slot_index in range(min(len(self.hole_values), len(self.slot_rects)))
            ],
            "teams": [
                {
                    "team_key": team.team_key,
                    "name": team.name,
                    "short_name": team.short_name,
                    "badge_file": team.badge_file,
                    "points": int(self.team_points.get(team.team_key, 0)),
                }
                for team in self.teams
            ],
            "standings": self._build_standings(),
            "active_balls": active_balls,
            "round_results": list(self.current_round_results or self.latest_completed_round_results),
            "latest_completed_round_results": list(self.latest_completed_round_results),
            "round_progress": self._round_progress_ratio(),
            "round_status_text": self._round_status_text(),
            "show_final_overlay": self.phase in {"final", "finished"},
            "champion_team_key": champion_key,
            "champion_name": self._team_name(champion_key),
            "show_intro_overlay": self.phase == "intro",
            "intro_countdown": max(1, int(math.ceil(intro_remaining))),
        }

    def export_results(self) -> dict[str, Any]:
        standings = self._build_standings()
        champion_key = str(standings[0]["team_key"]) if standings else None
        return {
            "team_points": {key: int(value) for key, value in self.team_points.items()},
            "rounds": list(self.round_history),
            "champion_team_key": champion_key,
        }

    def _start_next_round(self) -> None:
        self.current_round += 1
        self.phase = "action"
        self.phase_elapsed = 0.0
        self._collision_sparks = []  # Yeni raund baslarken eski çarpışma verilerini temizle
        self._round_awarded = False
        self.current_round_results = []
        self.current_entries = self._build_round_entries()
        self._pending_audio_cues.append("whistle_start")

    def _build_round_entries(self) -> list[RoundEntry]:
        entries: list[RoundEntry] = []
        spawn_xs = self._spawn_x_positions(len(self.teams))
        start_y = self.board_rect["y"] + 62
        for team, spawn_x in zip(self.teams, spawn_xs):
            body, shape = self._spawn_ball(spawn_x, start_y)
            entries.append(
                RoundEntry(
                    team=team,
                    body=body,
                    shape=shape,
                    last_x=float(body.position.x),
                    last_y=float(body.position.y),
                )
            )
        return entries

    def _spawn_ball(self, spawn_x: float, spawn_y: float) -> tuple[pymunk.Body, pymunk.Circle]:
        inertia = pymunk.moment_for_circle(self.ball_mass, 0.0, float(self.ball_radius))
        body = pymunk.Body(self.ball_mass, inertia)
        body.position = (spawn_x, spawn_y + self.rng.uniform(-300.0, 30.0))
        body.velocity = (self.rng.uniform(-110.0, 110.0), self.rng.uniform(10.0, 70.0))
        body.angular_velocity = self.rng.uniform(-7.0, 7.0)

        shape = pymunk.Circle(body, self.ball_radius)
        shape.elasticity = self.ball_elasticity
        shape.friction = self.ball_friction
        self.space.add(body, shape)
        return body, shape

    def _advance_action_phase(self, delta: float) -> None:
        substeps = max(3, int(self.cfg.physics.substeps) + 1)
        step_dt = delta / substeps
        for _ in range(substeps):
            self.space.step(step_dt)
            self._capture_exits()
            self._resolve_stuck_entries(step_dt)

        # Spark temizliği
        if len(self._collision_sparks) > 64:
            self._collision_sparks = self._collision_sparks[-48:]

        if self.phase_elapsed >= self.action_timeout_seconds and not self._all_entries_exited():
            self._force_exit_remaining()

    def _handle_spark_collision(self, arbiter: pymunk.Arbiter, _space=None, _data=None) -> None:
        """Herhangi iki cisim arasındaki çarpışmalarda spark verisi toplar."""
        if not arbiter:
            return

        # Sadece bu frame'deki impulse'u kontrol et
        impulse = float(arbiter.total_impulse.length)
        if impulse < 45.0:  # Çok düşük impulseları yoksay
            return

        # Temas noktası yoksa hayalet çarpışmadır
        contact_set = arbiter.contact_point_set
        if not contact_set.points:
            return

        # İlk temas noktasını al
        contact = contact_set.points[0]
        self._collision_sparks.append({
            "time": float(self.phase_elapsed),
            "x": float(contact.point_a.x),
            "y": float(contact.point_a.y),
            "impulse": min(1.0, impulse / 900.0),
        })

    def _capture_exits(self) -> None:
        for entry in self.current_entries:
            if entry.exited:
                continue
            x = float(entry.body.position.x)
            y = float(entry.body.position.y)
            if y >= self.exit_capture_y:
                slot_index = self._resolve_slot_index(x)
                self._mark_entry_exited(entry, slot_index)
                continue

            if y > self.exit_capture_y + 200.0:
                slot_index = self._resolve_slot_index(x)
                self._mark_entry_exited(entry, slot_index)

    def _force_exit_remaining(self) -> None:
        for entry in self.current_entries:
            if entry.exited:
                continue
            x = float(entry.body.position.x)
            slot_index = self._resolve_slot_index(x)
            self._mark_entry_exited(entry, slot_index)

    def _mark_entry_exited(self, entry: RoundEntry, slot_index: int) -> None:
        if entry.exited:
            return
        safe_slot = max(0, min(self.hole_count - 1, int(slot_index)))
        entry.slot_index = safe_slot
        entry.slot_value = int(self.hole_values[safe_slot])
        entry.exit_time = max(0.01, self.phase_elapsed)
        entry.exited = True
        try:
            self.space.remove(entry.shape, entry.body)
        except Exception:
            pass

    def _all_entries_exited(self) -> bool:
        return all(entry.exited for entry in self.current_entries)

    def _resolve_stuck_entries(self, dt: float) -> None:
        left_bound = self.board_rect["x"] + self.ball_radius + 8.0
        right_bound = self.board_rect["x"] + self.board_rect["width"] - self.ball_radius - 8.0

        for entry in self.current_entries:
            if entry.exited:
                continue

            x = float(entry.body.position.x)
            y = float(entry.body.position.y)
            dx = x - entry.last_x
            dy = y - entry.last_y
            moved = (dx * dx + dy * dy) ** 0.5
            speed = float(entry.body.velocity.length)

            if moved < 1.1 and speed < 38.0 and y > self.board_rect["y"] + 120:
                entry.stall_timer += dt
            else:
                entry.stall_timer = 0.0

            entry.last_x = x
            entry.last_y = y

            if entry.stall_timer < 0.4 or entry.nudge_count >= 20:
                continue

            push_x = self.rng.uniform(-100.0, 100.0)
            if x < left_bound + 32.0:
                push_x = abs(push_x) + 60.0
            elif x > right_bound - 32.0:
                push_x = -abs(push_x) - 60.0
            push_y = self.rng.uniform(200.0, 350.0)
            entry.body.apply_impulse_at_local_point((push_x * self.ball_mass, push_y * self.ball_mass))
            vx = float(entry.body.velocity.x)
            vy = max(float(entry.body.velocity.y), 150.0)
            entry.body.velocity = (vx, vy)
            entry.stall_timer = 0.0
            entry.nudge_count += 1

    def _complete_action_phase(self) -> None:
        if self._round_awarded:
            return

        placements: list[dict[str, Any]] = []
        for entry in sorted(self.current_entries, key=lambda row: (row.exit_time, row.team.name.lower())):
            self.team_points[entry.team.team_key] += int(entry.slot_value)
            placements.append(
                {
                    "team_key": entry.team.team_key,
                    "team_name": entry.team.name,
                    "short_name": entry.team.short_name,
                    "badge_file": entry.team.badge_file,
                    "slot_index": int(entry.slot_index),
                    "points": int(entry.slot_value),
                    "total_points": int(self.team_points[entry.team.team_key]),
                }
            )

        self.completed_rounds = self.current_round
        payload = {
            "round_index": int(self.current_round),
            "placements": placements,
        }
        self.round_history.append(payload)
        self.current_round_results = placements
        self.latest_completed_round_results = placements
        self._pending_round_payloads.append(payload)
        self._pending_audio_cues.append("goal")
        self.phase = "summary"
        self.phase_elapsed = 0.0
        self._collision_sparks = []  # Aksiyon biterken de listeyi temizle
        self._round_awarded = True

    def _build_static_world(self) -> None:
        static_body = self.space.static_body
        board_left = self.board_rect["x"]
        board_right = self.board_rect["x"] + self.board_rect["width"]
        top_y = self.board_rect["y"] + 34
        bottom_y = self.board_rect["y"] + self.board_rect["height"] + 30.0

        left_wall = pymunk.Segment(static_body, (board_left, top_y), (board_left, bottom_y), 5.0)
        right_wall = pymunk.Segment(static_body, (board_right, top_y), (board_right, bottom_y), 5.0)
        for wall in (left_wall, right_wall):
            wall.elasticity = 0.48
            wall.friction = 0.26

        peg_shapes: list[pymunk.Circle] = []
        for x, y in self.peg_positions:
            peg = pymunk.Circle(static_body, self.peg_radius, offset=(x, y))
            peg.elasticity = 0.94
            peg.friction = 0.62
            peg_shapes.append(peg)

        self.space.add(left_wall, right_wall, *peg_shapes)
        
        # Collision handler for sparks (with fallback for different pymunk versions)
        try:
            if hasattr(self.space, "on_collision"):
                self.space.on_collision(post_solve=self._handle_spark_collision)
            else:
                handler = self.space.add_default_collision_handler()
                handler.post_solve = self._handle_spark_collision
        except Exception:
            pass

    def _build_peg_positions(self) -> list[tuple[float, float]]:
        positions: list[tuple[float, float]] = []
        board_left, board_right = self._horizontal_bounds()

        bottom_columns = self.hole_count - 1
        upper_columns = bottom_columns + 4
        upper_gap = (board_right - board_left) / max(1, upper_columns - 1)

        top_y = self.board_rect["y"] + 150.0
        last_regular_y = self.board_rect["y"] + self.board_rect["height"] - 290.0
        regular_rows = 10
        row_gap = (last_regular_y - top_y) / max(1, regular_rows - 1)

        for row_index in range(regular_rows):
            row_y = top_y + row_index * row_gap
            odd_row = row_index % 2 == 1
            offset = upper_gap * 0.5 if odd_row else 0.0
            row_columns = upper_columns - 1 if odd_row else upper_columns
            for column_index in range(row_columns):
                x = board_left + column_index * upper_gap + offset
                positions.append((x, row_y))

        bottom_row_y = self.board_rect["y"] + self.board_rect["height"] - 178.0
        bottom_gap = (board_right - board_left) / max(1, self.hole_count)
        self.bottom_row_pegs = []
        for column_index in range(1, self.hole_count):
            x = board_left + column_index * bottom_gap
            positions.append((x, bottom_row_y))
            self.bottom_row_pegs.append((x, bottom_row_y))
        return positions

    def _build_slot_rects(self) -> list[dict[str, float]]:
        board_bottom = self.board_rect["y"] + self.board_rect["height"]
        bottom_pegs = sorted(self.bottom_row_pegs, key=lambda item: item[0])
        if len(bottom_pegs) < max(1, self.hole_count - 1):
            return []
        board_left, board_right = self._horizontal_bounds()
        boundaries = [board_left] + [x for x, _ in bottom_pegs] + [board_right]
        if len(boundaries) < self.hole_count + 1:
            return []

        slots: list[dict[str, float]] = []
        peg_y = bottom_pegs[0][1]
        for idx in range(self.hole_count):
            left_x = boundaries[idx]
            right_x = boundaries[idx + 1]
            if right_x <= left_x:
                center = (left_x + right_x) / 2.0
                left_x = center - 10.0
                right_x = center + 10.0
            width = right_x - left_x
            y = peg_y + self.peg_radius - 1.0
            height = min(54.0, max(34.0, board_bottom - y - 16.0))
            slots.append(
                {
                    "x": left_x,
                    "y": y,
                    "width": width,
                    "height": height,
                    "center_x": left_x + width / 2.0,
                    "start_x": left_x,
                    "end_x": right_x,
                }
            )
        return slots

    def _spawn_x_positions(self, team_count: int) -> list[float]:
        board_left, board_right = self._horizontal_bounds()
        left = board_left + 64.0
        right = board_right - 64.0
        lane_count = max(self.hole_count + 3, team_count + 4)
        lane_gap = (right - left) / max(1, lane_count - 1)
        lane_xs = [left + lane_index * lane_gap for lane_index in range(lane_count)]
        selected_indices = self.rng.sample(range(lane_count), k=min(team_count, lane_count))
        self.rng.shuffle(selected_indices)
        positions: list[float] = []
        for lane_index in selected_indices[:team_count]:
            jitter = self.rng.uniform(-20.0, 20.0)
            x = lane_xs[lane_index] + jitter
            x = max(self.board_rect["x"] + 84.0, min(self.board_rect["x"] + self.board_rect["width"] - 84.0, x))
            positions.append(x)
        while len(positions) < team_count:
            positions.append(self.rng.uniform(left, right))
        return positions

    def _horizontal_bounds(self) -> tuple[float, float]:
        # Fizik duvarı ile çivi çakışmasını engellemek için güvenli iç sınır.
        left = self.board_rect["x"] + self.peg_radius + 6.0
        right = self.board_rect["x"] + self.board_rect["width"] - self.peg_radius - 6.0
        return left, right

    def _resolve_slot_index(self, x_value: float) -> int:
        x = float(x_value)
        if not self.slot_rects:
            return 0

        for idx, slot in enumerate(self.slot_rects):
            if float(slot["start_x"]) <= x <= float(slot["end_x"]):
                return idx

        first = self.slot_rects[0]
        last = self.slot_rects[-1]
        if x <= float(first["start_x"]):
            return 0
        if x >= float(last["end_x"]):
            return len(self.slot_rects) - 1

        nearest_idx = 0
        nearest_dist = float("inf")
        for idx, slot in enumerate(self.slot_rects):
            dist = abs(float(slot["center_x"]) - x)
            if dist < nearest_dist:
                nearest_dist = dist
                nearest_idx = idx
        return nearest_idx

    def _build_standings(self) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for team in self.teams:
            rows.append(
                {
                    "team_key": team.team_key,
                    "name": team.name,
                    "short_name": team.short_name,
                    "badge_file": team.badge_file,
                    "points": int(self.team_points.get(team.team_key, 0)),
                }
            )
        rows.sort(key=lambda row: (-int(row["points"]), str(row["name"]).lower()))
        for index, row in enumerate(rows, start=1):
            row["rank"] = index
        return rows

    def _round_progress_ratio(self) -> float:
        if self.phase == "action":
            return min(1.0, self.phase_elapsed / max(0.001, self.action_timeout_seconds))
        if self.phase in {"summary", "final"}:
            return 1.0
        return 0.0

    def _round_status_text(self) -> str:
        return ""

    def _team_name(self, team_key: str | None) -> str:
        if not team_key:
            return "TBD"
        for team in self.teams:
            if team.team_key == team_key:
                return team.name
        return "TBD"

    def _coerce_hole_values(self, values: list[int]) -> list[int]:
        parsed: list[int] = []
        for value in values:
            try:
                parsed.append(int(value))
            except Exception:
                continue
        if len(parsed) == self.TARGET_HOLE_COUNT:
            return parsed

        template = list(self.DEFAULT_HOLE_TEMPLATE)
        rng = random.Random(self.random_seed)
        rng.shuffle(template)
        if parsed:
            merged = list(parsed[: self.TARGET_HOLE_COUNT])
            for candidate in template:
                if len(merged) >= self.TARGET_HOLE_COUNT:
                    break
                if candidate not in merged:
                    merged.append(candidate)
            while len(merged) < self.TARGET_HOLE_COUNT:
                merged.append(template[len(merged) % len(template)])
            return merged
        return template

    @staticmethod
    def _color_seed(team_key: str) -> int:
        text = str(team_key or "")
        return sum((index + 1) * ord(ch) for index, ch in enumerate(text)) % 360
