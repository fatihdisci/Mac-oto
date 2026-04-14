from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class LeagueSpec:
    api_name: str
    slug: str
    country: str
    aliases: tuple[str, ...] = field(default_factory=tuple)

    def all_candidate_names(self) -> list[str]:
        candidates: list[str] = []

        for value in (self.api_name, *self.aliases):
            clean = value.strip()
            if clean and clean not in candidates:
                candidates.append(clean)

        return candidates

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "LeagueSpec":
        aliases = payload.get("aliases") or ()
        if isinstance(aliases, list):
            aliases = tuple(str(item).strip() for item in aliases if str(item).strip())

        return cls(
            api_name=str(payload.get("api_name") or "").strip(),
            slug=str(payload.get("slug") or "").strip(),
            country=str(payload.get("country") or "").strip(),
            aliases=tuple(aliases),
        )


@dataclass(frozen=True)
class TeamRecord:
    team_id: str
    name: str
    short_name: str
    league_name: str
    league_slug: str
    country: str
    badge_url: str
    badge_file: str
    stadium: str = ""
    formed_year: str = ""
    website: str = ""
    description: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "TeamRecord":
        name = str(payload.get("name") or "").strip()
        short_name = str(payload.get("short_name") or "").strip() or cls._derive_short_name(name)

        return cls(
            team_id=str(payload.get("team_id") or "").strip(),
            name=name,
            short_name=short_name,
            league_name=str(payload.get("league_name") or "").strip(),
            league_slug=str(payload.get("league_slug") or "").strip(),
            country=str(payload.get("country") or "").strip(),
            badge_url=str(payload.get("badge_url") or "").strip(),
            badge_file=str(payload.get("badge_file") or "").strip(),
            stadium=str(payload.get("stadium") or "").strip(),
            formed_year=str(payload.get("formed_year") or "").strip(),
            website=str(payload.get("website") or "").strip(),
            description=str(payload.get("description") or "").strip(),
        )

    @property
    def team_key(self) -> str:
        if self.team_id:
            return self.team_id
        return f"{self.league_slug}:{self.name.lower()}"

    def logo_path(self, data_dir: Path) -> Path:
        return data_dir / "logos" / self.badge_file

    @staticmethod
    def _derive_short_name(name: str) -> str:
        words = [part for part in name.split() if part]
        if not words:
            return "TEAM"
        if len(words) == 1:
            return words[0][:4].upper()
        return "".join(word[0] for word in words[:4]).upper()[:4]


@dataclass(frozen=True)
class MatchSelection:
    team_a: TeamRecord
    team_b: TeamRecord
    title: str
    engine_mode: str = "power_pegs"
    guided_target_score_a: int | None = None
    guided_target_score_b: int | None = None
    is_real_fixture_reference: bool = False
    video_preset: str = "shorts_55"
    created_at_utc: str = field(
        default_factory=lambda: datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    )

    def to_dict(self) -> dict[str, Any]:
        return {
            "team_a": self.team_a.to_dict(),
            "team_b": self.team_b.to_dict(),
            "title": self.title,
            "engine_mode": self.engine_mode,
            "guided_target_score_a": self.guided_target_score_a,
            "guided_target_score_b": self.guided_target_score_b,
            "is_real_fixture_reference": self.is_real_fixture_reference,
            "video_preset": self.video_preset,
            "created_at_utc": self.created_at_utc,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "MatchSelection":
        team_a_payload = payload.get("team_a")
        team_b_payload = payload.get("team_b")
        if not isinstance(team_a_payload, dict) or not isinstance(team_b_payload, dict):
            raise ValueError("MatchSelection icin team_a ve team_b alanlari gerekli.")

        team_a = TeamRecord.from_dict(team_a_payload)
        team_b = TeamRecord.from_dict(team_b_payload)

        raw_title = str(payload.get("title") or "").strip()
        title = raw_title or f"{team_a.name} vs {team_b.name}"

        return cls(
            team_a=team_a,
            team_b=team_b,
            title=title,
            engine_mode=str(payload.get("engine_mode") or "power_pegs").strip() or "power_pegs",
            guided_target_score_a=(
                int(payload.get("guided_target_score_a"))
                if payload.get("guided_target_score_a") is not None
                else None
            ),
            guided_target_score_b=(
                int(payload.get("guided_target_score_b"))
                if payload.get("guided_target_score_b") is not None
                else None
            ),
            is_real_fixture_reference=bool(payload.get("is_real_fixture_reference", False)),
            video_preset=str(payload.get("video_preset") or "shorts_55").strip() or "shorts_55",
            created_at_utc=str(payload.get("created_at_utc") or "").strip()
            or datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        )
