# main.py
from __future__ import annotations

import re
import sys
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
# YARDIMCI FONKSİYONLAR
# ============================================================

def show_messagebox(title: str, message: str, is_error: bool = False) -> None:
    """
    Terminale mecbur bırakmamak için basit masaüstü mesaj kutusu.
    """
    root = Tk()
    root.withdraw()

    if is_error:
        messagebox.showerror(title, message)
    else:
        messagebox.showinfo(title, message)

    root.destroy()


def _slugify(text: str) -> str:
    """Dosya adına uygun slug üret: 'Galatasaray' -> 'galatasaray'."""
    text = text.strip().lower()
    text = text.replace("&", "and")
    text = re.sub(r"[^\w\s-]", "", text, flags=re.UNICODE)
    text = re.sub(r"[\s-]+", "_", text).strip("_")
    return text or "team"


def generate_output_filename(match: MatchSelection) -> str:
    """
    Benzersiz dosya adı üret.
    Örnek: turkey_vs_greece_20260330_a3f1.mp4
    """
    team_a = _slugify(match.team_a.short_name or match.team_a.name)
    team_b = _slugify(match.team_b.short_name or match.team_b.name)
    date_str = datetime.now().strftime("%Y%m%d_%H%M%S")
    return f"{team_a}_vs_{team_b}_{date_str}.mp4"


def format_match_clock(match_seconds: float) -> str:
    """
    Maç saniyesini MM:SS formatına çevirir.
    """
    if match_seconds < 0:
        match_seconds = 0

    total_seconds = int(round(match_seconds))
    minutes = total_seconds // 60
    seconds = total_seconds % 60
    return f"{minutes:02d}:{seconds:02d}"


# ============================================================
# ANA SİMÜLASYON
# ============================================================

def run_simulation() -> Path:
    """
    Akış:
    1) config yüklenir
    2) selected_match.json okunur
    3) physics + renderer seçilen takımlarla başlatılır
    4) sabit 60 saniyelik / 60 FPS export yapılır
    """
    cfg = build_default_config()
    repository = TeamRepository(cfg.data_dir)

    match_selection = repository.load_selected_match()
    if match_selection is None:
        raise FileNotFoundError(
            "Seçili maç bulunamadı.\n"
            "Önce match_selector.py üzerinden iki takım seçip kaydetmelisin."
        )

    # Benzersiz dosya adı üret
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

    fixed_dt = 1.0 / cfg.video.fps
    total_frames = cfg.total_video_frames
    intro_seconds = 2.0
    outro_seconds = 2.0
    gameplay_seconds = max(1.0, cfg.video.total_duration_seconds - intro_seconds - outro_seconds)
    frozen_snapshot: dict | None = None

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

    # Ses event timeline'ı
    audio_events: list[dict] = []
    seen_goal_count = 0
    whistle_start_added = False

    try:
        with Mp4VideoWriter(cfg, output_path=video_output_path) as writer:
            for frame_index in range(total_frames):
                for event in pygame.event.get():
                    if event.type == pygame.QUIT:
                        running = False

                if not running:
                    break

                video_seconds_elapsed = (frame_index + 1) / cfg.video.fps
                is_intro = video_seconds_elapsed < intro_seconds
                is_outro = video_seconds_elapsed >= max(0.0, cfg.video.total_duration_seconds - outro_seconds)

                if not is_intro and not is_outro:
                    physics.update(fixed_dt)
                    frozen_snapshot = None

                    # Başlangıç düdüğü — gameplay başladığında
                    if not whistle_start_added:
                        audio_events.append({
                            "type": "whistle_start",
                            "time": round(video_seconds_elapsed, 2),
                        })
                        whistle_start_added = True

                    # Gol event'lerini yakala
                    current_goals = sum(physics.scores.values())
                    if current_goals > seen_goal_count:
                        audio_events.append({
                            "type": "goal",
                            "time": round(video_seconds_elapsed, 2),
                        })
                        seen_goal_count = current_goals

                gameplay_elapsed = min(max(video_seconds_elapsed - intro_seconds, 0.0), gameplay_seconds)
                progress_ratio = gameplay_elapsed / gameplay_seconds
                current_match_seconds = cfg.simulated_match_total_seconds * progress_ratio
                current_match_clock = format_match_clock(current_match_seconds)

                if is_outro:
                    if frozen_snapshot is None:
                        frozen_snapshot = physics.get_state_snapshot()
                        # Bitiş düdüğü — outro başladığında
                        audio_events.append({
                            "type": "whistle_end",
                            "time": round(video_seconds_elapsed, 2),
                        })
                    snapshot = dict(frozen_snapshot)
                    active_balls = []
                else:
                    snapshot = physics.get_state_snapshot()
                    active_balls = physics.get_active_ball_draw_data()

                snapshot["match_clock_text"] = current_match_clock
                snapshot["match_progress_ratio"] = progress_ratio
                snapshot["video_frame_index"] = frame_index
                snapshot["video_total_frames"] = total_frames
                snapshot["video_seconds_elapsed"] = video_seconds_elapsed
                snapshot["video_seconds_total"] = cfg.video.total_duration_seconds
                snapshot["show_full_time_overlay"] = is_outro
                snapshot["show_hook_overlay"] = is_intro
                snapshot["hook_progress"] = min(1.0, video_seconds_elapsed / intro_seconds) if intro_seconds else 1.0
                snapshot["show_final_result_overlay"] = is_outro
                snapshot["final_result_progress"] = (
                    min(1.0, (video_seconds_elapsed - (cfg.video.total_duration_seconds - outro_seconds)) / outro_seconds)
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

                clock.tick(240)

    finally:
        pygame.quit()

    total_seconds = exported_frames / cfg.video.fps if cfg.video.fps else 0
    print("=" * 60)
    print("VIDEO EXPORT TAMAMLANDI")
    print(f"Toplam frame         : {exported_frames}")
    print(f"Olusan video suresi  : {total_seconds:.2f} saniye")
    print(f"Sessiz dosya         : {video_output_path}")
    print("=" * 60)

    # Ses miksajı
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
# GİRİŞ NOKTASI
# ============================================================

def main() -> None:
    try:
        output_path = run_simulation()
        show_messagebox(
            title="Video Hazır",
            message=f"MP4 başarıyla oluşturuldu:\n{output_path}",
            is_error=False,
        )
    except Exception as exc:
        show_messagebox(
            title="Hata",
            message=str(exc),
            is_error=True,
        )
        sys.exit(1)


if __name__ == "__main__":
    main()
