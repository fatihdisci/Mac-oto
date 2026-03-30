# physics.py
from __future__ import annotations

import math
import random
from dataclasses import dataclass
from typing import Dict, List, Optional

import pymunk

from config import SimulationConfig
from models import MatchSelection, TeamRecord


# ============================================================
# VERİ MODELLERİ
# ============================================================

@dataclass
class GapDefinition:
    label: str
    start_x: float
    end_x: float

    @property
    def center_x(self) -> float:
        return (self.start_x + self.end_x) / 2.0


@dataclass
class BallState:
    ball_id: int
    round_index: int
    team_key: str
    team_name: str
    team_short_name: str
    team_badge_file: str
    body: pymunk.Body
    shape: pymunk.Circle
    is_active: bool = True
    result_label: Optional[str] = None
    stall_timer: float = 0.0
    nudge_count: int = 0
    last_x: float = 0.0
    last_y: float = 0.0


@dataclass
class BallExitEvent:
    round_index: int
    team_key: str
    team_name: str
    gap_label: str
    x_at_exit: float


# ============================================================
# ANA FİZİK MOTORU
# ============================================================
# Kritik değişiklik:
# - Artık sabit cfg.teams yok
# - Bu sınıf MatchSelection alır
# - Yani Team A ve Team B GUI'den seçilen gerçek takımlardır
# ============================================================

class MarbleRacePhysics:
    def __init__(self, cfg: SimulationConfig, match_selection: MatchSelection) -> None:
        self.cfg = cfg
        self.match_selection = match_selection
        self.rng = random.Random(cfg.gameplay.random_seed)

        # Pymunk fizik uzayı
        self.space = pymunk.Space()
        self.space.gravity = (0.0, cfg.physics.gravity_y)
        self.space.iterations = cfg.physics.space_iterations
        self.space.damping = cfg.physics.damping

        # Team A ve Team B referansları
        self.team_a = match_selection.team_a
        self.team_b = match_selection.team_b

        self.team_a_key = self._team_key(self.team_a)
        self.team_b_key = self._team_key(self.team_b)

        self.team_spawn_ratios: dict[str, float] = {
            self.team_a_key: cfg.gameplay.team_a_spawn_x_ratio,
            self.team_b_key: cfg.gameplay.team_b_spawn_x_ratio,
        }

        # Skor
        self.scores: Dict[str, int] = {
            self.team_a_key: 0,
            self.team_b_key: 0,
        }

        # Raund / akış durumu
        self.current_round: int = 0
        self.completed_rounds: int = 0
        self.pending_round_delay: float = 0.0
        self.simulation_finished: bool = False

        # Aktif toplar ve geçmiş olaylar
        self._ball_counter: int = 0
        self.active_balls: List[BallState] = []
        self.exit_events: List[BallExitEvent] = []
        self.latest_round_events: List[BallExitEvent] = []

        # Sıralı spawn: B topu A'dan 0.4s sonra düşer
        self._pending_b_timer: float = -1.0

        # Alt boşluk tanımları
        self.gaps: List[GapDefinition] = self._build_gap_definitions()

        # Dünya kur
        self._build_world()

        # İlk raundu başlat
        self._spawn_next_round()

    # --------------------------------------------------------
    # ANA UPDATE
    # --------------------------------------------------------
    def update(self, dt: float) -> None:
        """
        Her frame fizik akışını yürütür.
        """
        if self.simulation_finished:
            return

        sub_dt = dt / self.cfg.physics.substeps
        for _ in range(self.cfg.physics.substeps):
            self.space.step(sub_dt)

        self._process_ball_exits()
        self._resolve_stuck_balls(dt)

        if self._pending_b_timer > 0.0:
            self._pending_b_timer -= dt
            if self._pending_b_timer <= 0.0:
                self._pending_b_timer = -1.0
                self._spawn_ball_for_team(self.team_b, self.team_b_key)

        if not self.active_balls:
            if self.completed_rounds >= self.cfg.gameplay.max_rounds:
                self.simulation_finished = True
                return

            if self.pending_round_delay <= 0.0:
                self.pending_round_delay = self.cfg.gameplay.round_pause_seconds

            self.pending_round_delay -= dt
            if self.pending_round_delay <= 0.0:
                self._spawn_next_round()

    # --------------------------------------------------------
    # DIŞ VERİ METOTLARI
    # --------------------------------------------------------
    def is_finished(self) -> bool:
        return self.simulation_finished

    def get_scores(self) -> Dict[str, int]:
        """
        Skorları takım isimleriyle döner.
        Renderer tarafında daha rahat kullanılır.
        """
        return {
            self.team_a.name: self.scores.get(self.team_a_key, 0),
            self.team_b.name: self.scores.get(self.team_b_key, 0),
        }

    def get_active_ball_draw_data(self) -> List[dict]:
        """
        Renderer tarafı için aktif topları sade sözlükler halinde döner.
        """
        draw_list: List[dict] = []

        for ball in self.active_balls:
            draw_list.append(
                {
                    "ball_id": ball.ball_id,
                    "team_key": ball.team_key,
                    "team_name": ball.team_name,
                    "team_short_name": ball.team_short_name,
                    "team_badge_file": ball.team_badge_file,
                    "x": float(ball.body.position.x),
                    "y": float(ball.body.position.y),
                    "angle_radians": float(ball.body.angle),
                    "radius": float(ball.shape.radius),
                }
            )

        return draw_list

    def get_gap_draw_data(self) -> List[dict]:
        return [
            {
                "label": gap.label,
                "center_x": gap.center_x,
                "start_x": gap.start_x,
                "end_x": gap.end_x,
            }
            for gap in self.gaps
        ]

    def get_state_snapshot(self) -> dict:
        """
        GUI / renderer / main için özet state.
        """
        score_a = self.scores.get(self.team_a_key, 0)
        score_b = self.scores.get(self.team_b_key, 0)

        return {
            "current_round": self.current_round,
            "completed_rounds": self.completed_rounds,
            "scores": {
                self.team_a.name: score_a,
                self.team_b.name: score_b,
            },
            "teams": [
                {
                    "role": "A",
                    "team_key": self.team_a_key,
                    "name": self.team_a.name,
                    "short_name": self.team_a.short_name,
                    "badge_file": self.team_a.badge_file,
                    "league_name": self.team_a.league_name,
                    "score": score_a,
                },
                {
                    "role": "B",
                    "team_key": self.team_b_key,
                    "name": self.team_b.name,
                    "short_name": self.team_b.short_name,
                    "badge_file": self.team_b.badge_file,
                    "league_name": self.team_b.league_name,
                    "score": score_b,
                },
            ],
            "match_title": self.match_selection.title,
            "is_real_fixture_reference": self.match_selection.is_real_fixture_reference,
            "active_ball_count": len(self.active_balls),
            "latest_round_events": [
                {
                    "round_index": event.round_index,
                    "team_key": event.team_key,
                    "team_name": event.team_name,
                    "gap_label": event.gap_label,
                    "x_at_exit": event.x_at_exit,
                }
                for event in self.latest_round_events
            ],
            "finished": self.simulation_finished,
        }

    # --------------------------------------------------------
    # DÜNYA KURULUMU
    # --------------------------------------------------------
    def _build_world(self) -> None:
        self._build_side_walls()
        self._build_bottom_floor_with_gaps()
        self._build_pegs()

    def _build_side_walls(self) -> None:
        static_body = self.space.static_body
        left = self.cfg.playfield_left
        right = self.cfg.playfield_right
        top = 0
        bottom = self.cfg.video.height + 200
        thickness = 6

        ramp_top_y = self.cfg.layout.floor_y - 180

        wall_segments = [
            pymunk.Segment(static_body, (left, top), (left, ramp_top_y), thickness),
            pymunk.Segment(static_body, (right, top), (right, ramp_top_y), thickness),
        ]

        for seg in wall_segments:
            seg.elasticity = self.cfg.physics.wall_elasticity
            seg.friction = self.cfg.physics.wall_friction

        self.space.add(*wall_segments)

    def _build_bottom_floor_with_gaps(self) -> None:
        static_body = self.space.static_body
        floor_y = self.cfg.layout.floor_y
        thickness = 8
        ramp_rise = 180

        left_edge = self.cfg.playfield_left
        right_edge = self.cfg.playfield_right

        left_gap, center_gap, right_gap = self.gaps

        floor_segments = [
            pymunk.Segment(static_body, (left_edge, floor_y - ramp_rise), (left_gap.start_x, floor_y), thickness),
            pymunk.Segment(static_body, (left_gap.end_x, floor_y), (center_gap.start_x, floor_y), thickness),
            pymunk.Segment(static_body, (center_gap.end_x, floor_y), (right_gap.start_x, floor_y), thickness),
            pymunk.Segment(static_body, (right_gap.end_x, floor_y), (right_edge, floor_y - ramp_rise), thickness),
        ]

        post_h = self.cfg.layout.gap_post_height
        x_posts = [
            left_gap.start_x,
            left_gap.end_x,
            center_gap.start_x,
            center_gap.end_x,
            right_gap.start_x,
            right_gap.end_x,
        ]

        post_segments = [
            pymunk.Segment(static_body, (x, floor_y), (x, floor_y + post_h), thickness)
            for x in x_posts
        ]

        for seg in floor_segments + post_segments:
            seg.elasticity = self.cfg.physics.wall_elasticity
            seg.friction = self.cfg.physics.wall_friction

        self.space.add(*floor_segments, *post_segments)

    def _build_pegs(self) -> None:
        static_body = self.space.static_body
        peg_radius = self.cfg.physics.peg_radius
        peg_shapes = []

        for x, y in self._iter_peg_centers():
            peg = pymunk.Circle(static_body, peg_radius, offset=(x, y))
            peg.elasticity = self.cfg.physics.peg_elasticity
            peg.friction = self.cfg.physics.peg_friction
            peg_shapes.append(peg)

        self.space.add(*peg_shapes)

    def _iter_peg_centers(self) -> list[tuple[float, float]]:
        spacing_x = self.cfg.layout.peg_spacing_x
        spacing_y = self.cfg.layout.peg_spacing_y
        rows = self.cfg.layout.peg_rows
        top_y = self.cfg.layout.peg_top_y
        peg_radius = self.cfg.physics.peg_radius
        # Top, çivi ile duvar arasından kılpayı geçebilsin:
        # boşluk = margin - peg_radius = 2*ball_r + 2  (ball çapı=2*ball_r, +2px pay)
        margin = peg_radius + 2 * self.cfg.physics.ball_radius + 2

        left_wall = self.cfg.playfield_left + margin
        right_wall = self.cfg.playfield_right - margin
        cx = (self.cfg.playfield_left + self.cfg.playfield_right) / 2.0
        ramp_clearance_y = self.cfg.layout.floor_y - 280

        usable = right_wall - left_wall
        cols_even = max(1, int(usable // spacing_x))
        total_even = cols_even * spacing_x
        start_even = cx - total_even / 2.0

        result = []
        for row in range(2, rows):
            y = top_y + row * spacing_y
            if y > ramp_clearance_y:
                break

            if row % 2 == 0:
                for col in range(cols_even + 1):
                    x = start_even + col * spacing_x
                    if left_wall <= x <= right_wall:
                        result.append((x, y))
            else:
                for col in range(cols_even):
                    x = start_even + spacing_x / 2 + col * spacing_x
                    if left_wall <= x <= right_wall:
                        result.append((x, y))

        return result

    # --------------------------------------------------------
    # GAP HESABI
    # --------------------------------------------------------
    def _build_gap_definitions(self) -> List[GapDefinition]:
        cx = self.cfg.playfield_center_x
        side_gap_w = self.cfg.layout.side_gap_width
        goal_gap_w = self.cfg.layout.goal_gap_width
        divider_w = self.cfg.layout.divider_width

        total_span = side_gap_w + divider_w + goal_gap_w + divider_w + side_gap_w
        left_start = cx - total_span / 2

        left_gap = GapDefinition(
            label=self.cfg.gameplay.left_gap_label,
            start_x=left_start,
            end_x=left_start + side_gap_w,
        )

        center_gap = GapDefinition(
            label=self.cfg.gameplay.center_gap_label,
            start_x=left_gap.end_x + divider_w,
            end_x=left_gap.end_x + divider_w + goal_gap_w,
        )

        right_gap = GapDefinition(
            label=self.cfg.gameplay.right_gap_label,
            start_x=center_gap.end_x + divider_w,
            end_x=center_gap.end_x + divider_w + side_gap_w,
        )

        return [left_gap, center_gap, right_gap]

    # --------------------------------------------------------
    # RAUND YÖNETİMİ
    # --------------------------------------------------------
    def _spawn_next_round(self) -> None:
        if self.completed_rounds >= self.cfg.gameplay.max_rounds:
            self.simulation_finished = True
            return

        self.current_round += 1
        self.pending_round_delay = 0.0
        self.latest_round_events = []

        self._spawn_ball_for_team(self.team_a, self.team_a_key)
        self._pending_b_timer = 0.4

    def _spawn_ball_for_team(self, team: TeamRecord, team_key: str) -> None:
        radius = self.cfg.physics.ball_radius
        mass = self.cfg.physics.ball_mass
        moment = pymunk.moment_for_circle(mass, 0, radius)

        body = pymunk.Body(mass, moment)

        left_bound = self.cfg.playfield_left + radius + 20
        right_bound = self.cfg.playfield_right - radius - 20

        spawn_x = self.rng.uniform(left_bound, right_bound)

        spawn_y = self.cfg.layout.top_spawn_y
        body.position = (spawn_x, spawn_y)

        body.angle = self.rng.uniform(0, math.tau)
        body.angular_velocity = self.rng.uniform(
            self.cfg.physics.spawn_initial_angular_velocity_min,
            self.cfg.physics.spawn_initial_angular_velocity_max,
        )

        shape = pymunk.Circle(body, radius)
        shape.elasticity = self.cfg.physics.ball_elasticity
        shape.friction = self.cfg.physics.ball_friction

        self.space.add(body, shape)

        self._ball_counter += 1
        self.active_balls.append(
            BallState(
                ball_id=self._ball_counter,
                round_index=self.current_round,
                team_key=team_key,
                team_name=team.name,
                team_short_name=team.short_name,
                team_badge_file=team.badge_file,
                body=body,
                shape=shape,
                last_x=float(body.position.x),
                last_y=float(body.position.y),
            )
        )

    # --------------------------------------------------------
    # ÇIKIŞ / SKOR İŞLEME
    # --------------------------------------------------------
    def _process_ball_exits(self) -> None:
        if not self.active_balls:
            return

        balls_to_remove: List[BallState] = []

        for ball in self.active_balls:
            if ball.body.position.y >= self.cfg.layout.exit_line_y:
                x_at_exit = float(ball.body.position.x)
                result_label = self._classify_gap_by_x(x_at_exit)

                ball.is_active = False
                ball.result_label = result_label

                event = BallExitEvent(
                    round_index=ball.round_index,
                    team_key=ball.team_key,
                    team_name=ball.team_name,
                    gap_label=result_label,
                    x_at_exit=x_at_exit,
                )
                self.exit_events.append(event)
                self.latest_round_events.append(event)

                if result_label == self.cfg.gameplay.center_gap_label:
                    self.scores[ball.team_key] += 1

                balls_to_remove.append(ball)

        for ball in balls_to_remove:
            self._remove_ball(ball)

        if not self.active_balls and self.current_round > self.completed_rounds:
            self.completed_rounds = self.current_round

    def _resolve_stuck_balls(self, dt: float) -> None:
        center_x = self.cfg.playfield_center_x
        left_wall = self.cfg.playfield_left
        right_wall = self.cfg.playfield_right
        ball_r = self.cfg.physics.ball_radius

        for ball in self.active_balls:
            current_x = float(ball.body.position.x)
            current_y = float(ball.body.position.y)
            moved_distance = math.hypot(current_x - ball.last_x, current_y - ball.last_y)
            speed = float(ball.body.velocity.length)

            if moved_distance < 2.0 and speed < 40.0 and current_y > self.cfg.layout.peg_top_y - 20:
                ball.stall_timer += dt
            else:
                ball.stall_timer = max(0.0, ball.stall_timer - dt * 0.5)

            if ball.stall_timer >= 0.40:
                # Topu yukari kaldir ve merkeze dogru ittir
                lift_y = max(self.cfg.layout.peg_top_y, current_y - 80)
                ball.body.position = (current_x, lift_y)

                # Merkeze dogru yonlendir
                direction_to_center = 1.0 if current_x < center_x else -1.0
                distance_from_center = abs(current_x - center_x)
                horizontal_force = direction_to_center * min(350.0, distance_from_center * 1.2)
                horizontal_force += self.rng.uniform(-100.0, 100.0)

                ball.body.velocity = (horizontal_force, self.rng.uniform(150.0, 280.0))
                ball.body.angular_velocity = self.rng.uniform(-8.0, 8.0)
                ball.stall_timer = 0.0
                ball.nudge_count += 1

            # Guvenlik: cok fazla takilirsa direkt asagi birak
            if ball.nudge_count >= 5:
                ball.body.position = (center_x + self.rng.uniform(-100, 100), self.cfg.layout.floor_y - 200)
                ball.body.velocity = (self.rng.uniform(-50, 50), 300.0)
                ball.nudge_count = 0

            ball.last_x = current_x
            ball.last_y = current_y

    def _classify_gap_by_x(self, x_pos: float) -> str:
        for gap in self.gaps:
            if gap.start_x <= x_pos <= gap.end_x:
                return gap.label

        return "OUT"

    def _remove_ball(self, ball: BallState) -> None:
        if ball.shape in self.space.shapes and ball.body in self.space.bodies:
            self.space.remove(ball.body, ball.shape)

        self.active_balls = [b for b in self.active_balls if b.ball_id != ball.ball_id]

    # --------------------------------------------------------
    # HELPERLAR
    # --------------------------------------------------------
    def _team_key(self, team: TeamRecord) -> str:
        """
        Takımı iç sistemde benzersiz tanımlamak için anahtar.
        """
        if team.team_id:
            return team.team_id
        return f"{team.league_slug}:{team.name.lower()}"
