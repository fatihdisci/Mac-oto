from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable

from models import MatchSelection, TeamRecord


class TeamRepository:
    def __init__(self, data_dir: Path) -> None:
        self.data_dir = Path(data_dir)
        self.teams_dir = self.data_dir / "teams"
        self.logos_dir = self.data_dir / "logos"
        self.all_teams_path = self.data_dir / "all_teams.json"
        self.selected_match_path = self.data_dir / "selected_match.json"
        self.sync_manifest_path = self.data_dir / "sync_manifest.json"

        self._teams_cache: list[TeamRecord] | None = None

        self._ensure_directories()

    def _ensure_directories(self) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.teams_dir.mkdir(parents=True, exist_ok=True)
        self.logos_dir.mkdir(parents=True, exist_ok=True)

    def exists(self) -> bool:
        return self.all_teams_path.exists()

    def load_teams(self, force_reload: bool = False) -> list[TeamRecord]:
        if self._teams_cache is not None and not force_reload:
            return list(self._teams_cache)

        if not self.all_teams_path.exists():
            self._teams_cache = []
            return []

        payload = json.loads(self.all_teams_path.read_text(encoding="utf-8-sig"))
        raw_teams = payload.get("teams", payload) if isinstance(payload, dict) else payload
        if not isinstance(raw_teams, list):
            raise ValueError("all_teams.json beklenen formatta degil.")

        teams = [TeamRecord.from_dict(item) for item in raw_teams if isinstance(item, dict)]
        teams.sort(key=lambda team: (team.league_name.lower(), team.name.lower()))
        self._teams_cache = teams
        return list(teams)

    def get_league_names(self) -> list[str]:
        teams = self.load_teams()
        names = sorted({team.league_name for team in teams if team.league_name}, key=str.lower)
        return ["All Leagues", *names]

    def filter_teams(
        self,
        league_name: str | None = None,
        query: str = "",
    ) -> list[TeamRecord]:
        league_filter = (league_name or "").strip()
        query_filter = query.strip().lower()

        teams = self.load_teams()
        if league_filter and league_filter != "All Leagues":
            teams = [team for team in teams if team.league_name == league_filter]

        if query_filter:
            teams = [
                team
                for team in teams
                if query_filter in team.name.lower()
                or query_filter in team.short_name.lower()
                or query_filter in team.league_name.lower()
                or query_filter in team.country.lower()
            ]

        return teams

    def iter_teams(self) -> Iterable[TeamRecord]:
        return iter(self.load_teams())

    def get_team_by_key(self, team_key: str) -> TeamRecord | None:
        clean_key = team_key.strip()
        if not clean_key:
            return None

        for team in self.load_teams():
            if team.team_key == clean_key:
                return team
        return None

    def get_team_by_name(self, team_name: str, league_name: str | None = None) -> TeamRecord | None:
        clean_name = team_name.strip().lower()
        clean_league = (league_name or "").strip().lower()
        if not clean_name:
            return None

        for team in self.load_teams():
            if team.name.lower() != clean_name:
                continue
            if clean_league and team.league_name.lower() != clean_league:
                continue
            return team
        return None

    def save_selected_match(self, selection: MatchSelection) -> Path:
        self.selected_match_path.write_text(
            json.dumps(selection.to_dict(), ensure_ascii=False, indent=2),
            encoding="utf-8-sig",
        )
        return self.selected_match_path

    def load_selected_match(self) -> MatchSelection | None:
        if not self.selected_match_path.exists():
            return None

        payload = json.loads(self.selected_match_path.read_text(encoding="utf-8-sig"))
        if not isinstance(payload, dict):
            raise ValueError("selected_match.json beklenen formatta degil.")

        return MatchSelection.from_dict(payload)
