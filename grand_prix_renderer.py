from __future__ import annotations

import colorsys
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

    def draw(self, surface: pygame.Surface, snapshot: dict[str, Any]) -> None:
        surface.fill((13, 18, 29))
        self._draw_background_accents(surface)
        self._draw_board(surface, snapshot)
        self._draw_side_panel(surface, snapshot)
        self._draw_active_balls(surface, snapshot)
        if bool(snapshot.get("show_final_overlay", False)):
            self._draw_final_overlay(surface, snapshot)

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

        title = self.title_font.render("GRAND PRIX ARENA", True, (241, 245, 251))
        surface.blit(title, (board_rect.x + 24, board_rect.y + 18))

        subtitle = self.info_font.render(str(snapshot.get("title", "Grand Prix")), True, (167, 183, 212))
        surface.blit(subtitle, (board_rect.x + 24, board_rect.y + 58))

        peg_layer = pygame.Surface((board_rect.width, board_rect.height), pygame.SRCALPHA)
        for x, y in snapshot.get("peg_positions", []):
            local_x = int(x) - board_rect.x
            local_y = int(y) - board_rect.y
            pygame.draw.circle(peg_layer, (14, 18, 28, 255), (local_x + 2, local_y + 3), 7)
            pygame.draw.circle(peg_layer, (196, 204, 220, 255), (local_x, local_y), 7)
        surface.blit(peg_layer, board_rect.topleft)

        for item in snapshot.get("hole_values", []):
            rect = item.get("rect", {})
            slot_rect = pygame.Rect(
                int(rect.get("x", 0)),
                int(rect.get("y", 0)),
                int(rect.get("width", 0)),
                int(rect.get("height", 0)),
            )
            points = int(item.get("points", 0))
            fill = (41, 57, 82)
            if points < 0:
                fill = (101, 42, 48)
            elif points == 0:
                fill = (78, 84, 98)
            elif points >= 7:
                fill = (31, 106, 75)
            elif points >= 3:
                fill = (45, 86, 138)
            pygame.draw.rect(surface, fill, slot_rect, border_radius=18)
            pygame.draw.rect(surface, (231, 236, 246), slot_rect, width=2, border_radius=18)
            label = f"{points:+d}"
            text = self.section_font.render(label, True, (246, 248, 252))
            text_rect = text.get_rect(center=(slot_rect.centerx, slot_rect.centery - 8))
            surface.blit(text, text_rect)
            hole_text = self.micro_font.render(f"H{int(item.get('slot_index', 0)) + 1}", True, (205, 214, 232))
            surface.blit(hole_text, hole_text.get_rect(center=(slot_rect.centerx, slot_rect.bottom - 18)))

        round_label = self.section_font.render(
            f"ROUND {int(snapshot.get('current_round', 0))} / {int(snapshot.get('round_count', 0))}",
            True,
            (248, 249, 252),
        )
        surface.blit(round_label, (board_rect.x + 24, board_rect.bottom - 58))
        status_label = self.info_font.render(str(snapshot.get("round_status_text", "Round live")), True, (164, 206, 255))
        surface.blit(status_label, (board_rect.x + 360, board_rect.bottom - 52))

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
        start_y = panel_rect.y + 72
        row_h = 66 if len(standings) <= 4 else 58
        for index, row in enumerate(standings):
            row_rect = pygame.Rect(panel_rect.x + 18, start_y + index * row_h, panel_rect.width - 36, row_h - 8)
            band_fill = (25, 33, 48, 210 if index % 2 == 0 else 170)
            pygame.draw.rect(surface, band_fill, row_rect, border_radius=16)
            rank = self.team_font.render(f"{int(row.get('rank', index + 1))}.", True, (255, 255, 255))
            surface.blit(rank, (row_rect.x + 12, row_rect.y + 16))
            logo = self._get_logo_surface(str(row.get("name", "")), str(row.get("badge_file", "")), 38)
            surface.blit(logo, logo.get_rect(center=(row_rect.x + 62, row_rect.y + row_rect.height // 2)))
            name = self._fit_text(self.team_font, self._display_name(row), 280, (240, 244, 251))
            surface.blit(name, (row_rect.x + 90, row_rect.y + 15))
            points = self.team_font.render(f"{int(row.get('points', 0))}p", True, (158, 232, 182))
            surface.blit(points, points.get_rect(topright=(row_rect.right - 14, row_rect.y + 15)))

        summary_title = self.section_font.render("ROUND RESULT", True, (245, 247, 251))
        summary_y = panel_rect.y + 420 if len(standings) <= 4 else panel_rect.y + 540
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
        for index, row in enumerate(sorted_results):
            line_y = summary_y + 48 + index * 44
            logo = self._get_logo_surface(str(row.get("team_name", "")), str(row.get("badge_file", "")), 28)
            surface.blit(logo, logo.get_rect(center=(panel_rect.x + 38, line_y + 10)))
            name = self._fit_text(self.info_font, str(row.get("short_name") or row.get("team_name") or ""), 180, (235, 239, 246))
            surface.blit(name, (panel_rect.x + 58, line_y))
            slot = self.micro_font.render(f"H{int(row.get('slot_index', 0)) + 1}", True, (160, 192, 232))
            surface.blit(slot, (panel_rect.x + 268, line_y + 5))
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
            logo = self._get_logo_surface(str(ball.get("team_name", "")), str(ball.get("badge_file", "")), radius * 2 - 4)
            surface.blit(logo, logo.get_rect(center=(x, y)))

    def _draw_final_overlay(self, surface: pygame.Surface, snapshot: dict[str, Any]) -> None:
        panel = pygame.Surface(surface.get_size(), pygame.SRCALPHA)
        panel.fill((8, 12, 20, 132))
        surface.blit(panel, (0, 0))
        champion = str(snapshot.get("champion_name", "Champion"))
        title = self.overlay_font.render("CHAMPION", True, (255, 244, 194))
        sub = self.overlay_sub_font.render(champion, True, (248, 249, 252))
        surface.blit(title, title.get_rect(center=(surface.get_width() // 2, 420)))
        surface.blit(sub, sub.get_rect(center=(surface.get_width() // 2, 500)))

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
        image.thumbnail((size - 8, size - 8), Image.Resampling.LANCZOS)
        image = image.filter(ImageFilter.UnsharpMask(radius=1.2, percent=160, threshold=2))
        canvas = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        canvas.paste(image, ((size - image.width) // 2, (size - image.height) // 2), image)
        surface = pygame.image.fromstring(canvas.tobytes(), canvas.size, canvas.mode).convert_alpha()
        mask = pygame.Surface((size, size), pygame.SRCALPHA)
        pygame.draw.circle(mask, (255, 255, 255, 255), (size // 2, size // 2), max(2, size // 2 - 2))
        cropped = pygame.Surface((size, size), pygame.SRCALPHA)
        cropped.blit(surface, (0, 0))
        cropped.blit(mask, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
        pygame.draw.circle(cropped, (247, 249, 252, 220), (size // 2, size // 2), max(2, size // 2 - 2), width=2)
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
