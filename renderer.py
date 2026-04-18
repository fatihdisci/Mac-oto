from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

import pygame
from PIL import Image, ImageFilter

from config import SimulationConfig, get_arena_theme


@dataclass
class ConfettiParticle:
    x: float
    y: float
    vx: float
    vy: float
    color: Tuple[int, int, int]
    size: float
    lifetime: float
    age: float = 0.0
    angle: float = 0.0
    angular_vel: float = 0.0


class MarbleRaceRenderer:
    def __init__(self, cfg: SimulationConfig) -> None:
        self.cfg = cfg

        pygame.font.init()

        self.title_font = pygame.font.SysFont("arial", 30, bold=True)
        self.match_font = pygame.font.SysFont("arial", 32, bold=True)
        self.score_font = pygame.font.SysFont("arial", 72, bold=True)
        self.team_font = pygame.font.SysFont("arial", 26, bold=True)
        self.info_font = pygame.font.SysFont("arial", 28, bold=False)
        self.micro_font = pygame.font.SysFont("arial", 20, bold=True)
        self.bottom_font = pygame.font.SysFont("arial", cfg.hud.bottom_label_font_size, bold=True)
        self.clock_font = pygame.font.SysFont("arial", 52, bold=True)
        self.overlay_font = pygame.font.SysFont("arial", 84, bold=True)
        self.overlay_sub_font = pygame.font.SysFont("arial", 52, bold=True)
        self.goal_font = pygame.font.SysFont("arial", 98, bold=True)
        self.goal_sub_font = pygame.font.SysFont("arial", 34, bold=True)
        self.hook_font = pygame.font.SysFont("arial", 78, bold=True)
        self.hook_sub_font = pygame.font.SysFont("arial", 42, bold=True)
        self.hook_mega_font = pygame.font.SysFont("arial", 108, bold=True)
        self.hook_team_font = pygame.font.SysFont("arial", 52, bold=True)
        self.hook_vs_font = pygame.font.SysFont("arial", 68, bold=True)
        self.result_font = pygame.font.SysFont("arial", 88, bold=True)
        self.result_team_font = pygame.font.SysFont("arial", 36, bold=True)

        self.logo_base_surfaces: Dict[str, pygame.Surface] = {}
        self._seen_event_keys: set[tuple] = set()
        self.goal_flash_timer: float = 0.0
        self.goal_flash_event: dict | None = None
        self.confetti_particles: List[ConfettiParticle] = []
        self._confetti_rng = random.Random()
        self._hook_sparks: List[dict] = []
        self._hook_sparks_ready = False
        self._win_rate_rail_probs: Tuple[float, float, float] = (0.34, 0.32, 0.34)
        self._impact_particles: List[dict] = []
        self._spawned_spark_keys: set[tuple] = set()

        self.static_background: pygame.Surface | None = None
        self._background_mode_key: str = ""

    def draw(
        self,
        target_surface: pygame.Surface,
        state_snapshot: dict,
        active_ball_draw_data: List[dict],
    ) -> None:
        self._ensure_static_background(state_snapshot)
        self._update_dynamic_effects(state_snapshot)
        if self.static_background is not None:
            target_surface.blit(self.static_background, (0, 0))
        self._draw_pegs(target_surface, state_snapshot)
        self._draw_gears(target_surface, state_snapshot)
        self._draw_power_zones(target_surface, state_snapshot)

        self._draw_header(target_surface, state_snapshot)
        self._draw_scoreboard(target_surface, state_snapshot)

        for ball in active_ball_draw_data:
            self._draw_ball(target_surface, ball)

        self._draw_confetti(target_surface, 1.0 / self.cfg.video.fps)
        self._update_impact_particles(state_snapshot, 1.0 / self.cfg.video.fps)
        self._draw_impact_particles(target_surface)
        self._draw_goal_flash(target_surface)
        self._draw_tension_overlay(target_surface, state_snapshot)
        self._draw_var_review_overlay(target_surface, state_snapshot)
        self._draw_penalty_overlay(target_surface, state_snapshot)

        if state_snapshot.get("show_hook_overlay", False):
            self._draw_hook_overlay(target_surface, state_snapshot)

        if state_snapshot.get("show_final_result_overlay", False):
            self._draw_finish_overlay(target_surface, state_snapshot)

    def _ensure_static_background(self, snapshot: dict) -> None:
        theme_key = str(snapshot.get("arena_theme", "default")).strip() or "default"
        
        if self.static_background is not None and getattr(self, "_background_mode_key", None) == theme_key:
            return

        self.static_background = self._build_static_background(theme_key=theme_key)
        self._background_mode_key = theme_key

    def _draw_header(self, surface: pygame.Surface, snapshot: dict) -> None:
        cx = self.cfg.video.width // 2
        panel_w = 480
        panel_h = 52
        panel_x = cx - panel_w // 2
        panel_y = 28

        self._draw_glass_panel(
            surface,
            pygame.Rect(panel_x, panel_y, panel_w, panel_h),
            (9, 14, 22, 180),
            (60, 78, 114, 200),
            26,
        )

        # Dinamik başlık
        raw_title = snapshot.get("title")
        if not raw_title or str(raw_title).strip() == "":
            title_text = "FOOTBALL RACE"
        else:
            title_text = str(raw_title).upper()
            
        title = self.title_font.render(title_text, True, (200, 208, 224))
        title_rect = title.get_rect(center=(cx, panel_y + panel_h // 2))
        surface.blit(title, title_rect)

    def _build_static_background(self, theme_key: str = "default") -> pygame.Surface:
        theme = get_arena_theme(theme_key)
        width = self.cfg.video.width
        height = self.cfg.video.height

        background = pygame.Surface((width, height))
        background.fill(theme["bg"])

        self._draw_field_panel(background, theme)
        self._draw_side_walls(background, theme)
        self._draw_bottom_layout(background)

        return background

    def _draw_field_panel(self, surface: pygame.Surface, theme: dict) -> None:
        field_rect = pygame.Rect(
            self.cfg.playfield_left - 18,
            108,
            self.cfg.playfield_width + 36,
            self.cfg.video.height - 192,
        )
        pygame.draw.rect(surface, theme["field"], field_rect, border_radius=28)
        pygame.draw.rect(surface, theme["border"], field_rect, width=2, border_radius=28)

    def _draw_side_walls(self, surface: pygame.Surface, theme: dict) -> None:
        left_x = self.cfg.playfield_left
        right_x = self.cfg.playfield_right
        wall_top = 120
        ramp_top_y = self.cfg.layout.floor_y - 180

        pygame.draw.line(surface, theme["wall"], (left_x, wall_top), (left_x, ramp_top_y), 6)
        pygame.draw.line(surface, theme["wall"], (right_x, wall_top), (right_x, ramp_top_y), 6)

    def _draw_pegs(self, surface: pygame.Surface, snapshot: Optional[dict] = None) -> None:
        left = self.cfg.playfield_left
        right = self.cfg.playfield_right
        clip_rect = pygame.Rect(left, 0, right - left, self.cfg.video.height)
        surface.set_clip(clip_rect)

        theme_key = str(snapshot.get("arena_theme", "default")).strip() or "default" if snapshot else "default"
        theme = get_arena_theme(theme_key)

        peg_draw_data = snapshot.get("peg_draw_data", []) if snapshot else []
        gear_draw_data = snapshot.get("gear_draw_data", []) if snapshot else []
        
        # Eğer Gear Mode aktifse (gear_draw_data doluysa), pegleri hiç çizme.
        # Eğer Gear Mode değilse ama peg_draw_data boşsa (eski snapshotlar için), fallback yap.
        if gear_draw_data:
            peg_centers = []
        elif peg_draw_data:
            peg_centers = [
                (float(peg.get("x", 0.0)), float(peg.get("y", 0.0)))
                for peg in peg_draw_data
            ]
        else:
            peg_centers = list(self._iter_peg_centers())

        if not peg_centers:
            surface.set_clip(None)
            return

        tension_active = bool(snapshot.get("tension_active", False)) if snapshot else False
        tension_progress = float(snapshot.get("tension_progress", 0.0)) if snapshot else 0.0
        sim_time = float(snapshot.get("physics_sim_time", 0.0)) if snapshot else 0.0
        vib_amp = self.cfg.tension.peg_vibrate_amplitude * max(0.0, min(1.0, tension_progress))
        vib_speed = self.cfg.tension.peg_vibrate_speed

        for x, y in peg_centers:
            if not (left <= x <= right):
                continue
            if tension_active and vib_amp > 0.05:
                vib_x = math.sin(sim_time * vib_speed + x * 0.1) * vib_amp
                vib_y = math.cos(sim_time * (vib_speed + 4.0) + y * 0.1) * vib_amp * 0.6
                dx, dy = int(x + vib_x), int(y + vib_y)
            else:
                dx, dy = int(x), int(y)
            pygame.draw.circle(surface, theme["peg_sh"], (dx + 3, dy + 4), self.cfg.physics.peg_radius)
            pygame.draw.circle(surface, theme["peg"], (dx, dy), self.cfg.physics.peg_radius)
            pygame.draw.circle(
                surface,
                (228, 232, 240),
                (dx - 2, dy - 2),
                max(2, self.cfg.physics.peg_radius // 3),
            )

        surface.set_clip(None)

    def _draw_gears(self, surface: pygame.Surface, snapshot: dict) -> None:
        gears = snapshot.get("gear_draw_data", [])
        if not gears:
            return

        left = self.cfg.playfield_left
        right = self.cfg.playfield_right
        clip_rect = pygame.Rect(left, 0, right - left, self.cfg.video.height)
        surface.set_clip(clip_rect)

        theme_key = str(snapshot.get("arena_theme", "default")).strip() or "default"
        theme = get_arena_theme(theme_key)

        hub_color = theme["peg"]
        hub_sh_color = theme["peg_sh"]
        # Kollar biraz daha açık
        spoke_color = tuple(min(255, max(0, c + 30)) for c in hub_color)
        rim_color = tuple(min(255, max(0, c + 15)) for c in hub_color)

        for gear in gears:
            gx = float(gear["x"])
            gy = float(gear["y"])
            angle = float(gear["angle"])
            radius = float(gear["radius"])
            spokes = int(gear["spoke_count"])

            igx, igy = int(gx), int(gy)

            # Kol kalınlığı radius'a göre
            sw = max(3, int(radius * 0.045))   # ~4-5px

            # Kollar: merkezden uca (gölge + ana)
            for s in range(spokes):
                s_angle = angle + (s / spokes) * math.tau
                end_x = gx + radius * math.cos(s_angle)
                end_y = gy + radius * math.sin(s_angle)
                pygame.draw.line(surface, hub_sh_color,
                                 (igx + 2, igy + 2), (int(end_x) + 2, int(end_y) + 2), sw + 2)
                pygame.draw.line(surface, spoke_color,
                                 (igx, igy), (int(end_x), int(end_y)), sw)

            # Merkez nokta
            pygame.draw.circle(surface, hub_sh_color, (igx + 1, igy + 1), 6)
            pygame.draw.circle(surface, hub_color, (igx, igy), 5)
            pygame.draw.circle(surface, (220, 230, 245), (igx - 1, igy - 1), 2)

        # Bumper çivileri — hit zamanına göre flash
        bumpers = snapshot.get("gear_bumpers", [])
        hits = snapshot.get("gear_bumper_hits", [])
        sim_time = float(snapshot.get("physics_time_seconds", 0.0))
        # Son hit'leri konuma göre indexle
        hit_map: dict[tuple, float] = {}
        for h in hits:
            key = (round(h["x"]), round(h["y"]))
            t = float(h.get("time", 0.0))
            if key not in hit_map or hit_map[key] < t:
                hit_map[key] = t

        for b in bumpers:
            bx, by, br = int(b["x"]), int(b["y"]), int(b["r"])
            is_special = b.get("high_bounce", False)
            key = (bx, by)
            last_hit = hit_map.get(key, -999.0)
            age = sim_time - last_hit
            flash = age < 0.12

            if is_special:
                # Özel çivi: Neon Turuncu/Sarı ve Glow
                base_color = (255, 140, 0)
                pulse = 0.5 + 0.5 * math.sin(sim_time * 8.0)
                glow_r = br + 4 + int(6 * pulse)
                
                # Sabit Glow
                glow_surf = pygame.Surface((glow_r * 2, glow_r * 2), pygame.SRCALPHA)
                pygame.draw.circle(glow_surf, (255, 180, 0, int(60 + 40 * pulse)), (glow_r, glow_r), glow_r)
                surface.blit(glow_surf, glow_surf.get_rect(center=(bx, by)))

                if flash:
                    flash_t = 1.0 - (age / 0.12)
                    fc = int(255 * flash_t)
                    # Çok daha şiddetli beyaz/turuncu parlama
                    pygame.draw.circle(surface, (255, 255, 200), (bx, by), br + 2)
                    ring_r = br + int((0.12 - age) / 0.12 * 45) # Daha büyük halka
                    pygame.draw.circle(surface, (255, 200, 50), (bx, by), ring_r, 4)
                else:
                    pygame.draw.circle(surface, (40, 20, 0), (bx + 2, by + 2), br) # Gölge
                    pygame.draw.circle(surface, base_color, (bx, by), br)
                    pygame.draw.circle(surface, (255, 230, 150), (bx - 2, by - 2), br // 2) # Parlama noktası
            else:
                # Normal Bumper
                if flash:
                    flash_t = 1.0 - (age / 0.12)
                    fc = int(255 * flash_t)
                    flash_color = (min(255, 180 + fc), min(255, 160 + fc), 60)
                    pygame.draw.circle(surface, flash_color, (bx, by), br)
                    ring_r = br + int((0.12 - age) / 0.12 * 22)
                    pygame.draw.circle(surface, (255, 220, 80), (bx, by), ring_r, 3)
                else:
                    pygame.draw.circle(surface, hub_sh_color, (bx + 2, by + 2), br)
                    pygame.draw.circle(surface, spoke_color,  (bx,     by    ), br)
                    pygame.draw.circle(surface, (220, 230, 245), (bx - 2, by - 2), max(2, br // 3))

        surface.set_clip(None)

    def _draw_power_zones(self, surface: pygame.Surface, snapshot: dict) -> None:
        zones = snapshot.get("power_zone_draw_data", [])
        if not zones:
            return

        left = self.cfg.playfield_left
        right = self.cfg.playfield_right
        clip_rect = pygame.Rect(left, 0, right - left, self.cfg.video.height)
        surface.set_clip(clip_rect)

        glow_layer = pygame.Surface(surface.get_size(), pygame.SRCALPHA)
        for zone in zones:
            x = int(zone.get("x", 0))
            y = int(zone.get("y", 0))
            radius = max(8, int(zone.get("radius", 24)))
            pulse = float(zone.get("pulse", 0.5))
            hot_ratio = float(zone.get("hot_ratio", 0.0))
            zone_type = str(zone.get("zone_type", "speed_boost"))
            palette = self._power_zone_palette(zone_type)

            pulse_ring = int(radius + 10 + pulse * 13)
            glow_alpha = int(38 + pulse * 58 + hot_ratio * 95)
            ring_alpha = int(165 + pulse * 88 + hot_ratio * 28)

            pygame.draw.circle(glow_layer, (*palette["glow"], min(255, glow_alpha)), (x, y), pulse_ring + 12)
            pygame.draw.circle(glow_layer, (*palette["ring"], min(255, ring_alpha)), (x, y), pulse_ring, width=3)

            pygame.draw.circle(surface, (12, 16, 24), (x + 2, y + 3), radius)
            pygame.draw.circle(surface, palette["fill"], (x, y), radius)
            pygame.draw.circle(surface, palette["ring"], (x, y), radius, width=3)

        surface.blit(glow_layer, (0, 0))
        surface.set_clip(None)

    def _power_zone_palette(self, zone_type: str) -> Dict[str, Tuple[int, int, int]]:
        palettes: Dict[str, Dict[str, Tuple[int, int, int]]] = {
            "speed_boost": {"fill": (52, 162, 98), "ring": (112, 242, 158), "glow": (78, 214, 132), "text": (235, 255, 242)},
            "slow_zone": {"fill": (168, 54, 62), "ring": (248, 108, 118), "glow": (236, 92, 104), "text": (255, 236, 236)},
        }
        return palettes.get(zone_type, palettes["speed_boost"])

    def _draw_bottom_layout(self, surface: pygame.Surface) -> None:
        floor_y = self.cfg.layout.floor_y
        post_h = self.cfg.layout.gap_post_height
        ramp_rise = 180
        divider_peak_rise = max(20, int(self.cfg.physics.ball_radius * 0.8))

        gaps = self._build_gap_draw_data_from_cfg()
        left_gap, center_gap, right_gap = gaps

        left_divider_peak_x = (left_gap["end_x"] + center_gap["start_x"]) / 2.0
        right_divider_peak_x = (center_gap["end_x"] + right_gap["start_x"]) / 2.0

        left_edge = self.cfg.playfield_left
        right_edge = self.cfg.playfield_right

        floor_color = (155, 168, 190)
        post_color = (130, 142, 164)

        segments = [
            ((left_edge, floor_y - ramp_rise), (left_gap["start_x"], floor_y)),
            ((left_gap["end_x"], floor_y), (left_divider_peak_x, floor_y - divider_peak_rise)),
            ((left_divider_peak_x, floor_y - divider_peak_rise), (center_gap["start_x"], floor_y)),
            ((center_gap["end_x"], floor_y), (right_divider_peak_x, floor_y - divider_peak_rise)),
            ((right_divider_peak_x, floor_y - divider_peak_rise), (right_gap["start_x"], floor_y)),
            ((right_gap["end_x"], floor_y), (right_edge, floor_y - ramp_rise)),
        ]
        for a, b in segments:
            pygame.draw.line(surface, floor_color, a, b, 8)

        post_x_positions = [
            left_gap["start_x"],
            left_gap["end_x"],
            center_gap["start_x"],
            center_gap["end_x"],
            right_gap["start_x"],
            right_gap["end_x"],
        ]
        for x in post_x_positions:
            pygame.draw.line(surface, post_color, (x, floor_y), (x, floor_y + post_h), 8)

        self._draw_gap_zone(surface, left_gap, (235, 181, 77, 38))
        self._draw_gap_zone(surface, center_gap, (73, 201, 126, 58))
        self._draw_gap_zone(surface, right_gap, (214, 90, 90, 42))

        for gap in gaps:
            label_color = (236, 236, 240)
            if gap["label"] == "GOAL":
                label_color = (120, 235, 155)

            text = self.bottom_font.render(gap["label"], True, label_color)
            text_rect = text.get_rect(center=(gap["center_x"], floor_y + 46))
            surface.blit(text, text_rect)

    def _draw_gap_zone(self, surface: pygame.Surface, gap: dict, rgba: Tuple[int, int, int, int]) -> None:
        zone_w = int(gap["end_x"] - gap["start_x"])
        zone_h = 112
        zone = pygame.Surface((zone_w, zone_h), pygame.SRCALPHA)
        zone.fill(rgba)
        surface.blit(zone, (int(gap["start_x"]), self.cfg.layout.floor_y))

    def _draw_scoreboard(self, surface: pygame.Surface, snapshot: dict) -> None:
        self._draw_football_scoreboard(surface, snapshot)

    def _draw_football_scoreboard(self, surface: pygame.Surface, snapshot: dict) -> None:
        teams = snapshot.get("teams", [])
        if len(teams) < 2:
            return

        team_a = next((team for team in teams if team.get("role") == "A"), teams[0])
        team_b = next((team for team in teams if team.get("role") == "B"), teams[1])

        cx = self.cfg.video.width // 2
        match_clock_text = snapshot.get("match_clock_text", "00:00")
        progress_ratio = float(snapshot.get("match_progress_ratio", 0.0))
        show_full_time = bool(snapshot.get("show_final_result_overlay", False))
        match_phase = str(snapshot.get("match_phase", "regular_time"))
        knockout_decided_by = str(snapshot.get("knockout_decided_by", "normal_time"))

        # --- Ana skor paneli ---
        panel_w = 940
        panel_h = 230
        panel_x = cx - panel_w // 2
        panel_y = 94

        self._draw_glass_panel(
            surface,
            pygame.Rect(panel_x, panel_y, panel_w, panel_h),
            (10, 16, 26, 195),
            (55, 70, 105, 210),
            30,
        )

        # --- Takım A (sol - logo ve isim ortaya dogru) ---
        logo_size = 92
        logo_a = self._get_logo_surface(team_a["name"], team_a.get("badge_file", ""), logo_size)
        # Logo: skor alaninin hemen solunda, ortaya yakin
        logo_a_cx = cx - 195
        logo_a_cy = panel_y + 58
        surface.blit(logo_a, logo_a.get_rect(center=(logo_a_cx, logo_a_cy)))

        name_a = self._display_score_team_name(team_a)
        name_a_surf = self._fit_text(self.match_font, name_a, 240, (235, 240, 250))
        name_a_rect = name_a_surf.get_rect(center=(logo_a_cx, logo_a_cy + logo_size // 2 + 22))
        surface.blit(name_a_surf, name_a_rect)

        # --- Takım B (sag - logo ve isim ortaya dogru) ---
        logo_b = self._get_logo_surface(team_b["name"], team_b.get("badge_file", ""), logo_size)
        logo_b_cx = cx + 195
        logo_b_cy = panel_y + 58
        surface.blit(logo_b, logo_b.get_rect(center=(logo_b_cx, logo_b_cy)))

        name_b = self._display_score_team_name(team_b)
        name_b_surf = self._fit_text(self.match_font, name_b, 240, (235, 240, 250))
        name_b_rect = name_b_surf.get_rect(center=(logo_b_cx, logo_b_cy + logo_size // 2 + 22))
        surface.blit(name_b_surf, name_b_rect)

        # --- Skor (ortada buyuk) ---
        score_str = f"{team_a['score']}  -  {team_b['score']}"
        score_surf = self.score_font.render(score_str, True, (248, 248, 252))
        score_rect = score_surf.get_rect(center=(cx, panel_y + 52))
        surface.blit(score_surf, score_rect)

        # --- Saat (skor altinda) ---
        clock_surf = self.clock_font.render(match_clock_text, True, (240, 242, 248))
        clock_rect = clock_surf.get_rect(center=(cx, panel_y + 128))
        surface.blit(clock_surf, clock_rect)

        # --- LIVE chip + Half (saat altinda yan yana, buyuk) ---
        live_font = self.team_font
        live_chip = live_font.render("LIVE", True, (255, 255, 255))
        live_y = panel_y + 192
        chip_bg = pygame.Rect(0, 0, live_chip.get_width() + 28, 34)
        chip_bg.center = (cx - 72, live_y)
        pygame.draw.rect(surface, (194, 36, 61), chip_bg, border_radius=17)
        surface.blit(live_chip, live_chip.get_rect(center=chip_bg.center))

        if show_full_time:
            if knockout_decided_by == "penalties":
                phase_text = "FULL TIME (PEN)"
            elif knockout_decided_by == "extra_time":
                phase_text = "FULL TIME (AET)"
            else:
                phase_text = "FULL TIME"
            phase_color = (255, 227, 120)
        elif match_phase == "extra_time":
            phase_text = "EXTRA TIME"
            phase_color = (255, 210, 120)
        elif match_phase == "penalties":
            phase_text = "PENALTIES"
            phase_color = (255, 196, 128)
        else:
            phase_text = "1ST HALF" if progress_ratio < 0.5 else "2ND HALF"
            phase_color = (175, 185, 205)

        phase_surf = live_font.render(phase_text, True, phase_color)
        surface.blit(phase_surf, phase_surf.get_rect(center=(cx + 62, live_y)))
        self._draw_win_rate_rail(
            surface=surface,
            snapshot=snapshot,
            x=panel_x + 24,
            y=panel_y + panel_h + 10,
            width=panel_w - 48,
        )



    def _draw_win_odds_strip(
        self,
        surface: pygame.Surface,
        snapshot: dict,
        team_a: dict,
        team_b: dict,
        x: int,
        y: int,
        width: int,
        pop_mode: bool,
    ) -> None:
        odds = snapshot.get("win_probabilities")
        if not isinstance(odds, dict):
            return

        try:
            p_a = float(odds.get("team_a", 0.0))
            p_d = float(odds.get("draw", 0.0))
            p_b = float(odds.get("team_b", 0.0))
        except (TypeError, ValueError):
            return

        p_a, p_d, p_b = self._normalize_triplet(p_a, p_d, p_b)
        a_pct = int(round(p_a * 100.0))
        d_pct = int(round(p_d * 100.0))
        b_pct = 100 - a_pct - d_pct
        if b_pct < 0:
            d_pct = max(0, d_pct + b_pct)
            b_pct = 100 - a_pct - d_pct

        rect = pygame.Rect(x, y, width, 56)
        fill = (12, 18, 30, 175) if pop_mode else (10, 16, 26, 180)
        border = (86, 118, 172, 210) if pop_mode else (68, 92, 138, 205)
        self._draw_glass_panel(surface, rect, fill, border, 20)

        left_label = str(team_a.get("short_name") or self._display_score_team_name(team_a))
        right_label = str(team_b.get("short_name") or self._display_score_team_name(team_b))

        left_surf = self.info_font.render(f"{left_label} WINRATE {a_pct}%", True, (238, 155, 155))
        draw_surf = self.info_font.render(f"DRAW RATE {d_pct}%", True, (215, 220, 232))
        right_surf = self.info_font.render(f"{right_label} WINRATE {b_pct}%", True, (156, 190, 255))

        baseline_y = rect.y + 28
        surface.blit(left_surf, left_surf.get_rect(midleft=(rect.x + 18, baseline_y)))
        surface.blit(draw_surf, draw_surf.get_rect(center=(rect.centerx, baseline_y)))
        surface.blit(right_surf, right_surf.get_rect(midright=(rect.right - 18, baseline_y)))

    def _draw_win_rate_rail(self, surface: pygame.Surface, snapshot: dict, x: int, y: int, width: int) -> None:
        odds = snapshot.get("win_probabilities")
        if not isinstance(odds, dict):
            return

        try:
            p_a = float(odds.get("team_a", 0.0))
            p_d = float(odds.get("draw", 0.0))
            p_b = float(odds.get("team_b", 0.0))
        except (TypeError, ValueError):
            return

        p_a, p_d, p_b = self._normalize_triplet(p_a, p_d, p_b)
        s_a, s_d, s_b = self._win_rate_rail_probs
        smooth = 0.16
        s_a += (p_a - s_a) * smooth
        s_d += (p_d - s_d) * smooth
        s_b += (p_b - s_b) * smooth
        s_a, s_d, s_b = self._normalize_triplet(s_a, s_d, s_b)
        self._win_rate_rail_probs = (s_a, s_d, s_b)

        rect = pygame.Rect(x, y, width, 56)
        self._draw_glass_panel(surface, rect, (10, 16, 26, 180), (68, 92, 138, 205), 20)

        rail_margin = 20
        rail_h = 26
        rail_rect = pygame.Rect(rect.x + rail_margin, rect.y + (rect.height - rail_h) // 2, rect.width - rail_margin * 2, rail_h)
        pygame.draw.rect(surface, (42, 52, 74), rail_rect, border_radius=13)

        red_w = int(round(rail_rect.width * s_a))
        white_w = int(round(rail_rect.width * s_d))
        blue_w = rail_rect.width - red_w - white_w
        if blue_w < 0:
            blue_w = 0
            if white_w > 0:
                white_w = max(0, rail_rect.width - red_w)

        red_rect = pygame.Rect(rail_rect.x, rail_rect.y, red_w, rail_rect.height)
        white_rect = pygame.Rect(red_rect.right, rail_rect.y, white_w, rail_rect.height)
        blue_rect = pygame.Rect(white_rect.right, rail_rect.y, blue_w, rail_rect.height)

        if red_rect.width > 0:
            pygame.draw.rect(surface, (230, 96, 96), red_rect, border_radius=13)
        if white_rect.width > 0:
            pygame.draw.rect(surface, (238, 242, 250), white_rect, border_radius=13)
        if blue_rect.width > 0:
            pygame.draw.rect(surface, (112, 170, 250), blue_rect, border_radius=13)

        pygame.draw.rect(surface, (214, 222, 240), rail_rect, width=2, border_radius=13)

    def _draw_penalty_overlay(self, surface: pygame.Surface, snapshot: dict) -> None:
        if not bool(snapshot.get("penalty_overlay_active", False)):
            return

        teams = snapshot.get("teams", [])
        if len(teams) < 2:
            return

        team_a = next((team for team in teams if team.get("role") == "A"), teams[0])
        team_b = next((team for team in teams if team.get("role") == "B"), teams[1])
        pen_a = int(snapshot.get("penalty_display_score_a", 0))
        pen_b = int(snapshot.get("penalty_display_score_b", 0))
        marks_a = list(snapshot.get("penalty_marks_a", []))
        marks_b = list(snapshot.get("penalty_marks_b", []))
        total_shown = int(snapshot.get("penalty_shown_kicks", 0))
        total_all = int(snapshot.get("penalty_total_kicks", 0))

        panel = pygame.Rect(120, 360, self.cfg.video.width - 240, 250)
        self._draw_glass_panel(surface, panel, (8, 14, 24, 220), (248, 200, 110, 235), 28)

        title = self.team_font.render("PENALTY SHOOTOUT", True, (255, 223, 138))
        surface.blit(title, title.get_rect(center=(panel.centerx, panel.y + 36)))

        team_name_a = self._fit_text(self.team_font, self._display_score_team_name(team_a), 280, (245, 246, 250))
        team_name_b = self._fit_text(self.team_font, self._display_score_team_name(team_b), 280, (245, 246, 250))
        surface.blit(team_name_a, team_name_a.get_rect(center=(panel.x + 205, panel.y + 82)))
        surface.blit(team_name_b, team_name_b.get_rect(center=(panel.right - 205, panel.y + 82)))

        score_text = self.score_font.render(f"{pen_a}  -  {pen_b}", True, (255, 246, 230))
        surface.blit(score_text, score_text.get_rect(center=(panel.centerx, panel.y + 126)))

        box_w = 30
        box_h = 18
        gap = 8
        row_y_a = panel.y + 182
        row_y_b = panel.y + 212
        max_marks = max(len(marks_a), len(marks_b), 10)
        row_w = max_marks * box_w + max(0, max_marks - 1) * gap
        row_x = panel.centerx - row_w // 2
        for i in range(max_marks):
            x = row_x + i * (box_w + gap)
            mark_a = marks_a[i] if i < len(marks_a) else ""
            mark_b = marks_b[i] if i < len(marks_b) else ""
            color_a = (95, 198, 122) if mark_a == "GOAL" else ((206, 82, 82) if mark_a == "MISS" else (58, 70, 98))
            color_b = (95, 198, 122) if mark_b == "GOAL" else ((206, 82, 82) if mark_b == "MISS" else (58, 70, 98))
            pygame.draw.rect(surface, color_a, pygame.Rect(x, row_y_a, box_w, box_h), border_radius=6)
            pygame.draw.rect(surface, color_b, pygame.Rect(x, row_y_b, box_w, box_h), border_radius=6)

        status = self.micro_font.render(f"Kicks shown: {total_shown}/{total_all}", True, (196, 206, 226))
        surface.blit(status, status.get_rect(center=(panel.centerx, panel.bottom - 14)))

    def _draw_finish_overlay(self, surface: pygame.Surface, snapshot: dict) -> None:
        teams = snapshot.get("teams", [])
        if len(teams) < 2:
            return

        overlay = pygame.Surface((self.cfg.video.width, self.cfg.video.height), pygame.SRCALPHA)
        overlay.fill((7, 10, 18, 178))
        surface.blit(overlay, (0, 0))

        team_a = next((team for team in teams if team.get("role") == "A"), teams[0])
        team_b = next((team for team in teams if team.get("role") == "B"), teams[1])

        score_a = int(team_a["score"])
        score_b = int(team_b["score"])
        progress = float(snapshot.get("final_result_progress", 1.0))
        decided_by = str(snapshot.get("knockout_decided_by", "normal_time"))
        regular_a = int(snapshot.get("regular_time_score_a", score_a))
        regular_b = int(snapshot.get("regular_time_score_b", score_b))
        extra_raw_a = snapshot.get("extra_time_score_a")
        extra_raw_b = snapshot.get("extra_time_score_b")
        extra_a = int(extra_raw_a) if extra_raw_a is not None else 0
        extra_b = int(extra_raw_b) if extra_raw_b is not None else 0
        pen_raw_a = snapshot.get("penalty_score_a")
        pen_raw_b = snapshot.get("penalty_score_b")
        pen_a = int(pen_raw_a) if pen_raw_a is not None else None
        pen_b = int(pen_raw_b) if pen_raw_b is not None else None

        panel = pygame.Rect(120, 470, self.cfg.video.width - 240, 680)
        self._draw_glass_panel(surface, panel, (10, 16, 28, 220), (92, 114, 156, 235), 36)

        if decided_by == "penalties":
            final_label = "FULL TIME (PEN)"
        elif decided_by == "extra_time":
            final_label = "FULL TIME (AET)"
        else:
            final_label = "FINAL RESULT" if self._is_pop_mode(snapshot) else "FULL TIME"
        ft_text = self.overlay_font.render(final_label, True, (255, 228, 128))
        ft_rect = ft_text.get_rect(center=(self.cfg.video.width // 2, panel.y + 92))
        surface.blit(ft_text, ft_rect)

        if decided_by == "penalties" and pen_a is not None and pen_b is not None:
            winner_is_a = pen_a > pen_b
        else:
            winner_is_a = score_a > score_b

        if winner_is_a:
            headline = f"{team_a['name']} WINS!"
            color = (220, 72, 72)
        elif (decided_by == "penalties" and pen_a is not None and pen_b is not None and pen_b > pen_a) or score_b > score_a:
            headline = f"{team_b['name']} WINS!"
            color = (79, 137, 255)
        else:
            headline = "DRAW!"
            color = (240, 240, 244)

        winner_text = self.overlay_sub_font.render(headline, True, color)
        winner_rect = winner_text.get_rect(center=(self.cfg.video.width // 2, panel.y + 166))
        surface.blit(winner_text, winner_rect)

        left_logo = self._get_logo_surface(team_a["name"], team_a.get("badge_file", ""), 180)
        right_logo = self._get_logo_surface(team_b["name"], team_b.get("badge_file", ""), 180)
        surface.blit(left_logo, left_logo.get_rect(center=(panel.x + 190, panel.y + 360)))
        surface.blit(right_logo, right_logo.get_rect(center=(panel.right - 190, panel.y + 360)))

        team_a_text = self.result_team_font.render(team_a["name"], True, (245, 247, 252))
        team_b_text = self.result_team_font.render(team_b["name"], True, (245, 247, 252))
        surface.blit(team_a_text, team_a_text.get_rect(center=(panel.x + 190, panel.y + 495)))
        surface.blit(team_b_text, team_b_text.get_rect(center=(panel.right - 190, panel.y + 495)))

        if decided_by == "penalties" and pen_a is not None and pen_b is not None:
            base_a = regular_a + extra_a
            base_b = regular_b + extra_b
            detail_text = f"{base_a} - {base_b}   PEN {pen_a}-{pen_b}"
        elif decided_by == "extra_time":
            detail_text = f"{regular_a + extra_a} - {regular_b + extra_b}   (AET)"
        else:
            detail_text = f"{score_a} - {score_b}"

        detail = self._fit_text(self.result_font, detail_text, panel.width - 140, (246, 246, 248))
        detail_rect = detail.get_rect(center=(self.cfg.video.width // 2, panel.y + 372))
        surface.blit(detail, detail_rect)

        progress_bar = pygame.Rect(panel.x + 80, panel.bottom - 82, panel.width - 160, 18)
        pygame.draw.rect(surface, (40, 48, 66), progress_bar, border_radius=9)
        fill_rect = pygame.Rect(progress_bar.x, progress_bar.y, int(progress_bar.width * progress), progress_bar.height)
        pygame.draw.rect(surface, color, fill_rect, border_radius=9)

    def _draw_hook_overlay(self, surface: pygame.Surface, snapshot: dict) -> None:
        teams = snapshot.get("teams", [])
        if len(teams) < 2:
            return

        w = self.cfg.video.width
        h = self.cfg.video.height
        cx = w // 2
        progress = max(0.0, min(1.0, float(snapshot.get("hook_progress", 1.0))))

        anim = self._hook_anim_values(progress)
        scale = anim["scale"]
        content_alpha = max(0.0, min(1.0, anim["alpha"]))
        glow_intensity = max(0.0, min(1.0, anim["glow_intensity"]))

        team_a = next((team for team in teams if team.get("role") == "A"), teams[0])
        team_b = next((team for team in teams if team.get("role") == "B"), teams[1])
        
        # We can extract dominant colors if available, or fallback to default
        color_a = team_a.get("color", (220, 72, 72))
        color_b = team_b.get("color", (79, 137, 255))
        
        # Ensure they are tuples of length 3
        if isinstance(color_a, str): color_a = (220, 72, 72)
        if isinstance(color_b, str): color_b = (79, 137, 255)

        # 1) Dark overlay
        overlay = pygame.Surface((w, h), pygame.SRCALPHA)
        overlay.fill((3, 5, 12, int(140 + 95 * content_alpha)))
        surface.blit(overlay, (0, 0))

        # 2) Background color glow based on team colors
        # Increase distance between logos even further as requested
        logo_dist = 260
        logo_a_x = cx - logo_dist
        logo_b_x = cx + logo_dist
        logo_y = h // 2 + 50

        glow_strength = glow_intensity * content_alpha
        glow_surface = pygame.Surface((w, h), pygame.SRCALPHA)
        
        # Create gradient glow - Centered on logos
        pygame.draw.circle(glow_surface, (*color_a[:3], int(70 * glow_strength)), (logo_a_x, logo_y), 500)
        pygame.draw.circle(glow_surface, (*color_b[:3], int(70 * glow_strength)), (logo_b_x, logo_y), 500)
        
        surface.blit(glow_surface, (0, 0))

        # 3) Sparks (Make them thicker/bigger for dramatic effect)
        self._draw_hook_sparks(surface, progress, content_alpha * (0.6 + 0.4 * glow_intensity))

        # 4) Dynamic title
        raw_title = str(snapshot.get("match_title", "")).strip()
        default_auto_title = f"{team_a.get('name', '')} vs {team_b.get('name', '')}".strip()
        if not raw_title or raw_title.lower() == default_auto_title.lower():
            hook_text = "MATCH PREVIEW"
        else:
            hook_text = raw_title.upper()

        max_text_width = w - 160
        hook_font = self.hook_mega_font
        rendered_width = hook_font.size(hook_text)[0]
        text_scale = 1.0
        if rendered_width > max_text_width and rendered_width > 0:
            text_scale = max_text_width / rendered_width

        who_y = 200
        shadow = hook_font.render(hook_text, True, (0, 0, 0))
        shadow.set_alpha(int(185 * content_alpha))
        who = hook_font.render(hook_text, True, (255, 255, 255))
        who.set_alpha(int(255 * content_alpha))
        s = max(0.3, scale * text_scale)
        if abs(s - 1.0) > 0.01:
            shadow = pygame.transform.smoothscale(shadow, (max(1, int(shadow.get_width() * s)), max(1, int(shadow.get_height() * s))))
            who = pygame.transform.smoothscale(who, (max(1, int(who.get_width() * s)), max(1, int(who.get_height() * s))))
        surface.blit(shadow, shadow.get_rect(center=(cx + 5, who_y + 6)))
        surface.blit(who, who.get_rect(center=(cx, who_y)))

        # 5) Logos (Even bigger, and further apart)
        base_logo = 360
        logo_a = self._get_logo_surface(team_a["name"], team_a.get("badge_file", ""), base_logo)
        logo_b = self._get_logo_surface(team_b["name"], team_b.get("badge_file", ""), base_logo)
        scaled_size = max(48, int(base_logo * scale))
        logo_a = pygame.transform.smoothscale(logo_a, (scaled_size, scaled_size))
        logo_b = pygame.transform.smoothscale(logo_b, (scaled_size, scaled_size))

        toss_y = int((1.0 - min(1.2, scale)) * 210)
        toss_x = int((1.0 - min(1.1, scale)) * 90)

        logo_a.set_alpha(int(255 * content_alpha))
        logo_b.set_alpha(int(255 * content_alpha))
        
        surface.blit(logo_a, logo_a.get_rect(center=(logo_a_x - toss_x, logo_y + toss_y)))
        surface.blit(logo_b, logo_b.get_rect(center=(logo_b_x + toss_x, logo_y + toss_y)))

        # VS badge in between
        vs_y = logo_y + toss_y // 2
        vr = max(45, int(75 * scale))
        vs_s = pygame.Surface((vr * 4, vr * 4), pygame.SRCALPHA)
        vc = vr * 2
        pygame.draw.circle(vs_s, (255, 220, 100, int(88 * glow_strength)), (vc, vc), int(vr * 1.9))
        pygame.draw.circle(vs_s, (20, 28, 44, 240), (vc, vc), vr)
        pygame.draw.circle(vs_s, (255, 228, 128, int(240 * content_alpha)), (vc, vc), vr, width=4)
        surface.blit(vs_s, vs_s.get_rect(center=(cx, vs_y)))
        vs_t = self.hook_vs_font.render("VS", True, (255, 228, 128))
        vs_t.set_alpha(int(255 * content_alpha))
        surface.blit(vs_t, vs_t.get_rect(center=(cx, vs_y)))

        # Logo Names
        name_w = 380
        name_a = self._fit_text(self.hook_team_font, team_a["name"], name_w, (252, 253, 255))
        name_b = self._fit_text(self.hook_team_font, team_b["name"], name_w, (252, 253, 255))
        name_a_shadow = self._fit_text(self.hook_team_font, team_a["name"], name_w, (0, 0, 0))
        name_b_shadow = self._fit_text(self.hook_team_font, team_b["name"], name_w, (0, 0, 0))
        if abs(scale - 1.0) > 0.01:
            s_name = max(0.3, scale)
            name_a = pygame.transform.smoothscale(name_a, (max(1, int(name_a.get_width() * s_name)), max(1, int(name_a.get_height() * s_name))))
            name_b = pygame.transform.smoothscale(name_b, (max(1, int(name_b.get_width() * s_name)), max(1, int(name_b.get_height() * s_name))))
            name_a_shadow = pygame.transform.smoothscale(name_a_shadow, (max(1, int(name_a_shadow.get_width() * s_name)), max(1, int(name_a_shadow.get_height() * s_name))))
            name_b_shadow = pygame.transform.smoothscale(name_b_shadow, (max(1, int(name_b_shadow.get_width() * s_name)), max(1, int(name_b_shadow.get_height() * s_name))))
        name_a.set_alpha(int(255 * content_alpha))
        name_b.set_alpha(int(255 * content_alpha))
        name_a_shadow.set_alpha(int(130 * content_alpha))
        name_b_shadow.set_alpha(int(130 * content_alpha))
        
        na_pos = (logo_a_x - toss_x, logo_y + 240 + toss_y)
        nb_pos = (logo_b_x + toss_x, logo_y + 240 + toss_y)
        surface.blit(name_a_shadow, name_a_shadow.get_rect(center=(na_pos[0] + 3, na_pos[1] + 4)))
        surface.blit(name_b_shadow, name_b_shadow.get_rect(center=(nb_pos[0] + 3, nb_pos[1] + 4)))
        surface.blit(name_a, name_a.get_rect(center=na_pos))
        surface.blit(name_b, name_b.get_rect(center=nb_pos))

    def _hook_anim_values(self, progress: float) -> dict:
        """Timeline: 0.0-0.3 entry, 0.3-0.8 peak pulse, 0.8-1.0 full fade-out."""
        p = max(0.0, min(1.0, progress))
        if p <= 0.3:
            t = p / 0.3
            e = self._ease_out_back(t)
            return {
                "scale": 0.3 + 0.7 * e,
                "alpha": t,
                "glow_intensity": min(1.0, 0.15 + t * 0.9),
            }

        if p <= 0.8:
            t = (p - 0.3) / 0.5
            pulse = 0.92 + 0.08 * math.sin(t * math.tau * 2.4)
            center_peak = max(0.0, 1.0 - abs(p - 0.5) / 0.2)
            return {
                "scale": 1.0,
                "alpha": 1.0,
                "glow_intensity": min(1.0, pulse + 0.07 * center_peak),
            }

        t = (p - 0.8) / 0.2
        smooth = t * t * (3.0 - 2.0 * t)
        fade = 1.0 - smooth
        return {
            "scale": 1.0 - 0.14 * smooth,
            "alpha": fade,
            "glow_intensity": fade * fade,
        }

    @staticmethod
    def _ease_out_back(t: float) -> float:
        c1 = 1.70158
        c3 = c1 + 1.0
        return 1.0 + c3 * (t - 1.0) ** 3 + c1 * (t - 1.0) ** 2

    def _draw_hook_glow(
        self, surface: pygame.Surface,
        cx: int, cy: int, radius: int,
        color: Tuple[int, int, int], intensity: float,
    ) -> None:
        if intensity < 0.02:
            return
        glow = pygame.Surface((radius * 2, radius * 2), pygame.SRCALPHA)
        layers = 5
        for i in range(layers):
            t = i / max(1, layers - 1)
            r = int(radius * (1.03 - t * 0.58))
            a = int((140 - i * 22) * intensity)
            if a <= 0:
                continue
            pygame.draw.circle(glow, (*color, min(255, a)), (radius, radius), max(6, r))
        surface.blit(glow, (cx - radius, cy - radius))

    def _init_hook_sparks(self) -> None:
        rng = random.Random(42)
        w, h = self.cfg.video.width, self.cfg.video.height
        palette = [
            (255, 228, 128), (255, 255, 255), (200, 215, 255),
            (255, 180, 100), (180, 200, 255), (255, 200, 150),
        ]
        self._hook_sparks = []
        for _ in range(120):
            self._hook_sparks.append({
                "x": rng.uniform(-80, w + 80),
                "size": rng.uniform(1.5, 5.2),
                "alpha_base": rng.randint(70, 230),
                "rise": rng.uniform(h * 0.7, h * 1.25),
                "drift_x": rng.uniform(-34, 34),
                "amp_x": rng.uniform(6, 24),
                "phase": rng.uniform(0, math.tau),
                "start_shift": rng.uniform(-0.14, 0.2),
                "color": rng.choice(palette),
            })
        self._hook_sparks_ready = True

    def _draw_hook_sparks(self, surface: pygame.Surface, progress: float, alpha_mult: float) -> None:
        if not self._hook_sparks_ready:
            self._init_hook_sparks()
        h = self.cfg.video.height
        for sp in self._hook_sparks:
            flow = max(0.0, progress + sp["start_shift"])
            x = sp["x"] + math.sin(progress * 9.0 + sp["phase"]) * sp["amp_x"] + sp["drift_x"] * flow
            y = h + 110 - flow * sp["rise"]
            if y < -35:
                continue

            twinkle = 0.5 + 0.5 * math.sin(progress * 15.0 + sp["phase"] * 1.3)
            a = int(sp["alpha_base"] * twinkle * alpha_mult)
            if a <= 0:
                continue

            sz = max(1, int(sp["size"]))
            dot = pygame.Surface((sz * 2, sz * 2), pygame.SRCALPHA)
            pygame.draw.circle(dot, (*sp["color"], min(255, a)), (sz, sz), sz)
            if sz > 2:
                pygame.draw.circle(dot, (255, 255, 255, min(255, int(a * 0.7))), (sz, sz), max(1, sz // 2))
            surface.blit(dot, (int(x) - sz, int(y) - sz))

    def _draw_goal_flash(self, surface: pygame.Surface) -> None:
        if self.goal_flash_timer <= 0.0 or not self.goal_flash_event:
            return

        progress = min(1.0, self.goal_flash_timer / 0.95)
        alpha = int(205 * min(1.0, progress * 1.6))
        burst = pygame.Surface((self.cfg.video.width, 310), pygame.SRCALPHA)
        burst.fill((0, 0, 0, 0))

        team_color = self.goal_flash_event["color"]
        pygame.draw.rect(burst, (*team_color, alpha), pygame.Rect(80, 46, self.cfg.video.width - 160, 170), border_radius=34)
        pygame.draw.rect(burst, (255, 255, 255, min(255, alpha + 20)), pygame.Rect(80, 46, self.cfg.video.width - 160, 170), width=3, border_radius=34)

        is_pop_flash = bool(self.goal_flash_event.get("is_pop_mode", False))
        flash_text = str(self.goal_flash_event.get("flash_text", "POINT!" if is_pop_flash else "GOAL!"))
        goal_text = self.goal_font.render(flash_text, True, (255, 255, 255))
        goal_rect = goal_text.get_rect(center=(self.cfg.video.width // 2, 118))
        burst.blit(goal_text, goal_rect)

        sub_text = self.goal_sub_font.render(self.goal_flash_event["team_name"], True, (245, 248, 255))
        sub_rect = sub_text.get_rect(center=(self.cfg.video.width // 2, 175))
        burst.blit(sub_text, sub_rect)

        surface.blit(burst, (0, 370))

    def _update_impact_particles(self, snapshot: dict, dt: float) -> None:
        sparks = snapshot.get("collision_sparks", []) or []
        for spark in sparks:
            key = (round(float(spark.get("time", 0.0)), 4), round(float(spark.get("x", 0.0)), 1), round(float(spark.get("y", 0.0)), 1))
            if key in self._spawned_spark_keys:
                continue
            self._spawned_spark_keys.add(key)
            impulse = max(0.0, min(1.0, float(spark.get("impulse", 0.5))))
            count = max(2, int(3 + 4 * impulse))
            base_x = float(spark.get("x", 0.0))
            base_y = float(spark.get("y", 0.0))
            for _ in range(count):
                angle = random.uniform(0.0, 2.0 * math.pi)
                speed = random.uniform(70.0, 220.0) * (0.5 + impulse)
                self._impact_particles.append({
                    "x": base_x,
                    "y": base_y,
                    "vx": math.cos(angle) * speed,
                    "vy": math.sin(angle) * speed - 60.0,
                    "life": random.uniform(0.18, 0.42),
                    "age": 0.0,
                    "size": random.uniform(1.8, 4.2),
                    "color": random.choice([
                        (255, 220, 120),
                        (255, 185, 82),
                        (255, 248, 210),
                        (255, 160, 70),
                    ]),
                })
        if len(self._spawned_spark_keys) > 256:
            self._spawned_spark_keys = set(list(self._spawned_spark_keys)[-128:])
        alive: List[dict] = []
        for p in self._impact_particles:
            p["age"] += dt
            if p["age"] >= p["life"]:
                continue
            p["x"] += p["vx"] * dt
            p["y"] += p["vy"] * dt
            p["vy"] += 420.0 * dt
            alive.append(p)
        if len(alive) > 140:
            alive = alive[-110:]
        self._impact_particles = alive

    def _draw_impact_particles(self, surface: pygame.Surface) -> None:
        if not self._impact_particles:
            return
        for p in self._impact_particles:
            life = max(1e-6, float(p.get("life", 0.3)))
            age = float(p.get("age", 0.0))
            ratio = 1.0 - (age / life)
            if ratio <= 0.05:
                continue
            sz = max(1, int(float(p.get("size", 2.5)) * ratio))
            color = p.get("color", (255, 220, 120))
            pygame.draw.circle(surface, color, (int(p["x"]), int(p["y"])), sz)

    def _draw_tension_overlay(self, surface: pygame.Surface, snapshot: dict) -> None:
        if not bool(snapshot.get("tension_active", False)):
            return
        tp = max(0.0, min(1.0, float(snapshot.get("tension_progress", 0.0))))
        if tp <= 0.02:
            return
        tint = self.cfg.tension.bg_tint_color
        max_alpha = int(self.cfg.tension.bg_tint_alpha_max)
        pulse = 0.75 + 0.25 * math.sin(float(snapshot.get("physics_sim_time", 0.0)) * 4.5)
        alpha = int(max_alpha * tp * pulse)
        overlay = pygame.Surface(surface.get_size(), pygame.SRCALPHA)
        overlay.fill((tint[0], tint[1], tint[2], alpha))
        surface.blit(overlay, (0, 0))

    def _draw_var_review_overlay(self, surface: pygame.Surface, snapshot: dict) -> None:
        payload = snapshot.get("var_review")
        if not isinstance(payload, dict) or not bool(payload.get("active", False)):
            return

        phase = str(payload.get("phase", "checking"))
        decision = str(payload.get("decision", "pending"))
        progress = max(0.0, min(1.0, float(payload.get("progress", 0.0))))
        team_name = str(payload.get("team_name", "TEAM"))

        dim = pygame.Surface((self.cfg.video.width, self.cfg.video.height), pygame.SRCALPHA)
        dim.fill((4, 7, 13, 120))
        surface.blit(dim, (0, 0))

        panel_w = 920
        panel_h = 238
        panel_x = self.cfg.video.width // 2 - panel_w // 2
        panel_y = 510

        self._draw_glass_panel(
            surface,
            pygame.Rect(panel_x, panel_y, panel_w, panel_h),
            (6, 12, 22, 232),
            (126, 146, 186, 236),
            30,
        )

        if phase == "checking":
            title_text = "VAR CHECK"
            title_color = (255, 224, 134)
            sub_text = f"{team_name}"
            detail_text = "Potential goal is under review"
        else:
            if decision == "cancelled":
                title_text = "NO GOAL"
                title_color = (255, 122, 122)
                sub_text = f"{team_name}"
                detail_text = "Decision: Offside / Foul"
            else:
                title_text = "GOAL CONFIRMED"
                title_color = (124, 234, 154)
                sub_text = f"{team_name}"
                detail_text = "Decision: Goal stands"

        shadow = self.overlay_sub_font.render(title_text, True, (0, 0, 0))
        title_surf = self.overlay_sub_font.render(title_text, True, title_color)
        center_x = self.cfg.video.width // 2
        surface.blit(shadow, shadow.get_rect(center=(center_x + 2, panel_y + 57)))
        surface.blit(title_surf, title_surf.get_rect(center=(center_x, panel_y + 54)))

        team_surf = self.team_font.render(sub_text, True, (238, 242, 252))
        detail_surf = self.info_font.render(detail_text, True, (202, 212, 232))
        surface.blit(team_surf, team_surf.get_rect(center=(center_x, panel_y + 104)))
        surface.blit(detail_surf, detail_surf.get_rect(center=(center_x, panel_y + 138)))

        bar_w = panel_w - 140
        bar_h = 22
        bar_x = panel_x + 70
        bar_y = panel_y + 176
        pygame.draw.rect(surface, (44, 56, 82), pygame.Rect(bar_x, bar_y, bar_w, bar_h), border_radius=11)
        fill_color = (241, 194, 92) if phase == "checking" else ((241, 108, 108) if decision == "cancelled" else (108, 224, 142))
        pygame.draw.rect(surface, fill_color, pygame.Rect(bar_x, bar_y, max(3, int(bar_w * progress)), bar_h), border_radius=11)

        pct_text = self.micro_font.render(f"{int(progress * 100)}%", True, (232, 238, 250))
        surface.blit(pct_text, pct_text.get_rect(midleft=(bar_x + bar_w + 12, bar_y + bar_h // 2)))

    def _draw_ball(self, surface: pygame.Surface, ball: dict) -> None:
        team_name = ball["team_name"]
        badge_file = ball.get("team_badge_file", "")
        x = float(ball["x"])
        y = float(ball["y"])
        radius = int(ball["radius"])
        angle_radians = float(ball["angle_radians"])

        base_logo = self._get_logo_surface(team_name=team_name, badge_file=badge_file, diameter=radius * 4)

        self._draw_ball_shadow(surface, x, y, radius)

        angle_degrees = -math.degrees(angle_radians)
        rotated = pygame.transform.rotozoom(base_logo, angle_degrees, 0.5)
        rect = rotated.get_rect(center=(int(x), int(y)))
        surface.blit(rotated, rect)

    def _draw_ball_shadow(self, surface: pygame.Surface, x: float, y: float, radius: int) -> None:
        shadow_w = int(radius * 1.45)
        shadow_h = max(6, int(radius * 0.42))

        shadow = pygame.Surface((shadow_w * 2, shadow_h * 2), pygame.SRCALPHA)
        pygame.draw.ellipse(
            shadow,
            (6, 8, 12, 72),
            pygame.Rect(0, 0, shadow_w * 2, shadow_h * 2),
        )
        rect = shadow.get_rect(center=(int(x), int(y + radius * 0.78)))
        surface.blit(shadow, rect)

    def _get_logo_surface(self, team_name: str, badge_file: str, diameter: int) -> pygame.Surface:
        cache_key = f"{badge_file}|{diameter}"
        cached = self.logo_base_surfaces.get(cache_key)
        if cached is not None:
            return cached

        logo_path = self.cfg.data_dir / "logos" / badge_file

        try:
            surface = self._load_logo_surface(logo_path, diameter)
        except Exception:
            surface = self._build_placeholder_logo(team_name, diameter)

        self.logo_base_surfaces[cache_key] = surface
        return surface

    def _load_logo_surface(self, path: Path, size: int) -> pygame.Surface:
        if not path.exists():
            raise FileNotFoundError(f"Logo bulunamadi: {path}")

        image = Image.open(path).convert("RGBA")
        
        # 1) Auto-crop transparent borders
        bbox = image.getbbox()
        if bbox:
            image = image.crop(bbox)
            
        # 2) Calculate smart scale
        orig_w, orig_h = image.size
        aspect = orig_w / orig_h
        
        # We want to fill the circle as much as possible. 
        # Radius is size//2 - 3, so diameter is size - 6.
        target_inner = size - 4 
        
        if 0.85 <= aspect <= 1.15:
            # Nearly square/round: Fill both
            draw_w, draw_h = target_inner, target_inner
        elif aspect < 0.85:
            # Tall (Crest): Fix height, calculate width
            draw_h = target_inner
            draw_w = int(draw_h * aspect)
        else:
            # Wide: Fix width, calculate height
            draw_w = target_inner
            draw_h = int(draw_w / aspect)
            
        # Use resize instead of thumbnail to force upscaling if source is small
        image = image.resize((draw_w, draw_h), Image.Resampling.LANCZOS)
        image = image.filter(ImageFilter.UnsharpMask(radius=1.6, percent=165, threshold=2))

        canvas = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        paste_x = (size - image.width) // 2
        paste_y = (size - image.height) // 2
        canvas.paste(image, (paste_x, paste_y), image)

        disc = pygame.image.fromstring(canvas.tobytes(), canvas.size, canvas.mode).convert_alpha()

        center = (size // 2, size // 2)
        radius = size // 2 - 3
        mask = pygame.Surface((size, size), pygame.SRCALPHA)
        pygame.draw.circle(mask, (255, 255, 255, 255), center, radius)

        cropped = pygame.Surface((size, size), pygame.SRCALPHA)
        cropped.blit(disc, (0, 0))
        cropped.blit(mask, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)

        pygame.draw.circle(cropped, (248, 249, 252, 230), center, radius, width=4)
        pygame.draw.circle(cropped, (20, 24, 34, 180), center, radius - 1, width=1)

        return cropped

    def _build_placeholder_logo(self, team_name: str, size: int) -> pygame.Surface:
        surf = pygame.Surface((size, size), pygame.SRCALPHA)
        center = (size // 2, size // 2)
        radius = size // 2 - 3

        pygame.draw.circle(surf, (36, 44, 58, 255), center, radius)
        pygame.draw.circle(surf, (230, 230, 235, 255), center, radius, width=7)

        initials = "".join(word[0] for word in team_name.split()[:2]).upper()[:2] or "TM"
        font = pygame.font.SysFont("arial", max(18, size // 3), bold=True)
        text = font.render(initials, True, (245, 245, 245))
        text_rect = text.get_rect(center=center)
        surf.blit(text, text_rect)

        return surf

    def _draw_glass_panel(
        self,
        surface: pygame.Surface,
        rect: pygame.Rect,
        fill_rgba: Tuple[int, int, int, int],
        border_rgba: Tuple[int, int, int, int],
        radius: int,
    ) -> None:
        panel = pygame.Surface((rect.width, rect.height), pygame.SRCALPHA)
        pygame.draw.rect(panel, fill_rgba, pygame.Rect(0, 0, rect.width, rect.height), border_radius=radius)
        pygame.draw.rect(panel, border_rgba, pygame.Rect(0, 0, rect.width, rect.height), width=2, border_radius=radius)
        surface.blit(panel, rect.topleft)


    def _update_dynamic_effects(self, snapshot: dict) -> None:
        is_pop_mode = self._is_pop_mode(snapshot)
        scoring_gap_label = str(snapshot.get("scoring_gap_label", "POINT" if is_pop_mode else "GOAL"))
        is_var_mode = bool(snapshot.get("var_mode_enabled", False))

        confirmed_events = snapshot.get("confirmed_scoring_events", [])
        if isinstance(confirmed_events, list) and confirmed_events:
            events = confirmed_events
        elif is_var_mode:
            # VAR modunda sadece onayli olaylar gol/point efekti tetikleyebilir.
            events = []
        else:
            events = snapshot.get("latest_round_events", [])

        for event in events:
            key = (
                int(event.get("round_index", 0)),
                str(event.get("team_key", "")),
                str(event.get("gap_label", "")),
                round(float(event.get("x_at_exit", 0.0)), 2),
            )
            if key in self._seen_event_keys:
                continue

            self._seen_event_keys.add(key)
            if str(event.get("gap_label", "")) == scoring_gap_label:
                team_color = self._get_team_color_from_name(snapshot, str(event.get("team_name", "")))
                self.goal_flash_timer = 0.95
                self.goal_flash_event = {
                    "team_name": str(event.get("team_name", "POINT" if is_pop_mode else "GOAL")),
                    "color": team_color,
                    "flash_text": "POINT!" if is_pop_mode else "GOAL!",
                    "is_pop_mode": is_pop_mode,
                }
                self._spawn_confetti(team_color)

        if self.goal_flash_timer > 0.0:
            self.goal_flash_timer = max(0.0, self.goal_flash_timer - (1.0 / self.cfg.video.fps))

    def _iter_peg_centers(self) -> Iterable[Tuple[float, float]]:
        spacing_y = self.cfg.layout.peg_spacing_y
        rows = self.cfg.layout.peg_rows
        top_y = self.cfg.layout.peg_top_y
        ramp_clearance_y = self.cfg.layout.floor_y - 280

        left_edge = float(self.cfg.playfield_left)
        right_edge = float(self.cfg.playfield_right)
        usable = right_edge - left_edge

        cols_even = max(2, round(usable / self.cfg.layout.peg_spacing_x))
        spacing_x = usable / cols_even

        for row in range(2, rows):
            y = top_y + row * spacing_y
            if y > ramp_clearance_y:
                break

            if row % 2 == 0:
                for col in range(cols_even + 1):
                    x = left_edge + col * spacing_x
                    yield x, y
            else:
                for col in range(cols_even):
                    x = left_edge + spacing_x / 2 + col * spacing_x
                    yield x, y

    def _build_gap_draw_data_from_cfg(self) -> List[dict]:
        left_label = self.cfg.gameplay.left_gap_label
        center_label = self.cfg.gameplay.center_gap_label
        right_label = self.cfg.gameplay.right_gap_label

        cx = self.cfg.playfield_center_x
        side_gap_w = self.cfg.layout.side_gap_width
        goal_gap_w = self.cfg.layout.goal_gap_width
        divider_w = self.cfg.layout.divider_width

        total_span = side_gap_w + divider_w + goal_gap_w + divider_w + side_gap_w
        left_start = cx - total_span / 2

        left_gap = {
            "label": left_label,
            "start_x": left_start,
            "end_x": left_start + side_gap_w,
        }
        left_gap["center_x"] = (left_gap["start_x"] + left_gap["end_x"]) / 2

        center_gap = {
            "label": center_label,
            "start_x": left_gap["end_x"] + divider_w,
            "end_x": left_gap["end_x"] + divider_w + goal_gap_w,
        }
        center_gap["center_x"] = (center_gap["start_x"] + center_gap["end_x"]) / 2

        right_gap = {
            "label": right_label,
            "start_x": center_gap["end_x"] + divider_w,
            "end_x": center_gap["end_x"] + divider_w + side_gap_w,
        }
        right_gap["center_x"] = (right_gap["start_x"] + right_gap["end_x"]) / 2

        return [left_gap, center_gap, right_gap]

    def _get_team_color_from_name(self, snapshot: dict, team_name: str) -> Tuple[int, int, int]:
        teams = snapshot.get("teams", [])
        for team in teams:
            if team.get("name") == team_name:
                if team.get("role") == "A":
                    return (220, 72, 72)
                if team.get("role") == "B":
                    return (79, 137, 255)
        return (230, 230, 235)

    def _is_pop_mode(self, snapshot: dict) -> bool:
        if bool(snapshot.get("is_pop_mode", False)):
            return True
        mode = str(snapshot.get("engine_mode", "")).strip().lower()
        return mode.startswith("pop_") or mode == "pop_shift"

    @staticmethod
    def _normalize_triplet(a: float, d: float, b: float) -> Tuple[float, float, float]:
        total = max(1e-9, float(a) + float(d) + float(b))
        return (float(a) / total, float(d) / total, float(b) / total)

    def _spawn_confetti(self, team_color: Tuple[int, int, int]) -> None:
        rng = self._confetti_rng
        cx = self.cfg.video.width // 2
        spawn_y = self.cfg.layout.floor_y - 20

        palette = [
            team_color,
            (255, 230, 80),
            (255, 255, 255),
            (120, 240, 160),
            (255, 140, 80),
            (180, 120, 255),
        ]

        for _ in range(110):
            color = rng.choice(palette)
            self.confetti_particles.append(ConfettiParticle(
                x=rng.uniform(cx - 200, cx + 200),
                y=spawn_y,
                vx=rng.uniform(-420, 420),
                vy=rng.uniform(-900, -300),
                color=color,
                size=rng.uniform(8, 18),
                lifetime=rng.uniform(1.4, 2.4),
                angle=rng.uniform(0, math.tau),
                angular_vel=rng.uniform(-8, 8),
            ))

    def _draw_confetti(self, surface: pygame.Surface, dt: float) -> None:
        gravity = 600.0
        alive: List[ConfettiParticle] = []

        for p in self.confetti_particles:
            p.age += dt
            if p.age >= p.lifetime:
                continue

            p.vy += gravity * dt
            p.vx *= 0.985
            p.x += p.vx * dt
            p.y += p.vy * dt
            p.angle += p.angular_vel * dt

            progress = p.age / p.lifetime
            alpha = int(255 * (1.0 - progress ** 1.5))
            size = max(2, int(p.size * (1.0 - progress * 0.4)))

            rect_surf = pygame.Surface((size * 2, size), pygame.SRCALPHA)
            rect_surf.fill((*p.color, alpha))
            rotated = pygame.transform.rotate(rect_surf, math.degrees(p.angle))
            surface.blit(rotated, rotated.get_rect(center=(int(p.x), int(p.y))))

            alive.append(p)

        self.confetti_particles = alive

    def _gap_label_color(self, label: str) -> Tuple[int, int, int]:
        if label == "GOAL":
            return (110, 232, 150)
        if label == "CORNER":
            return (241, 193, 90)
        return (236, 118, 118)

    def _fit_text(
        self,
        font: pygame.font.Font,
        text: str,
        max_width: int,
        color: Tuple[int, int, int],
    ) -> pygame.Surface:
        if font.size(text)[0] <= max_width:
            return font.render(text, True, color)

        trimmed = text
        while trimmed and font.size(trimmed + "...")[0] > max_width:
            trimmed = trimmed[:-1]

        return font.render((trimmed + "...") if trimmed else text[:1], True, color)

    def _display_score_team_name(self, team: dict) -> str:
        short_name = str(team.get("short_name") or "").strip()
        full_name = str(team.get("name") or "").strip()
        if short_name and len(full_name) > 12:
            return short_name
        return full_name

    def _display_event_team_name(self, snapshot: dict, event: dict) -> str:
        target_name = str(event.get("team_name") or "")
        for team in snapshot.get("teams", []):
            if str(team.get("name") or "") == target_name:
                short_name = str(team.get("short_name") or "").strip()
                if short_name:
                    return short_name
        return target_name




