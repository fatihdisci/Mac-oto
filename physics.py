# physics.py
from __future__ import annotations

import math
import random
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

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


@dataclass
class PowerZoneDefinition:
    zone_id: int
    zone_type: str
    x: float
    y: float
    radius: float
    shape: pymunk.Circle


# ============================================================
# ANA FİZİK MOTORU
# ============================================================
# Kritik değişiklik:
# - Artık sabit cfg.teams yok
# - Bu sınıf MatchSelection alır
# - Yani Team A ve Team B GUI'den seçilen gerçek takımlardır
# ============================================================

@dataclass
class PegRowRuntime:
    row_index: int
    y: float
    body: pymunk.Body
    phase: float
    speed_x: float
    wrap_period: float
    peg_shapes: List[pymunk.Circle]


@dataclass
class PegStaticRuntime:
    x: float
    y: float
    shape: pymunk.Circle
    is_visible: bool = True


@dataclass
class GearRuntime:
    gear_id: int
    body: pymunk.Body
    pivot: pymunk.PivotJoint
    motor: pymunk.SimpleMotor
    radius: float
    spoke_count: int
    spoke_shapes: List[pymunk.Shape]



class MarbleRacePhysics:
    COLLISION_TYPE_BALL = 1
    COLLISION_TYPE_POWER_ZONE = 40
    COLLISION_TYPE_BUMPER = 2

    def __init__(self, cfg: SimulationConfig, match_selection: MatchSelection) -> None:
        self.cfg = cfg
        self.match_selection = match_selection
        self.engine_mode = (match_selection.engine_mode or "power_pegs").strip().lower()
        self.gear_mode_enabled = self.engine_mode == "football_gears"
        self.var_mode_enabled = self.engine_mode == "football_var"
        self.guided_mode_enabled = self.engine_mode == "football_result_guided_test"
        self.shifting_rows_enabled = self.engine_mode in {
            "football_shift",
            "power_pegs_shift",
            "normal_shift",
        }
        self.blinking_pegs_enabled = self.engine_mode in {
            "football_blink",
        }
        self.power_zones_enabled = self.engine_mode in {
            "power_pegs",
            "power_pegs_shift",
            "slowfast",
            "classic",
        }

        self.left_gap_label = self.cfg.gameplay.left_gap_label
        self.center_gap_label = self.cfg.gameplay.center_gap_label
        self.right_gap_label = self.cfg.gameplay.right_gap_label

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
        if self.guided_mode_enabled:
            raw_target_a = match_selection.guided_target_score_a
            raw_target_b = match_selection.guided_target_score_b
            self.guided_target_score_a: int | None = max(0, int(raw_target_a if raw_target_a is not None else 2))
            self.guided_target_score_b: int | None = max(0, int(raw_target_b if raw_target_b is not None else 1))
        else:
            self.guided_target_score_a = None
            self.guided_target_score_b = None

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

        # Power peg runtime state
        self._sim_time: float = 0.0
        self._power_zone_counter: int = 0
        self.power_zones: List[PowerZoneDefinition] = []
        self._power_zone_by_shape_id: Dict[int, PowerZoneDefinition] = {}
        self._power_zone_last_trigger_at: Dict[int, float] = {}
        self._ball_shape_id_to_ball_id: Dict[int, int] = {}
        self._ball_power_cooldown_until: Dict[int, float] = {}
        self._zone_hit_cooldown_until: Dict[Tuple[int, int], float] = {}
        self._peg_rows: List[PegRowRuntime] = []
        self._static_pegs: List[PegStaticRuntime] = []
        self._blink_hidden_indices: set[int] = set()
        self._blink_phase_hidden: bool = False
        self._blink_next_switch_at: float = 2.0
        self._blink_hidden_ratio: float = 0.20
        self._blink_hidden_duration: float = 0.95
        self._blink_visible_duration: float = 2.55

        # Sıralı spawn: B topu A'dan 0.4s sonra düşer
        self._pending_b_timer: float = -1.0

        self.gears: List[GearRuntime] = []
        self._gear_deflectors: List[dict] = []  # Kenar deflektör çizgileri (çizim için)
        self._gear_bumpers: List[dict] = []     # Statik bumper çivileri (çizim için)
        self._bumper_hits: List[dict] = []      # Bumper flash event listesi

        # Alt boşluk tanımları
        self.gaps: List[GapDefinition] = self._build_gap_definitions()
        if self.power_zones_enabled:
            self._register_power_collision_callbacks()

        # Çarpışma spark verileri (partikül sistemi için)
        self._collision_sparks: List[dict] = []
        self._register_spark_collision_callback()
        self._register_bumper_collision_callback()

        # Dünya kur
        self._build_world()

        # İlk raundu başlat
        self._spawn_next_round()

    # --------------------------------------------------------
    # ANA UPDATE
    # --------------------------------------------------------
    def update(self, dt: float, gravity_override: float | None = None) -> None:
        """
        Her frame fizik akışını yürütür.
        gravity_override: None ise config gravity'si kullanılır; değer verilirse
        o frame için y-gravity'si override edilir (Tension mode).
        """
        if self.simulation_finished:
            return

        default_gravity = float(self.cfg.physics.gravity_y)
        target_gravity = default_gravity if gravity_override is None else float(gravity_override)
        if abs(self.space.gravity[1] - target_gravity) > 0.5:
            self.space.gravity = (0.0, target_gravity)

        self._sim_time += dt
        self._advance_blinking_pegs()
        self._apply_guided_live_ball_bias(dt)
        sub_dt = dt / self.cfg.physics.substeps
        for _ in range(self.cfg.physics.substeps):
            self._advance_shifting_rows(sub_dt)
            self.space.step(sub_dt)

        self._expire_power_effect_cooldowns()
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
                    "vx": float(ball.body.velocity.x),
                    "vy": float(ball.body.velocity.y),
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
            "engine_mode": self.engine_mode,
            "var_mode_enabled": self.var_mode_enabled,
            "guided_mode_enabled": self.guided_mode_enabled,
            "guided_target_score_a": self.guided_target_score_a,
            "guided_target_score_b": self.guided_target_score_b,
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
            "gap_labels": {
                "left": self.left_gap_label,
                "center": self.center_gap_label,
                "right": self.right_gap_label,
            },
            "scoring_gap_label": self.center_gap_label,
            "arena_theme": self.match_selection.arena_theme,
            "shifting_rows_enabled": self.shifting_rows_enabled,
            "blinking_pegs_enabled": self.blinking_pegs_enabled,
            "peg_draw_data": self._build_peg_draw_data(),
            "gear_draw_data": self._build_gear_draw_data(),
            "gear_deflectors": self._gear_deflectors if self.gear_mode_enabled else [],
            "gear_bumpers": self._gear_bumpers if self.gear_mode_enabled else [],
            "gear_bumper_hits": list(self._bumper_hits) if self.gear_mode_enabled else [],
            "power_zone_draw_data": self._build_power_zone_draw_data(),
            "physics_time_seconds": self._sim_time,
            "finished": self.simulation_finished,
        }

    # --------------------------------------------------------
    # DÜNYA KURULUMU
    # --------------------------------------------------------
    def _build_world(self) -> None:
        self._build_side_walls()
        self._build_bottom_floor_with_gaps()
        if self.gear_mode_enabled:
            self._build_gears()
        else:
            self._build_pegs()
        if self.power_zones_enabled:
            self._build_power_zones()

    def _build_gears(self) -> None:
        self.gears = []
        static_body = self.space.static_body
        cx = self.cfg.playfield_center_x
        left = self.cfg.playfield_left
        right = self.cfg.playfield_right

        # Oyun alanı: left=70, right=1010, cx=540, genişlik=940
        # Top radius=34. Büyük çarklar, brick (tuğla) deseni — boşluk bırakmaz.
        # Satır A (tek): 3 büyük çark   sütunlarda sol/orta/sağ
        # Satır B (çift): 2 orta çark   araya girer
        # 4 katman: A-B-A-B

        rA = 105   # büyük çark kol uzunluğu
        rB = 95    # ara çark kol uzunluğu (yeterince büyük görünsün)

        # A satırı sütunları — kenar çarkları duvara çakışmasın: rA + top_r + güvenlik
        # top_r=34, güvenlik=20 → left + rA + 54
        margin = self.cfg.physics.ball_radius + 20   # 54px
        cA_l = left  + rA + margin   # ~229
        cA_c = cx                     # 540
        cA_r = right - rA - margin    # ~851

        # B satırı sütunları: A boşluklarının ortası
        cB_l = (cA_l + cA_c) // 2  # ~384
        cB_r = (cA_c + cA_r) // 2  # ~695

        # y koordinatları — HUD alt kenarı ~390px, ilk çark merkezi 390+rA+65 = 560
        y1 = 560
        y2 = 880
        y3 = 1190
        y4 = 1490

        # Komşu çarklar her zaman zıt yönde döner — kaotik saçılma sağlar
        # Aynı satırda yanyana = zıt, üst-alt = zıt → hiçbir yön baskın olmaz
        # Hızlar da hafif farklı (1.6-2.2 arası)
        # (x, y, radius, spokes, motor_rate)
        layout = [
            # Satır 1 — A (3 büyük): sol+, orta-, sağ+
            (cA_l, y1, rA, 6,  1.7),
            (cA_c, y1, rA, 6, -2.1),
            (cA_r, y1, rA, 6,  1.9),
            # Satır 2 — B (2 orta): zıt satır 1'e
            (cB_l, y2, rB, 6, -1.8),
            (cB_r, y2, rB, 6,  2.0),
            # Satır 3 — A (3 büyük): satır 1'e zıt
            (cA_l, y3, rA, 6, -2.0),
            (cA_c, y3, rA, 6,  1.7),
            (cA_r, y3, rA, 6, -1.9),
        ]

        for i, (x, y, radius, spokes, rate) in enumerate(layout):
            mass = 8.0
            moment = pymunk.moment_for_circle(mass, 0, radius)
            body = pymunk.Body(mass, moment)
            body.position = (x, y)

            # Sadece kollar — merkezden uca, hub yok
            spoke_shapes = []
            for s in range(spokes):
                angle = (s / spokes) * math.tau
                spoke = pymunk.Segment(
                    body,
                    (0, 0),
                    (radius * math.cos(angle), radius * math.sin(angle)),
                    4,
                )
                spoke.elasticity = 0.4
                spoke.friction = 0.65
                spoke_shapes.append(spoke)

            pivot = pymunk.PivotJoint(static_body, body, (x, y), (0, 0))
            motor = pymunk.SimpleMotor(static_body, body, rate)
            motor.max_force = 8e6

            self.space.add(body, *spoke_shapes, pivot, motor)

            self.gears.append(
                GearRuntime(
                    gear_id=i,
                    body=body,
                    pivot=pivot,
                    motor=motor,
                    radius=radius,
                    spoke_count=spokes,
                    spoke_shapes=spoke_shapes,
                )
            )

        self._gear_deflectors = []

        # Bumper çivileri — sadece kritik boşluklara, az sayıda
        br = 20   # normal bumper yarıçapı
        bumper_positions = [
            # Satır 1 (A) ve 2 (B) arası -> A'nın boşluk hizası (çarklar topu ezmesin diye y aşağı kaydırıldı)
            (cA_l, 770, br, 1.1),
            (cA_c, 770, br, 1.1),
            (cA_r, 770, br, 1.1),
            # Satır 2 (B) ve 3 (A) arası -> B'nin boşluk hizası
            (cB_l, 1070, br, 1.1),
            (cB_r, 1070, br, 1.1),
            # Satır 3 (A) ve 4 (B) arası -> A'nın boşluk hizası
            (cA_l, 1388, br, 1.1),
            (cA_c, 1388, br, 1.1),
            (cA_r, 1388, br, 1.1),
            # Alt satırdaki iptal edilen 2 çarkın yerine normal boyutta, biraz daha aşağıda sekme sağlayan çiviler
            (cB_l, y4 + 35, br, 1.55),
            (cB_r, y4 + 35, br, 1.55),
        ]
        self._gear_bumpers = [{"x": x, "y": y, "r": r} for x, y, r, e in bumper_positions]
        for bx, by, r, e in bumper_positions:
            shape = pymunk.Circle(static_body, r, offset=(bx, by))
            shape.elasticity = e   # yüksek sekme
            shape.friction = 0.1
            shape.collision_type = self.COLLISION_TYPE_BUMPER
            self.space.add(shape)

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
        divider_peak_rise = max(20, int(self.cfg.physics.ball_radius * 0.8))

        left_edge = self.cfg.playfield_left
        right_edge = self.cfg.playfield_right

        left_gap, center_gap, right_gap = self.gaps

        left_divider_peak_x = (left_gap.end_x + center_gap.start_x) / 2.0
        right_divider_peak_x = (center_gap.end_x + right_gap.start_x) / 2.0

        floor_segments = [
            pymunk.Segment(static_body, (left_edge, floor_y - ramp_rise), (left_gap.start_x, floor_y), thickness),
            pymunk.Segment(
                static_body,
                (left_gap.end_x, floor_y),
                (left_divider_peak_x, floor_y - divider_peak_rise),
                thickness,
            ),
            pymunk.Segment(
                static_body,
                (left_divider_peak_x, floor_y - divider_peak_rise),
                (center_gap.start_x, floor_y),
                thickness,
            ),
            pymunk.Segment(
                static_body,
                (center_gap.end_x, floor_y),
                (right_divider_peak_x, floor_y - divider_peak_rise),
                thickness,
            ),
            pymunk.Segment(
                static_body,
                (right_divider_peak_x, floor_y - divider_peak_rise),
                (right_gap.start_x, floor_y),
                thickness,
            ),
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
        self._peg_rows = []
        self._static_pegs = []
        self._blink_hidden_indices = set()
        self._blink_phase_hidden = False
        self._blink_next_switch_at = 2.0
        if not self.shifting_rows_enabled:
            static_body = self.space.static_body
            peg_radius = self.cfg.physics.peg_radius
            peg_shapes = []

            for x, y in self._iter_peg_centers():
                peg = pymunk.Circle(static_body, peg_radius, offset=(x, y))
                peg.elasticity = self.cfg.physics.peg_elasticity
                peg.friction = self.cfg.physics.peg_friction
                peg_shapes.append(peg)
                self._static_pegs.append(
                    PegStaticRuntime(
                        x=float(x),
                        y=float(y),
                        shape=peg,
                        is_visible=True,
                    )
                )

            self.space.add(*peg_shapes)
            self._apply_blink_visibility(self._blink_hidden_indices)
            return

        peg_radius = self.cfg.physics.peg_radius
        for row_spec in self._iter_shifting_row_layouts():
            body = pymunk.Body(body_type=pymunk.Body.KINEMATIC)
            body.position = (row_spec["phase"], row_spec["y"])
            body.velocity = (row_spec["speed_x"], 0.0)

            row_shapes: List[pymunk.Circle] = []
            for local_x in row_spec["local_xs"]:
                peg = pymunk.Circle(body, peg_radius, offset=(local_x, 0.0))
                peg.elasticity = self.cfg.physics.peg_elasticity
                peg.friction = self.cfg.physics.peg_friction
                row_shapes.append(peg)

            self.space.add(body, *row_shapes)
            self._peg_rows.append(
                PegRowRuntime(
                    row_index=row_spec["row_index"],
                    y=row_spec["y"],
                    body=body,
                    phase=row_spec["phase"],
                    speed_x=row_spec["speed_x"],
                    wrap_period=row_spec["wrap_period"],
                    peg_shapes=row_shapes,
                )
            )

    def _iter_shifting_row_layouts(self) -> List[dict]:
        spacing_y = self.cfg.layout.peg_spacing_y
        rows = self.cfg.layout.peg_rows
        top_y = self.cfg.layout.peg_top_y
        ramp_clearance_y = self.cfg.layout.floor_y - 280

        left_edge = float(self.cfg.playfield_left)
        right_edge = float(self.cfg.playfield_right)
        usable = right_edge - left_edge

        cols_even = max(2, round(usable / self.cfg.layout.peg_spacing_x))
        spacing_x = usable / cols_even
        base_speed = max(10.0, spacing_x * 0.34)

        row_specs: List[dict] = []
        visual_row_index = 0
        for row in range(2, rows):
            y = top_y + row * spacing_y
            if y > ramp_clearance_y:
                break

            visual_row_index += 1
            if row % 2 == 0:
                base_offset = 0.0
                col_values = range(-1, cols_even + 2)
            else:
                base_offset = spacing_x / 2.0
                col_values = range(-1, cols_even + 1)

            local_xs = [left_edge + base_offset + col * spacing_x for col in col_values]
            direction = 1.0 if (visual_row_index % 2 == 1) else -1.0
            speed_variation = 1.0 + (visual_row_index % 3) * 0.07
            row_specs.append(
                {
                    "row_index": row,
                    "y": y,
                    "local_xs": local_xs,
                    "speed_x": direction * base_speed * speed_variation,
                    "phase": self.rng.uniform(0.0, spacing_x),
                    "wrap_period": spacing_x,
                }
            )

        return row_specs

    def _iter_peg_centers(self) -> list[tuple[float, float]]:
        spacing_y = self.cfg.layout.peg_spacing_y
        rows = self.cfg.layout.peg_rows
        top_y = self.cfg.layout.peg_top_y
        ramp_clearance_y = self.cfg.layout.floor_y - 280

        left_edge = float(self.cfg.playfield_left)
        right_edge = float(self.cfg.playfield_right)
        usable = right_edge - left_edge

        cols_even = max(2, round(usable / self.cfg.layout.peg_spacing_x))
        spacing_x = usable / cols_even

        result = []
        for row in range(2, rows):
            y = top_y + row * spacing_y
            if y > ramp_clearance_y:
                break

            if row % 2 == 0:
                for col in range(cols_even + 1):
                    x = left_edge + col * spacing_x
                    result.append((x, y))
            else:
                for col in range(cols_even):
                    x = left_edge + spacing_x / 2 + col * spacing_x
                    result.append((x, y))

        return result

    def _advance_shifting_rows(self, dt: float) -> None:
        if not self._peg_rows:
            return

        for row in self._peg_rows:
            wrap_period = max(1e-4, row.wrap_period)
            row.phase = (row.phase + row.speed_x * dt) % wrap_period
            row.body.position = (row.phase, row.y)
            row.body.velocity = (row.speed_x, 0.0)

    def _advance_blinking_pegs(self) -> None:
        if not self.blinking_pegs_enabled or not self._static_pegs:
            return
        if self._sim_time < self._blink_next_switch_at:
            return

        if self._blink_phase_hidden:
            self._blink_phase_hidden = False
            self._blink_hidden_indices = set()
            self._apply_blink_visibility(self._blink_hidden_indices)
            self._blink_next_switch_at = self._sim_time + self._blink_visible_duration
            return

        peg_count = len(self._static_pegs)
        if peg_count <= 0:
            return

        target_hidden = int(round(peg_count * self._blink_hidden_ratio))
        min_hidden = max(1, int(math.floor(peg_count * 0.15)))
        max_hidden = max(min_hidden, int(math.ceil(peg_count * 0.25)))
        hidden_count = max(min_hidden, min(max_hidden, target_hidden))
        hidden_count = min(hidden_count, peg_count)

        picked = self.rng.sample(range(peg_count), hidden_count)
        self._blink_hidden_indices = set(picked)
        self._blink_phase_hidden = True
        self._apply_blink_visibility(self._blink_hidden_indices)
        self._blink_next_switch_at = self._sim_time + self._blink_hidden_duration

    def _apply_blink_visibility(self, hidden_indices: set[int]) -> None:
        if not self._static_pegs:
            return
        for idx, peg in enumerate(self._static_pegs):
            is_visible = idx not in hidden_indices
            peg.is_visible = is_visible
            peg.shape.sensor = not is_visible

    def _build_peg_draw_data(self) -> List[dict]:
        if self.gear_mode_enabled:
            return []
        
        if self._static_pegs:
            return [
                {"x": peg.x, "y": peg.y}
                for peg in self._static_pegs
                if peg.is_visible
            ]

        if not self._peg_rows:
            return [{"x": x, "y": y} for x, y in self._iter_peg_centers()]

        left_visible = float(self.cfg.playfield_left) - float(self.cfg.layout.peg_spacing_x)
        right_visible = float(self.cfg.playfield_right) + float(self.cfg.layout.peg_spacing_x)

        draw_data: List[dict] = []
        for row in self._peg_rows:
            row_shift_x = float(row.body.position.x)
            for peg in row.peg_shapes:
                x = row_shift_x + float(peg.offset.x)
                if left_visible <= x <= right_visible:
                    draw_data.append({"x": x, "y": row.y})

        return draw_data

    def _build_gear_draw_data(self) -> List[dict]:
        if not self.gear_mode_enabled or not self.gears:
            return []

        draw_data = []
        for gear in self.gears:
            draw_data.append({
                "gear_id": gear.gear_id,
                "x": float(gear.body.position.x),
                "y": float(gear.body.position.y),
                "angle": float(gear.body.angle),
                "radius": gear.radius,
                "spoke_count": gear.spoke_count
            })
        return draw_data

    def _register_power_collision_callbacks(self) -> None:
        if hasattr(self.space, "on_collision"):
            self.space.on_collision(
                self.COLLISION_TYPE_BALL,
                self.COLLISION_TYPE_POWER_ZONE,
                begin=self._handle_power_zone_collision,
            )
            return

        handler = self.space.add_collision_handler(
            self.COLLISION_TYPE_BALL,
            self.COLLISION_TYPE_POWER_ZONE,
        )
        handler.begin = self._handle_power_zone_collision

    def _register_spark_collision_callback(self) -> None:
        """Herhangi iki cisim arasındaki çarpışmalarda spark verisi toplar."""
        try:
            if hasattr(self.space, "on_collision"):
                self.space.on_collision(post_solve=self._handle_spark_collision)
                return
            handler = self.space.add_default_collision_handler()
            handler.post_solve = self._handle_spark_collision
        except Exception:
            pass

    def _register_bumper_collision_callback(self) -> None:
        """Bumper'a top çarpınca flash event üretir."""
        try:
            handler = self.space.add_collision_handler(
                self.COLLISION_TYPE_BALL, self.COLLISION_TYPE_BUMPER
            )
            handler.post_solve = self._handle_bumper_collision
        except Exception:
            pass

    def _handle_bumper_collision(self, arbiter, _space=None, _data=None) -> None:
        try:
            impulse_mag = float((arbiter.total_impulse.x**2 + arbiter.total_impulse.y**2)**0.5)
            if impulse_mag < 80.0:
                return
            # Bumper shape'i bul, merkez koordinatını al
            for shape in arbiter.shapes:
                if getattr(shape, "collision_type", 0) == self.COLLISION_TYPE_BUMPER:
                    offset = shape.offset
                    bx = float(shape.body.position.x + offset.x)
                    by = float(shape.body.position.y + offset.y)
                    self._bumper_hits.append({
                        "x": bx, "y": by,
                        "time": float(self._sim_time),
                        "impulse": min(1.0, impulse_mag / 600.0),
                    })
                    break
            # Flash listesini kısa tut
            if len(self._bumper_hits) > 32:
                self._bumper_hits = self._bumper_hits[-24:]
        except Exception:
            pass

    def _handle_spark_collision(self, arbiter, _space=None, _data=None) -> None:
        try:
            shapes = arbiter.shapes
            for shape in shapes:
                if getattr(shape, "collision_type", 0) == self.COLLISION_TYPE_POWER_ZONE:
                    return
            impulse_vec = arbiter.total_impulse
            impulse_mag = float((impulse_vec.x ** 2 + impulse_vec.y ** 2) ** 0.5)
            if impulse_mag < 120.0:
                return
            contact_set = arbiter.contact_point_set
            points = getattr(contact_set, "points", None)
            if not points:
                return
            contact = points[0]
            cx = float(getattr(contact.point_a, "x", 0.0))
            cy = float(getattr(contact.point_a, "y", 0.0))
            normalized = min(1.0, impulse_mag / 900.0)
            self._collision_sparks.append({
                "x": cx,
                "y": cy,
                "impulse": normalized,
                "time": float(self._sim_time),
            })
            if len(self._collision_sparks) > 64:
                self._collision_sparks = self._collision_sparks[-48:]
        except Exception:
            pass

    def get_collision_sparks(self, since: float) -> list[dict]:
        return [dict(s) for s in self._collision_sparks if s.get("time", 0.0) >= since]

    def _build_power_zones(self) -> None:
        if not self.power_zones_enabled:
            return
        self._reposition_power_pegs()

    def _reposition_power_pegs(self) -> None:
        if not self.power_zones_enabled:
            self.power_zones = []
            self._power_zone_by_shape_id.clear()
            self._power_zone_last_trigger_at.clear()
            return

        old_shapes = [zone.shape for zone in self.power_zones if zone.shape in self.space.shapes]
        if old_shapes:
            self.space.remove(*old_shapes)

        self.power_zones = []
        self._power_zone_by_shape_id.clear()
        self._power_zone_last_trigger_at.clear()

        edge_margin = max(
            float(self.cfg.physics.ball_radius * 2 + 24),
            float(self.cfg.physics.peg_radius * 4),
        )
        left_safe = float(self.cfg.playfield_left) + edge_margin
        right_safe = float(self.cfg.playfield_right) - edge_margin
        top_safe = float(self.cfg.layout.peg_top_y + 120)
        bottom_safe = float(self.cfg.layout.floor_y - 560)

        candidates = [
            (float(x), float(y))
            for x, y in self._iter_peg_centers()
            if (left_safe <= x <= right_safe and top_safe <= y <= bottom_safe)
        ]
        if not candidates:
            return

        zone_rng = random.Random()
        selected_positions = self._select_power_zone_positions(
            candidates=candidates,
            target_count=8,
            min_distance=190.0,
            rng=zone_rng,
        )
        if len(selected_positions) < 8:
            return

        zone_types = ["speed_boost"] * 4 + ["slow_zone"] * 4
        zone_rng.shuffle(zone_types)

        static_body = self.space.static_body
        sensor_radius = float(self.cfg.physics.peg_radius + 2)

        for (x, y), zone_type in zip(selected_positions, zone_types):
            shape = pymunk.Circle(static_body, sensor_radius, offset=(x, y))
            shape.sensor = True
            shape.elasticity = 0.0
            shape.friction = 0.0
            shape.collision_type = self.COLLISION_TYPE_POWER_ZONE

            self._power_zone_counter += 1
            zone = PowerZoneDefinition(
                zone_id=self._power_zone_counter,
                zone_type=zone_type,
                x=x,
                y=y,
                radius=sensor_radius,
                shape=shape,
            )
            self.power_zones.append(zone)
            self._power_zone_by_shape_id[id(shape)] = zone
            self.space.add(shape)

    def _select_power_zone_positions(
        self,
        candidates: List[Tuple[float, float]],
        target_count: int,
        min_distance: float,
        rng: random.Random,
    ) -> List[Tuple[float, float]]:
        if not candidates or target_count <= 0:
            return []

        for distance in (min_distance, 175.0, 160.0, 145.0):
            picked: List[Tuple[float, float]] = []
            shuffled = list(candidates)
            rng.shuffle(shuffled)
            for point in shuffled:
                if all(math.hypot(point[0] - other[0], point[1] - other[1]) >= distance for other in picked):
                    picked.append(point)
                    if len(picked) >= target_count:
                        return picked
            if len(picked) >= target_count:
                return picked
        return []

    def _handle_power_zone_collision(self, arbiter: pymunk.Arbiter, _space: pymunk.Space, _data: dict) -> bool:
        ball_shape: Optional[pymunk.Shape] = None
        zone_shape: Optional[pymunk.Shape] = None

        for shape in arbiter.shapes:
            if shape.collision_type == self.COLLISION_TYPE_BALL:
                ball_shape = shape
            elif shape.collision_type == self.COLLISION_TYPE_POWER_ZONE:
                zone_shape = shape

        if ball_shape is None or zone_shape is None:
            return True

        ball = self._get_active_ball_by_shape(ball_shape)
        zone = self._power_zone_by_shape_id.get(id(zone_shape))
        if ball is None or zone is None:
            return True

        global_cooldown = self._ball_power_cooldown_until.get(ball.ball_id, 0.0)
        if self._sim_time < global_cooldown:
            return True

        per_zone_key = (ball.ball_id, zone.zone_id)
        if self._sim_time < self._zone_hit_cooldown_until.get(per_zone_key, 0.0):
            return True

        self._apply_power_peg_effect(ball, zone)
        self._power_zone_last_trigger_at[zone.zone_id] = self._sim_time

        self._ball_power_cooldown_until[ball.ball_id] = self._sim_time + 0.16
        self._zone_hit_cooldown_until[per_zone_key] = self._sim_time + 0.55
        return True

    def _apply_power_peg_effect(self, ball: BallState, zone: PowerZoneDefinition) -> None:
        if zone.zone_type == "speed_boost":
            self._scale_ball_velocity(ball, factor=2.15, min_speed=640.0, max_speed=2800.0)
            ball.body.angular_velocity = self.rng.uniform(-20.0, 20.0)
            return

        if zone.zone_type == "slow_zone":
            self._scale_ball_velocity(ball, factor=0.18, min_speed=26.0, max_speed=320.0)
            return

    def _scale_ball_velocity(self, ball: BallState, factor: float, min_speed: float, max_speed: float) -> None:
        vx = float(ball.body.velocity.x) * factor
        vy = float(ball.body.velocity.y) * factor
        speed = math.hypot(vx, vy)

        if speed <= 1e-4:
            vx = self.rng.uniform(-120.0, 120.0)
            vy = min_speed
            speed = math.hypot(vx, vy)

        if speed < min_speed:
            scale = min_speed / max(1e-4, speed)
            vx *= scale
            vy *= scale
            speed = min_speed

        if speed > max_speed:
            scale = max_speed / speed
            vx *= scale
            vy *= scale

        ball.body.velocity = (vx, vy)

    def _expire_power_effect_cooldowns(self) -> None:
        if not self.power_zones_enabled:
            return
        self._ball_power_cooldown_until = {
            ball_id: until
            for ball_id, until in self._ball_power_cooldown_until.items()
            if until > self._sim_time
        }
        self._zone_hit_cooldown_until = {
            key: until
            for key, until in self._zone_hit_cooldown_until.items()
            if until > self._sim_time
        }

    def _build_power_zone_draw_data(self) -> List[dict]:
        if not self.power_zones_enabled:
            return []

        draw_data: List[dict] = []
        for zone in self.power_zones:
            pulse = 0.5 + 0.5 * math.sin(self._sim_time * 4.2 + zone.zone_id * 0.73)
            last_hit = self._power_zone_last_trigger_at.get(zone.zone_id, -999.0)
            hot_ratio = max(0.0, 1.0 - (self._sim_time - last_hit) / 0.40)
            draw_data.append(
                {
                    "zone_id": zone.zone_id,
                    "zone_type": zone.zone_type,
                    "x": zone.x,
                    "y": zone.y,
                    "radius": zone.radius,
                    "pulse": pulse,
                    "hot_ratio": hot_ratio,
                }
            )
        return draw_data

    def _get_active_ball_by_shape(self, shape: pymunk.Shape) -> Optional[BallState]:
        ball_id = self._ball_shape_id_to_ball_id.get(id(shape))
        if ball_id is None:
            return None
        return next((ball for ball in self.active_balls if ball.ball_id == ball_id), None)
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
            label=self.left_gap_label,
            start_x=left_start,
            end_x=left_start + side_gap_w,
        )

        center_gap = GapDefinition(
            label=self.center_gap_label,
            start_x=left_gap.end_x + divider_w,
            end_x=left_gap.end_x + divider_w + goal_gap_w,
        )

        right_gap = GapDefinition(
            label=self.right_gap_label,
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
        if self.power_zones_enabled:
            self._reposition_power_pegs()

        self._spawn_ball_for_team(self.team_a, self.team_a_key)
        self._pending_b_timer = 0.4

    def _spawn_ball_for_team(self, team: TeamRecord, team_key: str) -> None:
        radius = self.cfg.physics.ball_radius
        mass = self.cfg.physics.ball_mass
        moment = pymunk.moment_for_circle(mass, 0, radius)

        body = pymunk.Body(mass, moment)

        left_bound = self.cfg.playfield_left + radius + 20
        right_bound = self.cfg.playfield_right - radius - 20

        spawn_x = self._guided_spawn_x(
            team_key=team_key,
            left_bound=left_bound,
            right_bound=right_bound,
        )

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
        shape.collision_type = self.COLLISION_TYPE_BALL

        self.space.add(body, shape)

        self._ball_counter += 1
        ball_state = BallState(
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
        self.active_balls.append(ball_state)
        self._ball_shape_id_to_ball_id[id(shape)] = ball_state.ball_id

    def _guided_spawn_x(self, team_key: str, left_bound: float, right_bound: float) -> float:
        random_x = self.rng.uniform(left_bound, right_bound)
        if not self.guided_mode_enabled:
            return random_x
        if self.guided_target_score_a is None or self.guided_target_score_b is None:
            return random_x

        if team_key == self.team_a_key:
            target_team = self.guided_target_score_a
            score_team = int(self.scores.get(self.team_a_key, 0))
        elif team_key == self.team_b_key:
            target_team = self.guided_target_score_b
            score_team = int(self.scores.get(self.team_b_key, 0))
        else:
            return random_x

        remaining_team = max(0, target_team - score_team)
        sim_window = max(10.0, self.cfg.video.total_duration_seconds - 4.0)
        progress = max(0.0, min(1.0, self._sim_time / sim_window))
        center_x = float(self.cfg.playfield_center_x)
        goal_half = max(24.0, float(self.cfg.layout.goal_gap_width) / 2.0)
        if remaining_team <= 0:
            # Hedefini dolduran takim icin spawn'i merkezin disina it,
            # ama tamamen script gibi olmasin.
            side_sign = -1.0 if random_x < center_x else 1.0
            side_target = center_x + side_sign * goal_half * 3.35
            side_target = max(left_bound, min(right_bound, side_target))
            strength = min(0.96, 0.76 + 0.20 * progress)
            return random_x * (1.0 - strength) + side_target * strength

        sigma = max(18.0, goal_half * (1.12 - 0.66 * progress))
        guided_center = center_x + self.rng.uniform(-goal_half * 0.22, goal_half * 0.22)
        guided_x = max(left_bound, min(right_bound, self.rng.gauss(guided_center, sigma)))

        strength = min(0.94, 0.30 + 0.54 * progress + 0.12 * remaining_team)
        return random_x * (1.0 - strength) + guided_x * strength

    def _guided_remaining_goals(self, team_key: str) -> int:
        if self.guided_target_score_a is None or self.guided_target_score_b is None:
            return 0
        if team_key == self.team_a_key:
            return max(0, int(self.guided_target_score_a) - int(self.scores.get(self.team_a_key, 0)))
        if team_key == self.team_b_key:
            return max(0, int(self.guided_target_score_b) - int(self.scores.get(self.team_b_key, 0)))
        return 0

    def _apply_guided_live_ball_bias(self, dt: float) -> None:
        if not self.guided_mode_enabled:
            return
        if self.guided_target_score_a is None or self.guided_target_score_b is None:
            return
        if not self.active_balls:
            return

        center_x = float(self.cfg.playfield_center_x)
        sim_window = max(10.0, self.cfg.video.total_duration_seconds - 4.0)
        progress = max(0.0, min(1.0, self._sim_time / sim_window))
        urgency = progress ** 1.35

        rem_a = max(0, int(self.guided_target_score_a) - int(self.scores.get(self.team_a_key, 0)))
        rem_b = max(0, int(self.guided_target_score_b) - int(self.scores.get(self.team_b_key, 0)))

        for ball in self.active_balls:
            x = float(ball.body.position.x)
            vx = float(ball.body.velocity.x)
            y = float(ball.body.position.y)

            if ball.team_key == self.team_a_key:
                rem_team = rem_a
                rem_other = rem_b
            elif ball.team_key == self.team_b_key:
                rem_team = rem_b
                rem_other = rem_a
            else:
                continue

            # Asagi indikce bias biraz artsin.
            y_factor = max(0.0, min(1.0, (y - self.cfg.layout.peg_top_y) / max(1.0, self.cfg.layout.exit_line_y - self.cfg.layout.peg_top_y)))
            base = 120.0 + 210.0 * urgency + 120.0 * y_factor
            nudge = self.rng.uniform(-28.0, 28.0)

            if rem_team <= 0:
                # Hedefini dolduran takimi merkezden uzak tut.
                if abs(x - center_x) < 1.0:
                    direction = -1.0 if self.rng.random() < 0.5 else 1.0
                else:
                    direction = -1.0 if x < center_x else 1.0
                force_x = direction * (base * 1.45 + nudge)
            elif rem_other <= 0:
                # Rakip dolduysa bu takimi merkeze hafif cek.
                direction = 1.0 if x < center_x else -1.0
                force_x = direction * (base * 0.92 + nudge)
            else:
                # Ikisi de hedefte degilse, daha cok gole ihtiyaci olana merkez avantaji.
                if rem_team > rem_other:
                    direction = 1.0 if x < center_x else -1.0
                    force_x = direction * (base * 0.62 + nudge)
                else:
                    force_x = nudge * 0.28

            new_vx = vx + force_x * dt
            new_vx = max(-520.0, min(520.0, new_vx))
            ball.body.velocity = (new_vx, float(ball.body.velocity.y))

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
                result_label = self._classify_gap_by_x(
                    x_at_exit,
                    ball_radius=float(ball.shape.radius),
                )
                result_label = self._apply_guided_result_bias(
                    ball=ball,
                    current_label=result_label,
                    x_at_exit=x_at_exit,
                )

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

                if result_label == self.center_gap_label and not self.var_mode_enabled:
                    self.scores[ball.team_key] += 1

                balls_to_remove.append(ball)

        for ball in balls_to_remove:
            self._remove_ball(ball)

        if not self.active_balls and self.current_round > self.completed_rounds:
            self.completed_rounds = self.current_round

    def register_confirmed_goal(self, team_key: str) -> None:
        if team_key not in self.scores:
            return
        self.scores[team_key] += 1

    def _apply_guided_result_bias(self, ball: BallState, current_label: str, x_at_exit: float) -> str:
        if not self.guided_mode_enabled:
            return current_label
        if self.guided_target_score_a is None or self.guided_target_score_b is None:
            return current_label

        if ball.team_key == self.team_a_key:
            target_team = self.guided_target_score_a
            target_other = self.guided_target_score_b
            score_team = int(self.scores.get(self.team_a_key, 0))
            score_other = int(self.scores.get(self.team_b_key, 0))
        elif ball.team_key == self.team_b_key:
            target_team = self.guided_target_score_b
            target_other = self.guided_target_score_a
            score_team = int(self.scores.get(self.team_b_key, 0))
            score_other = int(self.scores.get(self.team_a_key, 0))
        else:
            return current_label

        remaining_team = max(0, target_team - score_team)
        remaining_other = max(0, target_other - score_other)
        sim_window = max(10.0, self.cfg.video.total_duration_seconds - 4.0)
        progress = max(0.0, min(1.0, self._sim_time / sim_window))
        urgency = progress ** 1.6

        center_x = float(self.cfg.playfield_center_x)
        goal_half = max(22.0, float(self.cfg.layout.goal_gap_width) / 2.0)
        dist_to_center = abs(x_at_exit - center_x)
        near_center_limit = goal_half * (0.78 + 0.95 * urgency)
        near_center = dist_to_center <= near_center_limit

        if current_label == self.center_gap_label:
            # Gercekten GOAL'e dusen top her zaman GOAL sayilir.
            return current_label

        # Gol disi cikislar: lagging tarafi merkeze yakin misslerde destekle.
        if remaining_team <= 0:
            return current_label

        if not near_center:
            far_from_center = dist_to_center > near_center_limit * 1.35
            if far_from_center or urgency < 0.95:
                return current_label

        # Son bolumde, hedefe kalan taraf icin merkeze yakin misslerde
        # boost ver ama yine olasilikla (zorla gol yazma yok).
        if progress >= 0.82 and near_center:
            late_boost = 0.24
        else:
            late_boost = 0.0

        if not near_center and urgency < 0.92:
            return current_label

        total_target = max(1, target_team + target_other)
        expected_share = target_team / total_target
        actual_share = (score_team + 0.5) / max(1.0, score_team + score_other + 1.0)
        lag_factor = max(0.0, expected_share - actual_share)

        boost_prob = 0.24 + 0.50 * urgency + 0.65 * lag_factor + late_boost
        if remaining_other <= 0:
            boost_prob += 0.18
        if remaining_team > remaining_other:
            boost_prob += 0.08
        if remaining_team >= 2:
            boost_prob += 0.10
        boost_prob = min(0.94, boost_prob)

        if self.rng.random() < boost_prob:
            return self.center_gap_label
        return current_label

    def _resolve_stuck_balls(self, dt: float) -> None:
        center_x = self.cfg.playfield_center_x

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

    def _classify_gap_by_x(self, x_pos: float, ball_radius: float = 0.0) -> str:
        # Topun bir kismi bir gap ustundeyse, merkez noktasi divider'da kalsa bile
        # gozle gorulen sonucu yansitmak icin overlap'e gore siniflandir.
        if ball_radius > 0.0:
            coverage_half = max(4.0, ball_radius * 0.60)
            left_edge = x_pos - coverage_half
            right_edge = x_pos + coverage_half
            best_overlap = 0.0
            best_label: str | None = None

            for gap in self.gaps:
                overlap = min(right_edge, gap.end_x) - max(left_edge, gap.start_x)
                if overlap > best_overlap:
                    best_overlap = overlap
                    best_label = gap.label

            required_overlap = max(6.0, (right_edge - left_edge) * 0.20)
            if best_label is not None and best_overlap >= required_overlap:
                return best_label

        for gap in self.gaps:
            if gap.start_x <= x_pos <= gap.end_x:
                return gap.label

        # Hiçbir gap'e net girmediyse (divider veya sinir), en yakin gap'e ver.
        nearest_gap = min(self.gaps, key=lambda gap: abs(x_pos - gap.center_x))
        return nearest_gap.label

    def _remove_ball(self, ball: BallState) -> None:
        if ball.shape in self.space.shapes and ball.body in self.space.bodies:
            self.space.remove(ball.body, ball.shape)

        self._ball_shape_id_to_ball_id.pop(id(ball.shape), None)
        self._ball_power_cooldown_until.pop(ball.ball_id, None)
        self._zone_hit_cooldown_until = {
            key: until
            for key, until in self._zone_hit_cooldown_until.items()
            if key[0] != ball.ball_id
        }
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



