from __future__ import annotations

import json
import math
from datetime import datetime
from pathlib import Path
from typing import Any

from knockout_rules import resolve_single_leg_knockout
from models import MatchSelection
from team_repository import TeamRepository


class TournamentManager:
    SUPPORTED_SIZES = {4, 8, 16, 32, 48}
    SUPPORTED_MODES = {"elimination", "playoff"}

    def __init__(self, data_dir: Path, repository: TeamRepository) -> None:
        self.repository = repository
        self.tournaments_dir = Path(data_dir) / "tournaments"
        self.tournaments_dir.mkdir(parents=True, exist_ok=True)

    def create_tournament(
        self,
        name: str,
        format_size: int,
        tournament_mode: str,
        team_keys: list[str],
        engine_mode: str,
        is_real_fixture_reference: bool = False,
    ) -> dict[str, Any]:
        clean_name = (name or "").strip() or "Untitled Tournament"
        if format_size not in self.SUPPORTED_SIZES:
            raise ValueError("Desteklenmeyen format. Sadece 4, 8, 16, 32 veya 48 secilebilir.")
        if tournament_mode not in self.SUPPORTED_MODES:
            raise ValueError("Desteklenmeyen turnuva modu.")

        unique_team_keys: list[str] = []
        seen: set[str] = set()
        for key in team_keys:
            k = (key or "").strip()
            if not k or k in seen:
                continue
            seen.add(k)
            unique_team_keys.append(k)

        if len(unique_team_keys) != format_size:
            raise ValueError(f"Turnuva formati icin tam {format_size} takim gerekli.")

        now = datetime.now().replace(microsecond=0).isoformat()
        tid = f"t_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        # Kullanici talebi: final/playoff fark etmeksizin her turnuva maci tek ayak.
        wins_needed = 1
        matches = self._build_matches(
            format_size=format_size,
            ordered_team_keys=unique_team_keys,
            wins_needed=wins_needed,
        )

        state: dict[str, Any] = {
            "id": tid,
            "name": clean_name,
            "format_size": format_size,
            "tournament_mode": tournament_mode,
            "engine_mode": engine_mode,
            "is_real_fixture_reference": bool(is_real_fixture_reference),
            "created_at": now,
            "updated_at": now,
            "status": "active",
            "champion_team_key": None,
            "team_keys": unique_team_keys,
            "matches": matches,
        }
        self.save_tournament(state)
        return state

    def save_tournament(self, state: dict[str, Any]) -> Path:
        state["updated_at"] = datetime.now().replace(microsecond=0).isoformat()
        path = self.tournaments_dir / f"{state['id']}.json"
        path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8-sig")
        return path

    def load_tournament(self, tournament_id: str) -> dict[str, Any] | None:
        path = self.tournaments_dir / f"{tournament_id}.json"
        if not path.exists():
            return None
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
        if not isinstance(payload, dict):
            return None
        self._enforce_single_leg_mode(payload)
        return payload

    def load_latest_tournament(self) -> dict[str, Any] | None:
        files = sorted(self.tournaments_dir.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
        if not files:
            return None
        payload = json.loads(files[0].read_text(encoding="utf-8-sig"))
        if not isinstance(payload, dict):
            return None
        self._enforce_single_leg_mode(payload)
        return payload

    def list_tournaments(self) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        files = sorted(self.tournaments_dir.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
        for path in files:
            try:
                payload = json.loads(path.read_text(encoding="utf-8-sig"))
                if isinstance(payload, dict):
                    self._enforce_single_leg_mode(payload)
                    rows.append(payload)
            except Exception:
                continue
        return rows

    def get_next_match(self, state: dict[str, Any]) -> dict[str, Any] | None:
        matches = sorted(
            list(state.get("matches", [])),
            key=lambda m: (int(m.get("round_index", 0)), int(m.get("order", 0))),
        )
        for match in matches:
            if match.get("winner_team_key"):
                continue
            if match.get("team_a_key") and match.get("team_b_key"):
                return match
        return None

    def get_champion_key(self, state: dict[str, Any]) -> str | None:
        champion = state.get("champion_team_key")
        return str(champion) if champion else None

    def get_round_matches(self, state: dict[str, Any]) -> list[tuple[int, list[dict[str, Any]]]]:
        buckets: dict[int, list[dict[str, Any]]] = {}
        for match in state.get("matches", []):
            r = int(match.get("round_index", 0))
            buckets.setdefault(r, []).append(match)
        ordered: list[tuple[int, list[dict[str, Any]]]] = []
        for ridx in sorted(buckets.keys()):
            ordered.append((ridx, sorted(buckets[ridx], key=lambda m: int(m.get("order", 0)))))
        return ordered

    def get_team_name(self, team_key: str | None) -> str:
        if not team_key:
            return "TBD"
        team = self.repository.get_team_by_key(team_key)
        if team is None:
            return "TBD"
        return team.name

    def build_match_selection(self, state: dict[str, Any], match: dict[str, Any]) -> MatchSelection:
        team_a_key = str(match.get("team_a_key") or "")
        team_b_key = str(match.get("team_b_key") or "")
        team_a = self.repository.get_team_by_key(team_a_key)
        team_b = self.repository.get_team_by_key(team_b_key)
        if team_a is None or team_b is None:
            raise ValueError("Mac takimi bulunamadi. Turnuva verisi bozuk olabilir.")

        round_name = str(match.get("round_name") or "Round")
        title = f"{state.get('name', 'Tournament')} | {round_name} | {team_a.name} vs {team_b.name}"
        return MatchSelection(
            team_a=team_a,
            team_b=team_b,
            title=title,
            engine_mode=str(state.get("engine_mode") or "normal"),
            is_real_fixture_reference=bool(state.get("is_real_fixture_reference", False)),
        )

    def record_match_result(
        self,
        state: dict[str, Any],
        match_id: str,
        score_a: int,
        score_b: int,
        resolution_override: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if score_a < 0 or score_b < 0:
            raise ValueError("Skorlar negatif olamaz.")

        matches = state.get("matches", [])
        match_by_id: dict[str, dict[str, Any]] = {str(m.get("id")): m for m in matches}
        match = match_by_id.get(match_id)
        if match is None:
            raise ValueError("Mac bulunamadi.")
        if match.get("winner_team_key"):
            raise ValueError("Bu mac zaten tamamlanmis.")
        if not match.get("team_a_key") or not match.get("team_b_key"):
            raise ValueError("Bu macin iki tarafi henuz belli degil.")

        # Global kural: tum turnuva maclari tek ayak oynanir.
        match["wins_needed"] = 1
        if match.get("status") == "active_series" and not match.get("winner_team_key"):
            match["status"] = "pending"

        resolved = self._resolve_knockout_draw_if_needed(
            match=match,
            score_a=int(score_a),
            score_b=int(score_b),
        )
        if isinstance(resolution_override, dict):
            resolved = self._normalize_resolution_override(
                fallback=resolved,
                score_a=int(score_a),
                score_b=int(score_b),
                override=resolution_override,
            )
        score_a = int(resolved["score_a"])
        score_b = int(resolved["score_b"])

        wins_needed = max(1, int(match.get("wins_needed", 1)))
        if wins_needed == 1:
            winner_key = str(match.get("team_a_key")) if score_a > score_b else str(match.get("team_b_key"))
            match["score_a"] = int(score_a)
            match["score_b"] = int(score_b)
            match["winner_team_key"] = winner_key
            match["status"] = "completed"
            match["regular_time_score_a"] = int(score_a) if resolved.get("decided_by") == "normal_time" else int(
                resolved.get("regular_time_score_a", score_a)
            )
            match["regular_time_score_b"] = int(score_b) if resolved.get("decided_by") == "normal_time" else int(
                resolved.get("regular_time_score_b", score_b)
            )
            match["decided_by"] = str(resolved.get("decided_by", "normal_time"))
            match["extra_time_score_a"] = resolved.get("extra_time_score_a")
            match["extra_time_score_b"] = resolved.get("extra_time_score_b")
            match["penalty_score_a"] = resolved.get("penalty_score_a")
            match["penalty_score_b"] = resolved.get("penalty_score_b")
        else:
            games = list(match.get("games", []))
            winner_key = str(match.get("team_a_key")) if score_a > score_b else str(match.get("team_b_key"))
            games.append(
                {
                    "score_a": int(score_a),
                    "score_b": int(score_b),
                    "winner_team_key": winner_key,
                    "regular_time_score_a": int(score_a)
                    if resolved.get("decided_by") == "normal_time"
                    else int(resolved.get("regular_time_score_a", score_a)),
                    "regular_time_score_b": int(score_b)
                    if resolved.get("decided_by") == "normal_time"
                    else int(resolved.get("regular_time_score_b", score_b)),
                    "decided_by": str(resolved.get("decided_by", "normal_time")),
                    "extra_time_score_a": resolved.get("extra_time_score_a"),
                    "extra_time_score_b": resolved.get("extra_time_score_b"),
                    "penalty_score_a": resolved.get("penalty_score_a"),
                    "penalty_score_b": resolved.get("penalty_score_b"),
                }
            )
            match["games"] = games
            wins_a = sum(1 for g in games if g.get("winner_team_key") == match.get("team_a_key"))
            wins_b = sum(1 for g in games if g.get("winner_team_key") == match.get("team_b_key"))
            match["wins_a"] = wins_a
            match["wins_b"] = wins_b
            match["last_score_a"] = int(score_a)
            match["last_score_b"] = int(score_b)
            if wins_a >= wins_needed or wins_b >= wins_needed:
                match["winner_team_key"] = str(match.get("team_a_key")) if wins_a > wins_b else str(match.get("team_b_key"))
                match["status"] = "completed"
            else:
                match["status"] = "active_series"
                self.save_tournament(state)
                return state

        winner_key = str(match.get("winner_team_key") or "")
        self._propagate_winner(match_by_id=match_by_id, match=match, winner_team_key=winner_key)
        self._update_tournament_status(state, match_by_id)
        self.save_tournament(state)
        return state

    def _enforce_single_leg_mode(self, state: dict[str, Any]) -> None:
        matches = state.get("matches", [])
        if not isinstance(matches, list):
            return
        for m in matches:
            if not isinstance(m, dict):
                continue
            m["wins_needed"] = 1
            if m.get("status") == "active_series" and not m.get("winner_team_key"):
                m["status"] = "pending"

    def record_match_result_with_knockout_rules(
        self,
        state: dict[str, Any],
        match_id: str,
        score_a: int,
        score_b: int,
        resolution_override: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        # Geriye donuk uyumluluk: artik asıl kural seti record_match_result icinde.
        return self.record_match_result(
            state=state,
            match_id=str(match_id),
            score_a=int(score_a),
            score_b=int(score_b),
            resolution_override=resolution_override,
        )

    def _resolve_knockout_draw_if_needed(
        self,
        match: dict[str, Any],
        score_a: int,
        score_b: int,
    ) -> dict[str, Any]:
        return resolve_single_leg_knockout(
            match_id=str(match.get("id") or ""),
            team_a_key=str(match.get("team_a_key") or ""),
            team_b_key=str(match.get("team_b_key") or ""),
            regular_score_a=int(score_a),
            regular_score_b=int(score_b),
            game_index=len(match.get("games", [])),
        )

    def _normalize_resolution_override(
        self,
        *,
        fallback: dict[str, Any],
        score_a: int,
        score_b: int,
        override: dict[str, Any],
    ) -> dict[str, Any]:
        try:
            final_a = int(override.get("score_a", fallback.get("score_a", score_a)))
            final_b = int(override.get("score_b", fallback.get("score_b", score_b)))
            regular_a = int(override.get("regular_time_score_a", score_a))
            regular_b = int(override.get("regular_time_score_b", score_b))
        except Exception:
            return fallback

        if final_a == final_b:
            return fallback

        decided_by = str(override.get("decided_by") or fallback.get("decided_by") or "normal_time")
        if decided_by not in {"normal_time", "extra_time", "penalties"}:
            decided_by = str(fallback.get("decided_by") or "normal_time")

        extra_a = override.get("extra_time_score_a", fallback.get("extra_time_score_a"))
        extra_b = override.get("extra_time_score_b", fallback.get("extra_time_score_b"))
        pen_a = override.get("penalty_score_a", fallback.get("penalty_score_a"))
        pen_b = override.get("penalty_score_b", fallback.get("penalty_score_b"))
        extra_a = int(extra_a) if extra_a is not None else None
        extra_b = int(extra_b) if extra_b is not None else None
        pen_a = int(pen_a) if pen_a is not None else None
        pen_b = int(pen_b) if pen_b is not None else None

        if decided_by == "normal_time":
            regular_a = final_a
            regular_b = final_b
            extra_a = None
            extra_b = None
            pen_a = None
            pen_b = None
        elif decided_by == "extra_time":
            if extra_a is None or extra_b is None:
                extra_a = max(0, final_a - regular_a)
                extra_b = max(0, final_b - regular_b)
            pen_a = None
            pen_b = None
        elif decided_by == "penalties":
            if extra_a is None or extra_b is None:
                base_total = min(final_a, final_b)
                extra_a = max(0, base_total - regular_a)
                extra_b = max(0, base_total - regular_b)
            if pen_a is None or pen_b is None:
                return fallback

        return {
            "score_a": int(final_a),
            "score_b": int(final_b),
            "decided_by": decided_by,
            "regular_time_score_a": int(regular_a),
            "regular_time_score_b": int(regular_b),
            "extra_time_score_a": extra_a,
            "extra_time_score_b": extra_b,
            "penalty_score_a": pen_a,
            "penalty_score_b": pen_b,
        }

    def _propagate_winner(self, match_by_id: dict[str, dict[str, Any]], match: dict[str, Any], winner_team_key: str) -> None:
        next_match_id = str(match.get("winner_to_match_id") or "")
        next_slot = str(match.get("winner_to_slot") or "").upper()
        if not next_match_id or next_slot not in {"A", "B"}:
            return
        nxt = match_by_id.get(next_match_id)
        if nxt is None:
            return
        nxt[f"team_{next_slot.lower()}_key"] = winner_team_key

    def _update_tournament_status(self, state: dict[str, Any], match_by_id: dict[str, dict[str, Any]]) -> None:
        completed = [m for m in match_by_id.values() if m.get("status") == "completed"]
        if not completed:
            return
        # Final = en yuksek round_index'teki tek mac
        max_round = max(int(m.get("round_index", 0)) for m in match_by_id.values())
        finals = [m for m in match_by_id.values() if int(m.get("round_index", 0)) == max_round]
        if len(finals) == 1 and finals[0].get("winner_team_key"):
            state["status"] = "completed"
            state["champion_team_key"] = finals[0].get("winner_team_key")

    def _build_matches(self, format_size: int, ordered_team_keys: list[str], wins_needed: int) -> list[dict[str, Any]]:
        if format_size in {4, 8, 16, 32}:
            return self._build_power_two_knockout(
                ordered_team_keys=ordered_team_keys,
                wins_needed=wins_needed,
            )
        if format_size == 48:
            return self._build_48_with_playin(
                ordered_team_keys=ordered_team_keys,
                wins_needed=wins_needed,
            )
        raise ValueError("Desteklenmeyen turnuva boyutu.")

    def _build_power_two_knockout(self, ordered_team_keys: list[str], wins_needed: int) -> list[dict[str, Any]]:
        size = len(ordered_team_keys)
        rounds = int(math.log2(size))
        round_matrix: list[list[dict[str, Any]]] = []

        # Round 0
        first_matches: list[dict[str, Any]] = []
        for i in range(size // 2):
            first_matches.append(
                self._new_match(
                    round_index=0,
                    order=i,
                    round_name=self._round_name(size),
                    team_a_key=ordered_team_keys[i * 2],
                    team_b_key=ordered_team_keys[i * 2 + 1],
                    wins_needed=wins_needed,
                )
            )
        round_matrix.append(first_matches)

        # Sonraki roundlar
        current_size = size // 2
        for ridx in range(1, rounds):
            matches_count = max(1, current_size // 2)
            next_round: list[dict[str, Any]] = []
            round_name = self._round_name(current_size)
            for m in range(matches_count):
                parent = self._new_match(
                    round_index=ridx,
                    order=m,
                    round_name=round_name,
                    team_a_key=None,
                    team_b_key=None,
                    wins_needed=wins_needed,
                )
                next_round.append(parent)
            round_matrix.append(next_round)
            current_size = matches_count

        # Parent link
        for ridx in range(len(round_matrix) - 1):
            for idx, child in enumerate(round_matrix[ridx]):
                parent = round_matrix[ridx + 1][idx // 2]
                child["winner_to_match_id"] = parent["id"]
                child["winner_to_slot"] = "A" if idx % 2 == 0 else "B"

        return [m for round_list in round_matrix for m in round_list]

    def _build_48_with_playin(self, ordered_team_keys: list[str], wins_needed: int) -> list[dict[str, Any]]:
        if len(ordered_team_keys) != 48:
            raise ValueError("48 formati icin tam 48 takim gerekir.")

        seeds = ordered_team_keys[:16]
        playin_pool = ordered_team_keys[16:]

        all_rounds: list[list[dict[str, Any]]] = []

        playin_round: list[dict[str, Any]] = []
        for i in range(16):
            playin_round.append(
                self._new_match(
                    round_index=0,
                    order=i,
                    round_name="Play-In",
                    team_a_key=playin_pool[i * 2],
                    team_b_key=playin_pool[i * 2 + 1],
                    wins_needed=wins_needed,
                )
            )
        all_rounds.append(playin_round)

        round32: list[dict[str, Any]] = []
        for i in range(16):
            m = self._new_match(
                round_index=1,
                order=i,
                round_name="Round of 32",
                team_a_key=seeds[i],
                team_b_key=None,
                wins_needed=wins_needed,
            )
            round32.append(m)
            playin_round[i]["winner_to_match_id"] = m["id"]
            playin_round[i]["winner_to_slot"] = "B"
        all_rounds.append(round32)

        # 32'den finale
        current_matches = round32
        current_round_idx = 2
        current_team_count = 16
        while current_team_count >= 2:
            next_count = current_team_count // 2
            round_name = self._round_name(current_team_count)
            nxt: list[dict[str, Any]] = []
            for i in range(next_count):
                nxt.append(
                    self._new_match(
                        round_index=current_round_idx,
                        order=i,
                        round_name=round_name,
                        team_a_key=None,
                        team_b_key=None,
                        wins_needed=wins_needed,
                    )
                )
            for idx, child in enumerate(current_matches):
                parent = nxt[idx // 2]
                child["winner_to_match_id"] = parent["id"]
                child["winner_to_slot"] = "A" if idx % 2 == 0 else "B"
            all_rounds.append(nxt)
            current_matches = nxt
            current_team_count = next_count
            current_round_idx += 1
            if next_count == 1:
                break

        return [m for round_list in all_rounds for m in round_list]

    def _new_match(
        self,
        round_index: int,
        order: int,
        round_name: str,
        team_a_key: str | None,
        team_b_key: str | None,
        wins_needed: int,
    ) -> dict[str, Any]:
        return {
            "id": f"r{round_index}_m{order}",
            "round_index": int(round_index),
            "order": int(order),
            "round_name": str(round_name),
            "team_a_key": team_a_key,
            "team_b_key": team_b_key,
            "winner_team_key": None,
            "winner_to_match_id": None,
            "winner_to_slot": None,
            "wins_needed": int(wins_needed),
            "wins_a": 0,
            "wins_b": 0,
            "games": [],
            "status": "pending",
            "score_a": None,
            "score_b": None,
            "last_score_a": None,
            "last_score_b": None,
        }

    def _round_name(self, team_count_at_round: int) -> str:
        if team_count_at_round <= 2:
            return "Final"
        if team_count_at_round == 4:
            return "Semi Finals"
        if team_count_at_round == 8:
            return "Quarter Finals"
        return f"Round of {team_count_at_round}"
