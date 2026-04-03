from __future__ import annotations

import argparse
import json
import time
import urllib.parse
from dataclasses import dataclass
from io import BytesIO
from typing import Any

import requests
from PIL import Image, ImageOps

from config import build_default_config
from team_repository import TeamRepository


WIKIPEDIA_SUMMARY_API = "https://en.wikipedia.org/api/rest_v1/page/summary/{title}"
HTTP_TIMEOUT_SECONDS = 30
MAX_RETRIES = 6
RETRY_BASE_SECONDS = 4.0
REQUEST_PAUSE_SECONDS = 1.1


@dataclass(frozen=True)
class LogoSource:
    wikipedia_title: str | None = None
    direct_url: str | None = None


TEAM_SOURCE_MAP: dict[str, LogoSource] = {
    # Superheroes
    "Spider-Man": LogoSource(wikipedia_title="Spider-Man"),
    "Batman": LogoSource(wikipedia_title="Batman"),
    "Iron Man": LogoSource(wikipedia_title="Iron Man"),
    "Superman": LogoSource(wikipedia_title="Superman"),
    # Star Wars
    "Darth Vader": LogoSource(wikipedia_title="Darth Vader"),
    "Luke Skywalker": LogoSource(wikipedia_title="Luke Skywalker"),
    "Yoda": LogoSource(wikipedia_title="Yoda"),
    "Obi-Wan Kenobi": LogoSource(wikipedia_title="Obi-Wan Kenobi"),
    "Kylo Ren": LogoSource(wikipedia_title="Kylo Ren"),
    # Game of Thrones
    "Jon Snow": LogoSource(wikipedia_title="Jon Snow (character)"),
    "Daenerys Targaryen": LogoSource(wikipedia_title="Daenerys Targaryen"),
    "Tyrion Lannister": LogoSource(wikipedia_title="Tyrion Lannister"),
    "Arya Stark": LogoSource(wikipedia_title="Arya Stark"),
    "Night King": LogoSource(wikipedia_title="Night King"),
    # Tech Brands
    "Apple": LogoSource(
        wikipedia_title="Apple Inc.",
        direct_url="https://logo.clearbit.com/apple.com",
    ),
    "Google": LogoSource(
        wikipedia_title="Google",
        direct_url="https://logo.clearbit.com/google.com",
    ),
    "Microsoft": LogoSource(
        wikipedia_title="Microsoft",
        direct_url="https://logo.clearbit.com/microsoft.com",
    ),
    "Amazon": LogoSource(
        wikipedia_title="Amazon (company)",
        direct_url="https://logo.clearbit.com/amazon.com",
    ),
    "Meta": LogoSource(
        wikipedia_title="Meta Platforms",
        direct_url="https://logo.clearbit.com/meta.com",
    ),
    "OpenAI": LogoSource(
        wikipedia_title="OpenAI",
        direct_url="https://commons.wikimedia.org/wiki/Special:FilePath/OpenAI_Logo_Since_February_2025.png",
    ),
    # Fast Food
    "McDonalds": LogoSource(
        wikipedia_title="McDonald's",
        direct_url="https://logo.clearbit.com/mcdonalds.com",
    ),
    "Burger King": LogoSource(
        wikipedia_title="Burger King",
        direct_url="https://logo.clearbit.com/bk.com",
    ),
    "KFC": LogoSource(
        wikipedia_title="KFC",
        direct_url="https://logo.clearbit.com/kfc.com",
    ),
    "Wendys": LogoSource(
        wikipedia_title="Wendy's",
        direct_url="https://logo.clearbit.com/wendys.com",
    ),
    "Taco Bell": LogoSource(
        wikipedia_title="Taco Bell",
        direct_url="https://logo.clearbit.com/tacobell.com",
    ),
    # Football legends
    "Lionel Messi": LogoSource(wikipedia_title="Lionel Messi"),
    "Cristiano Ronaldo": LogoSource(wikipedia_title="Cristiano Ronaldo"),
    "Diego Maradona": LogoSource(wikipedia_title="Diego Maradona"),
    "Pele": LogoSource(wikipedia_title="Pele"),
    "Zinedine Zidane": LogoSource(wikipedia_title="Zinedine Zidane"),
    "Ronaldinho": LogoSource(wikipedia_title="Ronaldinho"),
    # Games
    "League of Legends": LogoSource(wikipedia_title="League of Legends"),
    "Valorant": LogoSource(wikipedia_title="Valorant"),
    "CS:GO": LogoSource(wikipedia_title="Counter-Strike: Global Offensive"),
    "Dota 2": LogoSource(wikipedia_title="Dota 2"),
    "Minecraft": LogoSource(wikipedia_title="Minecraft"),
    "GTA V": LogoSource(wikipedia_title="Grand Theft Auto V"),
}


def _fetch_json(session: requests.Session, url: str) -> dict[str, Any]:
    last_error = ""
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            response = session.get(url, timeout=HTTP_TIMEOUT_SECONDS)
            if response.status_code == 429:
                retry_after = response.headers.get("Retry-After", "").strip()
                wait_seconds = float(retry_after) if retry_after.isdigit() else RETRY_BASE_SECONDS * attempt
                time.sleep(wait_seconds)
                continue
            response.raise_for_status()
            payload = response.json()
            if not isinstance(payload, dict):
                raise ValueError("JSON payload beklenen formatta degil.")
            return payload
        except Exception as exc:  # noqa: BLE001
            last_error = str(exc)
            if attempt < MAX_RETRIES:
                time.sleep(RETRY_BASE_SECONDS * attempt)
                continue
            break
    raise RuntimeError(last_error or "JSON indirilemedi.")


def _download_bytes(session: requests.Session, url: str) -> bytes:
    last_error = ""
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            response = session.get(url, timeout=HTTP_TIMEOUT_SECONDS)
            if response.status_code == 429:
                retry_after = response.headers.get("Retry-After", "").strip()
                wait_seconds = float(retry_after) if retry_after.isdigit() else RETRY_BASE_SECONDS * attempt
                time.sleep(wait_seconds)
                continue
            response.raise_for_status()
            return response.content
        except Exception as exc:  # noqa: BLE001
            last_error = str(exc)
            if attempt < MAX_RETRIES:
                time.sleep(RETRY_BASE_SECONDS * attempt)
                continue
            break
    raise RuntimeError(last_error or "Dosya indirilemedi.")


def _resolve_wikipedia_image_url(session: requests.Session, title: str) -> str | None:
    encoded_title = urllib.parse.quote(title, safe="")
    url = WIKIPEDIA_SUMMARY_API.format(title=encoded_title)
    payload = _fetch_json(session, url)

    original = payload.get("originalimage")
    if isinstance(original, dict):
        source = str(original.get("source") or "").strip()
        if source:
            return source

    thumbnail = payload.get("thumbnail")
    if isinstance(thumbnail, dict):
        source = str(thumbnail.get("source") or "").strip()
        if source:
            return source

    return None


def _normalize_to_logo_png(raw_bytes: bytes) -> bytes:
    image = Image.open(BytesIO(raw_bytes))
    image = ImageOps.exif_transpose(image).convert("RGBA")
    image.thumbnail((460, 460), Image.Resampling.LANCZOS)

    canvas = Image.new("RGBA", (512, 512), (0, 0, 0, 0))
    offset_x = (512 - image.width) // 2
    offset_y = (512 - image.height) // 2
    canvas.paste(image, (offset_x, offset_y), image)

    output = BytesIO()
    canvas.save(output, format="PNG")
    return output.getvalue()


def sync_pop_culture_logos(force: bool = False, only_team_names: set[str] | None = None) -> None:
    cfg = build_default_config()
    repo = TeamRepository(cfg.data_dir)
    teams = [team for team in repo.load_teams(force_reload=True) if team.league_slug.startswith("pop_culture_")]

    session = requests.Session()
    session.headers.update({"User-Agent": "PopCultureLogoSync/1.0"})

    manifest_entries: list[dict[str, str]] = []
    success = 0
    failed: list[str] = []

    for team in teams:
        if only_team_names and team.name not in only_team_names:
            continue

        source = TEAM_SOURCE_MAP.get(team.name)
        if source is None:
            failed.append(f"{team.name}: kaynagi tanimli degil")
            continue

        badge_path = cfg.data_dir / "logos" / team.badge_file
        if badge_path.exists() and not force:
            continue

        candidate_urls: list[str] = []
        if source.direct_url:
            candidate_urls.append(source.direct_url)
        if source.wikipedia_title:
            wiki_url = _resolve_wikipedia_image_url(session, source.wikipedia_title)
            if wiki_url:
                candidate_urls.append(wiki_url)

        if not candidate_urls:
            failed.append(f"{team.name}: URL bulunamadi")
            continue

        last_error = ""
        wrote_file = False
        used_url = ""
        for candidate_url in candidate_urls:
            try:
                raw = _download_bytes(session, candidate_url)
                normalized_png = _normalize_to_logo_png(raw)
                badge_path.parent.mkdir(parents=True, exist_ok=True)
                badge_path.write_bytes(normalized_png)
                used_url = candidate_url
                wrote_file = True
                break
            except Exception as exc:  # noqa: BLE001
                last_error = str(exc)
                continue
            finally:
                time.sleep(REQUEST_PAUSE_SECONDS)

        if wrote_file:
            success += 1
            manifest_entries.append(
                {
                    "team_name": team.name,
                    "league_name": team.league_name,
                    "badge_file": team.badge_file,
                    "source_url": used_url,
                    "wikipedia_title": source.wikipedia_title or "",
                }
            )
            print(f"[OK] {team.name} -> {team.badge_file}")
        else:
            failed.append(f"{team.name}: indirilemedi ({last_error})")

    manifest_path = cfg.data_dir / "pop_culture_logo_manifest.json"
    manifest_payload = {
        "updated_count": success,
        "failed_count": len(failed),
        "entries": manifest_entries,
        "failed_items": failed,
    }
    manifest_path.write_text(json.dumps(manifest_payload, ensure_ascii=False, indent=2), encoding="utf-8")

    print("-" * 72)
    print(f"Toplam pop culture takim: {len(teams)}")
    print(f"Guncellenen logo sayisi : {success}")
    print(f"Basarisiz sayi          : {len(failed)}")
    print(f"Manifest                : {manifest_path}")
    if failed:
        print("Basarisizlar:")
        for item in failed:
            print(f" - {item}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Sync pop culture logos from internet sources.")
    parser.add_argument("--force", action="store_true", help="Overwrite existing logo files.")
    parser.add_argument(
        "--only",
        type=str,
        default="",
        help="Comma-separated team names to process.",
    )
    args = parser.parse_args()

    only_names = {part.strip() for part in args.only.split(",") if part.strip()} or None
    sync_pop_culture_logos(force=args.force, only_team_names=only_names)
