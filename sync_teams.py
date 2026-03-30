from __future__ import annotations

import json
import os
import re
import sys
import time
from pathlib import Path
from typing import Any

import requests

from config import build_default_config
from models import LeagueSpec, TeamRecord


CFG = build_default_config()
BASE_DIR = CFG.base_dir
DATA_DIR = CFG.data_dir
TEAMS_DIR = DATA_DIR / "teams"
LOGOS_DIR = DATA_DIR / "logos"
MANIFEST_FILE = DATA_DIR / "sync_manifest.json"
ALL_TEAMS_FILE = DATA_DIR / "all_teams.json"

API_BASE_URL = "https://www.thesportsdb.com/api/v1/json/123"
FOOTBALL_DATA_API_BASE_URL = "https://api.football-data.org/v4"
HTTP_TIMEOUT_SECONDS = 30
REQUEST_PAUSE_SECONDS = 1.2
HTTP_MAX_RETRIES = 5
HTTP_RETRY_BACKOFF_SECONDS = 15.0
FOOTBALL_DATA_TOKEN_ENV = "FOOTBALL_DATA_API_TOKEN"
DEFAULT_FOOTBALL_DATA_TOKEN = "c6b9fdf34b424907b4076f04eb7209e2"

LEAGUES: list[LeagueSpec] = [
    LeagueSpec(
        api_name="English Premier League",
        slug="premier_league",
        country="England",
        aliases=("Premier League",),
    ),
    LeagueSpec(
        api_name="Spanish La Liga",
        slug="la_liga",
        country="Spain",
        aliases=("La Liga", "Primera Division"),
    ),
    LeagueSpec(
        api_name="Italian Serie A",
        slug="serie_a",
        country="Italy",
        aliases=("Serie A",),
    ),
    LeagueSpec(
        api_name="German Bundesliga",
        slug="bundesliga",
        country="Germany",
        aliases=("Bundesliga",),
    ),
    LeagueSpec(
        api_name="French Ligue 1",
        slug="ligue_1",
        country="France",
        aliases=("Ligue 1",),
    ),
    LeagueSpec(
        api_name="Turkish Super Lig",
        slug="super_lig",
        country="Turkiye",
        aliases=("Turkish Super Lig", "Super Lig", "Super Lig Turkey", "Süper Lig"),
    ),
    LeagueSpec(
        api_name="Scottish Premier League",
        slug="scottish_premiership",
        country="Scotland",
        aliases=("Scottish Premiership",),
    ),
    LeagueSpec(
        api_name="Dutch Eredivisie",
        slug="eredivisie",
        country="Netherlands",
        aliases=("Eredivisie",),
    ),
    LeagueSpec(
        api_name="Portuguese Primeira Liga",
        slug="primeira_liga",
        country="Portugal",
        aliases=("Primeira Liga",),
    ),
    LeagueSpec(
        api_name="Belgian Pro League",
        slug="belgian_pro_league",
        country="Belgium",
        aliases=("Belgian First Division A",),
    ),
    LeagueSpec(
        api_name="Greek Superleague Greece",
        slug="greek_superleague",
        country="Greece",
        aliases=("Superleague Greece",),
    ),
    LeagueSpec(
        api_name="Austrian Bundesliga",
        slug="austrian_bundesliga",
        country="Austria",
        aliases=(),
    ),
    LeagueSpec(
        api_name="Swiss Super League",
        slug="swiss_super_league",
        country="Switzerland",
        aliases=(),
    ),
    LeagueSpec(
        api_name="Danish Superliga",
        slug="danish_superliga",
        country="Denmark",
        aliases=(),
    ),
    LeagueSpec(
        api_name="Norwegian Eliteserien",
        slug="eliteserien",
        country="Norway",
        aliases=(),
    ),
    LeagueSpec(
        api_name="Swedish Allsvenskan",
        slug="allsvenskan",
        country="Sweden",
        aliases=(),
    ),
    LeagueSpec(
        api_name="Brazilian Serie A",
        slug="brazilian_serie_a",
        country="Brazil",
        aliases=("Brasileirao Serie A",),
    ),
    LeagueSpec(
        api_name="American Major League Soccer",
        slug="mls",
        country="United States",
        aliases=("Major League Soccer", "MLS"),
    ),
    LeagueSpec(
        api_name="Mexican Primera League",
        slug="liga_mx",
        country="Mexico",
        aliases=("Liga MX",),
    ),
]

NATIONAL_TEAMS_SPEC = LeagueSpec(
    api_name="National Teams",
    slug="national_teams",
    country="International",
    aliases=("FIFA World Cup", "National Teams"),
)

NATIONAL_TEAM_QUERIES: list[str] = [
    # --- Afrika ---
    "Algeria",
    "Cameroon",
    "Congo DR",
    "Egypt",
    "Ghana",
    "Ivory Coast",
    "Mali",
    "Morocco",
    "Nigeria",
    "Senegal",
    "South Africa",
    "Tunisia",
    # --- Asya ---
    "Australia",
    "China",
    "India",
    "Indonesia",
    "Iran",
    "Iraq",
    "Japan",
    "Qatar",
    "Saudi Arabia",
    "South Korea",
    "UAE",
    "Uzbekistan",
    # --- Avrupa ---
    "Albania",
    "Austria",
    "Belgium",
    "Bosnia and Herzegovina",
    "Bulgaria",
    "Croatia",
    "Czech Republic",
    "Denmark",
    "England",
    "Finland",
    "France",
    "Georgia",
    "Germany",
    "Greece",
    "Hungary",
    "Iceland",
    "Ireland",
    "Israel",
    "Italy",
    "Netherlands",
    "North Macedonia",
    "Norway",
    "Poland",
    "Portugal",
    "Romania",
    "Scotland",
    "Serbia",
    "Slovakia",
    "Slovenia",
    "Spain",
    "Sweden",
    "Switzerland",
    "Turkey",
    "Ukraine",
    "Wales",
    # --- Güney Amerika ---
    "Argentina",
    "Bolivia",
    "Brazil",
    "Chile",
    "Colombia",
    "Ecuador",
    "Paraguay",
    "Peru",
    "Uruguay",
    "Venezuela",
    # --- Kuzey & Orta Amerika ---
    "Canada",
    "Costa Rica",
    "Jamaica",
    "Mexico",
    "Panama",
    "USA",
    # --- Okyanusya ---
    "New Zealand",
]

FOOTBALL_DATA_COMPETITION_CODES: dict[str, str] = {
    "premier_league": "PL",
    "la_liga": "PD",
    "serie_a": "SA",
    "bundesliga": "BL1",
    "ligue_1": "FL1",
    "eredivisie": "DED",
    "primeira_liga": "PPL",
    "brazilian_serie_a": "BSA",
}


def slugify_filename(value: str) -> str:
    value = value.strip().lower()
    value = value.replace("&", "and")
    value = re.sub(r"[^\w\s-]", "", value, flags=re.UNICODE)
    value = re.sub(r"[\s-]+", "_", value).strip("_")
    return value or "team"


def ensure_directories() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    TEAMS_DIR.mkdir(parents=True, exist_ok=True)
    LOGOS_DIR.mkdir(parents=True, exist_ok=True)


class TeamSyncService:
    def __init__(self) -> None:
        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": "MarbleRaceTeamSync/1.0",
                "Accept": "application/json",
            }
        )
        self.football_data_token = os.environ.get(FOOTBALL_DATA_TOKEN_ENV, DEFAULT_FOOTBALL_DATA_TOKEN).strip()

    def sync_all(
        self,
        force_redownload_logos: bool = False,
        include_national_teams: bool = False,
    ) -> list[TeamRecord]:
        ensure_directories()

        all_teams: list[TeamRecord] = []
        league_summaries: list[dict[str, Any]] = []

        print("=" * 72)
        print("TAKIM SENKRONIZASYONU BASLADI")
        print("=" * 72)

        for league in LEAGUES:
            print(f"\n[+] Lig isleniyor: {league.api_name}")
            teams = self.fetch_league_teams(league)
            cached_teams = self.load_saved_league_teams(league.slug)

            if not teams and cached_teams:
                teams = cached_teams
                print(f"    - API bos dondu, kayitli lig havuzu kullanildi ({len(teams)} takim).")

            if not teams:
                print(f"    ! Uyari: {league.api_name} icin takim verisi alinamadi.")
                continue

            saved_count = self.save_league_teams(league, teams)
            downloaded_logos = self.download_league_logos(
                teams=teams,
                force_redownload=force_redownload_logos,
            )

            league_summaries.append(
                {
                    "league_name": league.api_name,
                    "league_slug": league.slug,
                    "country": league.country,
                    "team_count": saved_count,
                    "downloaded_logos": downloaded_logos,
                }
            )

            all_teams.extend(teams)

        cached_national_teams = self.load_saved_league_teams(NATIONAL_TEAMS_SPEC.slug)
        if include_national_teams:
            print(f"\n[+] Ozel havuz isleniyor: {NATIONAL_TEAMS_SPEC.api_name}")
            national_teams = self.fetch_national_teams()
            if national_teams and cached_national_teams:
                fetched_count = len(national_teams)
                national_teams = self._merge_team_lists([*cached_national_teams, *national_teams])
                if len(national_teams) > fetched_count:
                    print(f"    - Kayitli milli takimlarla birlestirildi, toplam {len(national_teams)} takim.")
            elif not national_teams and cached_national_teams:
                national_teams = cached_national_teams
                print(f"    - API bos dondu, kayitli milli takim havuzu kullanildi ({len(national_teams)} takim).")

            if national_teams:
                saved_count = self.save_league_teams(NATIONAL_TEAMS_SPEC, national_teams)
                downloaded_logos = self.download_league_logos(
                    teams=national_teams,
                    force_redownload=force_redownload_logos,
                )
                league_summaries.append(
                    {
                        "league_name": NATIONAL_TEAMS_SPEC.api_name,
                        "league_slug": NATIONAL_TEAMS_SPEC.slug,
                        "country": NATIONAL_TEAMS_SPEC.country,
                        "team_count": saved_count,
                        "downloaded_logos": downloaded_logos,
                    }
                )
                all_teams.extend(national_teams)
            else:
                print("    ! Uyari: Milli takim verisi alinamadi.")
        else:
            if cached_national_teams:
                print(f"\n[+] Kayitli milli takim havuzu korundu: {len(cached_national_teams)} takim")
                all_teams.extend(cached_national_teams)

        all_teams = self._deduplicate_teams(all_teams)
        self.save_all_teams(all_teams)
        self.save_manifest(all_teams, league_summaries)

        print("\n" + "=" * 72)
        print("TAKIM SENKRONIZASYONU TAMAMLANDI")
        print(f"Toplam benzersiz takim: {len(all_teams)}")
        print(f"Tum takimlar dosyasi  : {ALL_TEAMS_FILE}")
        print("=" * 72)

        return all_teams

    def fetch_league_teams(self, league: LeagueSpec) -> list[TeamRecord]:
        # Önce cache kontrol et — varsa API'yi zorlamadan dön
        cached = self.load_saved_league_teams(league.slug)
        if cached:
            print(f"    - Cache mevcut ({len(cached)} takim). API deneniyor ama basarisiz olursa cache kullanilacak.")

        collected_teams: list[TeamRecord] = []

        football_data_teams = self.fetch_league_teams_from_football_data(league)
        if football_data_teams:
            collected_teams.extend(football_data_teams)

        api_success = False
        for candidate_name in league.all_candidate_names():
            print(f"    - API denemesi: {candidate_name}")
            payload = self._get_json(
                endpoint="search_all_teams.php",
                params={"l": candidate_name},
            )

            teams_raw = payload.get("teams") if isinstance(payload, dict) else None
            if teams_raw:
                mapped = [
                    self._map_team_record(item, league)
                    for item in teams_raw
                    if isinstance(item, dict)
                    and str(item.get("strSport") or "").strip().lower() == "soccer"
                ]
                print(f"      Basarili. {len(mapped)} soccer takim bulundu.")
                collected_teams.extend(mapped)
                api_success = True
                time.sleep(REQUEST_PAUSE_SECONDS)
                break  # Basarili sonuc bulduk, diger alias'lari denemeye gerek yok

            print("      Sonuc bos geldi, sonraki lig adi deneniyor...")
            time.sleep(REQUEST_PAUSE_SECONDS)

        merged_teams = self._merge_team_lists(collected_teams)
        if merged_teams:
            print(f"    - Kaynaklar birlestirildi, toplam {len(merged_teams)} benzersiz takim.")
            return merged_teams

        # API tamamen bos döndüyse cache'e düş
        if not api_success and cached:
            print(f"    - API basarisiz, cache kullaniliyor ({len(cached)} takim).")
            return cached

        return merged_teams

    def fetch_league_teams_from_football_data(self, league: LeagueSpec) -> list[TeamRecord]:
        competition_code = FOOTBALL_DATA_COMPETITION_CODES.get(league.slug)
        if not competition_code or not self.football_data_token:
            return []

        print(f"    - football-data denemesi: {competition_code}")
        try:
            payload = self._get_json_football_data(f"competitions/{competition_code}/teams")
        except Exception as exc:
            print(f"      football-data hatasi, fallback'e geciliyor: {exc}")
            return []

        raw_teams = payload.get("teams") if isinstance(payload, dict) else None
        if not isinstance(raw_teams, list) or not raw_teams:
            print("      football-data bos sonuc verdi.")
            return []

        mapped = [self._map_football_data_team_record(item, league) for item in raw_teams if isinstance(item, dict)]
        print(f"      football-data basarili. {len(mapped)} takim bulundu.")
        time.sleep(REQUEST_PAUSE_SECONDS)
        return mapped

    def fetch_national_teams(self) -> list[TeamRecord]:
        teams: list[TeamRecord] = []
        total = len(NATIONAL_TEAM_QUERIES)
        for idx, query in enumerate(NATIONAL_TEAM_QUERIES, 1):
            print(f"    - [{idx}/{total}] Milli takim aranıyor: {query}")
            payload = self._get_json(
                endpoint="searchteams.php",
                params={"t": query},
            )

            teams_raw = payload.get("teams") if isinstance(payload, dict) else None
            if not teams_raw:
                print("      Sonuc bos geldi.")
                time.sleep(REQUEST_PAUSE_SECONDS)
                continue

            picked = self._pick_national_team_result(teams_raw, query)
            if picked is None:
                print("      Uygun milli takim kaydi bulunamadi.")
                time.sleep(REQUEST_PAUSE_SECONDS)
                continue

            team = self._map_national_team_record(picked, query)
            teams.append(team)
            print(f"      Eklendi: {team.name}")
            time.sleep(REQUEST_PAUSE_SECONDS)

        return self._deduplicate_teams(teams)

    def save_league_teams(self, league: LeagueSpec, teams: list[TeamRecord]) -> int:
        output_file = TEAMS_DIR / f"{league.slug}.json"
        payload = {
            "league_name": league.api_name,
            "league_slug": league.slug,
            "country": league.country,
            "team_count": len(teams),
            "teams": [team.to_dict() for team in teams],
        }
        output_file.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"    - Lig JSON kaydedildi: {output_file}")
        return len(teams)

    def load_saved_league_teams(self, league_slug: str) -> list[TeamRecord]:
        file_path = TEAMS_DIR / f"{league_slug}.json"
        if not file_path.exists():
            return []

        payload = json.loads(file_path.read_text(encoding="utf-8"))
        raw_teams = payload.get("teams", []) if isinstance(payload, dict) else []
        return [TeamRecord.from_dict(item) for item in raw_teams if isinstance(item, dict)]

    def save_all_teams(self, teams: list[TeamRecord]) -> None:
        payload = {
            "team_count": len(teams),
            "teams": [team.to_dict() for team in teams],
        }
        ALL_TEAMS_FILE.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"[*] Birlesik takim havuzu kaydedildi: {ALL_TEAMS_FILE}")

    def save_manifest(self, all_teams: list[TeamRecord], league_summaries: list[dict[str, Any]]) -> None:
        payload = {
            "total_teams": len(all_teams),
            "league_count": len(league_summaries),
            "leagues": league_summaries,
        }
        MANIFEST_FILE.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"[*] Manifest kaydedildi: {MANIFEST_FILE}")

    def download_league_logos(self, teams: list[TeamRecord], force_redownload: bool = False) -> int:
        download_count = 0

        for team in teams:
            if not team.badge_url:
                print(f"    ! Logo URL yok: {team.name}")
                continue

            target_file = team.logo_path(DATA_DIR)
            if target_file.exists() and not force_redownload:
                continue

            try:
                self._download_file(team.badge_url, target_file)
                download_count += 1
                print(f"    - Logo indirildi: {team.name} -> {target_file.name}")
            except Exception as exc:
                print(f"    ! Logo indirilemedi: {team.name} | {exc}")

            time.sleep(REQUEST_PAUSE_SECONDS)

        return download_count

    def _get_json(self, endpoint: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        url = f"{API_BASE_URL}/{endpoint}"

        for attempt in range(1, HTTP_MAX_RETRIES + 1):
            try:
                response = self.session.get(url, params=params or {}, timeout=HTTP_TIMEOUT_SECONDS)

                if response.status_code == 429:
                    wait_seconds = HTTP_RETRY_BACKOFF_SECONDS * attempt
                    print(f"      429 rate limit alindi (deneme {attempt}/{HTTP_MAX_RETRIES}). {wait_seconds:.0f} sn bekleniyor...")
                    time.sleep(wait_seconds)
                    continue

                response.raise_for_status()

                try:
                    payload = response.json()
                except ValueError:
                    print(f"      API JSON dondurmedi (HTML/bos cevap). Atlaniyor.")
                    return {}

                if not isinstance(payload, dict):
                    return {}
                return payload

            except requests.HTTPError as exc:
                print(f"      HTTP hatasi ({exc}). Atlaniyor.")
                return {}
            except requests.ConnectionError as exc:
                print(f"      Baglanti hatasi ({exc}). Atlaniyor.")
                return {}
            except requests.Timeout:
                print(f"      Zaman asimi. Atlaniyor.")
                return {}
            except Exception as exc:
                print(f"      Beklenmeyen hata ({exc}). Atlaniyor.")
                return {}

        print(f"      {HTTP_MAX_RETRIES} deneme sonrasi basarisiz. Cache kullanilacak.")
        return {}

    def _get_json_football_data(self, endpoint: str) -> dict[str, Any]:
        url = f"{FOOTBALL_DATA_API_BASE_URL}/{endpoint}"
        response = self.session.get(
            url,
            headers={"X-Auth-Token": self.football_data_token},
            timeout=HTTP_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict):
            raise ValueError("football-data beklenmeyen formatta veri dondurdu.")
        return payload

    def _download_file(self, url: str, target_file: Path) -> None:
        target_file.parent.mkdir(parents=True, exist_ok=True)
        with self.session.get(url, timeout=HTTP_TIMEOUT_SECONDS, stream=True) as response:
            response.raise_for_status()
            with open(target_file, "wb") as file_obj:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        file_obj.write(chunk)

    def _map_team_record(self, item: dict[str, Any], league: LeagueSpec) -> TeamRecord:
        team_name = str(item.get("strTeam") or "").strip()
        short_name = str(item.get("strTeamShort") or "").strip()
        if not short_name:
            short_name = self._build_short_name(team_name)

        badge_url = str(item.get("strBadge") or "").strip()
        safe_name = slugify_filename(team_name)
        badge_file = f"{league.slug}__{safe_name}.png"

        return TeamRecord(
            team_id=str(item.get("idTeam") or "").strip(),
            name=team_name,
            short_name=short_name,
            league_name=league.api_name,
            league_slug=league.slug,
            country=league.country,
            badge_url=badge_url,
            badge_file=badge_file,
            stadium=str(item.get("strStadium") or "").strip(),
            formed_year=str(item.get("intFormedYear") or "").strip(),
            website=str(item.get("strWebsite") or "").strip(),
            description=str(item.get("strDescriptionEN") or "").strip(),
        )

    def _map_football_data_team_record(self, item: dict[str, Any], league: LeagueSpec) -> TeamRecord:
        team_name = str(item.get("name") or "").strip()
        short_name = str(item.get("shortName") or "").strip() or str(item.get("tla") or "").strip()
        if not short_name:
            short_name = self._build_short_name(team_name)

        badge_url = self._normalize_football_data_crest_url(str(item.get("crest") or "").strip())
        safe_name = slugify_filename(team_name)
        badge_file = f"{league.slug}__{safe_name}.png"

        return TeamRecord(
            team_id=str(item.get("id") or "").strip(),
            name=team_name,
            short_name=short_name,
            league_name=league.api_name,
            league_slug=league.slug,
            country=str((item.get("area") or {}).get("name") or league.country).strip(),
            badge_url=badge_url,
            badge_file=badge_file,
            stadium=str(item.get("venue") or "").strip(),
            formed_year=str(item.get("founded") or "").strip(),
            website=str(item.get("website") or "").strip(),
            description="",
        )

    def _map_national_team_record(self, item: dict[str, Any], query: str) -> TeamRecord:
        team_name = str(item.get("strTeam") or "").strip() or query
        short_name = str(item.get("strTeamShort") or "").strip()
        if not short_name:
            short_name = self._build_short_name(team_name)

        country = str(item.get("strCountry") or "").strip() or team_name
        badge_url = str(item.get("strBadge") or "").strip()
        safe_name = slugify_filename(team_name)
        badge_file = f"{NATIONAL_TEAMS_SPEC.slug}__{safe_name}.png"
        league_name = NATIONAL_TEAMS_SPEC.api_name

        return TeamRecord(
            team_id=str(item.get("idTeam") or "").strip(),
            name=team_name,
            short_name=short_name,
            league_name=league_name,
            league_slug=NATIONAL_TEAMS_SPEC.slug,
            country=country,
            badge_url=badge_url,
            badge_file=badge_file,
            stadium=str(item.get("strStadium") or "").strip(),
            formed_year=str(item.get("intFormedYear") or "").strip(),
            website=str(item.get("strWebsite") or "").strip(),
            description=str(item.get("strDescriptionEN") or "").strip(),
        )

    def _build_short_name(self, team_name: str) -> str:
        if not team_name:
            return "TEAM"

        words = [part for part in re.split(r"\s+", team_name.strip()) if part]
        if len(words) == 1:
            return words[0][:4].upper()
        return "".join(word[0] for word in words[:4]).upper()[:4]

    def _merge_team_lists(self, teams: list[TeamRecord]) -> list[TeamRecord]:
        merged: dict[str, TeamRecord] = {}
        for team in teams:
            league_key = team.league_slug.strip().lower()
            team_name_key = team.name.strip().lower()
            team_id_key = team.team_id.strip().lower()
            fallback_key = team_name_key or team_id_key or team.short_name.strip().lower() or "unknown"
            key = f"{league_key}:{fallback_key}"

            existing = merged.get(key)
            if existing is None:
                merged[key] = team
            else:
                merged[key] = self._merge_team_records(existing, team)

        return sorted(merged.values(), key=lambda item: (item.league_name.lower(), item.name.lower()))

    def _merge_team_records(self, first: TeamRecord, second: TeamRecord) -> TeamRecord:
        short_name = first.short_name.strip()
        if not short_name or short_name.upper() == "TEAM":
            short_name = second.short_name.strip() or self._build_short_name(first.name or second.name)

        return TeamRecord(
            team_id=first.team_id.strip() or second.team_id.strip(),
            name=first.name.strip() or second.name.strip(),
            short_name=short_name,
            league_name=first.league_name.strip() or second.league_name.strip(),
            league_slug=first.league_slug.strip() or second.league_slug.strip(),
            country=self._pick_richer_text(first.country, second.country),
            badge_url=first.badge_url.strip() or second.badge_url.strip(),
            badge_file=first.badge_file.strip() or second.badge_file.strip(),
            stadium=self._pick_richer_text(first.stadium, second.stadium),
            formed_year=first.formed_year.strip() or second.formed_year.strip(),
            website=self._pick_richer_text(first.website, second.website),
            description=self._pick_richer_text(first.description, second.description),
        )

    def _pick_richer_text(self, first: str, second: str) -> str:
        first_clean = first.strip()
        second_clean = second.strip()
        if len(second_clean) > len(first_clean):
            return second_clean
        return first_clean

    def _deduplicate_teams(self, teams: list[TeamRecord]) -> list[TeamRecord]:
        return self._merge_team_lists(teams)

    def _pick_national_team_result(self, teams_raw: list[Any], query: str) -> dict[str, Any] | None:
        normalized_query = query.strip().lower()
        candidates: list[dict[str, Any]] = [item for item in teams_raw if isinstance(item, dict)]
        if not candidates:
            return None

        for item in candidates:
            team_name = str(item.get("strTeam") or "").strip().lower()
            country = str(item.get("strCountry") or "").strip().lower()
            sport = str(item.get("strSport") or "").strip().lower()
            league = str(item.get("strLeague") or "").strip().lower()
            if sport != "soccer":
                continue
            if normalized_query in (team_name, country):
                return item
            if "world cup" in league or "qualifying" in league or "nations league" in league:
                return item

        return candidates[0]

    def _normalize_football_data_crest_url(self, url: str) -> str:
        if not url:
            return url
        if url.endswith(".svg"):
            return url[:-4] + ".png"
        return url


def main() -> None:
    force_redownload = "--force-logos" in sys.argv
    include_national_teams = "--include-national-teams" in sys.argv
    try:
        service = TeamSyncService()
        service.sync_all(
            force_redownload_logos=force_redownload,
            include_national_teams=include_national_teams,
        )
    except requests.HTTPError as exc:
        print("\nHTTP HATASI OLUSTU")
        print(exc)
        sys.exit(1)
    except Exception as exc:
        print("\nBEKLENMEYEN HATA OLUSTU")
        print(exc)
        sys.exit(1)


if __name__ == "__main__":
    main()
