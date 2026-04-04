from __future__ import annotations

import json
import random
from datetime import datetime
from pathlib import Path
from typing import Any

from team_repository import TeamRepository


class GrandPrixManager:
    SUPPORTED_TEAM_COUNTS = {4, 8}
    SUPPORTED_ROUND_COUNTS = {5, 10, 15, 20, 25, 30}
    HOLE_VALUE_POOL = (-1, 0, 1, 2, 3, 5, 7, 10)

    def __init__(self, data_dir: Path, repository: TeamRepository) -> None:
        self.repository = repository
        self.grand_prix_dir = Path(data_dir) / "grand_prix"
        self.grand_prix_dir.mkdir(parents=True, exist_ok=True)

    def create_grand_prix(
        self,
        *,
        name: str,
        team_keys: list[str],
        round_count: int,
    ) -> dict[str, Any]:
        clean_name = (name or "").strip() or "Grand Prix"
        if round_count not in self.SUPPORTED_ROUND_COUNTS:
            raise ValueError("Raunt sayisi sadece 5, 10, 15, 20, 25 veya 30 olabilir.")

        unique_team_keys: list[str] = []
        seen: set[str] = set()
        for key in team_keys:
            clean_key = str(key or "").strip()
            if not clean_key or clean_key in seen:
                continue
            seen.add(clean_key)
            unique_team_keys.append(clean_key)

        if len(unique_team_keys) not in self.SUPPORTED_TEAM_COUNTS:
            raise ValueError("Grand Prix su an sadece 4 veya 8 takimla baslatilabilir.")

        missing = [key for key in unique_team_keys if self.repository.get_team_by_key(key) is None]
        if missing:
            raise ValueError("Secilen takimlardan bazilari havuzda bulunamadi.")

        created_at = datetime.now().replace(microsecond=0).isoformat()
        grand_prix_id = f"gp_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        seed = random.randint(100_000, 999_999_999)
        hole_values = self._build_hole_values(seed)

        state: dict[str, Any] = {
            "id": grand_prix_id,
            "name": clean_name,
            "created_at": created_at,
            "updated_at": created_at,
            "status": "ready",
            "random_seed": seed,
            "team_keys": unique_team_keys,
            "round_count": int(round_count),
            "hole_values": hole_values,
            "completed_rounds": 0,
            "champion_team_key": None,
            "team_points": {key: 0 for key in unique_team_keys},
            "rounds": [],
        }
        self.save_state(state)
        return state

    def save_state(self, state: dict[str, Any]) -> Path:
        state["updated_at"] = datetime.now().replace(microsecond=0).isoformat()
        path = self.grand_prix_dir / f"{state['id']}.json"
        path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8-sig")
        return path

    def load_state(self, grand_prix_id: str) -> dict[str, Any] | None:
        path = self.grand_prix_dir / f"{grand_prix_id}.json"
        if not path.exists():
            return None
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
        return payload if isinstance(payload, dict) else None

    def load_latest_state(self) -> dict[str, Any] | None:
        files = sorted(self.grand_prix_dir.glob("*.json"), key=lambda item: item.stat().st_mtime, reverse=True)
        if not files:
            return None
        payload = json.loads(files[0].read_text(encoding="utf-8-sig"))
        return payload if isinstance(payload, dict) else None

    def list_states(self) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        files = sorted(self.grand_prix_dir.glob("*.json"), key=lambda item: item.stat().st_mtime, reverse=True)
        for path in files:
            try:
                payload = json.loads(path.read_text(encoding="utf-8-sig"))
            except Exception:
                continue
            if isinstance(payload, dict):
                rows.append(payload)
        return rows

    def reset_runtime(self, state: dict[str, Any]) -> dict[str, Any]:
        team_keys = [str(key) for key in state.get("team_keys", []) if str(key).strip()]
        state["status"] = "ready"
        state["completed_rounds"] = 0
        state["champion_team_key"] = None
        state["team_points"] = {key: 0 for key in team_keys}
        state["rounds"] = []
        self.save_state(state)
        return state

    def record_round(
        self,
        state: dict[str, Any],
        *,
        round_index: int,
        placements: list[dict[str, Any]],
        team_points: dict[str, int],
    ) -> dict[str, Any]:
        state["status"] = "active"
        state["completed_rounds"] = int(round_index)
        state["team_points"] = {str(key): int(value) for key, value in team_points.items()}
        rounds = [row for row in state.get("rounds", []) if int(row.get("round_index", 0)) != int(round_index)]
        rounds.append(
            {
                "round_index": int(round_index),
                "placements": placements,
            }
        )
        rounds.sort(key=lambda row: int(row.get("round_index", 0)))
        state["rounds"] = rounds
        self.save_state(state)
        return state

    def finalize(
        self,
        state: dict[str, Any],
        *,
        team_points: dict[str, int],
        rounds: list[dict[str, Any]],
    ) -> dict[str, Any]:
        normalized_points = {str(key): int(value) for key, value in team_points.items()}
        state["status"] = "completed"
        state["completed_rounds"] = int(state.get("round_count", 0))
        state["team_points"] = normalized_points
        state["rounds"] = rounds
        winner = self._resolve_champion_key(state, normalized_points)
        state["champion_team_key"] = winner
        self.save_state(state)
        return state

    def get_team_rows(self, state: dict[str, Any]) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        team_points = state.get("team_points", {})
        for team_key in state.get("team_keys", []):
            team = self.repository.get_team_by_key(str(team_key))
            if team is None:
                continue
            rows.append(
                {
                    "team_key": team.team_key,
                    "name": team.name,
                    "short_name": team.short_name,
                    "badge_file": team.badge_file,
                    "points": int(team_points.get(team.team_key, 0)),
                }
            )
        rows.sort(key=lambda item: (-int(item["points"]), str(item["name"]).lower()))
        for index, row in enumerate(rows, start=1):
            row["rank"] = index
        return rows

    def get_team_name(self, team_key: str | None) -> str:
        if not team_key:
            return "TBD"
        team = self.repository.get_team_by_key(str(team_key))
        return team.name if team is not None else "TBD"

    def _build_hole_values(self, seed: int) -> list[int]:
        rng = random.Random(seed)
        values = list(self.HOLE_VALUE_POOL)
        rng.shuffle(values)
        return values

    def _resolve_champion_key(self, state: dict[str, Any], team_points: dict[str, int]) -> str | None:
        best_key: str | None = None
        best_score: int | None = None
        for key in state.get("team_keys", []):
            score = int(team_points.get(str(key), 0))
            if best_score is None or score > best_score:
                best_key = str(key)
                best_score = score
                continue
            if score == best_score and best_key is not None:
                current_name = self.get_team_name(str(key))
                best_name = self.get_team_name(best_key)
                if current_name.lower() < best_name.lower():
                    best_key = str(key)
                    best_score = score
        return best_key
