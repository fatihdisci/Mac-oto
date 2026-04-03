# main.py
from __future__ import annotations

import math
import random
import re
import sys
import json
import argparse
from datetime import datetime
from pathlib import Path
from tkinter import Tk, messagebox

import pygame

from audio_mixer import mix_audio_into_video
from config import build_default_config
from models import MatchSelection
from physics import MarbleRacePhysics
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
        "pop_power_pegs": 8.0,
        "pop_normal": 5.4,
        "football_shift": 6.9,
        "pop_shift": 6.5,
        "football_blink": 6.2,
        "pop_blink": 5.9,
    }
    if mode in explicit:
        return explicit[mode]

    base = 6.0
    if "power" in mode or "slowfast" in mode or "pegs" in mode:
        base += 2.0
    if "shift" in mode:
        base += 1.0
    if mode.startswith("pop_") or mode == "pop_shift":
        base -= 0.3
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


# ============================================================
# ANA SÄ°MÃœLASYON
# ============================================================

def run_simulation() -> Path:
    """
    AkÄ±ÅŸ:
    1) config yÃ¼klenir
    2) selected_match.json okunur
    3) physics + renderer seÃ§ilen takÄ±mlarla baÅŸlatÄ±lÄ±r
    4) sabit 60 saniyelik / 60 FPS export yapÄ±lÄ±r
    """
    cfg = build_default_config()
    repository = TeamRepository(cfg.data_dir)

    match_selection = repository.load_selected_match()
    if match_selection is None:
        raise FileNotFoundError(
            "SeÃ§ili maÃ§ bulunamadÄ±.\n"
            "Ã–nce match_selector.py Ã¼zerinden iki takÄ±m seÃ§ip kaydetmelisin."
        )

    # Benzersiz dosya adÄ± Ã¼ret
    output_dir = cfg.base_dir / "output"
    output_dir.mkdir(parents=True, exist_ok=True)
    video_filename = generate_output_filename(match_selection)
    video_output_path = output_dir / video_filename

    pygame.init()
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
    normalized_mode = (match_selection.engine_mode or "").strip().lower()
    if normalized_mode == "football_rail_test":
        normalized_mode = "normal"
    is_pop_mode = normalized_mode.startswith("pop_") or normalized_mode == "pop_shift"
    football_var_mode = normalized_mode == "football_var"
    football_guided_mode = normalized_mode == "football_result_guided_test"
    start_event_type = "pop_start" if is_pop_mode else "whistle_start"
    score_event_type = "pop_point" if is_pop_mode else "goal"
    end_event_type = "pop_end" if is_pop_mode else "whistle_end"

    fixed_dt = 1.0 / cfg.video.fps
    base_video_seconds = cfg.video.total_duration_seconds
    total_frames = cfg.total_video_frames
    intro_seconds = 2.0
    outro_seconds = 2.0
    gameplay_seconds = max(1.0, base_video_seconds - intro_seconds - outro_seconds)
    frozen_snapshot: dict | None = None
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
    print("=" * 60)

    running = True
    exported_frames = 0

    # Ses event timeline'Ä±
    audio_events: list[dict] = []
    seen_goal_count = 0
    whistle_start_added = False
    live_probs: tuple[float, float, float] | None = None
    last_score_tuple: tuple[int, int] | None = None
    seen_round_event_keys: set[tuple[int, str, str, float]] = set()
    recent_scoring_events: list[tuple[float, str]] = []
    max_progress_ratio = 0.0
    final_score_a = 0
    final_score_b = 0
    final_team_a_key = match_selection.team_a.team_key
    final_team_b_key = match_selection.team_b.team_key

    try:
        with Mp4VideoWriter(cfg, output_path=video_output_path) as writer:
            frame_index = 0
            while True:
                total_video_seconds = base_video_seconds + var_extra_seconds + guided_extra_seconds
                if guided_forced_total_seconds is not None:
                    total_video_seconds = min(total_video_seconds, guided_forced_total_seconds)
                total_frames = int(round(cfg.video.fps * total_video_seconds))
                if frame_index >= total_frames:
                    break
                for event in pygame.event.get():
                    if event.type == pygame.QUIT:
                        running = False

                if not running:
                    break

                video_seconds_elapsed = (frame_index + 1) / cfg.video.fps
                is_intro = video_seconds_elapsed < intro_seconds
                is_outro = video_seconds_elapsed >= max(0.0, total_video_seconds - outro_seconds)

                if not is_intro and not is_outro:
                    if not (football_var_mode and active_var_review is not None):
                        physics.update(fixed_dt)
                        frozen_snapshot = None

                    # BaÅŸlangÄ±Ã§ dÃ¼dÃ¼ÄŸÃ¼ â€” gameplay baÅŸladÄ±ÄŸÄ±nda
                    if not whistle_start_added:
                        audio_events.append({
                            "type": start_event_type,
                            "time": round(video_seconds_elapsed, 2),
                        })
                        whistle_start_added = True


                gameplay_seconds = max(1.0, total_video_seconds - intro_seconds - outro_seconds)
                gameplay_elapsed = min(max(video_seconds_elapsed - intro_seconds, 0.0), gameplay_seconds)
                raw_progress_ratio = gameplay_elapsed / gameplay_seconds
                progress_ratio = max(max_progress_ratio, min(1.0, raw_progress_ratio))
                max_progress_ratio = progress_ratio
                current_match_seconds = cfg.simulated_match_total_seconds * progress_ratio
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
                else:
                    snapshot = physics.get_state_snapshot()
                    active_balls = physics.get_active_ball_draw_data()

                snapshot_needs_refresh = False
                teams_for_odds = snapshot.get("teams", [])
                scoring_gap_label = str(snapshot.get("scoring_gap_label", "POINT" if is_pop_mode else "GOAL"))
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
                final_score_a = score_a
                final_score_b = score_b
                if team_a_key:
                    final_team_a_key = team_a_key
                if team_b_key:
                    final_team_b_key = team_b_key

                if football_guided_mode and not is_intro:
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
                rail_position_edge = 0.0
                if not is_intro and not is_outro:
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

                renderer.draw(
                    target_surface=render_surface,
                    state_snapshot=snapshot,
                    active_ball_draw_data=active_balls,
                )

                preview_frame = pygame.transform.smoothscale(render_surface, (preview_width, preview_height))
                screen.blit(preview_frame, (0, 0))
                pygame.display.flip()
                writer.write_surface(render_surface)
                exported_frames += 1
                frame_index += 1

                clock.tick(240)

    finally:
        pygame.quit()

    total_seconds = exported_frames / cfg.video.fps if cfg.video.fps else 0
    print("=" * 60)
    print("VIDEO EXPORT TAMAMLANDI")
    print(f"Toplam frame         : {exported_frames}")
    print(f"Olusan video suresi  : {total_seconds:.2f} saniye")
    print(f"Sessiz dosya         : {video_output_path}")
    print(
        "TOURNAMENT_RESULT_JSON:"
        + json.dumps(
            {
                "team_a_key": final_team_a_key,
                "team_b_key": final_team_b_key,
                "score_a": int(final_score_a),
                "score_b": int(final_score_b),
            },
            ensure_ascii=False,
        )
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
        result_path = mix_audio_into_video(
            video_path=video_output_path,
            event_timeline=audio_events,
            output_path=final_path,
        )
        print("=" * 60)
        print("SES MIKSAJI TAMAMLANDI")
        print(f"Final video          : {result_path}")
        print("=" * 60)
        return result_path
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
    args = parser.parse_args(argv)

    try:
        output_path = run_simulation()
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
