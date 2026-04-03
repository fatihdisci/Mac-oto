from __future__ import annotations

import re
from pathlib import Path
from typing import Iterable

from models import TeamRecord

try:
    from PIL import Image, ImageDraw, ImageFont
except Exception:  # pragma: no cover - optional runtime dependency
    Image = None
    ImageDraw = None
    ImageFont = None


POP_CULTURE_CATEGORIES: list[dict] = [
    {
        "id": "superheroes",
        "name": "Superkahramanlar",
        "display_title": "SUPERHERO BATTLE",
        "theme_primary": (139, 92, 246),
        "theme_secondary": (0, 212, 255),
        "background_color": (13, 5, 32),
        "contestants": [
            {"name": "Spider-Man", "short_name": "SPDY", "color": (227, 37, 37), "universe": "Marvel"},
            {"name": "Batman", "short_name": "BTMN", "color": (40, 40, 40), "universe": "DC"},
            {"name": "Iron Man", "short_name": "IRON", "color": (200, 50, 30), "universe": "Marvel"},
            {"name": "Superman", "short_name": "SUPE", "color": (30, 80, 180), "universe": "DC"},
        ],
    },
    {
        "id": "starwars",
        "name": "Star Wars Karakterleri",
        "display_title": "STAR WARS BATTLE",
        "theme_primary": (255, 232, 31),
        "theme_secondary": (20, 20, 20),
        "background_color": (5, 5, 10),
        "contestants": [
            {"name": "Darth Vader", "short_name": "VADR", "color": (220, 20, 20), "universe": "Empire"},
            {"name": "Luke Skywalker", "short_name": "LUKE", "color": (50, 200, 50), "universe": "Jedi"},
            {"name": "Yoda", "short_name": "YODA", "color": (100, 220, 80), "universe": "Jedi"},
            {"name": "Obi-Wan Kenobi", "short_name": "MSTR", "color": (50, 100, 220), "universe": "Jedi"},
            {"name": "Kylo Ren", "short_name": "KYLO", "color": (255, 50, 50), "universe": "First Order"},
        ],
    },
    {
        "id": "got",
        "name": "Game of Thrones Haneleri",
        "display_title": "WESTEROS BATTLE",
        "theme_primary": (150, 0, 0),
        "theme_secondary": (200, 150, 50),
        "background_color": (20, 10, 10),
        "contestants": [
            {"name": "Jon Snow", "short_name": "SNOW", "color": (100, 110, 120), "universe": "Stark"},
            {"name": "Daenerys Targaryen", "short_name": "DANY", "color": (180, 30, 30), "universe": "Targaryen"},
            {"name": "Tyrion Lannister", "short_name": "TYRN", "color": (210, 180, 40), "universe": "Lannister"},
            {"name": "Arya Stark", "short_name": "ARYA", "color": (90, 90, 100), "universe": "Stark"},
            {"name": "Night King", "short_name": "NITE", "color": (40, 120, 255), "universe": "White Walkers"},
        ],
    },
    {
        "id": "techbrands",
        "name": "Teknoloji Devleri",
        "display_title": "TECH BRAND WARS",
        "theme_primary": (0, 150, 255),
        "theme_secondary": (200, 200, 200),
        "background_color": (15, 20, 30),
        "contestants": [
            {"name": "Apple", "short_name": "APPL", "color": (150, 150, 150), "universe": "Tech"},
            {"name": "Google", "short_name": "GOOG", "color": (66, 133, 244), "universe": "Tech"},
            {"name": "Microsoft", "short_name": "MSFT", "color": (242, 80, 34), "universe": "Tech"},
            {"name": "Amazon", "short_name": "AMZN", "color": (255, 153, 0), "universe": "Tech"},
            {"name": "Meta", "short_name": "META", "color": (6, 104, 225), "universe": "Tech"},
            {"name": "OpenAI", "short_name": "O-AI", "color": (16, 163, 127), "universe": "Tech"},
        ],
    },
    {
        "id": "fastfood",
        "name": "Fast Food Markalari",
        "display_title": "FAST FOOD WARS",
        "theme_primary": (255, 100, 0),
        "theme_secondary": (255, 200, 0),
        "background_color": (30, 15, 5),
        "contestants": [
            {"name": "McDonalds", "short_name": "MCD", "color": (255, 199, 44), "universe": "Fast Food"},
            {"name": "Burger King", "short_name": "BK", "color": (215, 35, 0), "universe": "Fast Food"},
            {"name": "KFC", "short_name": "KFC", "color": (163, 20, 32), "universe": "Fast Food"},
            {"name": "Wendys", "short_name": "WNDY", "color": (225, 40, 40), "universe": "Fast Food"},
            {"name": "Taco Bell", "short_name": "TACO", "color": (112, 32, 130), "universe": "Fast Food"},
        ],
    },
    {
        "id": "football_legends",
        "name": "Futbol Efsaneleri",
        "display_title": "FOOTBALL LEGENDS",
        "theme_primary": (40, 200, 80),
        "theme_secondary": (255, 255, 255),
        "background_color": (10, 30, 15),
        "contestants": [
            {"name": "Lionel Messi", "short_name": "MESI", "color": (100, 180, 255), "universe": "Argentina / Barca"},
            {"name": "Cristiano Ronaldo", "short_name": "CR7", "color": (220, 20, 40), "universe": "Portugal / RM"},
            {"name": "Diego Maradona", "short_name": "D10S", "color": (80, 160, 240), "universe": "Argentina / Napoli"},
            {"name": "Pele", "short_name": "PELE", "color": (255, 220, 0), "universe": "Brazil / Santos"},
            {"name": "Zinedine Zidane", "short_name": "ZIZU", "color": (0, 85, 164), "universe": "France / RM"},
            {"name": "Ronaldinho", "short_name": "R10", "color": (255, 200, 50), "universe": "Brazil / Barca"},
        ],
    },
    {
        "id": "games",
        "name": "Video Oyunlari",
        "display_title": "GAMING WARS",
        "theme_primary": (138, 43, 226),
        "theme_secondary": (0, 255, 255),
        "background_color": (20, 20, 40),
        "contestants": [
            {"name": "League of Legends", "short_name": "LOL", "color": (200, 170, 70), "universe": "Riot Games"},
            {"name": "Valorant", "short_name": "VALO", "color": (255, 70, 85), "universe": "Riot Games"},
            {"name": "CS:GO", "short_name": "CSGO", "color": (255, 200, 0), "universe": "Valve"},
            {"name": "Dota 2", "short_name": "DOTA", "color": (220, 60, 40), "universe": "Valve"},
            {"name": "Minecraft", "short_name": "MC", "color": (80, 200, 80), "universe": "Mojang"},
            {"name": "GTA V", "short_name": "GTA5", "color": (80, 180, 90), "universe": "Rockstar"},
        ],
    },
]


def _slugify(value: str) -> str:
    value = value.strip().lower()
    value = value.replace("&", "and")
    value = re.sub(r"[^a-z0-9\s_-]", "", value)
    value = re.sub(r"[\s_-]+", "_", value).strip("_")
    return value or "team"


def _mix_color(color_a: tuple[int, int, int], color_b: tuple[int, int, int], ratio: float) -> tuple[int, int, int]:
    ratio = max(0.0, min(1.0, ratio))
    return tuple(int(color_a[idx] * (1.0 - ratio) + color_b[idx] * ratio) for idx in range(3))


def _load_font(size: int):
    if ImageFont is None:
        return None

    for candidate in ("arialbd.ttf", "arial.ttf", "segoeuib.ttf", "segoeui.ttf", "DejaVuSans-Bold.ttf"):
        try:
            return ImageFont.truetype(candidate, size=size)
        except OSError:
            continue
    return ImageFont.load_default()


def _create_logo(
    output_path: Path,
    short_name: str,
    primary: tuple[int, int, int],
    secondary: tuple[int, int, int],
    background: tuple[int, int, int],
) -> None:
    if Image is None or ImageDraw is None:
        return

    size = 512
    img = Image.new("RGBA", (size, size), (*background, 255))
    draw = ImageDraw.Draw(img, "RGBA")

    for idx in range(7):
        ratio = idx / 6.0
        color = _mix_color(primary, secondary, ratio)
        inset = 14 + idx * 22
        draw.ellipse(
            (inset, inset, size - inset, size - inset),
            outline=(*color, 228),
            width=14,
        )

    draw.ellipse((72, 72, size - 72, size - 72), fill=(*secondary, 55))
    draw.ellipse((108, 108, size - 108, size - 108), fill=(*background, 170))
    draw.ellipse((128, 128, size - 128, size - 128), outline=(*primary, 255), width=8)

    label = (short_name.strip().upper() or "POP")[:4]
    font_size = 170 if len(label) <= 3 else 140
    font = _load_font(font_size)
    if font is not None:
        bbox = draw.textbbox((0, 0), label, font=font)
        text_w = bbox[2] - bbox[0]
        text_h = bbox[3] - bbox[1]
        draw.text(
            ((size - text_w) // 2, (size - text_h) // 2 - 6),
            label,
            font=font,
            fill=(244, 247, 252, 255),
        )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    img.save(output_path, format="PNG")


def _ensure_pop_culture_logos(data_dir: Path, teams: Iterable[TeamRecord]) -> None:
    lookup: dict[str, dict] = {}
    for category in POP_CULTURE_CATEGORIES:
        category_id = str(category.get("id") or "").strip()
        if not category_id:
            continue
        for contestant in category.get("contestants", []):
            name = str(contestant.get("name") or "").strip()
            if not name:
                continue
            key = f"{category_id}:{name.lower()}"
            lookup[key] = {
                "short_name": str(contestant.get("short_name") or "").strip() or "POP",
                "primary": tuple(category.get("theme_primary") or (120, 120, 120)),
                "secondary": tuple(category.get("theme_secondary") or (200, 200, 200)),
                "background": tuple(category.get("background_color") or (18, 18, 24)),
            }

    for team in teams:
        logo_path = data_dir / "logos" / team.badge_file
        if logo_path.exists():
            continue

        category_id = team.league_slug.replace("pop_culture_", "", 1).strip()
        lookup_key = f"{category_id}:{team.name.lower()}"
        style = lookup.get(lookup_key)
        if style is None:
            style = {
                "short_name": team.short_name or "POP",
                "primary": (120, 120, 120),
                "secondary": (200, 200, 200),
                "background": (18, 18, 24),
            }

        _create_logo(
            output_path=logo_path,
            short_name=style["short_name"],
            primary=style["primary"],
            secondary=style["secondary"],
            background=style["background"],
        )


def build_pop_culture_teams(data_dir: Path) -> list[TeamRecord]:
    teams: list[TeamRecord] = []

    for category in POP_CULTURE_CATEGORIES:
        category_id = str(category.get("id") or "").strip()
        category_name = str(category.get("name") or "").strip()
        display_title = str(category.get("display_title") or "").strip()
        if not category_id or not category_name:
            continue

        league_slug = f"pop_culture_{_slugify(category_id)}"
        league_name = f"Pop Culture / {category_name}"

        for contestant in category.get("contestants", []):
            name = str(contestant.get("name") or "").strip()
            if not name:
                continue

            short_name = str(contestant.get("short_name") or "").strip()[:6]
            if not short_name:
                short_name = TeamRecord._derive_short_name(name)

            universe = str(contestant.get("universe") or "Pop Culture").strip()
            safe_name = _slugify(name)
            team_id = f"pc_{category_id}_{safe_name}"
            badge_file = f"pop_culture__{_slugify(category_id)}__{safe_name}.png"

            teams.append(
                TeamRecord(
                    team_id=team_id,
                    name=name,
                    short_name=short_name,
                    league_name=league_name,
                    league_slug=league_slug,
                    country=universe,
                    badge_url="",
                    badge_file=badge_file,
                    stadium=display_title,
                    formed_year="",
                    website="",
                    description=f"{name} ({universe}) - Pop Culture roster item.",
                )
            )

    _ensure_pop_culture_logos(data_dir, teams)
    return teams

