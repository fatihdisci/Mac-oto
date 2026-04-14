from __future__ import annotations

import colorsys
import math
import random
from pathlib import Path
from typing import Any

import pygame
from PIL import Image, ImageFilter

from config import SimulationConfig


class GrandPrixRenderer:
    def __init__(self, cfg: SimulationConfig) -> None:
        self.cfg = cfg
        pygame.font.init()
        self.title_font = pygame.font.SysFont("arial", 34, bold=True)
        self.section_font = pygame.font.SysFont("arial", 28, bold=True)
        self.team_font = pygame.font.SysFont("arial", 24, bold=True)
        self.info_font = pygame.font.SysFont("arial", 22, bold=False)
        self.micro_font = pygame.font.SysFont("arial", 18, bold=True)
        self.overlay_font = pygame.font.SysFont("arial", 72, bold=True)
        self.overlay_sub_font = pygame.font.SysFont("arial", 34, bold=True)
        self.logo_cache: dict[str, pygame.Surface] = {}
        
        self._spawned_spark_keys: set[tuple] = set()
        self._impact_particles: list[dict] = []

    def draw(self, surface: pygame.Surface, snapshot: dict[str, Any]) -> None:
        dt = 1.0 / self.cfg.video.fps
        self._update_impact_particles(snapshot, dt)
        
        surface.fill((13, 18, 29))
        self._draw_background_accents(surface)
        self._draw_board(surface, snapshot)
        self._draw_side_panel(surface, snapshot)
        self._draw_active_balls(surface, snapshot)
        self._draw_impact_particles(surface)
        
        if bool(snapshot.get("show_intro_overlay", False)):
            self._draw_intro_overlay(surface, snapshot)
        if bool(snapshot.get("show_final_overlay", False)):
            self._draw_final_overlay(surface, snapshot)

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
        alive: list[dict] = []
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

    def _draw_background_accents(self, surface: pygame.Surface) -> None:
        glow = pygame.Surface(surface.get_size(), pygame.SRCALPHA)
        pygame.draw.circle(glow, (34, 88, 181, 55), (260, 130), 210)
        pygame.draw.circle(glow, (213, 118, 42, 40), (1650, 920), 260)
        pygame.draw.circle(glow, (255, 255, 255, 16), (1020, 540), 360, width=1)
        surface.blit(glow, (0, 0))

    def _draw_board(self, surface: pygame.Surface, snapshot: dict[str, Any]) -> None:
        board = snapshot.get("board_rect", {})
        board_rect = pygame.Rect(
            int(board.get("x", 40)),
            int(board.get("y", 40)),
            int(board.get("width", 1220)),
            int(board.get("height", 980)),
        )
        self._draw_glass_panel(surface, board_rect, (20, 26, 38, 215), (226, 233, 246, 210), 26)

        # Sol üst dinamik turnuva ismi
        raw_title = snapshot.get("title")
        if not raw_title or str(raw_title).strip() == "":
            raw_title = "GRAND PRIX"
        
        title_text = str(raw_title).upper()
        title = self.title_font.render(title_text, True, (241, 245, 251))
        surface.blit(title, (board_rect.x + 24, board_rect.y + 18))

        peg_layer = pygame.Surface((board_rect.width, board_rect.height), pygame.SRCALPHA)
        peg_radius = max(6, int(snapshot.get("peg_radius", 7)))
        for x, y in snapshot.get("peg_positions", []):
            local_x = int(x) - board_rect.x
            local_y = int(y) - board_rect.y
            pygame.draw.circle(peg_layer, (14, 18, 28, 255), (local_x + 2, local_y + 3), peg_radius)
            pygame.draw.circle(peg_layer, (196, 204, 220, 255), (local_x, local_y), peg_radius)
        surface.blit(peg_layer, board_rect.topleft)

        for item in snapshot.get("hole_values", []):
            rect = item.get("rect", {})
            slot_rect = pygame.Rect(
                int(rect.get("x", 0)),
                int(rect.get("y", 0)),
                int(rect.get("width", 0)),
                int(rect.get("height", 0)),
            )
            if slot_rect.width < 10 or slot_rect.height < 10:
                continue

            points = int(item.get("points", 0))
            fill = (40, 54, 78)
            if points < 0:
                fill = (118, 46, 54)
            elif points == 0:
                fill = (86, 92, 108)
            elif points >= 7:
                fill = (28, 114, 78)
            elif points >= 3:
                fill = (42, 90, 145)

            pit_poly = [
                (slot_rect.left, slot_rect.top),
                (slot_rect.right, slot_rect.top),
                (slot_rect.right - 8, slot_rect.bottom),
                (slot_rect.left + 8, slot_rect.bottom),
            ]
            pygame.draw.polygon(surface, fill, pit_poly)
            pygame.draw.polygon(surface, (232, 238, 248), pit_poly, width=2)
            pygame.draw.line(
                surface,
                (245, 248, 252),
                (slot_rect.left, slot_rect.top),
                (slot_rect.right, slot_rect.top),
                3,
            )

            label = f"{points:+d}"
            font = self.info_font if slot_rect.width < 76 else self.section_font
            text = font.render(label, True, (246, 248, 252))
            text_rect = text.get_rect(center=(slot_rect.centerx, slot_rect.centery - 2))
            surface.blit(text, text_rect)

        round_label = self.section_font.render(
            f"ROUND {int(snapshot.get('current_round', 0))} / {int(snapshot.get('round_count', 0))}",
            True,
            (248, 249, 252),
        )
        surface.blit(round_label, (board_rect.x + 24, board_rect.bottom - 58))

    def _draw_side_panel(self, surface: pygame.Surface, snapshot: dict[str, Any]) -> None:
        panel = snapshot.get("side_panel_rect", {})
        panel_rect = pygame.Rect(
            int(panel.get("x", 1286)),
            int(panel.get("y", 46)),
            int(panel.get("width", 596)),
            int(panel.get("height", 988)),
        )
        self._draw_glass_panel(surface, panel_rect, (16, 21, 32, 225), (164, 188, 230, 200), 24)

        standings_title = self.section_font.render("STANDINGS", True, (245, 247, 251))
        surface.blit(standings_title, (panel_rect.x + 24, panel_rect.y + 22))

        standings = list(snapshot.get("standings", []))
        team_count = len(standings)
        start_y = panel_rect.y + 72

        is_vertical = bool(snapshot.get("is_vertical", False))

        # Takım sayısına göre layout parametreleri
        if is_vertical:
            if team_count <= 8:
                row_h, logo_size = 42, 28
                name_font, pts_font = self.info_font, self.info_font
                columns, show_round_result = 2, False
            else: # 16 or 32 takim
                row_h, logo_size = 34, 22
                name_font, pts_font = self.micro_font, self.micro_font
                columns, show_round_result = 4, False
        else:
            if team_count <= 4:
                row_h, logo_size = 66, 38
                name_font, pts_font = self.team_font, self.team_font
                columns, show_round_result = 1, True
            elif team_count <= 8:
                row_h, logo_size = 54, 32
                name_font, pts_font = self.team_font, self.team_font
                columns, show_round_result = 1, True
            elif team_count <= 16:
                row_h, logo_size = 40, 26
                name_font, pts_font = self.info_font, self.info_font
                columns, show_round_result = 1, False
            else:  # 32 takım: iki sütun
                row_h, logo_size = 38, 22
                name_font, pts_font = self.micro_font, self.micro_font
                columns, show_round_result = 2, False

        import math
        if columns > 1:
            per_col = math.ceil(team_count / columns)
            col_w = (panel_rect.width - 24) // columns
            for col_idx in range(columns):
                col_x = panel_rect.x + col_idx * (col_w + 8) + 8
                col_rows = standings[col_idx * per_col: (col_idx + 1) * per_col]
                for row_idx, row in enumerate(col_rows):
                    rr = pygame.Rect(col_x, start_y + row_idx * row_h, col_w, row_h - 3)
                    pygame.draw.rect(surface, (25, 33, 48, 210 if row_idx % 2 == 0 else 170), rr, border_radius=10)
                    cy = rr.y + rr.height // 2
                    rank_s = pts_font.render(f"{int(row.get('rank', 1))}.", True, (255, 255, 255))
                    surface.blit(rank_s, (rr.x + 4, cy - rank_s.get_height() // 2))
                    logo = self._get_logo_surface(str(row.get("name", "")), str(row.get("badge_file", "")), logo_size)
                    logo_cx = rr.x + 34 + logo_size // 2
                    surface.blit(logo, logo.get_rect(center=(logo_cx, cy)))
                    name_surf = self._fit_text(name_font, self._display_name(row), col_w - logo_size - 58, (240, 244, 251))
                    surface.blit(name_surf, (rr.x + 38 + logo_size, cy - name_surf.get_height() // 2))
                    pts_s = pts_font.render(f"{int(row.get('points', 0))}p", True, (158, 232, 182))
                    surface.blit(pts_s, pts_s.get_rect(topright=(rr.right - 4, cy - pts_s.get_height() // 2)))
        else:
            for index, row in enumerate(standings):
                rr = pygame.Rect(panel_rect.x + 18, start_y + index * row_h, panel_rect.width - 36, row_h - 4)
                pygame.draw.rect(surface, (25, 33, 48, 210 if index % 2 == 0 else 170), rr, border_radius=16)
                cy = rr.y + rr.height // 2
                rank_s = name_font.render(f"{int(row.get('rank', index + 1))}.", True, (255, 255, 255))
                surface.blit(rank_s, (rr.x + 12, cy - rank_s.get_height() // 2))
                logo = self._get_logo_surface(str(row.get("name", "")), str(row.get("badge_file", "")), logo_size)
                surface.blit(logo, logo.get_rect(center=(rr.x + 44 + logo_size // 2, cy)))
                name_surf = self._fit_text(name_font, self._display_name(row), panel_rect.width - 36 - logo_size - 124, (240, 244, 251))
                surface.blit(name_surf, (rr.x + 50 + logo_size, cy - name_surf.get_height() // 2))
                pts_s = pts_font.render(f"{int(row.get('points', 0))}p", True, (158, 232, 182))
                surface.blit(pts_s, pts_s.get_rect(topright=(rr.right - 14, cy - pts_s.get_height() // 2)))

        if not show_round_result:
            return

        summary_y = start_y + team_count * row_h + 24
        summary_title = self.section_font.render("ROUND RESULT", True, (245, 247, 251))
        surface.blit(summary_title, (panel_rect.x + 24, summary_y))
        latest_results = list(snapshot.get("latest_completed_round_results", []))
        if not latest_results:
            waiting = self.info_font.render("Result table will fill after round 1.", True, (169, 180, 204))
            surface.blit(waiting, (panel_rect.x + 24, summary_y + 42))
            return

        sorted_results = sorted(
            latest_results,
            key=lambda row: (-int(row.get("points", 0)), -int(row.get("total_points", 0)), str(row.get("team_name", "")).lower()),
        )
        result_row_h = 44 if team_count <= 4 else 36
        for index, row in enumerate(sorted_results):
            line_y = summary_y + 48 + index * result_row_h
            if line_y + result_row_h > panel_rect.bottom - 8:
                break
            logo = self._get_logo_surface(str(row.get("team_name", "")), str(row.get("badge_file", "")), 28)
            surface.blit(logo, logo.get_rect(center=(panel_rect.x + 38, line_y + 10)))
            name = self._fit_text(self.info_font, str(row.get("short_name") or row.get("team_name") or ""), 180, (235, 239, 246))
            surface.blit(name, (panel_rect.x + 58, line_y))
            # Hx (slot index) metni kaldırıldı
            delta = self.info_font.render(f"{int(row.get('points', 0)):+d}", True, self._points_color(int(row.get("points", 0))))
            surface.blit(delta, delta.get_rect(topright=(panel_rect.x + 372, line_y)))
            total = self.info_font.render(f"{int(row.get('total_points', 0))}p", True, (240, 244, 251))
            surface.blit(total, total.get_rect(topright=(panel_rect.right - 18, line_y)))

    def _draw_active_balls(self, surface: pygame.Surface, snapshot: dict[str, Any]) -> None:
        for ball in snapshot.get("active_balls", []):
            x = int(ball.get("x", 0))
            y = int(ball.get("y", 0))
            radius = max(12, int(ball.get("radius", 18)))
            color = self._team_color(int(ball.get("color_seed", 0)))
            shadow = pygame.Surface((radius * 3, radius * 3), pygame.SRCALPHA)
            pygame.draw.circle(shadow, (0, 0, 0, 90), (shadow.get_width() // 2, shadow.get_height() // 2), radius)
            surface.blit(shadow, shadow.get_rect(center=(x + 4, y + 6)))
            pygame.draw.circle(surface, color, (x, y), radius)
            pygame.draw.circle(surface, (244, 247, 252), (x, y), radius, width=2)
            logo = self._get_logo_surface(str(ball.get("team_name", "")), str(ball.get("badge_file", "")), radius * 2)
            surface.blit(logo, logo.get_rect(center=(x, y)))

    def _draw_final_overlay(self, surface: pygame.Surface, snapshot: dict[str, Any]) -> None:
        panel = pygame.Surface(surface.get_size(), pygame.SRCALPHA)
        panel.fill((8, 12, 20, 132))
        surface.blit(panel, (0, 0))

        box_w = 980
        box_h = 300
        box_rect = pygame.Rect(
            (surface.get_width() - box_w) // 2,
            (surface.get_height() - box_h) // 2 - 20,
            box_w,
            box_h,
        )
        glow = pygame.Surface((box_rect.width + 60, box_rect.height + 60), pygame.SRCALPHA)
        pygame.draw.rect(glow, (255, 214, 132, 44), glow.get_rect(), border_radius=36)
        surface.blit(glow, (box_rect.x - 30, box_rect.y - 30))
        pygame.draw.rect(surface, (15, 24, 40), box_rect, border_radius=26)
        pygame.draw.rect(surface, (255, 223, 149), box_rect, width=3, border_radius=26)

        champion = str(snapshot.get("champion_name", "Champion"))
        title = self.overlay_font.render("CHAMPION", True, (255, 244, 194))
        sub = self.overlay_sub_font.render(champion, True, (248, 249, 252))
        surface.blit(title, title.get_rect(center=(box_rect.centerx, box_rect.y + 108)))
        surface.blit(sub, sub.get_rect(center=(box_rect.centerx, box_rect.y + 194)))

    def _draw_intro_overlay(self, surface: pygame.Surface, snapshot: dict[str, Any]) -> None:
        panel = pygame.Surface(surface.get_size(), pygame.SRCALPHA)
        panel.fill((6, 10, 20, 128))
        surface.blit(panel, (0, 0))

        display_title = snapshot.get('title')
        if not display_title or str(display_title).strip() == "":
            display_title = "Grand Prix"

        w, h = surface.get_width(), surface.get_height()
        cx = w // 2

        intro_str = f"{display_title}".upper()
        # Draw shadow
        title_shadow = self.overlay_font.render(intro_str, True, (0, 0, 0))
        shadow_rect = title_shadow.get_rect(center=(cx + 4, h // 2 - 316))
        surface.blit(title_shadow, shadow_rect)
        
        # Draw main title
        title = self.overlay_font.render(intro_str, True, (255, 230, 100))
        title_rect = title.get_rect(center=(cx, h // 2 - 320))
        surface.blit(title, title_rect)

        # Teams grid
        teams = snapshot.get("teams", [])
        num_teams = len(teams)
        
        intro_rem = float(snapshot.get("intro_remaining", 3.5))
        intro_dur = float(snapshot.get("intro_duration", 3.5))
        elapsed = max(0.0, intro_dur - intro_rem)
        
        if num_teams > 0:
            import math
            cols = 4 if num_teams >= 4 else 2
            rows = math.ceil(num_teams / cols)
            
            logo_size = 120 if num_teams > 8 else 160
            gap_x = logo_size + 40
            gap_y = logo_size + 60
            
            start_x = cx - (cols - 1) * gap_x // 2
            start_y = h // 2 - (rows - 1) * gap_y // 2 - 20
            
            for idx, team in enumerate(teams):
                delay = idx * 0.15
                if elapsed < delay:
                    continue
                    
                anim_p = min(1.0, (elapsed - delay) / 0.4)
                anim_p = 1.0 - (1.0 - anim_p) ** 3  # ease out cubic
                
                r = idx // cols
                c = idx % cols
                tx = start_x + c * gap_x
                ty = start_y + r * gap_y
                
                logo = self._get_logo_surface(team["name"], team.get("badge_file", ""), logo_size)
                
                alpha = int(255 * anim_p)
                s = max(0.01, anim_p)
                if abs(s - 1.0) > 0.01:
                    scaled_logo = pygame.transform.smoothscale(logo, (int(logo_size * s), int(logo_size * s)))
                else:
                    scaled_logo = logo
                scaled_logo.set_alpha(alpha)
                
                surface.blit(scaled_logo, scaled_logo.get_rect(center=(tx, ty)))

        # Countdown with pulse
        countdown_num = int(math.ceil(intro_rem))
        pulse = intro_rem - math.floor(intro_rem) # goes from 1.0 to 0.0
        
        # Scale and alpha for pulse effect
        scale = 1.0 + 0.5 * pulse
        alpha = int(120 + 135 * pulse)
        
        countdown_text = self.overlay_font.render(str(max(1, countdown_num)), True, (248, 249, 252))
        cw, ch = countdown_text.get_width(), countdown_text.get_height()
        scaled_cw = max(1, int(cw * scale))
        scaled_ch = max(1, int(ch * scale))
        
        if abs(scale - 1.0) > 0.01:
            scaled_cd = pygame.transform.smoothscale(countdown_text, (scaled_cw, scaled_ch))
        else:
            scaled_cd = countdown_text
            
        scaled_cd.set_alpha(alpha)
        surface.blit(scaled_cd, scaled_cd.get_rect(center=(cx, h // 2 + 280)))

    def _draw_glass_panel(
        self,
        surface: pygame.Surface,
        rect: pygame.Rect,
        fill_rgba: tuple[int, int, int, int],
        border_rgba: tuple[int, int, int, int],
        radius: int,
    ) -> None:
        panel = pygame.Surface((rect.width, rect.height), pygame.SRCALPHA)
        pygame.draw.rect(panel, fill_rgba, pygame.Rect(0, 0, rect.width, rect.height), border_radius=radius)
        pygame.draw.rect(panel, border_rgba, pygame.Rect(0, 0, rect.width, rect.height), width=2, border_radius=radius)
        surface.blit(panel, rect.topleft)

    def _fit_text(
        self,
        font: pygame.font.Font,
        text: str,
        max_width: int,
        color: tuple[int, int, int],
    ) -> pygame.Surface:
        if font.size(text)[0] <= max_width:
            return font.render(text, True, color)
        trimmed = text
        while trimmed and font.size(trimmed + "...")[0] > max_width:
            trimmed = trimmed[:-1]
        return font.render((trimmed + "...") if trimmed else text[:1], True, color)

    def _get_logo_surface(self, team_name: str, badge_file: str, diameter: int) -> pygame.Surface:
        cache_key = f"{badge_file}|{diameter}"
        cached = self.logo_cache.get(cache_key)
        if cached is not None:
            return cached

        logo_path = self.cfg.data_dir / "logos" / badge_file
        try:
            surface = self._load_logo_surface(logo_path, diameter)
        except Exception:
            surface = self._build_placeholder_logo(team_name, diameter)
        self.logo_cache[cache_key] = surface
        return surface

    def _load_logo_surface(self, path: Path, size: int) -> pygame.Surface:
        if not path.exists():
            raise FileNotFoundError(path)
        image = Image.open(path).convert("RGBA")
        image.thumbnail((size, size), Image.Resampling.LANCZOS)
        image = image.filter(ImageFilter.UnsharpMask(radius=1.2, percent=160, threshold=2))
        canvas = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        canvas.paste(image, ((size - image.width) // 2, (size - image.height) // 2), image)
        surface = pygame.image.fromstring(canvas.tobytes(), canvas.size, canvas.mode).convert_alpha()
        mask = pygame.Surface((size, size), pygame.SRCALPHA)
        pygame.draw.circle(mask, (255, 255, 255, 255), (size // 2, size // 2), size // 2)
        cropped = pygame.Surface((size, size), pygame.SRCALPHA)
        cropped.blit(surface, (0, 0))
        cropped.blit(mask, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
        pygame.draw.circle(cropped, (247, 249, 252, 220), (size // 2, size // 2), size // 2, width=2)
        return cropped

    def _build_placeholder_logo(self, team_name: str, size: int) -> pygame.Surface:
        surf = pygame.Surface((size, size), pygame.SRCALPHA)
        center = (size // 2, size // 2)
        pygame.draw.circle(surf, (47, 57, 72), center, max(2, size // 2 - 2))
        pygame.draw.circle(surf, (244, 247, 252), center, max(2, size // 2 - 2), width=2)
        initials = "".join(word[:1] for word in str(team_name).split()[:2]).upper()[:2] or "TM"
        font = pygame.font.SysFont("arial", max(14, size // 3), bold=True)
        text = font.render(initials, True, (244, 247, 252))
        surf.blit(text, text.get_rect(center=center))
        return surf

    @staticmethod
    def _display_name(row: dict[str, Any]) -> str:
        short_name = str(row.get("short_name") or "").strip()
        full_name = str(row.get("name") or "").strip()
        if short_name and len(full_name) > 16:
            return short_name
        return full_name or short_name or "TEAM"

    @staticmethod
    def _points_color(points: int) -> tuple[int, int, int]:
        if points < 0:
            return (255, 138, 138)
        if points == 0:
            return (201, 209, 227)
        if points >= 7:
            return (150, 240, 176)
        return (168, 212, 255)

    @staticmethod
    def _team_color(seed_value: int) -> tuple[int, int, int]:
        hue = (int(seed_value) % 360) / 360.0
        r, g, b = colorsys.hsv_to_rgb(hue, 0.42, 0.92)
        return (int(r * 255), int(g * 255), int(b * 255))
