from __future__ import annotations

import argparse
import json
import random
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

from config import build_default_config
from team_repository import TeamRepository
from tournament_manager import TournamentManager


RESULT_MARKER = "TOURNAMENT_RESULT_JSON:"


def _safe_print(text: str) -> None:
    try:
        print(text)
    except UnicodeEncodeError:
        enc = getattr(sys.stdout, "encoding", None) or "utf-8"
        data = (text + "\n").encode(enc, errors="replace")
        sys.stdout.buffer.write(data)
        sys.stdout.buffer.flush()


def _parse_result_from_line(line: str) -> dict | None:
    clean = (line or "").strip()
    if not clean.startswith(RESULT_MARKER):
        return None
    payload_text = clean[len(RESULT_MARKER) :].strip()
    if not payload_text:
        return None
    try:
        payload = json.loads(payload_text)
    except Exception:
        return None
    return payload if isinstance(payload, dict) else None


def _as_int_or_none(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except Exception:
        return None


def _run_single_match(
    script_path: Path,
    *,
    tournament_match_id: str,
    tournament_progress: str,
) -> tuple[dict | None, Path | None]:
    cmd = [
        sys.executable,
        "-u",
        str(script_path),
        "--no-messagebox",
        "--headless",
        "--fps-override",
        "30",
        "--progress-every",
        "90",
        "--tournament-match-id",
        tournament_match_id,
        "--tournament-progress",
        tournament_progress,
    ]
    process = subprocess.Popen(
        cmd,
        cwd=str(script_path.parent),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    result_payload: dict | None = None
    output_path: Path | None = None

    assert process.stdout is not None
    for line in process.stdout:
        clean = line.rstrip()
        _safe_print(clean)
        parsed = _parse_result_from_line(clean)
        if parsed is not None:
            result_payload = parsed
        if clean.startswith("VIDEO_OUTPUT_PATH:"):
            maybe = clean.split("VIDEO_OUTPUT_PATH:", 1)[1].strip()
            if maybe:
                output_path = Path(maybe)
        elif "Final video" in clean:
            m = re.search(r"Final video\s*:\s*(.+)$", clean)
            if m:
                output_path = Path(m.group(1).strip())

    code = process.wait()
    if code != 0:
        raise RuntimeError(f"main.py failed with code {code}")
    return result_payload, output_path


def _concat_videos(videos: list[Path], output_path: Path) -> Path:
    if not videos:
        raise ValueError("No videos to concat.")
    output_path.parent.mkdir(parents=True, exist_ok=True)

    list_file = output_path.with_suffix(".txt")
    def _escape_concat_path(p: Path) -> str:
        return str(p.resolve()).replace("'", "'\\''")

    lines = [f"file '{_escape_concat_path(p)}'" for p in videos]
    list_file.write_text("\n".join(lines) + "\n", encoding="utf-8")

    copy_cmd = [
        "ffmpeg",
        "-y",
        "-f",
        "concat",
        "-safe",
        "0",
        "-i",
        str(list_file),
        "-c",
        "copy",
        str(output_path),
    ]
    copy_run = subprocess.run(copy_cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if copy_run.returncode == 0 and output_path.exists():
        return output_path

    transcode_cmd = [
        "ffmpeg",
        "-y",
        "-f",
        "concat",
        "-safe",
        "0",
        "-i",
        str(list_file),
        "-c:v",
        "libx264",
        "-preset",
        "medium",
        "-crf",
        "18",
        "-c:a",
        "aac",
        "-b:a",
        "192k",
        str(output_path),
    ]
    transcode_run = subprocess.run(
        transcode_cmd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if transcode_run.returncode != 0 or not output_path.exists():
        raise RuntimeError("ffmpeg concat/transcode failed.")
    return output_path


def _ffmpeg_escape_text(value: str) -> str:
    text = str(value or "")
    text = text.replace("\\", "\\\\")
    text = text.replace(":", r"\:")
    text = text.replace("'", r"\'")
    text = text.replace("%", r"\%")
    text = text.replace(",", r"\,")
    text = text.replace(";", r"\;")
    text = text.replace("[", r"\[")
    text = text.replace("]", r"\]")
    text = text.replace("|", r"\|")
    return text


def _broadcast_safe_text(value: Any) -> str:
    text = str(value or "")
    text = text.replace("\r", " ").replace("\n", " ")
    # drawtext filterinde sorun cikarabilen karakterleri sadeleştir.
    text = text.replace("'", "")
    text = text.replace("|", " / ")
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _build_center_lines(
    left_record: dict[str, Any],
    right_record: dict[str, Any] | None,
    previous_record: dict[str, Any] | None,
    next_match: dict[str, Any] | None,
    bracket_progress_line: str,
    completed_matches: int,
    total_matches: int,
) -> list[str]:
    def _fmt_result_line(prefix: str, rec: dict[str, Any] | None) -> str:
        if rec is None:
            return f"{prefix}: -"
        decision = str(rec.get("decided_by") or "normal_time")
        if decision in {"extra_time", "penalties"}:
            reg_a = rec.get("regular_time_score_a", rec.get("score_a", 0))
            reg_b = rec.get("regular_time_score_b", rec.get("score_b", 0))
            base_text = f"{reg_a}-{reg_b}"
        else:
            base_text = f"{rec.get('score_a', 0)}-{rec.get('score_b', 0)}"
        line = (
            f"{prefix}: {_broadcast_safe_text(rec.get('team_a_name', 'A'))} "
            f"{base_text} "
            f"{_broadcast_safe_text(rec.get('team_b_name', 'B'))}"
        )
        if decision == "extra_time":
            line += f" (ET {rec.get('extra_time_score_a', 0)}-{rec.get('extra_time_score_b', 0)})"
        elif decision == "penalties":
            et_a = rec.get("extra_time_score_a")
            et_b = rec.get("extra_time_score_b")
            if et_a is not None and et_b is not None:
                line += f" (AET {et_a}-{et_b})"
            line += f" (PEN {rec.get('penalty_score_a', 0)}-{rec.get('penalty_score_b', 0)})"
        return line

    header_round = _broadcast_safe_text(left_record.get("round_name") or "Round")
    line0 = f"Tournament Live | {header_round}"
    line1 = _fmt_result_line("PREV", previous_record)
    line2 = _fmt_result_line("NOW L", left_record)
    line3 = _fmt_result_line("NOW R", right_record) if right_record else "NOW R: Waiting"
    if next_match is None:
        line4 = "NEXT: Tournament completed"
    else:
        line4 = (
            f"NEXT: {_broadcast_safe_text(next_match.get('team_a_name', 'TBD'))} vs "
            f"{_broadcast_safe_text(next_match.get('team_b_name', 'TBD'))} "
            f"({_broadcast_safe_text(next_match.get('round_name', 'Round'))})"
        )
    line5 = bracket_progress_line
    line6 = f"Progress: {completed_matches}/{total_matches} matches"
    return [line0, line1, line2, line3, line4, line5, line6]


def _short_round_name(round_name: str) -> str:
    clean = str(round_name or "").strip()
    if not clean:
        return "R?"
    lowered = clean.lower()
    if lowered == "play-in":
        return "PI"
    if lowered == "quarter finals":
        return "QF"
    if lowered == "semi finals":
        return "SF"
    if lowered == "final":
        return "F"
    m = re.match(r"round of\s+(\d+)", lowered)
    if m:
        return f"R{m.group(1)}"
    return clean[:4].upper()


def _build_bracket_progress_line(
    schedule: list[dict[str, Any]],
    completed_count: int,
) -> str:
    total_by_round: dict[str, int] = {}
    done_by_round: dict[str, int] = {}
    ordered_rounds: list[str] = []
    for idx, row in enumerate(schedule):
        rn = str(row.get("round_name") or "Round")
        if rn not in total_by_round:
            ordered_rounds.append(rn)
            total_by_round[rn] = 0
            done_by_round[rn] = 0
        total_by_round[rn] += 1
        if idx < completed_count:
            done_by_round[rn] += 1
    parts = [f"{_short_round_name(rn)} {done_by_round[rn]}/{total_by_round[rn]}" for rn in ordered_rounds]
    text = "Bracket: " + " | ".join(parts)
    if len(text) > 94:
        text = text[:91] + "..."
    return text


def _make_landscape_segment(
    left_video: Path,
    right_video: Path | None,
    lines: list[str],
    output_path: Path,
) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)

    left_input = ["-i", str(left_video)]
    if right_video is not None:
        right_input = ["-i", str(right_video)]
        right_has_audio = True
    else:
        right_input = ["-f", "lavfi", "-i", "color=c=#101a2b:s=1080x1920:r=60"]
        right_has_audio = False

    panel_draw_chain: list[str] = [
        "drawbox=x=640:y=30:w=640:h=1020:color=#0f1e36@0.88:t=fill",
        "drawbox=x=640:y=30:w=640:h=1020:color=#2d4f8f@0.95:t=3",
    ]
    text_draw_chain: list[str] = []
    y = 96
    font_path = "C\\:/Windows/Fonts/arial.ttf"
    for idx, line in enumerate(lines):
        size = 40 if idx == 0 else 30
        escaped = _ffmpeg_escape_text(line)
        text_draw_chain.append(
            f"drawtext=fontfile='{font_path}':fontcolor=white:fontsize={size}:x=670:y={y}:text='{escaped}'"
        )
        y += 140 if idx == 0 else 120

    base_video_prefix = (
        "[0:v]scale=-2:1080,setsar=1[leftv];"
        "[1:v]scale=-2:1080,setsar=1[rightv];"
        "color=c=#07111f:s=1920x1080:r=60[base];"
        "[base][leftv]overlay=x=20:y=(H-h)/2[tmp1];"
        "[tmp1][rightv]overlay=x=W-w-20:y=(H-h)/2[tmp2];"
    )
    with_text_chain = panel_draw_chain + text_draw_chain
    without_text_chain = panel_draw_chain
    base_video_filter = base_video_prefix + f"[tmp2]{','.join(with_text_chain)}[v]"

    if right_has_audio:
        filter_complex = (
            base_video_filter
            + ";"
            + "[0:a]volume=0.65[a0];[1:a]volume=0.65[a1];[a0][a1]amix=inputs=2:duration=shortest[a]"
        )
        cmd = ["ffmpeg", "-y", *left_input, *right_input, "-filter_complex", filter_complex]
        cmd.extend(
            [
                "-map",
                "[v]",
                "-map",
                "[a]",
            ]
        )
    else:
        cmd = ["ffmpeg", "-y", *left_input, *right_input, "-filter_complex", base_video_filter]
        cmd.extend(["-map", "[v]", "-map", "0:a?"])

    cmd.extend(["-shortest", "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-c:a", "aac", "-b:a", "160k", str(output_path)])

    run = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if run.returncode != 0 or not output_path.exists():
        _safe_print("LANDSCAPE_TEXT_RENDER_WARN: text overlay failed, retrying without center text.")
        fallback_base_video_filter = base_video_prefix + f"[tmp2]{','.join(without_text_chain)}[v]"
        if right_has_audio:
            fallback_filter_complex = (
                fallback_base_video_filter
                + ";"
                + "[0:a]volume=0.65[a0];[1:a]volume=0.65[a1];[a0][a1]amix=inputs=2:duration=shortest[a]"
            )
            fallback_cmd = ["ffmpeg", "-y", *left_input, *right_input, "-filter_complex", fallback_filter_complex]
            fallback_cmd.extend(["-map", "[v]", "-map", "[a]"])
        else:
            fallback_cmd = ["ffmpeg", "-y", *left_input, *right_input, "-filter_complex", fallback_base_video_filter]
            fallback_cmd.extend(["-map", "[v]", "-map", "0:a?"])
        fallback_cmd.extend(
            ["-shortest", "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-c:a", "aac", "-b:a", "160k", str(output_path)]
        )
        fallback_run = subprocess.run(
            fallback_cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        if fallback_run.returncode != 0 or not output_path.exists():
            raise RuntimeError(f"landscape segment render failed: {fallback_run.stderr[-700:]}")
    return output_path


def _build_landscape_broadcast_video(
    videos: list[Path],
    records: list[dict[str, Any]],
    schedule: list[dict[str, Any]],
    output_path: Path,
    total_matches: int,
) -> Path:
    if not videos:
        raise ValueError("No videos to build landscape broadcast.")

    segment_dir = output_path.parent / f"{output_path.stem}_segments"
    segment_dir.mkdir(parents=True, exist_ok=True)
    segments: list[Path] = []

    for i in range(0, len(videos), 2):
        left_video = videos[i]
        right_video = videos[i + 1] if i + 1 < len(videos) else None
        left_record = records[i]
        right_record = records[i + 1] if i + 1 < len(records) else None
        completed = min(i + (2 if right_video else 1), len(records))
        previous_record = records[i - 1] if i - 1 >= 0 else None
        next_match = schedule[completed] if completed < len(schedule) else None
        bracket_progress_line = _build_bracket_progress_line(schedule=schedule, completed_count=completed)
        lines = _build_center_lines(
            left_record=left_record,
            right_record=right_record,
            previous_record=previous_record,
            next_match=next_match,
            bracket_progress_line=bracket_progress_line,
            completed_matches=completed,
            total_matches=total_matches,
        )
        seg_path = segment_dir / f"seg_{i//2:03d}.mp4"
        _safe_print(f"LANDSCAPE_SEGMENT: {seg_path.name}")
        _make_landscape_segment(
            left_video=left_video,
            right_video=right_video,
            lines=lines,
            output_path=seg_path,
        )
        segments.append(seg_path)

    return _concat_videos(segments, output_path)


def run_full_tournament(
    tournament_id: str | None,
    dry_run: bool = False,
    layout: str = "portrait_concat",
    replay_completed: bool = False,
) -> Path | None:
    cfg = build_default_config()
    repo = TeamRepository(cfg.data_dir)
    tm = TournamentManager(cfg.data_dir, repo)

    if tournament_id:
        state = tm.load_tournament(tournament_id)
    else:
        state = tm.load_latest_tournament()
    if state is None:
        raise ValueError("Tournament not found.")

    # Completed turnuvada oynanacak mac kalmaz; istenirse ayni ayarlarla replay olustur.
    if replay_completed and str(state.get("status") or "") == "completed":
        replay_state = tm.create_tournament(
            name=f"{state.get('name', 'Tournament')} (Replay)",
            format_size=int(state.get("format_size", 16)),
            tournament_mode=str(state.get("tournament_mode", "elimination")),
            team_keys=list(state.get("team_keys", [])),
            engine_mode=str(state.get("engine_mode", "power_pegs")),
            is_real_fixture_reference=bool(state.get("is_real_fixture_reference", False)),
        )
        _safe_print(
            f"REPLAY_CREATED: source={state.get('id')} -> replay={replay_state.get('id')}"
        )
        state = replay_state

    runner_tm = tm
    if dry_run:
        dry_data_dir = cfg.data_dir / "_dryrun_tmp"
        runner_tm = TournamentManager(dry_data_dir, repo)

    print("=" * 64)
    print(f"FULL TOURNAMENT RUN STARTED: {state.get('id')} | {state.get('name')}")
    print(f"Mode={state.get('tournament_mode')}  Format={state.get('format_size')}  Status={state.get('status')}")
    print("=" * 64)

    main_script = Path(__file__).resolve().parent / "main.py"
    produced_videos: list[Path] = []
    match_records: list[dict[str, Any]] = []
    match_schedule: list[dict[str, Any]] = []
    match_counter = 0

    while True:
        nxt = runner_tm.get_next_match(state)
        if nxt is None:
            break
        match_counter += 1
        match_id = str(nxt.get("id") or "")
        team_a_key = str(nxt.get("team_a_key") or "")
        team_b_key = str(nxt.get("team_b_key") or "")
        team_a_name = runner_tm.get_team_name(team_a_key)
        team_b_name = runner_tm.get_team_name(team_b_key)
        round_name = str(nxt.get("round_name") or "Round")
        print(f"[{match_counter}] {round_name} | {team_a_name} vs {team_b_name} ({match_id})")
        match_schedule.append(
            {
                "match_id": match_id,
                "round_name": round_name,
                "team_a_name": team_a_name,
                "team_b_name": team_b_name,
            }
        )

        if dry_run:
            score_a = random.randint(0, 4)
            score_b = random.randint(0, 4)
            state = runner_tm.record_match_result_with_knockout_rules(
                state=state,
                match_id=match_id,
                score_a=score_a,
                score_b=score_b,
            )
            updated_match = next((m for m in state.get("matches", []) if str(m.get("id")) == match_id), None)
            decided_by = str((updated_match or {}).get("decided_by") or "normal_time")
            print(f"DRY-RUN RESULT: {score_a}-{score_b} ({decided_by})")
            continue

        selection = runner_tm.build_match_selection(state, nxt)
        repo.save_selected_match(selection)
        print(f"SELECTED_MATCH: {selection.title}")

        total_matches = len(state.get("matches", []))
        result_payload, output_path = _run_single_match(
            main_script,
            tournament_match_id=match_id,
            tournament_progress=f"{match_counter}/{total_matches}",
        )
        if output_path is not None and output_path.exists():
            produced_videos.append(output_path)

        if result_payload is None:
            raise RuntimeError("Could not parse match result payload from main.py output.")

        r_team_a = str(result_payload.get("team_a_key") or "")
        r_team_b = str(result_payload.get("team_b_key") or "")
        try:
            raw_final_a = int(result_payload.get("score_a"))
            raw_final_b = int(result_payload.get("score_b"))
        except Exception as exc:
            raise RuntimeError(f"Invalid score payload: {result_payload}") from exc

        raw_regular_a = _as_int_or_none(result_payload.get("regular_time_score_a"))
        raw_regular_b = _as_int_or_none(result_payload.get("regular_time_score_b"))
        if raw_regular_a is None:
            raw_regular_a = raw_final_a
        if raw_regular_b is None:
            raw_regular_b = raw_final_b
        raw_et_a = _as_int_or_none(result_payload.get("extra_time_score_a"))
        raw_et_b = _as_int_or_none(result_payload.get("extra_time_score_b"))
        raw_pen_a = _as_int_or_none(result_payload.get("penalty_score_a"))
        raw_pen_b = _as_int_or_none(result_payload.get("penalty_score_b"))
        raw_decided_by = str(result_payload.get("decided_by") or "normal_time")

        swap_payload = False
        if r_team_a == team_a_key and r_team_b == team_b_key:
            swap_payload = False
        elif r_team_a == team_b_key and r_team_b == team_a_key:
            swap_payload = True
        else:
            raise RuntimeError("Rendered teams do not match tournament next-match teams.")

        if swap_payload:
            final_a, final_b = raw_final_b, raw_final_a
            regular_a, regular_b = raw_regular_b, raw_regular_a
            et_a, et_b = raw_et_b, raw_et_a
            pen_a, pen_b = raw_pen_b, raw_pen_a
        else:
            final_a, final_b = raw_final_a, raw_final_b
            regular_a, regular_b = raw_regular_a, raw_regular_b
            et_a, et_b = raw_et_a, raw_et_b
            pen_a, pen_b = raw_pen_a, raw_pen_b

        resolution_override = {
            "score_a": int(final_a),
            "score_b": int(final_b),
            "decided_by": raw_decided_by,
            "regular_time_score_a": int(regular_a),
            "regular_time_score_b": int(regular_b),
            "extra_time_score_a": et_a,
            "extra_time_score_b": et_b,
            "penalty_score_a": pen_a,
            "penalty_score_b": pen_b,
        }

        state = runner_tm.record_match_result_with_knockout_rules(
            state=state,
            match_id=match_id,
            score_a=int(regular_a),
            score_b=int(regular_b),
            resolution_override=resolution_override,
        )
        updated_match = next((m for m in state.get("matches", []) if str(m.get("id")) == match_id), None)
        final_a = int((updated_match or {}).get("score_a") or final_a)
        final_b = int((updated_match or {}).get("score_b") or final_b)
        regular_a = int((updated_match or {}).get("regular_time_score_a") or regular_a)
        regular_b = int((updated_match or {}).get("regular_time_score_b") or regular_b)
        decided_by = str((updated_match or {}).get("decided_by") or "normal_time")
        print(f"RECORDED_RESULT: {regular_a}-{regular_b} -> {final_a}-{final_b} ({decided_by})")
        winner_name = team_a_name if final_a > final_b else team_b_name
        match_records.append(
            {
                "match_id": match_id,
                "round_name": round_name,
                "team_a_name": team_a_name,
                "team_b_name": team_b_name,
                "score_a": final_a,
                "score_b": final_b,
                "winner_name": winner_name,
                "decided_by": decided_by,
                "regular_time_score_a": regular_a,
                "regular_time_score_b": regular_b,
                "extra_time_score_a": (updated_match or {}).get("extra_time_score_a"),
                "extra_time_score_b": (updated_match or {}).get("extra_time_score_b"),
                "penalty_score_a": (updated_match or {}).get("penalty_score_a"),
                "penalty_score_b": (updated_match or {}).get("penalty_score_b"),
            }
        )

    champion = runner_tm.get_team_name(runner_tm.get_champion_key(state))
    print("=" * 64)
    print(f"FULL TOURNAMENT FINISHED: {state.get('id')} | Champion: {champion}")
    print("=" * 64)

    if dry_run:
        return None

    if not produced_videos:
        raise RuntimeError("No produced videos found, cannot build full tournament output.")

    runs_dir = cfg.base_dir / "output" / "tournament_runs"
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    tid = state.get("id", "tournament")
    portrait_target = runs_dir / f"{tid}_{stamp}_full.mp4"
    portrait_final = _concat_videos(produced_videos, portrait_target)
    print(f"TOURNAMENT_FULL_OUTPUT:{portrait_final}")

    if layout == "portrait_concat":
        return portrait_final

    if layout == "landscape_broadcast":
        landscape_target = runs_dir / f"{tid}_{stamp}_broadcast_1920x1080.mp4"
        landscape_final = _build_landscape_broadcast_video(
            videos=produced_videos,
            records=match_records,
            schedule=match_schedule,
            output_path=landscape_target,
            total_matches=len(state.get("matches", [])),
        )
        print(f"TOURNAMENT_BROADCAST_OUTPUT:{landscape_final}")
        return landscape_final

    if layout == "both":
        landscape_target = runs_dir / f"{tid}_{stamp}_broadcast_1920x1080.mp4"
        landscape_final = _build_landscape_broadcast_video(
            videos=produced_videos,
            records=match_records,
            schedule=match_schedule,
            output_path=landscape_target,
            total_matches=len(state.get("matches", [])),
        )
        print(f"TOURNAMENT_BROADCAST_OUTPUT:{landscape_final}")
        return landscape_final

    raise ValueError(f"Unsupported layout mode: {layout}")


def main() -> None:
    # Windows konsol codepage farklarinda Unicode yazdirma hatasini engelle.
    try:
        if hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(errors="replace")
        if hasattr(sys.stderr, "reconfigure"):
            sys.stderr.reconfigure(errors="replace")
    except Exception:
        pass

    parser = argparse.ArgumentParser(description="Run full tournament from start to finish.")
    parser.add_argument("--tournament-id", type=str, default=None)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument(
        "--layout",
        type=str,
        choices=["portrait_concat", "landscape_broadcast", "both"],
        default="portrait_concat",
    )
    parser.add_argument(
        "--replay-completed",
        action="store_true",
        help="If tournament is already completed, create a replay copy and run it.",
    )
    args = parser.parse_args()

    try:
        run_full_tournament(
            tournament_id=args.tournament_id,
            dry_run=args.dry_run,
            layout=args.layout,
            replay_completed=args.replay_completed,
        )
    except Exception as exc:
        print(f"FULL_TOURNAMENT_ERROR:{exc}", file=sys.stderr)
        raise


if __name__ == "__main__":
    main()
