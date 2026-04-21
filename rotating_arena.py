import os
import math
import random
import subprocess
from pathlib import Path
from dataclasses import dataclass
from typing import Dict, List, Tuple, Any

import pygame
import pymunk
from PIL import Image, ImageFilter

from video_writer import Mp4VideoWriter
from audio_mixer import mix_audio_into_video

def _normalize_triplet(a: float, d: float, b: float) -> Tuple[float, float, float]:
    total = max(1e-9, float(a) + float(d) + float(b))
    return (float(a) / total, float(d) / total, float(b) / total)

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

class RotatingArenaRenderer:
    def __init__(self, w: int, h: int, fps: int):
        self.w = w
        self.h = h
        self.fps = fps
        pygame.font.init()
        self.match_font = pygame.font.SysFont("arial", 32, bold=True)
        self.score_font = pygame.font.SysFont("arial", 72, bold=True)
        self.team_font = pygame.font.SysFont("arial", 26, bold=True)
        self.info_font = pygame.font.SysFont("arial", 28, bold=False)
        self.micro_font = pygame.font.SysFont("arial", 20, bold=True)
        self.clock_font = pygame.font.SysFont("arial", 52, bold=True)
        self.overlay_font = pygame.font.SysFont("arial", 84, bold=True)
        self.overlay_sub_font = pygame.font.SysFont("arial", 52, bold=True)
        self.goal_font = pygame.font.SysFont("arial", 98, bold=True)
        self.goal_sub_font = pygame.font.SysFont("arial", 34, bold=True)
        self.hook_mega_font = pygame.font.SysFont("arial", 108, bold=True)
        self.hook_team_font = pygame.font.SysFont("arial", 52, bold=True)
        self.hook_vs_font = pygame.font.SysFont("arial", 68, bold=True)
        self.result_font = pygame.font.SysFont("arial", 88, bold=True)
        self.result_team_font = pygame.font.SysFont("arial", 36, bold=True)

        self.logo_base_surfaces: Dict[str, pygame.Surface] = {}
        self.goal_flash_timer: float = 0.0
        self.goal_flash_event: dict | None = None
        self.confetti_particles: List[ConfettiParticle] = []
        self._confetti_rng = random.Random()
        self._hook_sparks: List[dict] = []
        self._hook_sparks_ready = False
        self._win_rate_rail_probs: Tuple[float, float, float] = (0.34, 0.32, 0.34)

    def _draw_glass_panel(self, surface: pygame.Surface, rect: pygame.Rect, fill_rgba: Tuple[int, int, int, int], border_rgba: Tuple[int, int, int, int], radius: int) -> None:
        panel = pygame.Surface((rect.width, rect.height), pygame.SRCALPHA)
        pygame.draw.rect(panel, fill_rgba, pygame.Rect(0, 0, rect.width, rect.height), border_radius=radius)
        pygame.draw.rect(panel, border_rgba, pygame.Rect(0, 0, rect.width, rect.height), width=2, border_radius=radius)
        surface.blit(panel, rect.topleft)

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

    def _load_logo_surface(self, path: Path, size: int) -> pygame.Surface:
        if not path.exists():
            raise FileNotFoundError(f"Logo bulunamadi: {path}")
        image = Image.open(path).convert("RGBA")
        bbox = image.getbbox()
        if bbox:
            image = image.crop(bbox)
        orig_w, orig_h = image.size
        aspect = orig_w / orig_h
        target_inner = size - 4 
        if 0.85 <= aspect <= 1.15:
            draw_w, draw_h = target_inner, target_inner
        elif aspect < 0.85:
            draw_h = target_inner
            draw_w = int(draw_h * aspect)
        else:
            draw_w = target_inner
            draw_h = int(draw_w / aspect)
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

    def _get_logo_surface(self, team_name: str, badge_file: str, diameter: int) -> pygame.Surface:
        cache_key = f"{badge_file}|{diameter}"
        cached = self.logo_base_surfaces.get(cache_key)
        if cached is not None:
            return cached
        # Ensure correct path to logos
        root = Path(__file__).resolve().parent
        logo_path = root / "data" / "logos" / badge_file
        try:
            surface = self._load_logo_surface(logo_path, diameter)
        except Exception:
            surface = self._build_placeholder_logo(team_name, diameter)
        self.logo_base_surfaces[cache_key] = surface
        return surface

    def _fit_text(self, font: pygame.font.Font, text: str, max_width: int, color: Tuple[int, int, int]) -> pygame.Surface:
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

    def _draw_win_rate_rail(self, surface: pygame.Surface, snapshot: dict, x: int, y: int, width: int) -> None:
        odds = snapshot.get("win_probabilities", {})
        try:
            p_a = float(odds.get("team_a", 0.0))
            p_d = float(odds.get("draw", 0.0))
            p_b = float(odds.get("team_b", 0.0))
        except (TypeError, ValueError):
            return

        p_a, p_d, p_b = _normalize_triplet(p_a, p_d, p_b)
        s_a, s_d, s_b = self._win_rate_rail_probs
        smooth = 0.16
        s_a += (p_a - s_a) * smooth
        s_d += (p_d - s_d) * smooth
        s_b += (p_b - s_b) * smooth
        s_a, s_d, s_b = _normalize_triplet(s_a, s_d, s_b)
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

    def _draw_ball_shadow(self, surface: pygame.Surface, x: float, y: float, radius: int) -> None:
        shadow_w = int(radius * 1.45)
        shadow_h = max(6, int(radius * 0.42))
        shadow = pygame.Surface((shadow_w * 2, shadow_h * 2), pygame.SRCALPHA)
        pygame.draw.ellipse(shadow, (6, 8, 12, 72), pygame.Rect(0, 0, shadow_w * 2, shadow_h * 2))
        rect = shadow.get_rect(center=(int(x), int(y + radius * 0.78)))
        surface.blit(shadow, rect)

    def _draw_ball(self, surface: pygame.Surface, ball: dict) -> None:
        team_name = ball["team_name"]
        badge_file = ball.get("team_badge_file", "")
        x = float(ball["x"])
        y = float(ball["y"])
        radius = int(ball["radius"])
        angle_radians = float(ball["angle_radians"])
        
        # Use diameter that matches radius * 2 but request higher resolution surface
        base_logo = self._get_logo_surface(team_name=team_name, badge_file=badge_file, diameter=radius * 4)
        self._draw_ball_shadow(surface, x, y, radius)
        
        angle_degrees = -math.degrees(angle_radians)
        # 0.5 scale means (radius * 4) * 0.5 = radius * 2. Perfect fit.
        rotated = pygame.transform.rotozoom(base_logo, angle_degrees, 0.5)
        rect = rotated.get_rect(center=(int(x), int(y)))
        surface.blit(rotated, rect)

    def _ease_out_back(self, t: float) -> float:
        c1 = 1.70158
        c3 = c1 + 1.0
        return 1.0 + c3 * (t - 1.0) ** 3 + c1 * (t - 1.0) ** 2

    def _hook_anim_values(self, progress: float) -> dict:
        p = max(0.0, min(1.0, progress))
        if p <= 0.3:
            t = p / 0.3
            e = self._ease_out_back(t)
            return {"scale": 0.3 + 0.7 * e, "alpha": t, "glow_intensity": min(1.0, 0.15 + t * 0.9)}
        if p <= 0.8:
            t = (p - 0.3) / 0.5
            pulse = 0.92 + 0.08 * math.sin(t * math.tau * 2.4)
            center_peak = max(0.0, 1.0 - abs(p - 0.5) / 0.2)
            return {"scale": 1.0, "alpha": 1.0, "glow_intensity": min(1.0, pulse + 0.07 * center_peak)}
        t = (p - 0.8) / 0.2
        smooth = t * t * (3.0 - 2.0 * t)
        fade = 1.0 - smooth
        return {"scale": 1.0 - 0.14 * smooth, "alpha": fade, "glow_intensity": fade * fade}

    def _init_hook_sparks(self) -> None:
        rng = random.Random(42)
        w, h = self.w, self.h
        palette = [(255, 228, 128), (255, 255, 255), (200, 215, 255), (255, 180, 100), (180, 200, 255), (255, 200, 150)]
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
        h = self.h
        for sp in self._hook_sparks:
            flow = max(0.0, progress + sp["start_shift"])
            x = sp["x"] + math.sin(progress * 9.0 + sp["phase"]) * sp["amp_x"] + sp["drift_x"] * flow
            y = h + 110 - flow * sp["rise"]
            if y < -35: continue
            twinkle = 0.5 + 0.5 * math.sin(progress * 15.0 + sp["phase"] * 1.3)
            a = int(sp["alpha_base"] * twinkle * alpha_mult)
            if a <= 0: continue
            sz = max(1, int(sp["size"]))
            dot = pygame.Surface((sz * 2, sz * 2), pygame.SRCALPHA)
            pygame.draw.circle(dot, (*sp["color"], min(255, a)), (sz, sz), sz)
            if sz > 2:
                pygame.draw.circle(dot, (255, 255, 255, min(255, int(a * 0.7))), (sz, sz), max(1, sz // 2))
            surface.blit(dot, (int(x) - sz, int(y) - sz))

    def _draw_hook_overlay(self, surface: pygame.Surface, snapshot: dict) -> None:
        teams = snapshot.get("teams", [])
        if len(teams) < 2: return
        w, h = self.w, self.h
        cx = w // 2
        progress = max(0.0, min(1.0, float(snapshot.get("hook_progress", 1.0))))
        anim = self._hook_anim_values(progress)
        scale = anim["scale"]
        content_alpha = max(0.0, min(1.0, anim["alpha"]))
        glow_intensity = max(0.0, min(1.0, anim["glow_intensity"]))
        team_a = next((team for team in teams if team.get("role") == "A"), teams[0])
        team_b = next((team for team in teams if team.get("role") == "B"), teams[1])
        color_a = team_a.get("color", (220, 72, 72))
        color_b = team_b.get("color", (79, 137, 255))
        overlay = pygame.Surface((w, h), pygame.SRCALPHA)
        overlay.fill((3, 5, 12, int(140 + 95 * content_alpha)))
        surface.blit(overlay, (0, 0))
        logo_dist = 260
        logo_a_x, logo_b_x = cx - logo_dist, cx + logo_dist
        logo_y = h // 2 + 50
        glow_strength = glow_intensity * content_alpha
        glow_surface = pygame.Surface((w, h), pygame.SRCALPHA)
        pygame.draw.circle(glow_surface, (*color_a[:3], int(70 * glow_strength)), (logo_a_x, logo_y), 500)
        pygame.draw.circle(glow_surface, (*color_b[:3], int(70 * glow_strength)), (logo_b_x, logo_y), 500)
        surface.blit(glow_surface, (0, 0))
        self._draw_hook_sparks(surface, progress, content_alpha * (0.6 + 0.4 * glow_intensity))
        hook_text = "MATCH PREVIEW"
        max_text_width = w - 160
        hook_font = self.hook_mega_font
        rendered_width = hook_font.size(hook_text)[0]
        text_scale = max_text_width / rendered_width if rendered_width > max_text_width else 1.0
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

    def _draw_finish_overlay(self, surface: pygame.Surface, snapshot: dict) -> None:
        teams = snapshot.get("teams", [])
        if len(teams) < 2: return
        overlay = pygame.Surface((self.w, self.h), pygame.SRCALPHA)
        overlay.fill((7, 10, 18, 178))
        surface.blit(overlay, (0, 0))
        team_a = next((team for team in teams if team.get("role") == "A"), teams[0])
        team_b = next((team for team in teams if team.get("role") == "B"), teams[1])
        score_a = int(team_a["score"])
        score_b = int(team_b["score"])
        progress = float(snapshot.get("final_result_progress", 1.0))
        panel = pygame.Rect(120, 470, self.w - 240, 680)
        self._draw_glass_panel(surface, panel, (10, 16, 28, 220), (92, 114, 156, 235), 36)
        ft_text = self.overlay_font.render("FULL TIME", True, (255, 228, 128))
        ft_rect = ft_text.get_rect(center=(self.w // 2, panel.y + 92))
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
        winner_rect = winner_text.get_rect(center=(self.w // 2, panel.y + 166))
        surface.blit(winner_text, winner_rect)
        left_logo = self._get_logo_surface(team_a["name"], team_a.get("badge_file", ""), 180)
        right_logo = self._get_logo_surface(team_b["name"], team_b.get("badge_file", ""), 180)
        surface.blit(left_logo, left_logo.get_rect(center=(panel.x + 190, panel.y + 360)))
        surface.blit(right_logo, right_logo.get_rect(center=(panel.right - 190, panel.y + 360)))
        team_a_text = self.result_team_font.render(team_a["name"], True, (245, 247, 252))
        team_b_text = self.result_team_font.render(team_b["name"], True, (245, 247, 252))
        surface.blit(team_a_text, team_a_text.get_rect(center=(panel.x + 190, panel.y + 495)))
        surface.blit(team_b_text, team_b_text.get_rect(center=(panel.right - 190, panel.y + 495)))
        detail = self._fit_text(self.result_font, f"{score_a} - {score_b}", panel.width - 140, (246, 246, 248))
        detail_rect = detail.get_rect(center=(self.w // 2, panel.y + 372))
        surface.blit(detail, detail_rect)
        progress_bar = pygame.Rect(panel.x + 80, panel.bottom - 82, panel.width - 160, 18)
        pygame.draw.rect(surface, (40, 48, 66), progress_bar, border_radius=9)
        fill_rect = pygame.Rect(progress_bar.x, progress_bar.y, int(progress_bar.width * progress), progress_bar.height)
        pygame.draw.rect(surface, color, fill_rect, border_radius=9)

    def _spawn_confetti(self, team_color: Tuple[int, int, int]) -> None:
        rng = self._confetti_rng
        cx = self.w // 2
        spawn_y = self.h - 100
        palette = [team_color, (255, 230, 80), (255, 255, 255), (120, 240, 160), (255, 140, 80), (180, 120, 255)]
        for _ in range(110):
            color = rng.choice(palette)
            self.confetti_particles.append(ConfettiParticle(
                x=rng.uniform(cx - 200, cx + 200), y=spawn_y,
                vx=rng.uniform(-420, 420), vy=rng.uniform(-900, -300),
                color=color, size=rng.uniform(8, 18),
                lifetime=rng.uniform(1.4, 2.4), angle=rng.uniform(0, math.tau),
                angular_vel=rng.uniform(-8, 8)
            ))

    def _draw_confetti(self, surface: pygame.Surface, dt: float) -> None:
        gravity = 600.0
        alive = []
        for p in self.confetti_particles:
            p.age += dt
            if p.age >= p.lifetime: continue
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

    def _draw_goal_flash(self, surface: pygame.Surface) -> None:
        if self.goal_flash_timer <= 0.0 or not self.goal_flash_event: return
        progress = min(1.0, self.goal_flash_timer / 0.95)
        alpha = int(205 * min(1.0, progress * 1.6))
        burst = pygame.Surface((self.w, 310), pygame.SRCALPHA)
        burst.fill((0, 0, 0, 0))
        team_color = self.goal_flash_event["color"]
        pygame.draw.rect(burst, (*team_color, alpha), pygame.Rect(80, 46, self.w - 160, 170), border_radius=34)
        pygame.draw.rect(burst, (255, 255, 255, min(255, alpha + 20)), pygame.Rect(80, 46, self.w - 160, 170), width=3, border_radius=34)
        goal_text = self.goal_font.render(self.goal_flash_event["flash_text"], True, (255, 255, 255))
        goal_rect = goal_text.get_rect(center=(self.w // 2, 118))
        burst.blit(goal_text, goal_rect)
        sub_text = self.goal_sub_font.render(self.goal_flash_event["team_name"], True, (245, 248, 255))
        sub_rect = sub_text.get_rect(center=(self.w // 2, 175))
        burst.blit(sub_text, sub_rect)
        surface.blit(burst, (0, 370))

    def trigger_goal(self, team_name: str, color: Tuple[int, int, int]):
        self.goal_flash_timer = 0.95
        self.goal_flash_event = {"team_name": team_name, "color": color, "flash_text": "GOAL!"}
        self._spawn_confetti(color)

    def draw_football_scoreboard(self, surface: pygame.Surface, snapshot: dict) -> None:
        teams = snapshot.get("teams", [])
        if len(teams) < 2: return
        team_a = next((team for team in teams if team.get("role") == "A"), teams[0])
        team_b = next((team for team in teams if team.get("role") == "B"), teams[1])
        cx = self.w // 2
        match_clock_text = snapshot.get("match_clock_text", "00:00")
        match_progress = snapshot.get("match_progress", 0.0)

        panel_w, panel_h = 940, 230
        panel_x = cx - panel_w // 2
        panel_y = 94
        self._draw_glass_panel(surface, pygame.Rect(panel_x, panel_y, panel_w, panel_h), (10, 16, 26, 195), (55, 70, 105, 210), 30)
        logo_size = 92
        logo_a = self._get_logo_surface(team_a["name"], team_a.get("badge_file", ""), logo_size)
        logo_a_cx = cx - 195
        logo_a_cy = panel_y + 58
        surface.blit(logo_a, logo_a.get_rect(center=(logo_a_cx, logo_a_cy)))
        name_a_surf = self._fit_text(self.match_font, team_a["name"], 240, (235, 240, 250))
        surface.blit(name_a_surf, name_a_surf.get_rect(center=(logo_a_cx, logo_a_cy + logo_size // 2 + 22)))
        logo_b = self._get_logo_surface(team_b["name"], team_b.get("badge_file", ""), logo_size)
        logo_b_cx = cx + 195
        logo_b_cy = panel_y + 58
        surface.blit(logo_b, logo_b.get_rect(center=(logo_b_cx, logo_b_cy)))
        name_b_surf = self._fit_text(self.match_font, team_b["name"], 240, (235, 240, 250))
        surface.blit(name_b_surf, name_b_surf.get_rect(center=(logo_b_cx, logo_b_cy + logo_size // 2 + 22)))
        score_str = f"{team_a['score']}  -  {team_b['score']}"
        score_surf = self.score_font.render(score_str, True, (248, 248, 252))
        surface.blit(score_surf, score_surf.get_rect(center=(cx, panel_y + 52)))
        clock_surf = self.clock_font.render(match_clock_text, True, (240, 242, 248))
        surface.blit(clock_surf, clock_surf.get_rect(center=(cx, panel_y + 128)))
        live_font = self.team_font
        live_chip = live_font.render("LIVE", True, (255, 255, 255))
        live_y = panel_y + 192
        chip_bg = pygame.Rect(0, 0, live_chip.get_width() + 28, 34)
        chip_bg.center = (cx - 72, live_y)
        pygame.draw.rect(surface, (194, 36, 61), chip_bg, border_radius=17)
        surface.blit(live_chip, live_chip.get_rect(center=chip_bg.center))
        
        phase_text = "1ST HALF" if match_progress < 0.5 else "2ND HALF"
        phase_surf = live_font.render(phase_text, True, (175, 185, 205))
        surface.blit(phase_surf, phase_surf.get_rect(center=(cx + 80, live_y)))
        self._draw_win_rate_rail(surface, snapshot, panel_x + 24, panel_y + panel_h + 10, panel_w - 48)

    def draw_goal_visual(self, surface: pygame.Surface, cx: float, cy: float, radius: float, angle_deg: float, gap_deg: float, thickness: float):
        """Gerçekçi bir kale görseli çizer."""
        a1 = math.radians(angle_deg - gap_deg/2)
        a2 = math.radians(angle_deg + gap_deg/2)
        
        p1 = (cx + radius * math.cos(a1), cy + radius * math.sin(a1))
        p2 = (cx + radius * math.cos(a2), cy + radius * math.sin(a2))
        
        # Kale direkleri
        pygame.draw.line(surface, (255, 255, 255), p1, p2, 6) # Eşik
        
        # File görseli için ufak çizgiler
        for i in range(1, 5):
            r_ext = radius + i * 12
            ext_p1 = (cx + r_ext * math.cos(a1), cy + r_ext * math.sin(a1))
            ext_p2 = (cx + r_ext * math.cos(a2), cy + r_ext * math.sin(a2))
            pygame.draw.line(surface, (200, 200, 200, 100), ext_p1, ext_p2, 2)
            pygame.draw.line(surface, (255, 255, 255), p1, ext_p1, 4)
            pygame.draw.line(surface, (255, 255, 255), p2, ext_p2, 4)


def build_arena_walls(space, cx, cy, radius, thickness, elasticity, friction, current_rotation_deg, gap_degrees, old_shapes):
    if old_shapes:
        try:
            space.remove(*old_shapes)
        except Exception:
            pass
    new_shapes = []
    total_arc = 360.0 - gap_degrees
    # Increase num_segs for extreme smoothness
    num_segs = max(16, int(240 * (total_arc / 360.0)))
    step = total_arc / num_segs
    for i in range(num_segs):
        a1 = gap_degrees / 2.0 + i * step
        a2 = gap_degrees / 2.0 + (i + 1) * step
        rad1 = math.radians(current_rotation_deg + a1)
        rad2 = math.radians(current_rotation_deg + a2)
        p1 = (cx + radius * math.cos(rad1), cy + radius * math.sin(rad1))
        p2 = (cx + radius * math.cos(rad2), cy + radius * math.sin(rad2))
        seg = pymunk.Segment(space.static_body, p1, p2, thickness / 2.0)
        seg.elasticity = elasticity
        seg.friction = friction
        new_shapes.append(seg)
    space.add(*new_shapes)
    return new_shapes

def run(config: dict) -> Path:
    width = int(config.get("width", 1080))
    height = int(config.get("height", 1920))
    fps = int(config.get("fps", 60))
    duration_seconds = float(config.get("duration_seconds", 55.0))
    intro_seconds = float(config.get("intro_seconds", 3.0))
    outro_seconds = float(config.get("outro_seconds", 3.0))
    headless = config.get("headless", False)
    
    # Rotation speed and gap
    arena_radius = float(config.get("arena_radius", 420.0))
    gap_degrees = float(config.get("gap_degrees", 22.0))
    rotation_speed = float(config.get("rotation_speed", 38.0))
    wall_thickness = float(config.get("wall_thickness", 24.0))
    
    ball_radius = float(config.get("ball_radius", 48.0))
    target_speed = float(config.get("target_speed", 580.0))
    ball_elast = float(config.get("ball_elasticity", 0.98))
    ball_fric = float(config.get("ball_friction", 0.01))
    wall_elast = float(config.get("wall_elasticity", 0.98))
    wall_fric = float(config.get("wall_friction", 0.05))
    
    team_a = config.get("team_a", {"name": "Team A", "role": "A", "score": 0, "color": (220, 72, 72)})
    team_b = config.get("team_b", {"name": "Team B", "role": "B", "score": 0, "color": (79, 137, 255)})
    
    output_path = Path(config.get("output_path", "output_arena.mp4"))
    bg_music = config.get("background_music_path", None)
    
    space = pymunk.Space()
    space.gravity = (0, 0)
    space.damping = 1.0

    cx, cy = width / 2.0, height / 2.0 + 100.0

    def create_ball(x, y, color, team_info):
        mass = 1.0
        moment = pymunk.moment_for_circle(mass, 0, ball_radius)
        body = pymunk.Body(mass, moment)
        body.position = (x, y)
        angle = random.uniform(0, 2*math.pi)
        body.velocity = pymunk.Vec2d(math.cos(angle), math.sin(angle)) * target_speed
        shape = pymunk.Circle(body, ball_radius)
        shape.elasticity = ball_elast
        shape.friction = ball_fric
        space.add(body, shape)
        return {"body": body, "shape": shape, "team": team_info}

    ball_a = create_ball(cx - 50, cy, team_a.get("color"), team_a)
    ball_b = create_ball(cx + 50, cy, team_b.get("color"), team_b)
    balls = [ball_a, ball_b]

    pygame.init()
    surface = pygame.Surface((width, height))
    renderer = RotatingArenaRenderer(width, height, fps)
    
    screen = None
    preview_width, preview_height = 0, 0
    if not headless:
        preview_max_height = 780
        preview_scale = min(1.0, preview_max_height / height)
        preview_width = max(360, int(width * preview_scale))
        preview_height = max(640, int(height * preview_scale))
        pygame.display.set_caption("Rotating Arena Exporter Preview")
        screen = pygame.display.set_mode((preview_width, preview_height))
    
    class MockVideoCfg: pass
    class MockVideoSubCfg: pass
    cfg_mock = MockVideoCfg()
    cfg_mock.video = MockVideoSubCfg()
    cfg_mock.video.width = width
    cfg_mock.video.height = height
    cfg_mock.video.fps = fps
    cfg_mock.output_path = output_path

    total_frames = int(duration_seconds * fps)
    dt = 1.0 / fps

    arena_shapes = []
    current_rotation = 0.0
    next_turn_time = random.uniform(8, 12)
    
    event_timeline = [{"type": "whistle_start", "time": intro_seconds}]
    
    collision_vols = []
    def handle_collision(arbiter, space, data):
        if arbiter.is_first_contact:
            impulse = arbiter.total_impulse.length
            if impulse > 50:
                vol = max(0.1, min(1.0, impulse / 1000.0))
                collision_vols.append(vol)
        return True
    
    handler = None
    try:
        if hasattr(space, "on_collision"):
            space.on_collision(post_solve=handle_collision)
        else:
            handler = space.add_default_collision_handler()
            handler.post_solve = handle_collision
    except Exception as e:
        print(f"[RotatingArena] Collision handler error: {e}")
    
    running = True
    with Mp4VideoWriter(cfg_mock, output_path) as writer:
        for frame in range(total_frames):
            if not headless:
                for event in pygame.event.get():
                    if event.type == pygame.QUIT:
                        running = False
            if not running:
                break
            
            time_sec = frame * dt
            
            collision_vols.clear()
            space.step(dt)
            
            for vol in collision_vols:
                event_timeline.append({"type": "ball_hit", "time": time_sec, "volume": vol})
            
            for b_info in balls:
                v = b_info["body"].velocity
                if v.length > 0.01:
                    b_info["body"].velocity = v.normalized() * target_speed
                else:
                    a = random.uniform(0, 2*math.pi)
                    b_info["body"].velocity = pymunk.Vec2d(math.cos(a), math.sin(a)) * target_speed
            
            for b_info in balls:
                dist = math.hypot(b_info["body"].position.x - cx, b_info["body"].position.y - cy)
                if dist > arena_radius + ball_radius + 5:
                    b_info["team"]["score"] += 1
                    b_info["body"].position = (cx, cy)
                    a = random.uniform(0, 2*math.pi)
                    b_info["body"].velocity = pymunk.Vec2d(math.cos(a), math.sin(a)) * target_speed
                    event_timeline.append({"type": "goal", "time": time_sec, "volume": 1.0})
                    renderer.trigger_goal(b_info["team"]["name"], b_info["team"].get("color", (255,255,255)))
            
            current_rotation += rotation_speed * dt
            arena_shapes = build_arena_walls(space, cx, cy, arena_radius, wall_thickness, wall_elast, wall_fric, current_rotation, gap_degrees, arena_shapes)
            
            if time_sec > next_turn_time:
                next_turn_time = time_sec + random.uniform(5, 9)
                rotation_speed = random.choice([-1, 1]) * random.uniform(25, 55)

            surface.fill((16, 22, 34))
            pygame.draw.circle(surface, (22, 30, 44), (int(cx), int(cy)), int(arena_radius))
            
            # Goal visual
            renderer.draw_goal_visual(surface, cx, cy, arena_radius, current_rotation, gap_degrees, wall_thickness)

            # Smooth Arena Drawing: Draw each segment as a filled polygon to avoid gaps (notches)
            wall_color = (180, 180, 190)
            for shp in arena_shapes:
                p1 = shp.a
                p2 = shp.b
                
                # Calculate normal vector for thickness
                dx = p2.x - p1.x
                dy = p2.y - p1.y
                dist = math.hypot(dx, dy)
                if dist == 0: continue
                
                nx = -dy / dist * (wall_thickness / 2.0)
                ny = dx / dist * (wall_thickness / 2.0)
                
                # Create a 4-point polygon (rectangle/trapezoid) representing the thick line segment
                pts = [
                    (p1.x + nx, p1.y + ny),
                    (p2.x + nx, p2.y + ny),
                    (p2.x - nx, p2.y - ny),
                    (p1.x - nx, p1.y - ny)
                ]
                pygame.draw.polygon(surface, wall_color, pts)
                # Overdraw with a line to ensure even better anti-aliasing
                pygame.draw.line(surface, wall_color, (p1.x, p1.y), (p2.x, p2.y), int(wall_thickness))
            
            a1 = math.radians(current_rotation - gap_degrees/2)
            a2 = math.radians(current_rotation + gap_degrees/2)
            for a in [a1, a2]:
                px = cx + arena_radius * math.cos(a)
                py = cy + arena_radius * math.sin(a)
                pin_p1 = (px - 15*math.cos(a), py - 15*math.sin(a))
                pin_p2 = (px + 15*math.cos(a), py + 15*math.sin(a))
                pygame.draw.line(surface, (255, 220, 50), pin_p1, pin_p2, int(wall_thickness + 4))

            for b_info in balls:
                renderer._draw_ball(surface, {
                    "team_name": b_info["team"]["name"],
                    "team_badge_file": b_info["team"].get("badge_file", ""),
                    "radius": ball_radius,
                    "x": b_info["body"].position.x,
                    "y": b_info["body"].position.y,
                    "angle_radians": b_info["body"].angle
                })

            if renderer.goal_flash_timer > 0:
                renderer.goal_flash_timer = max(0.0, renderer.goal_flash_timer - dt)
            renderer._draw_confetti(surface, dt)
            renderer._draw_goal_flash(surface)

            # Match clock calculation (00:00 -> 90:00)
            gameplay_duration = max(1.0, duration_seconds - intro_seconds - outro_seconds)
            
            if time_sec < intro_seconds:
                match_progress = 0.0
                sim_mins, sim_secs = 0, 0
            elif time_sec > duration_seconds - outro_seconds:
                match_progress = 1.0
                sim_mins, sim_secs = 90, 0
            else:
                gameplay_elapsed = time_sec - intro_seconds
                match_progress = min(1.0, gameplay_elapsed / gameplay_duration)
                sim_match_sec = match_progress * 90 * 60
                sim_mins = int(sim_match_sec // 60)
                sim_secs = int(sim_match_sec % 60)
            
            snapshot = {
                "teams": [team_a, team_b],
                "match_clock_text": f"{sim_mins:02d}:{sim_secs:02d}",
                "match_progress": match_progress,
                "win_probabilities": {"team_a": max(0.1, team_a["score"]), "team_b": max(0.1, team_b["score"]), "draw": 0.5}
            }
            
            if time_sec < intro_seconds:
                snapshot["hook_progress"] = time_sec / intro_seconds
                renderer._draw_hook_overlay(surface, snapshot)
            elif time_sec > duration_seconds - outro_seconds:
                if "whistle_end" not in [e["type"] for e in event_timeline]:
                    event_timeline.append({"type": "whistle_end", "time": time_sec})
                snapshot["final_result_progress"] = (time_sec - (duration_seconds - outro_seconds)) / outro_seconds
                renderer._draw_finish_overlay(surface, snapshot)
            else:
                renderer.draw_football_scoreboard(surface, snapshot)

            if not headless and screen is not None:
                preview_frame = pygame.transform.smoothscale(surface, (preview_width, preview_height))
                screen.blit(preview_frame, (0, 0))
                pygame.display.flip()

            writer.write_surface(surface)
            if frame % 300 == 0:
                print(f"[RotatingArena] Rendered frame {frame}/{total_frames} ({(frame/total_frames)*100:.1f}%)")

    pygame.quit()
    print("[RotatingArena] Rendering complete.")

    final_output_path = output_path.with_name(output_path.stem + "_final.mp4")
    print("[RotatingArena] Processing final video (Audio + Greenscreen Overlay)...")
    
    try:
        final_video = mix_audio_into_video(
            video_path=output_path,
            event_timeline=event_timeline,
            output_path=final_output_path,
            background_music_path=bg_music,
            overlay_video_path=Path(__file__).resolve().parent / "likebell.mp4",
            overlay_start_time=20.0
        )
        print(f"[RotatingArena] Done: {final_video}")
        return final_video
    except Exception as e:
        print(f"[RotatingArena] Post-processing error: {e}")
        return output_path

if __name__ == "__main__":
    test_config = {
        "width": 1080, "height": 1920, "fps": 60, "duration_seconds": 30.0,
        "team_a": {"name": "Galatasaray", "short_name": "GS", "score": 0, "color": (255,0,0), "badge_file": "gs.png"},
        "team_b": {"name": "Fenerbahce", "short_name": "FB", "score": 0, "color": (0,0,255), "badge_file": "fb.png"},
        "output_path": "rotating_test.mp4",
        "background_music_path": None
    }
    print(run(test_config))
