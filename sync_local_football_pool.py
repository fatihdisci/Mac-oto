from __future__ import annotations

import json
import re
import shutil
import unicodedata
from dataclasses import asdict, dataclass
from pathlib import Path

from config import build_default_config
from models import TeamRecord


@dataclass(frozen=True)
class LocalLeagueSpec:
    folder_name: str
    league_name: str
    league_slug: str
    country: str
    source_league_slug: str | None = None


LOCAL_LEAGUES: list[LocalLeagueSpec] = [
    LocalLeagueSpec("premier lig", "English Premier League", "premier_league", "England", "premier_league"),
    LocalLeagueSpec("la liga", "Spanish La Liga", "la_liga", "Spain", "la_liga"),
    LocalLeagueSpec("bundesliga", "German Bundesliga", "bundesliga", "Germany", "bundesliga"),
    LocalLeagueSpec("serie a", "Italian Serie A", "serie_a", "Italy", "serie_a"),
    LocalLeagueSpec("ligue 1", "French Ligue 1", "ligue_1", "France", "ligue_1"),
    LocalLeagueSpec("hollanda ligi", "Dutch Eredivisie", "eredivisie", "Netherlands", "eredivisie"),
    LocalLeagueSpec("türkiye süper lig", "Turkish Super Lig", "super_lig", "Turkiye", "super_lig"),
    LocalLeagueSpec("dünya kupası", "National Teams", "national_teams", "International", "national_teams"),
    LocalLeagueSpec("şampiyonlar ligi", "UEFA Champions League", "champions_league", "Europe", None),
    LocalLeagueSpec("avrupa ligi", "UEFA Europa League", "europa_league", "Europe", None),
]


STOPWORDS = {
    "fc",
    "cf",
    "ac",
    "sc",
    "sv",
    "as",
    "rc",
    "afc",
    "if",
    "fk",
    "club",
    "de",
    "del",
    "the",
    "team",
    "football",
    "futbol",
    "national",
}


def _ascii(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value)
    return normalized.encode("ascii", "ignore").decode("ascii")


def _slugify(value: str) -> str:
    value = _ascii(value).lower()
    value = value.replace("&", " and ")
    value = re.sub(r"[^a-z0-9]+", "_", value)
    return value.strip("_")


def _normalize_name(value: str) -> str:
    text = _ascii(value).lower()
    text = text.replace("&", " and ")
    text = re.sub(r"[^a-z0-9]+", " ", text)
    parts = [p for p in text.split() if p and p not in STOPWORDS and not p.isdigit()]
    return " ".join(parts)


def _short_name(name: str) -> str:
    words = [w for w in re.split(r"\s+", name.strip()) if w]
    if not words:
        return "TEAM"
    if len(words) == 1:
        return words[0][:4].upper()
    return "".join(w[0] for w in words[:4]).upper()[:4]


def _title_from_slug(slug: str) -> str:
    return " ".join(part.capitalize() for part in slug.replace("_", "-").split("-") if part)


def _load_all_existing_teams(all_teams_path: Path) -> list[TeamRecord]:
    if not all_teams_path.exists():
        return []
    payload = json.loads(all_teams_path.read_text(encoding="utf-8-sig"))
    raw = payload.get("teams", []) if isinstance(payload, dict) else []
    return [TeamRecord.from_dict(item) for item in raw if isinstance(item, dict)]


def _build_candidate_index(teams: list[TeamRecord]) -> dict[str, list[TeamRecord]]:
    index: dict[str, list[TeamRecord]] = {}
    for team in teams:
        keys = {
            _normalize_name(team.name),
            _normalize_name(team.short_name),
        }

        if "__" in team.badge_file:
            badge_key = team.badge_file.split("__", 1)[1].rsplit(".", 1)[0]
            keys.add(_normalize_name(badge_key))

        for key in keys:
            if not key:
                continue
            index.setdefault(key, []).append(team)
    return index


def _pick_existing_team(
    source_slug: str,
    candidates: list[TeamRecord],
    index: dict[str, list[TeamRecord]],
) -> TeamRecord | None:
    norm = _normalize_name(source_slug)
    if not norm:
        return None

    league_candidates = candidates
    hits = [t for t in index.get(norm, []) if t in league_candidates]
    if hits:
        return hits[0]

    source_tokens = set(norm.split())
    best_team: TeamRecord | None = None
    best_score = 0
    for team in league_candidates:
        team_norm = _normalize_name(team.name)
        tokens = set(team_norm.split())
        if not tokens:
            continue
        overlap = len(source_tokens & tokens)
        if overlap > best_score:
            best_score = overlap
            best_team = team
    if best_score >= 1:
        return best_team

    return None


def _copy_logo(source_path: Path, target_path: Path) -> None:
    target_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source_path, target_path)


def main() -> None:
    cfg = build_default_config()
    root = cfg.base_dir
    local_logo_root = root / "takımlar logoları"
    if not local_logo_root.exists():
        raise FileNotFoundError(f"Klasor bulunamadi: {local_logo_root}")

    data_dir = cfg.data_dir
    teams_dir = data_dir / "teams"
    logos_dir = data_dir / "logos"
    all_teams_path = data_dir / "all_teams.json"
    manifest_path = data_dir / "sync_manifest.json"

    existing_teams = _load_all_existing_teams(all_teams_path)
    by_league: dict[str, list[TeamRecord]] = {}
    for team in existing_teams:
        by_league.setdefault(team.league_slug, []).append(team)
    candidate_index = _build_candidate_index(existing_teams)

    collected: list[TeamRecord] = []
    league_summaries: list[dict[str, object]] = []

    # temiz lig jsonlari: sadece yeni ligler yazilacak
    teams_dir.mkdir(parents=True, exist_ok=True)
    for old_file in teams_dir.glob("*.json"):
        old_file.unlink()

    for spec in LOCAL_LEAGUES:
        folder = local_logo_root / spec.folder_name
        if not folder.exists():
            continue

        source_files = sorted(folder.glob("*.png"))
        league_teams: list[TeamRecord] = []
        pool = by_league.get(spec.source_league_slug or "", existing_teams)

        for file_path in source_files:
            raw_slug = file_path.stem
            raw_slug = re.sub(r"\.football-logos\.cc$", "", raw_slug, flags=re.IGNORECASE)
            clean_slug = _slugify(raw_slug)
            if not clean_slug:
                continue

            match = _pick_existing_team(clean_slug, pool, candidate_index)
            if match:
                team_name = match.name
                base_id = (match.team_id or clean_slug).strip()
                team_id = f"{spec.league_slug}::{base_id}"
                short_name = match.short_name or _short_name(team_name)
                country = match.country or spec.country
                stadium = match.stadium
                formed = match.formed_year
                website = match.website
                description = match.description
            else:
                team_name = _title_from_slug(clean_slug)
                team_id = f"{spec.league_slug}::local_{clean_slug}"
                short_name = _short_name(team_name)
                country = spec.country
                stadium = ""
                formed = ""
                website = ""
                description = ""

            badge_file = f"{spec.league_slug}__{clean_slug}.png"
            target_logo = logos_dir / badge_file
            _copy_logo(file_path, target_logo)

            league_teams.append(
                TeamRecord(
                    team_id=team_id,
                    name=team_name,
                    short_name=short_name,
                    league_name=spec.league_name,
                    league_slug=spec.league_slug,
                    country=country,
                    badge_url="",
                    badge_file=badge_file,
                    stadium=stadium,
                    formed_year=formed,
                    website=website,
                    description=description,
                )
            )

        # lig icinde name+short duplike temizle
        dedup: dict[str, TeamRecord] = {}
        for team in league_teams:
            key = _normalize_name(team.name)
            dedup[key or team.team_key] = team
        league_teams = sorted(dedup.values(), key=lambda t: t.name.lower())

        league_payload = {
            "league_name": spec.league_name,
            "league_slug": spec.league_slug,
            "country": spec.country,
            "team_count": len(league_teams),
            "teams": [asdict(team) for team in league_teams],
        }
        (teams_dir / f"{spec.league_slug}.json").write_text(
            json.dumps(league_payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        collected.extend(league_teams)
        league_summaries.append(
            {
                "league_name": spec.league_name,
                "league_slug": spec.league_slug,
                "country": spec.country,
                "team_count": len(league_teams),
                "downloaded_logos": 0,
            }
        )

    # tum futbol takim havuzu (pop culture runtime'da ayri ekleniyor)
    all_payload = {
        "team_count": len(collected),
        "teams": [asdict(team) for team in collected],
    }
    all_teams_path.write_text(json.dumps(all_payload, ensure_ascii=False, indent=2), encoding="utf-8")

    manifest_payload = {
        "total_teams": len(collected),
        "league_count": len(league_summaries),
        "leagues": league_summaries,
    }
    manifest_path.write_text(json.dumps(manifest_payload, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"Leagues written: {len(league_summaries)}")
    print(f"Teams written  : {len(collected)}")
    print(f"All teams path : {all_teams_path}")


if __name__ == "__main__":
    main()
