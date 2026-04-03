from __future__ import annotations

import json
import math
import random
from datetime import datetime
from pathlib import Path
from typing import Any

from models import MatchSelection
from team_repository import TeamRepository


class TournamentManager:
    SUPPORTED_SIZES = {16, 32, 48}
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
            raise ValueError("Desteklenmeyen format. Sadece 16, 32 veya 48 secilebilir.")
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
        wins_needed = 1 if tournament_mode == "elimination" else 2
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
        return payload

    def load_latest_tournament(self) -> dict[str, Any] | None:
        files = sorted(self.tournaments_dir.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
        if not files:
            return None
        payload = json.loads(files[0].read_text(encoding="utf-8-sig"))
        return payload if isinstance(payload, dict) else None

    def list_tournaments(self) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        files = sorted(self.tournaments_dir.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
        for path in files:
            try:
                payload = json.loads(path.read_text(encoding="utf-8-sig"))
                if isinstance(payload, dict):
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
    ) -> dict[str, Any]:
        if score_a < 0 or score_b < 0:
            raise ValueError("Skorlar negatif olamaz.")
        if score_a == score_b:
            raise ValueError("Turnuva macinda beraberlik kaydi yapilamaz.")

        matches = state.get("matches", [])
        match_by_id: dict[str, dict[str, Any]] = {str(m.get("id")): m for m in matches}
        match = match_by_id.get(match_id)
        if match is None:
            raise ValueError("Mac bulunamadi.")
        if match.get("winner_team_key"):
            raise ValueError("Bu mac zaten tamamlanmis.")
        if not match.get("team_a_key") or not match.get("team_b_key"):
            raise ValueError("Bu macin iki tarafi henuz belli degil.")

        wins_needed = max(1, int(match.get("wins_needed", 1)))
        if wins_needed == 1:
            winner_key = str(match.get("team_a_key")) if score_a > score_b else str(match.get("team_b_key"))
            match["score_a"] = int(score_a)
            match["score_b"] = int(score_b)
            match["winner_team_key"] = winner_key
            match["status"] = "completed"
        else:
            games = list(match.get("games", []))
            winner_key = str(match.get("team_a_key")) if score_a > score_b else str(match.get("team_b_key"))
            games.append(
                {
                    "score_a": int(score_a),
                    "score_b": int(score_b),
                    "winner_team_key": winner_key,
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

    def record_match_result_with_knockout_rules(
        self,
        state: dict[str, Any],
        match_id: str,
        score_a: int,
        score_b: int,
    ) -> dict[str, Any]:
        matches = state.get("matches", [])
        match_by_id: dict[str, dict[str, Any]] = {str(m.get("id")): m for m in matches}
        match = match_by_id.get(str(match_id))
        if match is None:
            raise ValueError("Mac bulunamadi.")

        resolved = self._resolve_knockout_draw_if_needed(
            match=match,
            score_a=int(score_a),
            score_b=int(score_b),
        )
        state = self.record_match_result(
            state=state,
            match_id=str(match_id),
            score_a=int(resolved["score_a"]),
            score_b=int(resolved["score_b"]),
        )

        matches_after = state.get("matches", [])
        match_after = next((m for m in matches_after if str(m.get("id")) == str(match_id)), None)
        if match_after is None:
            return state

        if int(match_after.get("wins_needed", 1)) == 1:
            match_after["regular_time_score_a"] = int(score_a)
            match_after["regular_time_score_b"] = int(score_b)
            match_after["decided_by"] = str(resolved.get("decided_by", "normal_time"))
            match_after["extra_time_score_a"] = resolved.get("extra_time_score_a")
            match_after["extra_time_score_b"] = resolved.get("extra_time_score_b")
            match_after["penalty_score_a"] = resolved.get("penalty_score_a")
            match_after["penalty_score_b"] = resolved.get("penalty_score_b")
            if resolved.get("decided_by") == "extra_time":
                match_after["score_a"] = int(resolved["score_a"])
                match_after["score_b"] = int(resolved["score_b"])
        else:
            games = list(match_after.get("games", []))
            if games:
                g = dict(games[-1])
                g["regular_time_score_a"] = int(score_a)
                g["regular_time_score_b"] = int(score_b)
                g["decided_by"] = str(resolved.get("decided_by", "normal_time"))
                g["extra_time_score_a"] = resolved.get("extra_time_score_a")
                g["extra_time_score_b"] = resolved.get("extra_time_score_b")
                g["penalty_score_a"] = resolved.get("penalty_score_a")
                g["penalty_score_b"] = resolved.get("penalty_score_b")
                if resolved.get("decided_by") == "extra_time":
                    g["score_a"] = int(resolved["score_a"])
                    g["score_b"] = int(resolved["score_b"])
                games[-1] = g
                match_after["games"] = games

        self.save_tournament(state)
        return state

    def _resolve_knockout_draw_if_needed(
        self,
        match: dict[str, Any],
        score_a: int,
        score_b: int,
    ) -> dict[str, Any]:
        if score_a < 0 or score_b < 0:
            raise ValueError("Skorlar negatif olamaz.")
        if score_a != score_b:
            return {
                "score_a": int(score_a),
                "score_b": int(score_b),
                "decided_by": "normal_time",
                "extra_time_score_a": None,
                "extra_time_score_b": None,
                "penalty_score_a": None,
                "penalty_score_b": None,
            }

        seed_key = (
            f"{match.get('id','')}:"
            f"{match.get('team_a_key','')}:"
            f"{match.get('team_b_key','')}:"
            f"{score_a}:{score_b}:"
            f"{len(match.get('games', []))}"
        )
        rng = random.Random(seed_key)

        # Uzatma: +15 ve +15 dakikada ek gol
        et_a = rng.choices([0, 1, 2], weights=[0.63, 0.30, 0.07], k=1)[0]
        et_b = rng.choices([0, 1, 2], weights=[0.63, 0.30, 0.07], k=1)[0]
        total_a = int(score_a) + int(et_a)
        total_b = int(score_b) + int(et_b)
        if total_a != total_b:
            return {
                "score_a": total_a,
                "score_b": total_b,
                "decided_by": "extra_time",
                "extra_time_score_a": int(et_a),
                "extra_time_score_b": int(et_b),
                "penalty_score_a": None,
                "penalty_score_b": None,
            }

        # Penaltilar: 5 + sudden death
        pen_a = 0
        pen_b = 0
        for i in range(5):
            if rng.random() < 0.74:
                pen_a += 1
            if rng.random() < 0.74:
                pen_b += 1
            rem = 4 - i
            if pen_a > pen_b + rem:
                break
            if pen_b > pen_a + rem:
                break

        sudden_rounds = 0
        while pen_a == pen_b and sudden_rounds < 12:
            a_goal = rng.random() < 0.74
            b_goal = rng.random() < 0.74
            pen_a += int(a_goal)
            pen_b += int(b_goal)
            sudden_rounds += 1

        if pen_a == pen_b:
            if rng.random() < 0.5:
                pen_a += 1
            else:
                pen_b += 1

        # record_match_result beraberlik kabul etmedigi icin skorlar winner lehine ayarlanir
        if pen_a > pen_b:
            resolved_a = total_a + 1
            resolved_b = total_b
        else:
            resolved_a = total_a
            resolved_b = total_b + 1

        return {
            "score_a": int(resolved_a),
            "score_b": int(resolved_b),
            "decided_by": "penalties",
            "extra_time_score_a": int(et_a),
            "extra_time_score_b": int(et_b),
            "penalty_score_a": int(pen_a),
            "penalty_score_b": int(pen_b),
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
        if format_size in {16, 32}:
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
