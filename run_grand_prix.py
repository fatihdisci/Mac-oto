from __future__ import annotations

import argparse
import json
import time
from dataclasses import replace
from datetime import datetime
from pathlib import Path

import pygame

from audio_mixer import mix_audio_into_video
from config import build_default_config
from grand_prix_engine import GrandPrixEngine
from grand_prix_manager import GrandPrixManager
from grand_prix_renderer import GrandPrixRenderer
from team_repository import TeamRepository
from video_writer import Mp4VideoWriter


def build_grand_prix_config():
    cfg = build_default_config()
    return replace(
        cfg,
        video=replace(
            cfg.video,
            width=1920,
            height=1080,
            fps=30,
            output_filename="grand_prix_output.mp4",
            background_color=(13, 18, 29),
        ),
    )


def _safe_print(text: str) -> None:
    try:
        print(text)
    except UnicodeEncodeError:
        encoded = (text + "\n").encode("utf-8", errors="replace")
        import sys

        sys.stdout.buffer.write(encoded)
        sys.stdout.buffer.flush()


def run_grand_prix(
    *,
    grand_prix_id: str | None = None,
    headless: bool = False,
    progress_every: int = 0,
) -> Path:
    cfg = build_grand_prix_config()
    repo = TeamRepository(cfg.data_dir)
    manager = GrandPrixManager(cfg.data_dir, repo)

    state = manager.load_state(grand_prix_id) if grand_prix_id else manager.load_latest_state()
    if state is None:
        raise ValueError("Grand Prix bulunamadi.")

    state = manager.reset_runtime(state)
    teams = []
    for team_key in state.get("team_keys", []):
        team = repo.get_team_by_key(str(team_key))
        if team is None:
            raise ValueError("Grand Prix takim havuzu eksik veya bozuk.")
        teams.append(team)

    output_dir = cfg.base_dir / "output" / "grand_prix_runs"
    output_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_path = output_dir / f"{state.get('id', 'grand_prix')}_{stamp}.mp4"

    pygame.init()
    screen = None
    if not headless:
        preview_width = 1280
        preview_height = int(preview_width * cfg.video.height / cfg.video.width)
        pygame.display.set_caption("Grand Prix Preview")
        screen = pygame.display.set_mode((preview_width, preview_height))
    else:
        pygame.display.set_mode((1, 1), flags=pygame.HIDDEN)
    render_surface = pygame.Surface((cfg.video.width, cfg.video.height))
    clock = pygame.time.Clock()

    engine = GrandPrixEngine(
        cfg,
        title=str(state.get("name", "Grand Prix")),
        teams=teams,
        hole_values=list(state.get("hole_values", [])),
        round_count=int(state.get("round_count", 5)),
        random_seed=int(state.get("random_seed", 0)),
    )
    renderer = GrandPrixRenderer(cfg)

    fixed_dt = 1.0 / cfg.video.fps
    progress_every = max(0, int(progress_every))
    frame_index = 0
    audio_events: list[dict[str, float | str]] = []
    render_start = time.perf_counter()

    _safe_print("=" * 60)
    _safe_print(f"GRAND PRIX STARTED: {state.get('id')} | {state.get('name')}")
    _safe_print(f"Teams                : {len(teams)}")
    _safe_print(f"Rounds               : {state.get('round_count')}")
    _safe_print(f"Hole values          : {state.get('hole_values')}")
    _safe_print("=" * 60)

    running = True
    try:
        with Mp4VideoWriter(cfg, output_path=output_path) as writer:
            while running and not engine.is_finished():
                if not headless:
                    for event in pygame.event.get():
                        if event.type == pygame.QUIT:
                            running = False

                engine.update(fixed_dt)
                current_video_time = (frame_index + 1) / cfg.video.fps
                for cue in engine.drain_audio_cues():
                    audio_events.append({"type": cue, "time": round(current_video_time, 2)})

                for payload in engine.drain_completed_round_payloads():
                    state = manager.record_round(
                        state,
                        round_index=int(payload.get("round_index", 0)),
                        placements=list(payload.get("placements", [])),
                        team_points=dict(engine.team_points),
                    )
                    _safe_print(
                        f"ROUND_RESULT: round={payload.get('round_index')} "
                        f"standings={[row['points'] for row in engine.get_snapshot().get('standings', [])]}"
                    )

                snapshot = engine.get_snapshot()
                renderer.draw(render_surface, snapshot)
                writer.write_surface(render_surface)

                if screen is not None:
                    preview = pygame.transform.smoothscale(render_surface, screen.get_size())
                    screen.blit(preview, (0, 0))
                    pygame.display.flip()
                    clock.tick(cfg.video.fps)

                frame_index += 1
                if progress_every and frame_index % progress_every == 0:
                    elapsed = time.perf_counter() - render_start
                    _safe_print(
                        f"[progress] frame={frame_index} round={snapshot.get('current_round')} "
                        f"phase={snapshot.get('phase')} elapsed={elapsed:.1f}s"
                    )
    finally:
        pygame.quit()

    if not running:
        raise RuntimeError("Grand Prix render kullanici tarafindan kapatildi.")

    result = engine.export_results()
    state = manager.finalize(
        state,
        team_points=dict(result.get("team_points", {})),
        rounds=list(result.get("rounds", [])),
    )
    champion_key = str(state.get("champion_team_key") or "")
    champion_name = manager.get_team_name(champion_key)

    _safe_print("=" * 60)
    _safe_print(f"GRAND PRIX FINISHED: {state.get('id')} | Champion: {champion_name}")
    _safe_print(
        "GRAND_PRIX_RESULT_JSON:"
        + json.dumps(
            {
                "grand_prix_id": state.get("id"),
                "champion_team_key": champion_key,
                "champion_name": champion_name,
                "team_points": state.get("team_points", {}),
            },
            ensure_ascii=False,
        )
    )
    _safe_print("=" * 60)

    final_path = output_path.with_name(output_path.stem + "_final.mp4")
    try:
        mixed = mix_audio_into_video(
            video_path=output_path,
            event_timeline=audio_events,
            output_path=final_path,
            background_music_path=cfg.data_dir / "sounds" / "grandprixbg.mp3",
        )
    except Exception as exc:
        _safe_print(f"GRAND_PRIX_AUDIO_WARN:{exc}")
        mixed = output_path

    _safe_print(f"GRAND_PRIX_OUTPUT_PATH:{mixed}")
    return mixed


def main() -> None:
    parser = argparse.ArgumentParser(description="Run Grand Prix mode.")
    parser.add_argument("--grand-prix-id", type=str, default=None)
    parser.add_argument("--headless", action="store_true")
    parser.add_argument("--progress-every", type=int, default=0)
    args = parser.parse_args()

    run_grand_prix(
        grand_prix_id=args.grand_prix_id,
        headless=bool(args.headless),
        progress_every=max(0, int(args.progress_every)),
    )


if __name__ == "__main__":
    main()
