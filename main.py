# main.py
from __future__ import annotations

import math
import random
import re
import sys
import json
import argparse
import time
from dataclasses import replace
from datetime import datetime
from pathlib import Path
from tkinter import Tk, messagebox

import pygame

from audio_mixer import mix_audio_into_video
from config import build_default_config, get_video_preset
from knockout_rules import resolve_single_leg_knockout
from models import MatchSelection
from physics import MarbleRacePhysics
from penalty_renderer import PenaltyRenderer
from renderer import MarbleRaceRenderer
from team_repository import TeamRepository
from video_writer import Mp4VideoWriter


# ============================================================
# YARDIMCI FONKSÄ°YONLAR
# ============================================================

def show_messagebox(title: str, message: str, is_error: bool = False) -> None:
    """
    Terminale mecbur bÄ±rakmamak iÃ§in basit masaÃ¼stÃ¼ mesaj kutusu.
    """
    root = Tk()
    root.withdraw()

    if is_error:
        messagebox.showerror(title, message)
    else:
        messagebox.showinfo(title, message)

    root.destroy()


def _slugify(text: str) -> str:
    """Dosya adÄ±na uygun slug Ã¼ret: 'Galatasaray' -> 'galatasaray'."""
    text = text.strip().lower()
    text = text.replace("&", "and")
    text = re.sub(r"[^\w\s-]", "", text, flags=re.UNICODE)
    text = re.sub(r"[\s-]+", "_", text).strip("_")
    return text or "team"


def generate_output_filename(match: MatchSelection) -> str:
    """
    Benzersiz dosya adÄ± Ã¼ret.
    Ã–rnek: turkey_vs_greece_20260330_a3f1.mp4
    """
    team_a = _slugify(match.team_a.short_name or match.team_a.name)
    team_b = _slugify(match.team_b.short_name or match.team_b.name)
    date_str = datetime.now().strftime("%Y%m%d_%H%M%S")
    return f"{team_a}_vs_{team_b}_{date_str}.mp4"


def format_match_clock(match_seconds: float) -> str:
    """
    MaÃ§ saniyesini MM:SS formatÄ±na Ã§evirir.
    """
    if match_seconds < 0:
        match_seconds = 0

    total_seconds = int(round(match_seconds))
    minutes = total_seconds // 60
    seconds = total_seconds % 60
    return f"{minutes:02d}:{seconds:02d}"


def _mode_scoring_intensity(engine_mode: str) -> float:
    mode = (engine_mode or "").strip().lower()
    explicit = {
        "power_pegs": 8.4,
        "normal": 5.8,
        "football_var": 5.2,
        "football_result_guided_test": 5.8,
        "football_shift": 6.9,
        "football_blink": 6.2,
        "football_gears": 6.5,
    }
    if mode in explicit:
        return explicit[mode]

    base = 6.0
    if "power" in mode or "slowfast" in mode or "pegs" in mode:
        base += 2.0
    if "shift" in mode:
        base += 1.0
    return max(2.8, base)


def _normalize_probs(a: float, d: float, b: float) -> tuple[float, float, float]:
    total = max(1e-9, a + d + b)
    return (a / total, d / total, b / total)


def _poisson_pmf_series(lmbd: float, max_k: int) -> list[float]:
    lmbd = max(0.0, float(lmbd))
    max_k = max(0, int(max_k))

    p0 = math.exp(-lmbd)
    probs = [p0]
    for k in range(1, max_k + 1):
        probs.append(probs[-1] * lmbd / k)

    s = sum(probs)
    if s <= 1e-12:
        return [1.0 / (max_k + 1)] * (max_k + 1)
    return [p / s for p in probs]


def _estimate_live_outcome_probs(
    score_a: int,
    score_b: int,
    remaining_ratio: float,
    engine_mode: str,
    momentum: float,
) -> tuple[float, float, float]:
    remaining = max(0.0, min(1.0, float(remaining_ratio)))
    diff = int(score_a) - int(score_b)

    if remaining <= 1e-6:
        if diff > 0:
            return (1.0, 0.0, 0.0)
        if diff < 0:
            return (0.0, 0.0, 1.0)
        return (0.0, 1.0, 0.0)

    expected_total = _mode_scoring_intensity(engine_mode) * remaining
    momentum = max(-1.0, min(1.0, float(momentum)))
    balance = max(0.30, min(0.70, 0.5 + 0.22 * momentum))
    lambda_a = max(1e-4, expected_total * balance)
    lambda_b = max(1e-4, expected_total * (1.0 - balance))

    max_lambda = max(lambda_a, lambda_b)
    k_max = int(max(18, math.ceil(max_lambda + 9.5 * math.sqrt(max_lambda + 1.0))))
    pmf_a = _poisson_pmf_series(lambda_a, k_max)
    pmf_b = _poisson_pmf_series(lambda_b, k_max)

    cdf_b: list[float] = []
    running = 0.0
    for p in pmf_b:
        running += p
        cdf_b.append(running)

    # Mevcut skor farkini dahil et:
    # final_diff = diff + future_a - future_b
    # A kazanir <=> future_b < future_a + diff
    # Beraberlik <=> future_b == future_a + diff
    p_a_win = 0.0
    p_draw = 0.0
    max_idx_b = len(pmf_b) - 1
    for idx_a, p_a in enumerate(pmf_a):
        threshold_b = idx_a + diff
        less_idx = threshold_b - 1
        if less_idx < 0:
            less_b = 0.0
        elif less_idx >= max_idx_b:
            less_b = 1.0
        else:
            less_b = cdf_b[less_idx]
        p_a_win += p_a * less_b

        if 0 <= threshold_b <= max_idx_b:
            p_draw += p_a * pmf_b[threshold_b]

    p_b_win = max(0.0, 1.0 - p_a_win - p_draw)
    raw_a, raw_d, raw_b = _normalize_probs(p_a_win, p_draw, p_b_win)

    # Erken oyunda oranlarin asiri ziplamasini azaltan hafif prior.
    adv = max(-1.0, min(1.0, diff * 0.28))
    prior_a = 0.42 + 0.16 * adv
    prior_b = 0.42 - 0.16 * adv
    prior_d = max(0.08, 1.0 - prior_a - prior_b)
    prior_a, prior_d, prior_b = _normalize_probs(prior_a, prior_d, prior_b)

    prior_weight = 0.50 * (remaining ** 1.2)
    blended_a = raw_a * (1.0 - prior_weight) + prior_a * prior_weight
    blended_d = raw_d * (1.0 - prior_weight) + prior_d * prior_weight
    blended_b = raw_b * (1.0 - prior_weight) + prior_b * prior_weight

    return _normalize_probs(blended_a, blended_d, blended_b)


def _estimate_live_position_edge(
    active_balls: list[dict],
    team_a_key: str,
    team_b_key: str,
    goal_center_x: float,
    goal_half_width: float,
    peg_top_y: float,
    exit_line_y: float,
) -> float:
    """
    Toplarin anlik konumuna gore -1..1 arasi "kim daha avantajli" skoru.
    +1 -> Team A avantaji, -1 -> Team B avantaji.
    """
    if not active_balls:
        return 0.0

    span_y = max(1.0, exit_line_y - peg_top_y)
    threat_a = 0.0
    threat_b = 0.0

    for ball in active_balls:
        key = str(ball.get("team_key", ""))
        if key not in {team_a_key, team_b_key}:
            continue

        x = float(ball.get("x", 0.0))
        y = float(ball.get("y", 0.0))
        vx = float(ball.get("vx", 0.0))
        vy = float(ball.get("vy", 0.0))
        radius = max(6.0, float(ball.get("radius", 0.0)))

        depth = max(0.0, min(1.0, (y - peg_top_y) / span_y))
        depth_w = 0.22 + 0.78 * (depth ** 1.45)

        dx = abs(x - goal_center_x)
        proximity = max(0.0, 1.0 - dx / max(36.0, goal_half_width * 1.40))
        proximity = proximity ** 1.85

        toward_center = 1.0 if (goal_center_x - x) * vx > 0 else 0.0
        motion_center_w = 0.30 + 0.70 * toward_center
        fall_w = max(0.0, min(1.0, (vy + 140.0) / 720.0))

        threat = depth_w * (0.60 * proximity + 0.26 * fall_w + 0.14 * motion_center_w)

        imminent = (
            y >= (exit_line_y - (160.0 + radius * 1.3))
            and dx <= max(goal_half_width * 0.92, radius * 1.2)
        )
        if imminent:
            threat += 0.22

        if key == team_a_key:
            threat_a += threat
        else:
            threat_b += threat

    denom = threat_a + threat_b + 0.28
    edge = (threat_a - threat_b) / denom
    return max(-1.0, min(1.0, edge))


def _plan_extra_time_goal_triggers(
    *,
    match_id: str,
    team_a_key: str,
    team_b_key: str,
    regular_score_a: int,
    regular_score_b: int,
    et_score_a: int,
    et_score_b: int,
    et_video_seconds: float,
) -> list[tuple[float, str]]:
    events: list[tuple[float, str]] = []
    if et_video_seconds <= 0:
        return events
    seed = (
        f"et_timeline:{match_id}:{team_a_key}:{team_b_key}:"
        f"{regular_score_a}:{regular_score_b}:{et_score_a}:{et_score_b}"
    )
    rng = random.Random(seed)
    pad = min(1.2, max(0.2, et_video_seconds * 0.12))
    start = pad
    end = max(start + 0.01, et_video_seconds - pad)
    for _ in range(max(0, int(et_score_a))):
        events.append((rng.uniform(start, end), team_a_key))
    for _ in range(max(0, int(et_score_b))):
        events.append((rng.uniform(start, end), team_b_key))
    events.sort(key=lambda item: item[0])
    return events


def _compute_penalty_display(
    kicks: list[dict],
    shown_count: int,
) -> tuple[int, int, list[str], list[str]]:
    a_score = 0
    b_score = 0
    a_marks: list[str] = []
    b_marks: list[str] = []
    limit = max(0, min(int(shown_count), len(kicks)))
    for kick in kicks[:limit]:
        team = str(kick.get("team") or "")
        scored = bool(kick.get("scored", False))
        mark = "GOAL" if scored else "MISS"
        if team == "A":
            a_marks.append(mark)
            if scored:
                a_score += 1
        elif team == "B":
            b_marks.append(mark)
            if scored:
                b_score += 1
    return a_score, b_score, a_marks, b_marks


# ============================================================
# ANA SÄ°MÃœLASYON
# ============================================================

def run_simulation(
    *,
    headless: bool = False,
    fps_override: int | None = None,
    progress_every: int = 0,
    tournament_match_id: str = "",
    tournament_progress: str = "",
) -> Path:
    """
    AkÄ±ÅŸ:
    1) config yÃ¼klenir
    2) selected_match.json okunur
    3) physics + renderer seÃ§ilen takÄ±mlarla baÅŸlatÄ±lÄ±r
    4) sabit 60 saniyelik / 60 FPS export yapÄ±lÄ±r
    """
    cfg = build_default_config()
    if fps_override is not None and int(fps_override) > 0:
        cfg = replace(cfg, video=replace(cfg.video, fps=int(fps_override)))
    repository = TeamRepository(cfg.data_dir)

    match_selection = repository.load_selected_match()
    if match_selection is None:
        raise FileNotFoundError(
            "Seçili maç bulunamadı.\n"
            "Önce match_selector.py üzerinden iki takım seçip kaydetmelisin."
        )

    if getattr(match_selection, "engine_mode", None) == "rotating_arena":
        import rotating_arena
        cfg = build_default_config()
        if fps_override is not None and int(fps_override) > 0:
            cfg = replace(cfg, video=replace(cfg.video, fps=int(fps_override)))
        video_preset = get_video_preset(getattr(match_selection, "video_preset", None))
        
        output_dir = cfg.base_dir / "output"
        output_dir.mkdir(parents=True, exist_ok=True)
        video_filename = generate_output_filename(match_selection)
        video_output_path = output_dir / video_filename
        
        # Build the config dictionary for rotating_arena.run:
        ra_config = {
            "width": cfg.video.width,
            "height": cfg.video.height,
            "fps": cfg.video.fps,
            "duration_seconds": video_preset.total_duration_seconds,
            "intro_seconds": video_preset.intro_seconds,
            "outro_seconds": video_preset.outro_seconds,
            "headless": headless,
            "title": match_selection.title,
            "team_a": {
                "name": match_selection.team_a.name,
                "short_name": match_selection.team_a.short_name,
                "score": 0,
                "color": (220, 72, 72),
                "badge_file": match_selection.team_a.badge_file or "",
                "role": "A"
            },
            "team_b": {
                "name": match_selection.team_b.name,
                "short_name": match_selection.team_b.short_name,
                "score": 0,
                "color": (79, 137, 255),
                "badge_file": match_selection.team_b.badge_file or "",
                "role": "B"
            },
            "output_path": str(video_output_path),
            "background_music_path": str(Path(__file__).resolve().parent / "data" / "sounds" / "normalbg.mp3")
        }
        
        print("=" * 60)
        print("ROTATING ARENA EXPORT BASLADI")
        print(f"Eslesme              : {match_selection.title}")
        print(f"Cikti                : {video_output_path}")
        print("=" * 60)
        final_path = rotating_arena.run(ra_config)
        return Path(final_path)

    video_preset = get_video_preset(getattr(match_selection, "video_preset", None))
    cfg = replace(cfg, video=replace(cfg.video, total_duration_seconds=video_preset.total_duration_seconds))

    # Benzersiz dosya adÄ± Ã¼ret
    output_dir = cfg.base_dir / "output"
    output_dir.mkdir(parents=True, exist_ok=True)
    video_filename = generate_output_filename(match_selection)
    video_output_path = output_dir / video_filename

    pygame.init()
    screen = None
    preview_width = 0
    preview_height = 0
    if not headless:
        preview_max_height = 780
        preview_scale = min(1.0, preview_max_height / cfg.video.height)
        preview_width = max(360, int(cfg.video.width * preview_scale))
        preview_height = max(640, int(cfg.video.height * preview_scale))
        pygame.display.set_caption("Marble Football Race Exporter Preview")
        screen = pygame.display.set_mode((preview_width, preview_height))
    render_surface = pygame.Surface((cfg.video.width, cfg.video.height))
    clock = pygame.time.Clock()

    physics = MarbleRacePhysics(cfg, match_selection)
    renderer = MarbleRaceRenderer(cfg)
    penalty_renderer = PenaltyRenderer(cfg)
    normalized_mode = (match_selection.engine_mode or "").strip().lower()
    if normalized_mode == "football_rail_test":
        normalized_mode = "normal"
    football_var_mode = normalized_mode == "football_var"
    football_guided_mode = normalized_mode == "football_result_guided_test"
    start_event_type = "whistle_start"
    score_event_type = "goal"
    end_event_type = "whistle_end"
    is_tournament_run = bool(str(tournament_match_id or "").strip())
    knockout_mode_enabled = is_tournament_run

    fixed_dt = 1.0 / cfg.video.fps
    base_video_seconds = cfg.video.total_duration_seconds
    total_frames = cfg.total_video_frames
    intro_seconds = video_preset.intro_seconds
    outro_seconds = video_preset.outro_seconds
    gameplay_seconds = max(1.0, base_video_seconds - intro_seconds - outro_seconds)
    regular_video_seconds = gameplay_seconds
    extra_time_video_seconds = 0.0
    penalties_video_seconds = 0.0
    configured_extra_time_video_seconds = 18.0
    configured_penalties_video_seconds = 14.0
    et_goal_triggers: list[tuple[float, str]] = []
    et_goal_next_idx = 0
    et_goal_offset = 0.0
    penalty_kicks: list[dict] = []
    penalty_kick_times: list[float] = []
    penalty_revealed_count = 0
    knockout_resolution: dict | None = None
    knockout_final_resolution: dict | None = None
    frozen_snapshot: dict | None = None
    extra_time_frozen_snapshot: dict | None = None
    penalty_frozen_snapshot: dict | None = None
    var_rng = random.Random(cfg.gameplay.random_seed)
    var_check_probability = 0.20
    var_cancel_probability = 0.30
    var_check_duration = 1.85
    var_result_duration = 0.95
    var_extra_seconds = 0.0
    guided_extra_seconds = 0.0
    guided_extra_cap_seconds = 36.0
    guided_next_extend_at = 0.0
    guided_forced_total_seconds: float | None = None
    guided_lock_min_progress = 0.62
    guided_target_a = match_selection.guided_target_score_a
    guided_target_b = match_selection.guided_target_score_b
    var_pending_reviews: list[dict] = []
    active_var_review: dict | None = None

    print("=" * 60)
    print("FOOTBALL RACE EXPORT BASLADI")
    print(f"Eslesme              : {match_selection.title}")
    print(f"Cozunurluk           : {cfg.video.width}x{cfg.video.height}")
    print(f"FPS                  : {cfg.video.fps}")
    print(f"Video suresi         : {cfg.video.total_duration_seconds:.2f} saniye")
    print(f"Toplam frame         : {total_frames}")
    print(f"Simule mac suresi    : {cfg.gameplay.simulated_match_minutes:.2f} dakika")
    print(f"Cikti                : {video_output_path}")
    if headless:
        print("Render mode          : HEADLESS")
    if tournament_match_id:
        print(f"Tournament match     : {tournament_match_id}")
    if tournament_progress:
        print(f"Tournament progress  : {tournament_progress}")
    if knockout_mode_enabled:
        print("Knockout rules       : 90 + ET(+15,+15) + PEN")
    print("=" * 60)

    running = True
    exported_frames = 0

    # Ses event timeline'Ä±
    audio_events: list[dict] = []
    seen_goal_count = 0
    whistle_start_added = False
    last_hit_sound_time: float = -1.0
    live_probs: tuple[float, float, float] | None = None
    last_score_tuple: tuple[int, int] | None = None
    seen_round_event_keys: set[tuple[int, str, str, float]] = set()
    recent_scoring_events: list[tuple[float, str]] = []
    max_progress_ratio = 0.0
    final_score_a = 0
    final_score_b = 0
    final_team_a_key = match_selection.team_a.team_key
    final_team_b_key = match_selection.team_b.team_key
    progress_every = max(0, int(progress_every))
    render_start_ts = time.perf_counter()

    try:
        with Mp4VideoWriter(cfg, output_path=video_output_path) as writer:
            frame_index = 0
            while True:
                regular_phase_seconds = regular_video_seconds + var_extra_seconds + guided_extra_seconds
                if guided_forced_total_seconds is not None and not knockout_mode_enabled:
                    regular_phase_seconds = min(
                        regular_phase_seconds,
                        max(1.0, guided_forced_total_seconds - intro_seconds - outro_seconds),
                    )
                gameplay_seconds = max(
                    1.0,
                    regular_phase_seconds + extra_time_video_seconds + penalties_video_seconds,
                )
                total_video_seconds = intro_seconds + gameplay_seconds + outro_seconds
                total_frames = int(round(cfg.video.fps * total_video_seconds))
                if frame_index >= total_frames:
                    break
                if not headless:
                    for event in pygame.event.get():
                        if event.type == pygame.QUIT:
                            running = False

                if not running:
                    break

                video_seconds_elapsed = (frame_index + 1) / cfg.video.fps
                is_intro = video_seconds_elapsed < intro_seconds
                is_outro = video_seconds_elapsed >= max(0.0, total_video_seconds - outro_seconds)
                gameplay_elapsed = min(max(video_seconds_elapsed - intro_seconds, 0.0), gameplay_seconds)

                regular_phase_end = regular_phase_seconds
                extra_phase_end = regular_phase_end + extra_time_video_seconds
                penalties_phase_end = extra_phase_end + penalties_video_seconds
                if is_intro:
                    match_phase = "intro"
                elif gameplay_elapsed < regular_phase_end:
                    match_phase = "regular_time"
                elif extra_time_video_seconds > 0.0 and gameplay_elapsed < extra_phase_end:
                    match_phase = "extra_time"
                elif penalties_video_seconds > 0.0 and gameplay_elapsed < penalties_phase_end:
                    match_phase = "penalties"
                elif is_outro:
                    match_phase = "outro"
                elif penalties_video_seconds > 0.0:
                    match_phase = "penalties"
                elif extra_time_video_seconds > 0.0:
                    match_phase = "extra_time"
                else:
                    match_phase = "regular_time"

                tension_active = False
                tension_progress = 0.0
                tension_cfg = cfg.tension
                gravity_override: float | None = None
                if not is_intro and not is_outro and match_phase == "regular_time":
                    live_score_a = int(physics.scores.get(physics.team_a_key, 0))
                    live_score_b = int(physics.scores.get(physics.team_b_key, 0))
                    score_diff = abs(live_score_a - live_score_b)
                    live_progress = min(1.0, max(0.0, max_progress_ratio))
                    if (
                        live_progress >= tension_cfg.threshold_progress
                        and score_diff <= tension_cfg.max_score_diff
                    ):
                        tension_active = True
                        span = max(1e-6, 1.0 - tension_cfg.threshold_progress)
                        tension_progress = min(1.0, (live_progress - tension_cfg.threshold_progress) / span)
                        gravity_override = float(cfg.physics.gravity_y) * tension_cfg.gravity_multiplier

                if not is_intro and not is_outro and match_phase not in {"extra_time", "penalties"}:
                    if not (football_var_mode and active_var_review is not None):
                        physics.update(fixed_dt, gravity_override=gravity_override)
                        frozen_snapshot = None

                    # BaÅŸlangÄ±Ã§ dÃ¼dÃ¼ÄŸÃ¼ â€” gameplay baÅŸladÄ±ÄŸÄ±nda
                    if not whistle_start_added:
                        audio_events.append({
                            "type": start_event_type,
                            "time": round(video_seconds_elapsed, 2),
                        })
                        whistle_start_added = True

                raw_progress_ratio = gameplay_elapsed / gameplay_seconds
                progress_ratio = max(max_progress_ratio, min(1.0, raw_progress_ratio))
                max_progress_ratio = progress_ratio
                if regular_phase_seconds <= 1e-6:
                    current_match_seconds = 0.0
                elif gameplay_elapsed <= regular_phase_end:
                    current_match_seconds = 90.0 * 60.0 * (gameplay_elapsed / max(1e-6, regular_phase_seconds))
                elif extra_time_video_seconds > 0.0 and gameplay_elapsed <= extra_phase_end:
                    et_elapsed = gameplay_elapsed - regular_phase_end
                    current_match_seconds = 90.0 * 60.0 + 30.0 * 60.0 * (
                        et_elapsed / max(1e-6, extra_time_video_seconds)
                    )
                else:
                    current_match_seconds = 120.0 * 60.0
                current_match_clock = format_match_clock(current_match_seconds)

                if is_outro:
                    if frozen_snapshot is None:
                        frozen_snapshot = physics.get_state_snapshot()
                        # BitiÅŸ dÃ¼dÃ¼ÄŸÃ¼ â€” outro baÅŸladÄ±ÄŸÄ±nda
                        audio_events.append({
                            "type": end_event_type,
                            "time": round(video_seconds_elapsed, 2),
                        })
                    snapshot = dict(frozen_snapshot)
                    active_balls = []
                elif match_phase == "penalties":
                    if penalty_frozen_snapshot is None:
                        penalty_frozen_snapshot = physics.get_state_snapshot()
                    snapshot = dict(penalty_frozen_snapshot)
                    active_balls = []
                elif match_phase == "extra_time" and knockout_mode_enabled and knockout_resolution is not None:
                    if extra_time_frozen_snapshot is None:
                        extra_time_frozen_snapshot = physics.get_state_snapshot()
                    snapshot = dict(extra_time_frozen_snapshot)
                    active_balls = []
                else:
                    penalty_frozen_snapshot = None
                    extra_time_frozen_snapshot = None
                    snapshot = physics.get_state_snapshot()
                    active_balls = physics.get_active_ball_draw_data()

                snapshot_needs_refresh = False
                teams_for_odds = snapshot.get("teams", [])
                scoring_gap_label = str(snapshot.get("scoring_gap_label", "GOAL"))
                confirmed_scoring_events: list[dict] = []

                for evt in snapshot.get("latest_round_events", []):
                    evt_key = (
                        int(evt.get("round_index", 0)),
                        str(evt.get("team_key", "")),
                        str(evt.get("gap_label", "")),
                        round(float(evt.get("x_at_exit", 0.0)), 2),
                    )
                    if evt_key in seen_round_event_keys:
                        continue
                    seen_round_event_keys.add(evt_key)
                    if str(evt.get("gap_label", "")) != scoring_gap_label:
                        continue

                    event_team_key = str(evt.get("team_key", ""))
                    event_team_name = str(evt.get("team_name", ""))
                    if football_var_mode:
                        if var_rng.random() < var_check_probability:
                            is_cancelled = var_rng.random() < var_cancel_probability
                            var_pending_reviews.append(
                                {
                                    "team_key": event_team_key,
                                    "team_name": event_team_name,
                                    "cancelled": is_cancelled,
                                    "round_index": int(evt.get("round_index", 0)),
                                    "gap_label": str(evt.get("gap_label", "")),
                                    "x_at_exit": float(evt.get("x_at_exit", 0.0)),
                                }
                            )
                            var_extra_seconds += var_check_duration + var_result_duration
                        else:
                            physics.register_confirmed_goal(event_team_key)
                            confirmed_scoring_events.append(
                                {
                                    "round_index": int(evt.get("round_index", 0)),
                                    "team_key": event_team_key,
                                    "team_name": event_team_name,
                                    "gap_label": str(evt.get("gap_label", "")),
                                    "x_at_exit": float(evt.get("x_at_exit", 0.0)),
                                }
                            )
                            recent_scoring_events.append((video_seconds_elapsed, event_team_key))
                            snapshot_needs_refresh = True
                    else:
                        confirmed_scoring_events.append(
                            {
                                "round_index": int(evt.get("round_index", 0)),
                                "team_key": event_team_key,
                                "team_name": event_team_name,
                                "gap_label": str(evt.get("gap_label", "")),
                                "x_at_exit": float(evt.get("x_at_exit", 0.0)),
                            }
                        )
                        recent_scoring_events.append((video_seconds_elapsed, event_team_key))

                if football_var_mode and active_var_review is None and var_pending_reviews and not is_intro and not is_outro:
                    next_review = var_pending_reviews.pop(0)
                    active_var_review = {
                        "team_key": str(next_review.get("team_key", "")),
                        "team_name": str(next_review.get("team_name", "")),
                        "cancelled": bool(next_review.get("cancelled", False)),
                        "round_index": int(next_review.get("round_index", 0)),
                        "gap_label": str(next_review.get("gap_label", scoring_gap_label)),
                        "x_at_exit": float(next_review.get("x_at_exit", 0.0)),
                        "start_time": video_seconds_elapsed,
                        "resolved": False,
                    }

                if football_var_mode and active_var_review is not None:
                    elapsed_review = max(0.0, video_seconds_elapsed - float(active_var_review.get("start_time", 0.0)))
                    if elapsed_review >= (var_check_duration + var_result_duration):
                        if not bool(active_var_review.get("resolved", False)):
                            if not bool(active_var_review.get("cancelled", False)):
                                review_team_key = str(active_var_review.get("team_key", ""))
                                physics.register_confirmed_goal(review_team_key)
                                confirmed_scoring_events.append(
                                    {
                                        "round_index": int(active_var_review.get("round_index", 0)),
                                        "team_key": review_team_key,
                                        "team_name": str(active_var_review.get("team_name", "")),
                                        "gap_label": str(active_var_review.get("gap_label", scoring_gap_label)),
                                        "x_at_exit": float(active_var_review.get("x_at_exit", 0.0)),
                                    }
                                )
                                recent_scoring_events.append((video_seconds_elapsed, review_team_key))
                                snapshot_needs_refresh = True
                            active_var_review["resolved"] = True
                        active_var_review = None

                if snapshot_needs_refresh and not is_outro:
                    snapshot = physics.get_state_snapshot()
                    active_balls = physics.get_active_ball_draw_data()
                    teams_for_odds = snapshot.get("teams", [])

                if football_var_mode:
                    if active_var_review is None:
                        snapshot["var_review"] = {"active": False}
                    else:
                        elapsed_review = max(0.0, video_seconds_elapsed - float(active_var_review.get("start_time", 0.0)))
                        if elapsed_review < var_check_duration:
                            phase = "checking"
                            decision = "pending"
                            phase_progress = min(1.0, elapsed_review / var_check_duration)
                        else:
                            phase = "result"
                            decision = "cancelled" if bool(active_var_review.get("cancelled", False)) else "confirmed"
                            phase_progress = min(1.0, (elapsed_review - var_check_duration) / var_result_duration)
                        snapshot["var_review"] = {
                            "active": True,
                            "team_name": str(active_var_review.get("team_name", "")),
                            "phase": phase,
                            "decision": decision,
                            "progress": phase_progress,
                        }
                else:
                    snapshot["var_review"] = {"active": False}

                snapshot["confirmed_scoring_events"] = confirmed_scoring_events

                current_goals = sum(physics.scores.values())
                if not is_intro and current_goals > seen_goal_count:
                    for _ in range(current_goals - seen_goal_count):
                        audio_events.append(
                            {
                                "type": score_event_type,
                                "time": round(video_seconds_elapsed, 2),
                            }
                        )
                    seen_goal_count = current_goals

                teams_for_odds = snapshot.get("teams", [])
                team_a_meta = next(
                    (team for team in teams_for_odds if team.get("role") == "A"),
                    teams_for_odds[0] if teams_for_odds else {},
                )
                team_b_meta = next(
                    (team for team in teams_for_odds if team.get("role") == "B"),
                    teams_for_odds[1] if len(teams_for_odds) > 1 else {},
                )
                team_a_key = str(team_a_meta.get("team_key", ""))
                team_b_key = str(team_b_meta.get("team_key", ""))
                score_a = int(team_a_meta.get("score", 0))
                score_b = int(team_b_meta.get("score", 0))

                if (
                    knockout_mode_enabled
                    and knockout_resolution is None
                    and gameplay_elapsed >= regular_phase_end
                ):
                    knockout_resolution = resolve_single_leg_knockout(
                        match_id=str(tournament_match_id or ""),
                        team_a_key=team_a_key,
                        team_b_key=team_b_key,
                        regular_score_a=score_a,
                        regular_score_b=score_b,
                    )
                    knockout_final_resolution = dict(knockout_resolution)
                    decided_by_now = str(knockout_resolution.get("decided_by") or "normal_time")
                    if decided_by_now in {"extra_time", "penalties"}:
                        extra_time_video_seconds = configured_extra_time_video_seconds
                        # Regular time bitişinde anında snapshot al (else branch sıfırlamadan önce değil,
                        # ama bu frame'de knockout hesaplandıktan hemen sonra — bir frame gecikmeyi önler)
                        extra_time_frozen_snapshot = physics.get_state_snapshot()
                        et_goal_offset = regular_phase_end
                        et_goal_next_idx = 0
                        et_goal_triggers = _plan_extra_time_goal_triggers(
                            match_id=str(tournament_match_id or ""),
                            team_a_key=team_a_key,
                            team_b_key=team_b_key,
                            regular_score_a=score_a,
                            regular_score_b=score_b,
                            et_score_a=int(knockout_resolution.get("extra_time_score_a") or 0),
                            et_score_b=int(knockout_resolution.get("extra_time_score_b") or 0),
                            et_video_seconds=extra_time_video_seconds,
                        )
                    if decided_by_now == "penalties":
                        penalties_video_seconds = configured_penalties_video_seconds
                        penalty_kicks = list(knockout_resolution.get("penalty_kicks") or [])
                        penalty_revealed_count = 0
                        if penalty_kicks:
                            step = penalties_video_seconds / max(1, len(penalty_kicks) + 1)
                            penalty_kick_times = [step * (i + 1) for i in range(len(penalty_kicks))]
                        else:
                            penalty_kick_times = []
                    print(
                        "KNOCKOUT_DECISION:"
                        f"FT {score_a}-{score_b} -> "
                        f"{int(knockout_resolution.get('score_a', score_a))}"
                        f"-{int(knockout_resolution.get('score_b', score_b))} "
                        f"({decided_by_now})"
                    )

                if (
                    knockout_mode_enabled
                    and et_goal_triggers
                    and match_phase == "extra_time"
                    and not is_outro
                ):
                    et_elapsed = max(0.0, gameplay_elapsed - et_goal_offset)
                    while et_goal_next_idx < len(et_goal_triggers):
                        trigger_at, trigger_team_key = et_goal_triggers[et_goal_next_idx]
                        if et_elapsed + 1e-6 < trigger_at:
                            break
                        physics.register_confirmed_goal(trigger_team_key)
                        recent_scoring_events.append((video_seconds_elapsed, trigger_team_key))
                        snapshot_needs_refresh = True
                        et_goal_next_idx += 1

                if snapshot_needs_refresh and not is_outro:
                    snapshot = physics.get_state_snapshot()
                    if match_phase == "extra_time":
                        extra_time_frozen_snapshot = dict(snapshot)
                        active_balls = []
                    elif match_phase == "penalties":
                        penalty_frozen_snapshot = dict(snapshot)
                        active_balls = []
                    else:
                        active_balls = physics.get_active_ball_draw_data()
                    teams_for_odds = snapshot.get("teams", [])
                    team_a_meta = next(
                        (team for team in teams_for_odds if team.get("role") == "A"),
                        teams_for_odds[0] if teams_for_odds else {},
                    )
                    team_b_meta = next(
                        (team for team in teams_for_odds if team.get("role") == "B"),
                        teams_for_odds[1] if len(teams_for_odds) > 1 else {},
                    )
                    score_a = int(team_a_meta.get("score", 0))
                    score_b = int(team_b_meta.get("score", 0))

                penalty_display_a = 0
                penalty_display_b = 0
                penalty_marks_a: list[str] = []
                penalty_marks_b: list[str] = []
                penalty_kick_progress = 0.0
                penalty_current_kick: dict | None = None
                penalty_phase_start = regular_phase_end + extra_time_video_seconds
                if (
                    knockout_mode_enabled
                    and penalty_kicks
                    and penalties_video_seconds > 0.0
                    and match_phase == "penalties"
                ):
                    penalty_elapsed = max(0.0, gameplay_elapsed - penalty_phase_start)
                    while (
                        penalty_revealed_count < len(penalty_kicks)
                        and penalty_revealed_count < len(penalty_kick_times)
                        and penalty_elapsed + 1e-6 >= penalty_kick_times[penalty_revealed_count]
                    ):
                        kick = penalty_kicks[penalty_revealed_count]
                        if bool(kick.get("scored", False)):
                            audio_events.append(
                                {
                                    "type": score_event_type,
                                    "time": round(video_seconds_elapsed, 2),
                                }
                            )
                        penalty_revealed_count += 1

                    (
                        penalty_display_a,
                        penalty_display_b,
                        penalty_marks_a,
                        penalty_marks_b,
                    ) = _compute_penalty_display(penalty_kicks, penalty_revealed_count)

                    # Mevcut atışın animasyon ilerlemesi (0-1)
                    if penalty_revealed_count > 0 and penalty_kicks:
                        kick_idx = penalty_revealed_count - 1
                        penalty_current_kick = penalty_kicks[kick_idx]
                        last_t = penalty_kick_times[kick_idx] if kick_idx < len(penalty_kick_times) else 0.0
                        if penalty_revealed_count < len(penalty_kick_times):
                            next_t = penalty_kick_times[penalty_revealed_count]
                        else:
                            next_t = penalties_video_seconds
                        window = max(0.001, next_t - last_t)
                        penalty_kick_progress = min(1.0, max(0.0, (penalty_elapsed - last_t) / window))

                final_score_a = score_a
                final_score_b = score_b
                if knockout_final_resolution is not None:
                    final_score_a = int(knockout_final_resolution.get("score_a", final_score_a))
                    final_score_b = int(knockout_final_resolution.get("score_b", final_score_b))
                if team_a_key:
                    final_team_a_key = team_a_key
                if team_b_key:
                    final_team_b_key = team_b_key
                should_log_progress = (
                    progress_every > 0
                    and (
                        frame_index == 0
                        or frame_index % progress_every == 0
                        or (frame_index + 1) >= total_frames
                    )
                )
                if should_log_progress:
                    elapsed = max(1e-6, time.perf_counter() - render_start_ts)
                    produced = frame_index + 1
                    proc_fps = produced / elapsed
                    remain_frames = max(0, total_frames - produced)
                    eta_seconds = remain_frames / proc_fps if proc_fps > 1e-6 else 0.0
                    pct = (produced / max(1, total_frames)) * 100.0
                    match_tag = f"[{tournament_match_id}] " if tournament_match_id else ""
                    tourn_tag = f"[{tournament_progress}] " if tournament_progress else ""
                    score_part = f"{score_a}-{score_b}"
                    if match_phase == "penalties":
                        score_part += f" | pen {penalty_display_a}-{penalty_display_b}"
                    print(
                        f"PROGRESS {match_tag}{tourn_tag}"
                        f"{produced}/{total_frames} ({pct:.1f}%) | "
                        f"clock {current_match_clock} | phase {match_phase} | score {score_part} | "
                        f"speed {proc_fps:.1f} fps | ETA {eta_seconds:.1f}s"
                    )

                if football_guided_mode and not is_intro and not knockout_mode_enabled:
                    target_a = guided_target_a
                    target_b = guided_target_b
                    if target_a is not None and target_b is not None:
                        missing_a = max(0, int(target_a) - score_a)
                        missing_b = max(0, int(target_b) - score_b)
                        missing_total = missing_a + missing_b
                        near_tail = video_seconds_elapsed >= (total_video_seconds - (outro_seconds + 1.8))
                        can_extend = guided_extra_seconds < guided_extra_cap_seconds
                        if (
                            missing_total > 0
                            and near_tail
                            and can_extend
                            and guided_forced_total_seconds is None
                            and video_seconds_elapsed >= guided_next_extend_at
                        ):
                            guided_extra_seconds += min(2.0, guided_extra_cap_seconds - guided_extra_seconds)
                            guided_next_extend_at = video_seconds_elapsed + 0.90
                        if (
                            missing_total == 0
                            and progress_ratio >= guided_lock_min_progress
                            and guided_forced_total_seconds is None
                        ):
                            guided_forced_total_seconds = video_seconds_elapsed + outro_seconds

                momentum_window = 14.0
                cutoff_time = video_seconds_elapsed - momentum_window
                recent_scoring_events = [evt for evt in recent_scoring_events if evt[0] >= cutoff_time]
                recent_a = sum(1 for _, key in recent_scoring_events if key == team_a_key)
                recent_b = sum(1 for _, key in recent_scoring_events if key == team_b_key)
                momentum = (recent_a - recent_b) / max(1, recent_a + recent_b)

                target_probs = _estimate_live_outcome_probs(
                    score_a=score_a,
                    score_b=score_b,
                    remaining_ratio=max(0.0, 1.0 - progress_ratio),
                    engine_mode=normalized_mode,
                    momentum=momentum,
                )
                if match_phase == "penalties":
                    if penalty_display_a > penalty_display_b:
                        target_probs = (0.84, 0.0, 0.16)
                    elif penalty_display_b > penalty_display_a:
                        target_probs = (0.16, 0.0, 0.84)
                    else:
                        target_probs = (0.50, 0.0, 0.50)
                rail_position_edge = 0.0
                if not is_intro and not is_outro and match_phase != "penalties":
                    rail_position_edge = _estimate_live_position_edge(
                        active_balls=active_balls,
                        team_a_key=team_a_key,
                        team_b_key=team_b_key,
                        goal_center_x=float(cfg.playfield_center_x),
                        goal_half_width=float(cfg.layout.goal_gap_width) / 2.0,
                        peg_top_y=float(cfg.layout.peg_top_y),
                        exit_line_y=float(cfg.layout.exit_line_y),
                    )
                    # Baslangicta oranin ortadan acilmasi icin konum etkisini
                    # kademeli ac (ani sola/saga kayma olmasin).
                    pos_edge_ramp = max(0.0, min(1.0, (gameplay_elapsed - 1.0) / 5.5))
                    p_a, p_d, p_b = target_probs
                    swing = 0.10 * rail_position_edge * pos_edge_ramp
                    p_a += swing
                    p_b -= swing
                    p_d *= 1.0 - min(0.16, abs(rail_position_edge) * 0.14 * pos_edge_ramp)
                    target_probs = _normalize_probs(p_a, p_d, p_b)

                remaining_ratio = max(0.0, 1.0 - progress_ratio)
                current_score_tuple = (score_a, score_b)
                if live_probs is None or remaining_ratio <= 0.02 or is_outro:
                    live_probs = target_probs
                else:
                    alpha = 0.10
                    if last_score_tuple is not None and current_score_tuple != last_score_tuple:
                        alpha = 0.45
                    elif recent_a + recent_b > 0:
                        alpha = 0.16
                    elif abs(rail_position_edge) >= 0.35:
                        alpha = 0.15
                    live_probs = (
                        live_probs[0] + alpha * (target_probs[0] - live_probs[0]),
                        live_probs[1] + alpha * (target_probs[1] - live_probs[1]),
                        live_probs[2] + alpha * (target_probs[2] - live_probs[2]),
                    )
                    live_probs = _normalize_probs(*live_probs)
                last_score_tuple = current_score_tuple
                snapshot["win_probabilities"] = {
                    "team_a": live_probs[0],
                    "draw": live_probs[1],
                    "team_b": live_probs[2],
                }
                snapshot["rail_position_edge"] = rail_position_edge

                snapshot["match_clock_text"] = current_match_clock
                snapshot["match_progress_ratio"] = progress_ratio
                snapshot["match_phase"] = match_phase
                snapshot["video_frame_index"] = frame_index
                snapshot["video_total_frames"] = total_frames
                snapshot["video_seconds_elapsed"] = video_seconds_elapsed
                snapshot["video_seconds_total"] = total_video_seconds
                snapshot["show_full_time_overlay"] = is_outro
                snapshot["show_hook_overlay"] = is_intro
                snapshot["hook_progress"] = min(1.0, video_seconds_elapsed / intro_seconds) if intro_seconds else 1.0
                snapshot["show_final_result_overlay"] = is_outro
                snapshot["final_result_progress"] = (
                    min(1.0, (video_seconds_elapsed - (total_video_seconds - outro_seconds)) / outro_seconds)
                    if outro_seconds
                    else 1.0
                )
                snapshot["intro_seconds"] = intro_seconds
                snapshot["outro_seconds"] = outro_seconds
                snapshot["gameplay_seconds"] = gameplay_seconds
                snapshot["knockout_mode"] = knockout_mode_enabled
                snapshot["tension_active"] = tension_active
                snapshot["tension_progress"] = tension_progress
                snapshot["physics_sim_time"] = getattr(physics, "_sim_time", 0.0)
                spark_window = 3.0 / cfg.video.fps
                current_sim_time = getattr(physics, "_sim_time", 0.0)
                if hasattr(physics, "get_collision_sparks"):
                    frame_sparks = physics.get_collision_sparks(
                        since=current_sim_time - spark_window
                    )
                else:
                    frame_sparks = []
                snapshot["collision_sparks"] = frame_sparks

                if (
                    frame_sparks
                    and not is_intro
                    and not is_outro
                    and match_phase in {"regular_time", "extra_time"}
                    and not getattr(physics, "gear_mode_enabled", False)
                ):
                    strongest = max(
                        (float(s.get("impulse", 0.0)) for s in frame_sparks), default=0.0
                    )
                    if strongest >= 0.40 and (video_seconds_elapsed - last_hit_sound_time) >= 0.15:
                        audio_events.append({
                            "type": "ball_hit_peg",
                            "time": round(video_seconds_elapsed, 2),
                            "impulse": round(strongest, 2)
                        })
                        last_hit_sound_time = video_seconds_elapsed
                decided_by = "normal_time"
                regular_time_score_a = score_a
                regular_time_score_b = score_b
                extra_time_score_a = None
                extra_time_score_b = None
                penalty_score_a = None
                penalty_score_b = None
                if knockout_final_resolution is not None:
                    decided_by = str(knockout_final_resolution.get("decided_by") or "normal_time")
                    regular_time_score_a = int(knockout_final_resolution.get("regular_time_score_a", score_a))
                    regular_time_score_b = int(knockout_final_resolution.get("regular_time_score_b", score_b))
                    extra_raw_a = knockout_final_resolution.get("extra_time_score_a")
                    extra_raw_b = knockout_final_resolution.get("extra_time_score_b")
                    pen_raw_a = knockout_final_resolution.get("penalty_score_a")
                    pen_raw_b = knockout_final_resolution.get("penalty_score_b")
                    extra_time_score_a = int(extra_raw_a) if extra_raw_a is not None else None
                    extra_time_score_b = int(extra_raw_b) if extra_raw_b is not None else None
                    penalty_score_a = int(pen_raw_a) if pen_raw_a is not None else None
                    penalty_score_b = int(pen_raw_b) if pen_raw_b is not None else None
                snapshot["knockout_decided_by"] = decided_by
                snapshot["regular_time_score_a"] = regular_time_score_a
                snapshot["regular_time_score_b"] = regular_time_score_b
                snapshot["extra_time_score_a"] = extra_time_score_a
                snapshot["extra_time_score_b"] = extra_time_score_b
                snapshot["penalty_score_a"] = penalty_score_a
                snapshot["penalty_score_b"] = penalty_score_b
                snapshot["penalty_overlay_active"] = (match_phase == "penalties")
                snapshot["penalty_display_score_a"] = penalty_display_a
                snapshot["penalty_display_score_b"] = penalty_display_b
                snapshot["penalty_marks_a"] = penalty_marks_a
                snapshot["penalty_marks_b"] = penalty_marks_b
                snapshot["penalty_total_kicks"] = len(penalty_kicks)
                snapshot["penalty_shown_kicks"] = penalty_revealed_count
                snapshot["penalty_kick_progress"] = penalty_kick_progress
                snapshot["penalty_current_kick"] = penalty_current_kick
                snapshot["match_id"] = str(tournament_match_id or "")

                renderer.draw(
                    target_surface=render_surface,
                    state_snapshot=snapshot,
                    active_ball_draw_data=active_balls,
                )
                if match_phase == "penalties":
                    penalty_renderer.draw(render_surface, snapshot)

                if not headless and screen is not None:
                    preview_frame = pygame.transform.smoothscale(render_surface, (preview_width, preview_height))
                    screen.blit(preview_frame, (0, 0))
                    pygame.display.flip()
                writer.write_surface(render_surface)
                exported_frames += 1
                frame_index += 1

                if not headless:
                    clock.tick(240)

    finally:
        pygame.quit()

    total_seconds = exported_frames / cfg.video.fps if cfg.video.fps else 0
    print("=" * 60)
    print("VIDEO EXPORT TAMAMLANDI")
    print(f"Toplam frame         : {exported_frames}")
    print(f"Olusan video suresi  : {total_seconds:.2f} saniye")
    print(f"Sessiz dosya         : {video_output_path}")
    result_payload: dict[str, object] = {
        "team_a_key": final_team_a_key,
        "team_b_key": final_team_b_key,
        "score_a": int(final_score_a),
        "score_b": int(final_score_b),
        "decided_by": "normal_time",
        "regular_time_score_a": int(final_score_a),
        "regular_time_score_b": int(final_score_b),
        "extra_time_score_a": None,
        "extra_time_score_b": None,
        "penalty_score_a": None,
        "penalty_score_b": None,
    }
    if knockout_final_resolution is not None:
        result_payload["score_a"] = int(knockout_final_resolution.get("score_a", final_score_a))
        result_payload["score_b"] = int(knockout_final_resolution.get("score_b", final_score_b))
        result_payload["decided_by"] = str(knockout_final_resolution.get("decided_by") or "normal_time")
        result_payload["regular_time_score_a"] = int(
            knockout_final_resolution.get("regular_time_score_a", final_score_a)
        )
        result_payload["regular_time_score_b"] = int(
            knockout_final_resolution.get("regular_time_score_b", final_score_b)
        )
        result_payload["extra_time_score_a"] = knockout_final_resolution.get("extra_time_score_a")
        result_payload["extra_time_score_b"] = knockout_final_resolution.get("extra_time_score_b")
        result_payload["penalty_score_a"] = knockout_final_resolution.get("penalty_score_a")
        result_payload["penalty_score_b"] = knockout_final_resolution.get("penalty_score_b")
    print(
        "TOURNAMENT_RESULT_JSON:"
        + json.dumps(result_payload, ensure_ascii=False)
    )
    print("=" * 60)

    # Ses miksajÄ±
    print()
    print("=" * 60)
    print("SES MIKSAJI BASLADI")
    print(f"Ses event sayisi     : {len(audio_events)}")
    for evt in audio_events:
        print(f"  [{evt['time']:6.2f}s] {evt['type']}")
    print("=" * 60)

    final_path = video_output_path.with_name(video_output_path.stem + "_final.mp4")
    try:
        # Tek geçişte hem ses hem de 20. saniyedeki greenscreen'i işle
        result_path = mix_audio_into_video(
            video_path=video_output_path,
            event_timeline=audio_events,
            output_path=final_path,
            background_music_path=Path(__file__).resolve().parent / "data" / "sounds" / "normalbg.mp3",
            overlay_video_path=Path(__file__).resolve().parent / "likebell.mp4",
            overlay_start_time=13.0
        )
        print("=" * 60)
        print("VIDEO ISLEME TAMAMLANDI (SES + GREENSCREEN)")
        print(f"Final video          : {result_path}")
        print("=" * 60)
        return result_path
    except Exception as exc:
        print(f"[AudioMixer] Hata: {exc}")
        return video_output_path
    except Exception as exc:
        print(f"[AudioMixer] Ses miksaji basarisiz: {exc}")
        print(f"[AudioMixer] Sessiz video korunuyor: {video_output_path}")
        return video_output_path


# ============================================================
# GÄ°RÄ°Å NOKTASI
# ============================================================

def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Run single match simulation export.")
    parser.add_argument(
        "--no-messagebox",
        action="store_true",
        help="Do not show desktop message boxes on completion/failure.",
    )
    parser.add_argument("--headless", action="store_true", help="Disable preview window.")
    parser.add_argument("--fps-override", type=int, default=None, help="Override video FPS for this run.")
    parser.add_argument(
        "--progress-every",
        type=int,
        default=0,
        help="Print progress log every N frames (0 disables periodic progress logs).",
    )
    parser.add_argument("--tournament-match-id", type=str, default="")
    parser.add_argument("--tournament-progress", type=str, default="")
    args = parser.parse_args(argv)

    try:
        output_path = run_simulation(
            headless=bool(args.headless),
            fps_override=args.fps_override,
            progress_every=max(0, int(args.progress_every)),
            tournament_match_id=str(args.tournament_match_id or ""),
            tournament_progress=str(args.tournament_progress or ""),
        )
        if args.no_messagebox:
            print(f"VIDEO_OUTPUT_PATH:{output_path}")
        else:
            show_messagebox(
                title="Video HazÄ±r",
                message=f"MP4 baÅŸarÄ±yla oluÅŸturuldu:\n{output_path}",
                is_error=False,
            )
    except Exception as exc:
        if args.no_messagebox:
            print(f"SIMULATION_ERROR:{exc}", file=sys.stderr)
        else:
            show_messagebox(
                title="Hata",
                message=str(exc),
                is_error=True,
            )
        sys.exit(1)


if __name__ == "__main__":
    main()
