# penalty_renderer.py
from __future__ import annotations

import colorsys
import math
import random
from pathlib import Path
from typing import Any

import pygame
from PIL import Image

from config import SimulationConfig


# ─────────────────────────────────────────────────────────────
# Yardımcı
# ─────────────────────────────────────────────────────────────

def _ease_out(t: float) -> float:
    return 1.0 - (1.0 - t) ** 2


def _ease_in(t: float) -> float:
    return t * t


def _team_color(team_key: str) -> tuple[int, int, int]:
    seed = sum((i + 1) * ord(c) for i, c in enumerate(str(team_key))) % 360
    h = seed / 360.0
    r, g, b = colorsys.hsv_to_rgb(h, 0.58, 0.90)
    return (int(r * 255), int(g * 255), int(b * 255))


# ─────────────────────────────────────────────────────────────
# PenaltyRenderer
# ─────────────────────────────────────────────────────────────

class PenaltyRenderer:
    """
    Penaltı fazında mevcut render surface'ın üstüne overlay olarak çizilir.
    main.py'de  renderer.draw()  çağrısından SONRA çağrılmalıdır.

    Snapshot'ta beklenen ekstra anahtarlar (main.py tarafından eklenir):
        penalty_kick_progress   float  0-1, mevcut atışın animasyon ilerlemesi
        penalty_current_kick    dict   {"team":"A"|"B","round":...,"scored":bool}
    """

    # ── Layout (1080 × 1920 portre) ──────────────────────────
    HEADER_Y   = 70
    TEAM_ROW_Y = 220
    MARKS_Y    = 460
    ARENA_Y    = 590

    GOAL_W     = 720
    GOAL_H     = 230
    GOAL_TOP_OFFSET = 60   # arena_y'den uzaklık

    SPOT_OFFSET = 520      # arena_y'den uzaklık (penaltı noktası)

    def __init__(self, cfg: SimulationConfig) -> None:
        self.cfg = cfg
        pygame.font.init()
        self.f_title   = pygame.font.SysFont("arial", 52, bold=True)
        self.f_sub     = pygame.font.SysFont("arial", 26, bold=False)
        self.f_score   = pygame.font.SysFont("arial", 88, bold=True)
        self.f_team    = pygame.font.SysFont("arial", 30, bold=True)
        self.f_result  = pygame.font.SysFont("arial", 68, bold=True)
        self.f_round   = pygame.font.SysFont("arial", 22, bold=False)
        self.f_kicking = pygame.font.SysFont("arial", 34, bold=True)
        self.logo_cache: dict[str, pygame.Surface] = {}

    # ── Ana giriş ─────────────────────────────────────────────

    def draw(self, surface: pygame.Surface, snapshot: dict[str, Any]) -> None:
        if not snapshot.get("penalty_overlay_active"):
            return

        sw, sh = surface.get_width(), surface.get_height()
        cx = sw // 2

        # Karartma
        dark = pygame.Surface((sw, sh), pygame.SRCALPHA)
        dark.fill((5, 8, 18, 200))
        surface.blit(dark, (0, 0))

        self._draw_header(surface, snapshot, cx)
        self._draw_team_row(surface, snapshot, cx)
        self._draw_marks(surface, snapshot, cx)
        self._draw_arena(surface, snapshot, cx)

    # ── Header: "PENALTY SHOOTOUT" + skor ─────────────────────

    def _draw_header(self, surface: pygame.Surface, snapshot: dict, cx: int) -> None:
        title = self.f_title.render("PENALTY SHOOTOUT", True, (255, 230, 90))
        surface.blit(title, title.get_rect(center=(cx, self.HEADER_Y + 36)))

        ft_a  = int(snapshot.get("regular_time_score_a") or 0)
        ft_b  = int(snapshot.get("regular_time_score_b") or 0)
        et_ra = snapshot.get("extra_time_score_a")
        et_rb = snapshot.get("extra_time_score_b")

        if et_ra is not None and et_rb is not None:
            aet_a = ft_a + int(et_ra)
            aet_b = ft_b + int(et_rb)
            sub_text = f"AET  {aet_a} – {aet_b}"
        else:
            sub_text = f"FT  {ft_a} – {ft_b}"

        sub = self.f_sub.render(sub_text, True, (180, 195, 225))
        surface.blit(sub, sub.get_rect(center=(cx, self.HEADER_Y + 102)))

    # ── Takım satırı ──────────────────────────────────────────

    def _draw_team_row(self, surface: pygame.Surface, snapshot: dict, cx: int) -> None:
        teams = list(snapshot.get("teams", []))
        team_a = next((t for t in teams if t.get("role") == "A"), teams[0] if teams else {})
        team_b = next((t for t in teams if t.get("role") == "B"), teams[1] if len(teams) > 1 else {})

        pen_a = int(snapshot.get("penalty_display_score_a") or 0)
        pen_b = int(snapshot.get("penalty_display_score_b") or 0)
        ty    = self.TEAM_ROW_Y

        # Sol takım (A)
        logo_a = self._logo(team_a, 76)
        surface.blit(logo_a, logo_a.get_rect(center=(cx - 290, ty + 50)))
        na = self.f_team.render(self._short(team_a), True, (235, 240, 252))
        surface.blit(na, na.get_rect(center=(cx - 290, ty + 110)))

        # Skor A
        sa = self.f_score.render(str(pen_a), True, (255, 255, 255))
        surface.blit(sa, sa.get_rect(center=(cx - 120, ty + 65)))

        # Tire
        dash = self.f_score.render("–", True, (160, 175, 210))
        surface.blit(dash, dash.get_rect(center=(cx, ty + 65)))

        # Skor B
        sb = self.f_score.render(str(pen_b), True, (255, 255, 255))
        surface.blit(sb, sb.get_rect(center=(cx + 120, ty + 65)))

        # Sağ takım (B)
        logo_b = self._logo(team_b, 76)
        surface.blit(logo_b, logo_b.get_rect(center=(cx + 290, ty + 50)))
        nb = self.f_team.render(self._short(team_b), True, (235, 240, 252))
        surface.blit(nb, nb.get_rect(center=(cx + 290, ty + 110)))

    # ── Atış işaretleri (● / ✕) ──────────────────────────────

    def _draw_marks(self, surface: pygame.Surface, snapshot: dict, cx: int) -> None:
        marks_a = list(snapshot.get("penalty_marks_a", []))
        marks_b = list(snapshot.get("penalty_marks_b", []))
        total   = int(snapshot.get("penalty_total_kicks") or 0)

        # Kaç normal tur var? 5'er olarak düşün, SD varsa daha fazla
        normal_rounds = max(5, (total // 2 + 4) // 5 * 5 // 2)  # en az 5, SD varsa yukarı yuvarla
        normal_rounds = min(normal_rounds, 8)  # ekranda max 8 slot

        my = self.MARKS_Y + 30
        r  = 18    # çember yarıçapı
        sp = 46    # spacing

        def draw_row(marks: list[str], start_x: int, count: int) -> None:
            for i in range(count):
                x = start_x + i * sp + r
                if i < len(marks):
                    if marks[i] == "GOAL":
                        pygame.draw.circle(surface, (60, 210, 120), (x, my), r)
                        pygame.draw.circle(surface, (140, 255, 180), (x, my), r, 3)
                    else:
                        pygame.draw.circle(surface, (210, 55, 65), (x, my), r)
                        d = r - 5
                        pygame.draw.line(surface, (255, 120, 130), (x - d, my - d), (x + d, my + d), 3)
                        pygame.draw.line(surface, (255, 120, 130), (x + d, my - d), (x - d, my + d), 3)
                else:
                    pygame.draw.circle(surface, (45, 58, 80), (x, my), r)
                    pygame.draw.circle(surface, (90, 110, 145), (x, my), r, 2)

        total_w = normal_rounds * sp
        ax = cx - total_w - 18
        bx = cx + 18
        draw_row(marks_a, ax, normal_rounds)
        draw_row(marks_b, bx, normal_rounds)

        # A / B etiketleri
        la = self.f_round.render("A", True, (150, 170, 210))
        surface.blit(la, (ax - 22, my - 10))
        lb = self.f_round.render("B", True, (150, 170, 210))
        surface.blit(lb, (bx - 22, my - 10))

        # SD bildirimi
        shown = int(snapshot.get("penalty_shown_kicks") or 0)
        if total > 0 and shown > 0:
            last_round = str(snapshot.get("penalty_current_kick", {}).get("round", ""))
            if isinstance(last_round, str) and last_round.startswith("SD"):
                sd_text = self.f_round.render(f"SUDDEN DEATH – {last_round}", True, (255, 200, 80))
                surface.blit(sd_text, sd_text.get_rect(center=(cx, my + 38)))

    # ── Arena: kale + top + kaleci animasyonu ─────────────────

    def _draw_arena(self, surface: pygame.Surface, snapshot: dict, cx: int) -> None:
        ay        = self.ARENA_Y
        goal_top  = ay + self.GOAL_TOP_OFFSET
        goal_left = cx - self.GOAL_W // 2
        goal_rect = pygame.Rect(goal_left, goal_top, self.GOAL_W, self.GOAL_H)
        spot_y    = ay + self.SPOT_OFFSET

        self._draw_goal(surface, goal_rect)
        pygame.draw.circle(surface, (255, 255, 255), (cx, spot_y), 7)

        kick_progress  = float(snapshot.get("penalty_kick_progress") or 0.0)
        current_kick   = snapshot.get("penalty_current_kick")
        shown          = int(snapshot.get("penalty_shown_kicks") or 0)
        total          = int(snapshot.get("penalty_total_kicks") or 0)

        if current_kick is not None and shown > 0:
            self._draw_kick_animation(
                surface, snapshot, cx, spot_y, goal_rect,
                current_kick, kick_progress, shown - 1,
            )
        elif shown == 0:
            # İlk atış henüz gelmedi — "Kicks off soon" göster
            waiting = self.f_round.render("Kicks off soon...", True, (180, 195, 225))
            surface.blit(waiting, waiting.get_rect(center=(cx, spot_y - 60)))
            # Boş kaleci
            kw, kh = 120, 55
            kr = pygame.Rect(cx - kw // 2, goal_top + self.GOAL_H - kh - 6, kw, kh)
            pygame.draw.rect(surface, (100, 120, 160), kr, border_radius=12)

        # Tüm atışlar bitti → şampiyon mesajı
        if shown >= total > 0:
            self._draw_winner(surface, snapshot, cx)

    def _draw_goal(self, surface: pygame.Surface, rect: pygame.Rect) -> None:
        # Çim zemini
        grass = pygame.Surface((rect.width + 200, rect.height + 220), pygame.SRCALPHA)
        grass.fill((18, 75, 32, 170))
        surface.blit(grass, (rect.x - 100, rect.y))

        # Kale ağı (grid)
        net = pygame.Surface((rect.width, rect.height), pygame.SRCALPHA)
        nc  = (210, 220, 235, 55)
        for x in range(0, rect.width, 38):
            pygame.draw.line(net, nc, (x, 0), (x, rect.height), 1)
        for y in range(0, rect.height, 38):
            pygame.draw.line(net, nc, (0, y), (rect.width, y), 1)
        surface.blit(net, rect.topleft)

        # Direkler + üst çıta
        post_c = (245, 248, 254)
        t = 9
        pygame.draw.rect(surface, post_c, (rect.left, rect.top, t, rect.height))
        pygame.draw.rect(surface, post_c, (rect.right - t, rect.top, t, rect.height))
        pygame.draw.rect(surface, post_c, (rect.left, rect.top, rect.width, t))

    def _draw_kick_animation(
        self,
        surface: pygame.Surface,
        snapshot: dict,
        cx: int,
        spot_y: int,
        goal_rect: pygame.Rect,
        kick: dict,
        progress: float,
        kick_idx: int,
    ) -> None:
        scored     = bool(kick.get("scored", False))
        team_side  = str(kick.get("team", "A"))
        round_lbl  = str(kick.get("round", ""))

        # Atış yönü: kick_idx + match_id'den deterministic
        match_id = str(snapshot.get("match_id") or snapshot.get("tournament_match_id") or "match")
        dir_rng  = random.Random(f"pen_dir:{match_id}:{kick_idx}")
        # -1 sol, 0 orta, +1 sağ (köşelere daha ağırlıklı)
        ball_dir = dir_rng.choice([-1, -1, 0, 1, 1])

        goal_cx   = goal_rect.centerx
        goal_cy   = goal_rect.centery
        ball_gx   = goal_cx + int(ball_dir * (self.GOAL_W // 2 - 90))
        ball_gy   = goal_rect.top + self.GOAL_H // 2

        # Kaleci: gol → yanlış tarafa, kaçırma → top tarafına
        if ball_dir == 0:
            keep_dir = dir_rng.choice([-1, 1])
        elif scored:
            keep_dir = -ball_dir
        else:
            keep_dir = ball_dir

        kw, kh   = 120, 55
        keep_travel = int(keep_dir * (self.GOAL_W // 2 - 55))
        keep_base_x = goal_cx
        keep_y  = goal_rect.top + self.GOAL_H - kh - 6

        teams   = list(snapshot.get("teams", []))
        team_a  = next((t for t in teams if t.get("role") == "A"), teams[0] if teams else {})
        team_b  = next((t for t in teams if t.get("role") == "B"), teams[1] if len(teams) > 1 else {})
        kicking_team  = team_a if team_side == "A" else team_b
        keeper_team   = team_b if team_side == "A" else team_a
        keeper_color  = _team_color(str(keeper_team.get("team_key", "")))

        # ── Faz 1: 0.00–0.28  Setup ──────────────────────────
        if progress < 0.28:
            t = progress / 0.28

            # Top penaltı noktasında
            self._ball(surface, cx, spot_y, 18)
            # Kaleci ortada
            kr = pygame.Rect(keep_base_x - kw // 2, keep_y, kw, kh)
            pygame.draw.rect(surface, keeper_color, kr, border_radius=12)
            pygame.draw.rect(surface, (220, 228, 245), kr, width=2, border_radius=12)

            if t > 0.35:
                alpha = min(255, int(255 * (t - 0.35) / 0.65))
                name = self._short(kicking_team)
                txt  = self.f_kicking.render(f"{name}  kicks", True, (255, 240, 170))
                ts   = pygame.Surface(txt.get_size(), pygame.SRCALPHA)
                ts.blit(txt, (0, 0))
                ts.set_alpha(alpha)
                surface.blit(ts, txt.get_rect(center=(cx, spot_y - 90)))

            r_txt = self.f_round.render(f"Round {round_lbl}", True, (160, 178, 215))
            surface.blit(r_txt, r_txt.get_rect(center=(cx, spot_y - 140)))

        # ── Faz 2: 0.28–0.65  Hareket ───────────────────────
        elif progress < 0.65:
            t      = (progress - 0.28) / 0.37
            t_ease = _ease_in(t)

            bx = int(cx + (ball_gx - cx) * t_ease)
            by_arc = 70  # top yayı yüksekliği
            by = int(spot_y + (ball_gy - spot_y) * t_ease
                     - by_arc * math.sin(t_ease * math.pi))
            self._ball(surface, bx, by, 18)

            # Kaleci dalış
            t_keep = min(1.0, t * 2.2)
            kcx    = int(keep_base_x + keep_travel * _ease_out(t_keep))
            kr     = pygame.Rect(kcx - kw // 2, keep_y, kw, kh)
            pygame.draw.rect(surface, keeper_color, kr, border_radius=12)
            pygame.draw.rect(surface, (220, 228, 245), kr, width=2, border_radius=12)

        # ── Faz 3: 0.65–1.00  Sonuç ─────────────────────────
        else:
            t = (progress - 0.65) / 0.35

            # Kaleci son konumda
            kcx = int(keep_base_x + keep_travel)
            kr  = pygame.Rect(kcx - kw // 2, keep_y, kw, kh)
            pygame.draw.rect(surface, keeper_color, kr, border_radius=12)
            pygame.draw.rect(surface, (220, 228, 245), kr, width=2, border_radius=12)

            if scored:
                self._ball(surface, ball_gx, ball_gy, 18)
                # Kale parlama
                if t < 0.45:
                    glow = pygame.Surface((goal_rect.width, goal_rect.height), pygame.SRCALPHA)
                    a    = int(130 * (1.0 - t / 0.45))
                    glow.fill((60, 230, 110, a))
                    surface.blit(glow, goal_rect.topleft)
                self._result_text(surface, cx, spot_y - 70, "GOAL!", (60, 230, 110), t)
            else:
                # Top direğin dışına uçar
                miss_x = ball_gx + int(ball_dir * 120)
                miss_y = goal_rect.top - 55
                self._ball(surface, miss_x, miss_y, 18)
                self._result_text(surface, cx, spot_y - 70, "MISS", (230, 60, 70), t)

    def _draw_winner(self, surface: pygame.Surface, snapshot: dict, cx: int) -> None:
        pen_a = int(snapshot.get("penalty_display_score_a") or 0)
        pen_b = int(snapshot.get("penalty_display_score_b") or 0)
        teams = list(snapshot.get("teams", []))
        team_a = next((t for t in teams if t.get("role") == "A"), teams[0] if teams else {})
        team_b = next((t for t in teams if t.get("role") == "B"), teams[1] if len(teams) > 1 else {})

        if pen_a > pen_b:
            winner_name = self._short(team_a)
        elif pen_b > pen_a:
            winner_name = self._short(team_b)
        else:
            return  # henüz belli değil

        bw, bh = 900, 130
        bx = cx - bw // 2
        by = self.ARENA_Y + self.SPOT_OFFSET + 80
        box = pygame.Surface((bw, bh), pygame.SRCALPHA)
        pygame.draw.rect(box, (12, 22, 44, 215), pygame.Rect(0, 0, bw, bh), border_radius=22)
        pygame.draw.rect(box, (255, 215, 90, 200), pygame.Rect(0, 0, bw, bh), width=3, border_radius=22)
        surface.blit(box, (bx, by))
        txt = self.f_result.render(f"{winner_name}  wins on penalties", True, (255, 240, 140))
        surface.blit(txt, txt.get_rect(center=(cx, by + bh // 2)))

    # ── Yardımcı çizim ────────────────────────────────────────

    def _ball(self, surface: pygame.Surface, x: int, y: int, r: int) -> None:
        shadow = pygame.Surface((r * 3, r * 3), pygame.SRCALPHA)
        pygame.draw.circle(shadow, (0, 0, 0, 80),
                           (shadow.get_width() // 2, shadow.get_height() // 2), r)
        surface.blit(shadow, shadow.get_rect(center=(x + 4, y + 6)))
        pygame.draw.circle(surface, (252, 252, 252), (x, y), r)
        pygame.draw.circle(surface, (40, 40, 40), (x, y), r, 2)
        # Basit pentagons izlenimi için iki küçük beşgen doku
        pygame.draw.circle(surface, (30, 30, 30), (x - r // 3, y - r // 3), r // 4)

    def _result_text(
        self,
        surface: pygame.Surface,
        cx: int,
        cy: int,
        text: str,
        color: tuple[int, int, int],
        t: float,
    ) -> None:
        alpha = min(255, int(255 * min(1.0, t * 3.5)))
        surf  = self.f_result.render(text, True, color)
        ts    = pygame.Surface(surf.get_size(), pygame.SRCALPHA)
        ts.blit(surf, (0, 0))
        ts.set_alpha(alpha)
        surface.blit(ts, surf.get_rect(center=(cx, cy)))

    # ── Logo ──────────────────────────────────────────────────

    def _logo(self, team: dict, size: int) -> pygame.Surface:
        badge = str(team.get("badge_file") or "")
        name  = str(team.get("name") or "")
        key   = f"{badge}|{size}"
        if key in self.logo_cache:
            return self.logo_cache[key]

        path = self.cfg.data_dir / "logos" / badge
        try:
            img = Image.open(path).convert("RGBA")
            img.thumbnail((size - 8, size - 8), Image.Resampling.LANCZOS)
            canvas = Image.new("RGBA", (size, size), (0, 0, 0, 0))
            canvas.paste(img, ((size - img.width) // 2, (size - img.height) // 2), img)
            surf = pygame.image.fromstring(canvas.tobytes(), canvas.size, canvas.mode).convert_alpha()
            mask = pygame.Surface((size, size), pygame.SRCALPHA)
            pygame.draw.circle(mask, (255, 255, 255, 255), (size // 2, size // 2), size // 2 - 2)
            out = pygame.Surface((size, size), pygame.SRCALPHA)
            out.blit(surf, (0, 0))
            out.blit(mask, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
            pygame.draw.circle(out, (220, 228, 245, 200), (size // 2, size // 2), size // 2 - 2, 2)
        except Exception:
            out = self._placeholder(name, size)

        self.logo_cache[key] = out
        return out

    def _placeholder(self, name: str, size: int) -> pygame.Surface:
        surf = pygame.Surface((size, size), pygame.SRCALPHA)
        pygame.draw.circle(surf, (55, 68, 90), (size // 2, size // 2), size // 2 - 2)
        pygame.draw.circle(surf, (180, 192, 215), (size // 2, size // 2), size // 2 - 2, 2)
        initials = "".join(w[:1] for w in str(name).split()[:2]).upper()[:2] or "TM"
        f = pygame.font.SysFont("arial", max(12, size // 3), bold=True)
        t = f.render(initials, True, (235, 242, 252))
        surf.blit(t, t.get_rect(center=(size // 2, size // 2)))
        return surf

    @staticmethod
    def _short(team: dict) -> str:
        s = str(team.get("short_name") or "").strip()
        n = str(team.get("name") or "").strip()
        if s and len(n) > 14:
            return s[:14]
        return (n or s or "TEAM")[:14]
