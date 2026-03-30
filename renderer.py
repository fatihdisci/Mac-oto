from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

import pygame
from PIL import Image, ImageFilter

from config import SimulationConfig


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

        self.static_background = self._build_static_background()

    def draw(
        self,
        target_surface: pygame.Surface,
        state_snapshot: dict,
        active_ball_draw_data: List[dict],
    ) -> None:
        self._update_dynamic_effects(state_snapshot)
        target_surface.blit(self.static_background, (0, 0))

        self._draw_header(target_surface, state_snapshot)
        self._draw_scoreboard(target_surface, state_snapshot)

        for ball in active_ball_draw_data:
            self._draw_ball(target_surface, ball)

        self._draw_confetti(target_surface, 1.0 / self.cfg.video.fps)
        self._draw_goal_flash(target_surface)

        if state_snapshot.get("show_hook_overlay", False):
            self._draw_hook_overlay(target_surface, state_snapshot)

        if state_snapshot.get("show_final_result_overlay", False):
            self._draw_finish_overlay(target_surface, state_snapshot)

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

        title = self.title_font.render("FOOTBALL RACE", True, (200, 208, 224))
        title_rect = title.get_rect(center=(cx, panel_y + panel_h // 2))
        surface.blit(title, title_rect)

    def _build_static_background(self) -> pygame.Surface:
        width = self.cfg.video.width
        height = self.cfg.video.height

        background = pygame.Surface((width, height))
        background.fill(self.cfg.video.background_color)

        self._draw_field_panel(background)
        self._draw_side_walls(background)
        self._draw_pegs(background)
        self._draw_bottom_layout(background)

        return background

    def _draw_field_panel(self, surface: pygame.Surface) -> None:
        field_rect = pygame.Rect(
            self.cfg.playfield_left - 18,
            108,
            self.cfg.playfield_width + 36,
            self.cfg.video.height - 192,
        )
        pygame.draw.rect(surface, (22, 30, 44), field_rect, border_radius=28)
        pygame.draw.rect(surface, (46, 58, 82), field_rect, width=2, border_radius=28)

    def _draw_side_walls(self, surface: pygame.Surface) -> None:
        left_x = self.cfg.playfield_left
        right_x = self.cfg.playfield_right
        wall_top = 120
        ramp_top_y = self.cfg.layout.floor_y - 180

        pygame.draw.line(surface, (105, 118, 145), (left_x, wall_top), (left_x, ramp_top_y), 6)
        pygame.draw.line(surface, (105, 118, 145), (right_x, wall_top), (right_x, ramp_top_y), 6)

    def _draw_pegs(self, surface: pygame.Surface) -> None:
        for x, y in self._iter_peg_centers():
            pygame.draw.circle(surface, (10, 14, 22), (int(x + 3), int(y + 4)), self.cfg.physics.peg_radius)
            pygame.draw.circle(surface, (194, 200, 214), (int(x), int(y)), self.cfg.physics.peg_radius)
            pygame.draw.circle(
                surface,
                (228, 232, 240),
                (int(x - 2), int(y - 2)),
                max(2, self.cfg.physics.peg_radius // 3),
            )

    def _draw_bottom_layout(self, surface: pygame.Surface) -> None:
        floor_y = self.cfg.layout.floor_y
        post_h = self.cfg.layout.gap_post_height
        ramp_rise = 180

        gaps = self._build_gap_draw_data_from_cfg()
        left_gap, center_gap, right_gap = gaps

        left_edge = self.cfg.playfield_left
        right_edge = self.cfg.playfield_right

        floor_color = (155, 168, 190)
        post_color = (130, 142, 164)

        segments = [
            ((left_edge, floor_y - ramp_rise), (left_gap["start_x"], floor_y)),
            ((left_gap["end_x"], floor_y), (center_gap["start_x"], floor_y)),
            ((center_gap["end_x"], floor_y), (right_gap["start_x"], floor_y)),
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
        teams = snapshot.get("teams", [])
        if len(teams) < 2:
            return

        team_a = next((team for team in teams if team.get("role") == "A"), teams[0])
        team_b = next((team for team in teams if team.get("role") == "B"), teams[1])

        cx = self.cfg.video.width // 2
        match_clock_text = snapshot.get("match_clock_text", "00:00")
        progress_ratio = float(snapshot.get("match_progress_ratio", 0.0))
        show_full_time = bool(snapshot.get("show_final_result_overlay", False))

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
            phase_text = "FULL TIME"
            phase_color = (255, 227, 120)
        else:
            phase_text = "1ST HALF" if progress_ratio < 0.5 else "2ND HALF"
            phase_color = (175, 185, 205)

        phase_surf = live_font.render(phase_text, True, phase_color)
        surface.blit(phase_surf, phase_surf.get_rect(center=(cx + 62, live_y)))

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

        panel = pygame.Rect(120, 470, self.cfg.video.width - 240, 680)
        self._draw_glass_panel(surface, panel, (10, 16, 28, 220), (92, 114, 156, 235), 36)

        ft_text = self.overlay_font.render("FULL TIME", True, (255, 228, 128))
        ft_rect = ft_text.get_rect(center=(self.cfg.video.width // 2, panel.y + 92))
        surface.blit(ft_text, ft_rect)

        if score_a > score_b:
            headline = f"{team_a['name']} WINS!"
            color = (220, 72, 72)
        elif score_b > score_a:
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

        detail = self.result_font.render(f"{score_a} - {score_b}", True, (246, 246, 248))
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
        progress = float(snapshot.get("hook_progress", 1.0))

        # Animasyon eğrisi
        anim = self._hook_anim_values(progress)
        scale = anim["scale"]
        ca = anim["alpha"]          # content alpha
        gi = anim["glow_intensity"]  # glow intensity

        team_a = next((team for team in teams if team.get("role") == "A"), teams[0])
        team_b = next((team for team in teams if team.get("role") == "B"), teams[1])
        color_a = (220, 72, 72)
        color_b = (79, 137, 255)

        # ═══ 1. Koyu overlay (neon-pop için daha yoğun) ═══
        overlay = pygame.Surface((w, h), pygame.SRCALPHA)
        overlay.fill((4, 6, 14, 218))
        surface.blit(overlay, (0, 0))

        # ═══ 2. Glow efektleri (takım renkleri + altın merkez) ═══
        self._draw_hook_glow(surface, cx - 240, 480, 340, color_a, gi * 0.65)
        self._draw_hook_glow(surface, cx + 240, 480, 340, color_b, gi * 0.65)
        self._draw_hook_glow(surface, cx, 260, 300, (255, 220, 80), gi * 0.45)

        # ═══ 3. Kıvılcım / toz partikülleri ═══
        self._draw_hook_sparks(surface, progress, ca)

        # ═══ 4. FOOTBALL RACE başlık ═══
        title = self.title_font.render("FOOTBALL RACE", True, (140, 155, 185))
        title.set_alpha(int(255 * ca))
        surface.blit(title, title.get_rect(center=(cx, 140)))

        # ═══ 5. BÜYÜK "WHO WINS?" (In-Your-Face) ═══
        who_y = 258
        shadow = self.hook_mega_font.render("WHO WINS?", True, (0, 0, 0))
        shadow.set_alpha(int(160 * ca))
        surface.blit(shadow, shadow.get_rect(center=(cx + 4, who_y + 5)))
        who = self.hook_mega_font.render("WHO WINS?", True, (255, 255, 255))
        who.set_alpha(int(255 * ca))
        surface.blit(who, who.get_rect(center=(cx, who_y)))

        # Altın ayırıcı çizgi
        line_w = 380
        line_s = pygame.Surface((line_w, 3), pygame.SRCALPHA)
        line_s.fill((255, 220, 100, int(200 * ca)))
        surface.blit(line_s, (cx - line_w // 2, 328))

        # ═══ 6. Takım panelleri ═══
        panel_w = 380
        panel_h = 520
        gap = 40
        left_panel = pygame.Rect(cx - panel_w - gap // 2, 380, panel_w, panel_h)
        right_panel = pygame.Rect(cx + gap // 2, 380, panel_w, panel_h)
        pa = int(210 * ca)
        ba = min(255, int(200 * ca))
        self._draw_glass_panel(surface, left_panel, (14, 20, 34, pa), (*color_a, ba), 30)
        self._draw_glass_panel(surface, right_panel, (14, 20, 34, pa), (*color_b, ba), 30)

        # ═══ 7. Logolar (animasyonlu scale) ═══
        base_logo = 200
        logo_a = self._get_logo_surface(team_a["name"], team_a.get("badge_file", ""), base_logo)
        logo_b = self._get_logo_surface(team_b["name"], team_b.get("badge_file", ""), base_logo)
        if abs(scale - 1.0) > 0.02:
            sz = max(40, int(base_logo * scale))
            logo_a = pygame.transform.smoothscale(logo_a, (sz, sz))
            logo_b = pygame.transform.smoothscale(logo_b, (sz, sz))
        surface.blit(logo_a, logo_a.get_rect(center=(left_panel.centerx, left_panel.y + 150)))
        surface.blit(logo_b, logo_b.get_rect(center=(right_panel.centerx, right_panel.y + 150)))

        # ═══ 8. Takım isimleri (büyük font) ═══
        na = self._fit_text(self.hook_team_font, team_a["name"], panel_w - 40, (245, 247, 252))
        nb = self._fit_text(self.hook_team_font, team_b["name"], panel_w - 40, (245, 247, 252))
        na.set_alpha(int(255 * ca))
        nb.set_alpha(int(255 * ca))
        surface.blit(na, na.get_rect(center=(left_panel.centerx, left_panel.y + 310)))
        surface.blit(nb, nb.get_rect(center=(right_panel.centerx, right_panel.y + 310)))

        # TEAM A / TEAM B etiketleri
        tag_a = self.micro_font.render("TEAM A", True, color_a)
        tag_b = self.micro_font.render("TEAM B", True, color_b)
        tag_a_bg = pygame.Rect(0, 0, tag_a.get_width() + 32, 32)
        tag_b_bg = pygame.Rect(0, 0, tag_b.get_width() + 32, 32)
        tag_a_bg.center = (left_panel.centerx, left_panel.y + 425)
        tag_b_bg.center = (right_panel.centerx, right_panel.y + 425)
        pygame.draw.rect(surface, (*color_a, int(40 * ca)), tag_a_bg, border_radius=16)
        pygame.draw.rect(surface, (*color_b, int(40 * ca)), tag_b_bg, border_radius=16)
        tag_a.set_alpha(int(255 * ca))
        tag_b.set_alpha(int(255 * ca))
        surface.blit(tag_a, tag_a.get_rect(center=tag_a_bg.center))
        surface.blit(tag_b, tag_b.get_rect(center=tag_b_bg.center))

        # ═══ 9. VS rozeti (büyük, parlamalı) ═══
        vs_y = left_panel.y + 150
        vr = max(36, int(55 * scale))
        vs_s = pygame.Surface((vr * 4, vr * 4), pygame.SRCALPHA)
        vc = vr * 2
        pygame.draw.circle(vs_s, (255, 228, 128, int(55 * gi)), (vc, vc), int(vr * 1.5))
        pygame.draw.circle(vs_s, (20, 28, 44, 240), (vc, vc), vr)
        pygame.draw.circle(vs_s, (255, 228, 128, int(220 * ca)), (vc, vc), vr, width=3)
        surface.blit(vs_s, vs_s.get_rect(center=(cx, vs_y)))
        vs_t = self.hook_vs_font.render("VS", True, (255, 228, 128))
        vs_t.set_alpha(int(255 * ca))
        surface.blit(vs_t, vs_t.get_rect(center=(cx, vs_y)))

        # ═══ 10. "Match is starting..." ═══
        dots = "." * (1 + int(progress * 3) % 4)
        starting = self.info_font.render(f"Match is starting{dots}", True, (130, 145, 175))
        starting.set_alpha(int(255 * ca))
        surface.blit(starting, starting.get_rect(center=(cx, left_panel.bottom + 60)))

    # ── Hook overlay yardımcı metodları ──────────────────────────────

    def _hook_anim_values(self, progress: float) -> dict:
        """0.0-0.3 giriş, 0.3-0.8 doruk (peak@0.5), 0.8-1.0 çıkış."""
        if progress < 0.3:
            t = progress / 0.3
            e = self._ease_out_back(t)
            return {"scale": 0.3 + 0.7 * e, "alpha": min(1.0, t * 1.5), "glow_intensity": t}
        if progress <= 0.8:
            gp = 1.0 - abs(progress - 0.5) * 2.5
            return {"scale": 1.0, "alpha": 1.0, "glow_intensity": 0.72 + 0.28 * max(0.0, gp)}
        t = (progress - 0.8) / 0.2
        return {"scale": 1.0 - 0.12 * t, "alpha": 1.0 - 0.25 * t, "glow_intensity": 1.0 - 0.4 * t}

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
        for i in range(5):
            t = i / 5
            r = int(radius * (1.0 - t * 0.55))
            a = int(intensity * 40 * (1.0 - t))
            if a > 0:
                pygame.draw.circle(glow, (*color, min(255, a)), (radius, radius), r)
        surface.blit(glow, (cx - radius, cy - radius))

    def _init_hook_sparks(self) -> None:
        rng = random.Random(42)
        w, h = self.cfg.video.width, self.cfg.video.height
        palette = [
            (255, 228, 128), (255, 255, 255), (200, 215, 255),
            (255, 180, 100), (180, 200, 255), (255, 200, 150),
        ]
        self._hook_sparks = []
        for _ in range(70):
            self._hook_sparks.append({
                "x": rng.uniform(0, w), "base_y": rng.uniform(60, h - 40),
                "size": rng.uniform(2, 5), "alpha_base": rng.randint(80, 200),
                "vy": rng.uniform(-60, -180), "vx": rng.uniform(-20, 20),
                "phase": rng.uniform(0, math.tau), "color": rng.choice(palette),
            })
        self._hook_sparks_ready = True

    def _draw_hook_sparks(self, surface: pygame.Surface, progress: float, alpha_mult: float) -> None:
        if not self._hook_sparks_ready:
            self._init_hook_sparks()
        h = self.cfg.video.height
        for sp in self._hook_sparks:
            dx = math.sin(progress * math.tau + sp["phase"]) * 14
            x = sp["x"] + dx + sp["vx"] * progress
            y = (sp["base_y"] + sp["vy"] * progress) % h
            twinkle = 0.5 + 0.5 * math.sin(progress * 8.0 + sp["phase"])
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

        goal_text = self.goal_font.render("GOAL!", True, (255, 255, 255))
        goal_rect = goal_text.get_rect(center=(self.cfg.video.width // 2, 118))
        burst.blit(goal_text, goal_rect)

        sub_text = self.goal_sub_font.render(self.goal_flash_event["team_name"], True, (245, 248, 255))
        sub_rect = sub_text.get_rect(center=(self.cfg.video.width // 2, 175))
        burst.blit(sub_text, sub_rect)

        surface.blit(burst, (0, 370))

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
        image.thumbnail((size - 10, size - 10), Image.Resampling.LANCZOS)
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
            if event.get("gap_label") == "GOAL":
                team_color = self._get_team_color_from_name(snapshot, str(event.get("team_name", "")))
                self.goal_flash_timer = 0.95
                self.goal_flash_event = {
                    "team_name": str(event.get("team_name", "GOAL")),
                    "color": team_color,
                }
                self._spawn_confetti(team_color)

        if self.goal_flash_timer > 0.0:
            self.goal_flash_timer = max(0.0, self.goal_flash_timer - (1.0 / self.cfg.video.fps))

    def _iter_peg_centers(self) -> Iterable[Tuple[float, float]]:
        spacing_x = self.cfg.layout.peg_spacing_x
        spacing_y = self.cfg.layout.peg_spacing_y
        rows = self.cfg.layout.peg_rows
        top_y = self.cfg.layout.peg_top_y
        peg_radius = self.cfg.physics.peg_radius
        margin = peg_radius + 8

        left_wall = self.cfg.playfield_left + margin
        right_wall = self.cfg.playfield_right - margin
        cx = (self.cfg.playfield_left + self.cfg.playfield_right) / 2.0
        ramp_clearance_y = self.cfg.layout.floor_y - 280

        usable = right_wall - left_wall
        cols_even = max(1, int(usable // spacing_x))
        total_even = cols_even * spacing_x
        start_even = cx - total_even / 2.0

        for row in range(2, rows):
            y = top_y + row * spacing_y
            if y > ramp_clearance_y:
                break

            if row % 2 == 0:
                for col in range(cols_even + 1):
                    x = start_even + col * spacing_x
                    if left_wall <= x <= right_wall:
                        yield x, y
            else:
                for col in range(cols_even):
                    x = start_even + spacing_x / 2 + col * spacing_x
                    if left_wall <= x <= right_wall:
                        yield x, y

    def _build_gap_draw_data_from_cfg(self) -> List[dict]:
        cx = self.cfg.playfield_center_x
        side_gap_w = self.cfg.layout.side_gap_width
        goal_gap_w = self.cfg.layout.goal_gap_width
        divider_w = self.cfg.layout.divider_width

        total_span = side_gap_w + divider_w + goal_gap_w + divider_w + side_gap_w
        left_start = cx - total_span / 2

        left_gap = {
            "label": self.cfg.gameplay.left_gap_label,
            "start_x": left_start,
            "end_x": left_start + side_gap_w,
        }
        left_gap["center_x"] = (left_gap["start_x"] + left_gap["end_x"]) / 2

        center_gap = {
            "label": self.cfg.gameplay.center_gap_label,
            "start_x": left_gap["end_x"] + divider_w,
            "end_x": left_gap["end_x"] + divider_w + goal_gap_w,
        }
        center_gap["center_x"] = (center_gap["start_x"] + center_gap["end_x"]) / 2

        right_gap = {
            "label": self.cfg.gameplay.right_gap_label,
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
