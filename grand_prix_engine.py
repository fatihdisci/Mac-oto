from __future__ import annotations

import math
import random
from dataclasses import dataclass
from typing import Any

from config import SimulationConfig
from models import TeamRecord


@dataclass
class RoundEntry:
    team: TeamRecord
    slot_index: int
    slot_value: int
    exit_time: float
    nodes: list[tuple[float, float]]
    exited: bool = False


class GrandPrixEngine:
    def __init__(
        self,
        cfg: SimulationConfig,
        *,
        title: str,
        teams: list[TeamRecord],
        hole_values: list[int],
        round_count: int,
        random_seed: int,
        round_duration_seconds: float = 60.0,
    ) -> None:
        self.cfg = cfg
        self.title = str(title or "Grand Prix")
        self.teams = list(teams)
        self.hole_values = [int(value) for value in hole_values]
        self.round_count = int(round_count)
        self.random_seed = int(random_seed)
        self.rng = random.Random(self.random_seed)

        self.round_duration_seconds = max(20.0, float(round_duration_seconds))
        self.action_duration_seconds = self.round_duration_seconds * 0.74
        self.summary_duration_seconds = self.round_duration_seconds - self.action_duration_seconds
        self.final_duration_seconds = 6.0

        self.board_rect = {
            "x": 38,
            "y": 46,
            "width": 1220,
            "height": 988,
        }
        self.side_panel_rect = {
            "x": 1286,
            "y": 46,
            "width": 596,
            "height": 988,
        }
        self.hole_count = len(self.hole_values)
        self.peg_rows = 11
        self.ball_radius = 21
        self.peg_radius = 7

        self.peg_positions = self._build_peg_positions()
        self.slot_rects = self._build_slot_rects()
        self.team_points: dict[str, int] = {team.team_key: 0 for team in self.teams}
        self.round_history: list[dict[str, Any]] = []

        self.current_round = 0
        self.completed_rounds = 0
        self.phase = "intro"
        self.phase_elapsed = 0.0
        self.final_elapsed = 0.0
        self.current_entries: list[RoundEntry] = []
        self.current_round_results: list[dict[str, Any]] = []
        self.latest_completed_round_results: list[dict[str, Any]] = []
        self._round_awarded = False
        self._pending_round_payloads: list[dict[str, Any]] = []
        self._pending_audio_cues: list[str] = []
        self._final_audio_sent = False

        self._start_next_round()

    def update(self, dt: float) -> None:
        if self.phase == "finished":
            return

        delta = max(0.0, float(dt))

        if self.phase in {"action", "summary"}:
            self.phase_elapsed += delta

        if self.phase == "action":
            self._advance_action_phase()
            if self._all_entries_exited():
                self._complete_action_phase()
        elif self.phase == "summary":
            if self.phase_elapsed >= self.summary_duration_seconds:
                if self.current_round >= self.round_count:
                    self.phase = "final"
                    self.final_elapsed = 0.0
                    if not self._final_audio_sent:
                        self._pending_audio_cues.append("pop_end")
                        self._final_audio_sent = True
                else:
                    self._start_next_round()
        elif self.phase == "final":
            self.final_elapsed += delta
            if self.final_elapsed >= self.final_duration_seconds:
                self.phase = "finished"

    def is_finished(self) -> bool:
        return self.phase == "finished"

    def drain_audio_cues(self) -> list[str]:
        cues = list(self._pending_audio_cues)
        self._pending_audio_cues = []
        return cues

    def drain_completed_round_payloads(self) -> list[dict[str, Any]]:
        payloads = list(self._pending_round_payloads)
        self._pending_round_payloads = []
        return payloads

    def get_snapshot(self) -> dict[str, Any]:
        active_balls = []
        for entry in self.current_entries:
            if entry.exited:
                continue
            progress = min(1.0, self.phase_elapsed / max(0.001, entry.exit_time))
            x, y = self._sample_path(entry.nodes, progress)
            active_balls.append(
                {
                    "team_key": entry.team.team_key,
                    "team_name": entry.team.name,
                    "team_short_name": entry.team.short_name,
                    "badge_file": entry.team.badge_file,
                    "color_seed": self._color_seed(entry.team.team_key),
                    "x": x,
                    "y": y,
                    "radius": self.ball_radius,
                }
            )

        champion_key = None
        if self.phase in {"final", "finished"}:
            standings = self._build_standings()
            champion_key = str(standings[0]["team_key"]) if standings else None

        return {
            "title": self.title,
            "phase": self.phase,
            "current_round": self.current_round,
            "round_count": self.round_count,
            "completed_rounds": self.completed_rounds,
            "board_rect": dict(self.board_rect),
            "side_panel_rect": dict(self.side_panel_rect),
            "peg_positions": list(self.peg_positions),
            "slot_rects": list(self.slot_rects),
            "hole_values": [
                {
                    "slot_index": slot_index,
                    "points": int(points),
                    "rect": dict(self.slot_rects[slot_index]),
                }
                for slot_index, points in enumerate(self.hole_values)
            ],
            "teams": [
                {
                    "team_key": team.team_key,
                    "name": team.name,
                    "short_name": team.short_name,
                    "badge_file": team.badge_file,
                    "points": int(self.team_points.get(team.team_key, 0)),
                }
                for team in self.teams
            ],
            "standings": self._build_standings(),
            "active_balls": active_balls,
            "round_results": list(self.current_round_results or self.latest_completed_round_results),
            "latest_completed_round_results": list(self.latest_completed_round_results),
            "round_progress": self._round_progress_ratio(),
            "round_status_text": self._round_status_text(),
            "show_final_overlay": self.phase in {"final", "finished"},
            "champion_team_key": champion_key,
            "champion_name": self._team_name(champion_key),
        }

    def export_results(self) -> dict[str, Any]:
        standings = self._build_standings()
        champion_key = str(standings[0]["team_key"]) if standings else None
        return {
            "team_points": {key: int(value) for key, value in self.team_points.items()},
            "rounds": list(self.round_history),
            "champion_team_key": champion_key,
        }

    def _start_next_round(self) -> None:
        self.current_round += 1
        self.phase = "action"
        self.phase_elapsed = 0.0
        self._round_awarded = False
        self.current_round_results = []
        self.current_entries = self._build_round_entries()
        self._pending_audio_cues.append("pop_start")

    def _build_round_entries(self) -> list[RoundEntry]:
        entries: list[RoundEntry] = []
        spawn_xs = self._spawn_x_positions(len(self.teams))
        slot_centers = [slot["center_x"] for slot in self.slot_rects]
        start_y = self.board_rect["y"] + 48

        for team_index, team in enumerate(self.teams):
            slot_index = self.rng.randrange(self.hole_count)
            slot_value = self.hole_values[slot_index]
            exit_time = self.rng.uniform(self.action_duration_seconds * 0.62, self.action_duration_seconds * 0.96)
            target_x = slot_centers[slot_index]
            nodes: list[tuple[float, float]] = [(spawn_xs[team_index], start_y)]
            current_x = spawn_xs[team_index]
            for row_index in range(self.peg_rows):
                row_y = self.board_rect["y"] + 92 + row_index * 72
                remaining = max(1, self.peg_rows - row_index)
                drift = (target_x - current_x) / remaining
                jitter = self.rng.uniform(-34.0, 34.0)
                current_x = max(
                    self.board_rect["x"] + 42,
                    min(self.board_rect["x"] + self.board_rect["width"] - 42, current_x + drift + jitter),
                )
                nodes.append((current_x, row_y))
            hole_y = self.slot_rects[slot_index]["y"] + 6
            nodes.append((target_x, hole_y))
            nodes.append((target_x, hole_y + 120))
            entries.append(
                RoundEntry(
                    team=team,
                    slot_index=slot_index,
                    slot_value=slot_value,
                    exit_time=exit_time,
                    nodes=nodes,
                )
            )
        return entries

    def _advance_action_phase(self) -> None:
        for entry in self.current_entries:
            if entry.exited:
                continue
            if self.phase_elapsed >= entry.exit_time:
                entry.exited = True

    def _all_entries_exited(self) -> bool:
        return all(entry.exited for entry in self.current_entries)

    def _complete_action_phase(self) -> None:
        if self._round_awarded:
            return

        placements: list[dict[str, Any]] = []
        for entry in sorted(self.current_entries, key=lambda row: (row.exit_time, row.team.name.lower())):
            self.team_points[entry.team.team_key] += int(entry.slot_value)
            placements.append(
                {
                    "team_key": entry.team.team_key,
                    "team_name": entry.team.name,
                    "short_name": entry.team.short_name,
                    "badge_file": entry.team.badge_file,
                    "slot_index": int(entry.slot_index),
                    "points": int(entry.slot_value),
                    "total_points": int(self.team_points[entry.team.team_key]),
                }
            )

        self.completed_rounds = self.current_round
        payload = {
            "round_index": int(self.current_round),
            "placements": placements,
        }
        self.round_history.append(payload)
        self.current_round_results = placements
        self.latest_completed_round_results = placements
        self._pending_round_payloads.append(payload)
        self._pending_audio_cues.append("pop_point")
        self.phase = "summary"
        self.phase_elapsed = 0.0
        self._round_awarded = True

    def _build_peg_positions(self) -> list[tuple[float, float]]:
        positions: list[tuple[float, float]] = []
        left = self.board_rect["x"] + 74
        right = self.board_rect["x"] + self.board_rect["width"] - 74
        usable_width = right - left
        columns = 13
        spacing = usable_width / max(1, columns - 1)
        for row_index in range(self.peg_rows):
            row_y = self.board_rect["y"] + 154 + row_index * 72
            offset = spacing * 0.5 if row_index % 2 else 0.0
            for column_index in range(columns - (1 if row_index % 2 else 0)):
                x = left + column_index * spacing + offset
                positions.append((x, row_y))
        return positions

    def _build_slot_rects(self) -> list[dict[str, float]]:
        slots: list[dict[str, float]] = []
        slot_width = 128.0
        gap = 14.0
        total_width = self.hole_count * slot_width + (self.hole_count - 1) * gap
        start_x = self.board_rect["x"] + (self.board_rect["width"] - total_width) / 2.0
        y = self.board_rect["y"] + self.board_rect["height"] - 118
        for slot_index in range(self.hole_count):
            x = start_x + slot_index * (slot_width + gap)
            slots.append(
                {
                    "x": x,
                    "y": y,
                    "width": slot_width,
                    "height": 110.0,
                    "center_x": x + slot_width / 2.0,
                }
            )
        return slots

    def _spawn_x_positions(self, team_count: int) -> list[float]:
        left = self.board_rect["x"] + 160.0
        right = self.board_rect["x"] + self.board_rect["width"] - 160.0
        if team_count == 1:
            return [(left + right) / 2.0]
        return [left + index * ((right - left) / (team_count - 1)) for index in range(team_count)]

    def _sample_path(self, nodes: list[tuple[float, float]], progress: float) -> tuple[float, float]:
        if not nodes:
            return (0.0, 0.0)
        if len(nodes) == 1:
            return nodes[0]
        clamped = max(0.0, min(1.0, float(progress)))
        eased = clamped * clamped * (3.0 - 2.0 * clamped)
        segment_count = len(nodes) - 1
        raw_position = eased * segment_count
        segment_index = min(segment_count - 1, int(math.floor(raw_position)))
        local_t = raw_position - segment_index
        x0, y0 = nodes[segment_index]
        x1, y1 = nodes[segment_index + 1]
        x = x0 + (x1 - x0) * local_t
        y = y0 + (y1 - y0) * local_t
        return (x, y)

    def _build_standings(self) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for team in self.teams:
            rows.append(
                {
                    "team_key": team.team_key,
                    "name": team.name,
                    "short_name": team.short_name,
                    "badge_file": team.badge_file,
                    "points": int(self.team_points.get(team.team_key, 0)),
                }
            )
        rows.sort(key=lambda row: (-int(row["points"]), str(row["name"]).lower()))
        for index, row in enumerate(rows, start=1):
            row["rank"] = index
        return rows

    def _round_progress_ratio(self) -> float:
        if self.phase == "action":
            return min(1.0, self.phase_elapsed / max(0.001, self.action_duration_seconds))
        if self.phase == "summary":
            return 1.0
        if self.phase == "final":
            return 1.0
        return 0.0

    def _round_status_text(self) -> str:
        if self.phase == "action":
            return "Round live"
        if self.phase == "summary":
            return "Round complete"
        if self.phase == "final":
            return "Grand Prix complete"
        return "Finished"

    def _team_name(self, team_key: str | None) -> str:
        if not team_key:
            return "TBD"
        for team in self.teams:
            if team.team_key == team_key:
                return team.name
        return "TBD"

    @staticmethod
    def _color_seed(team_key: str) -> int:
        return abs(hash(str(team_key))) % 360
