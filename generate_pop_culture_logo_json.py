from __future__ import annotations

import json
import re
import time
import urllib.parse
from pathlib import Path
from typing import Any

import requests


OUTPUT_PATH = Path("output/pop_culture_filled_logos.json")
LOGODEV_TOKEN = "pk_X6DlPlqQQGKBHnAhOQJeHA"
TIMEOUT = 30
MAX_RETRIES = 5
_STATUS_CACHE: dict[str, bool] = {}


BASE_DATA: dict[str, Any] = {
    "categories": [
        {
            "id": "superheroes",
            "name": "Superkahramanlar",
            "display_title": "SUPERHERO BATTLE",
            "icon": "⚡",
            "theme_primary": [139, 92, 246],
            "theme_secondary": [0, 212, 255],
            "background_color": [13, 5, 32],
            "contestants": [
                {"name": "Spider-Man", "short_name": "SPDY", "logo": "", "color": [227, 37, 37], "universe": "Marvel"},
                {"name": "Batman", "short_name": "BTMN", "logo": "", "color": [40, 40, 40], "universe": "DC"},
                {"name": "Iron Man", "short_name": "IRON", "logo": "", "color": [200, 50, 30], "universe": "Marvel"},
                {"name": "Superman", "short_name": "SUPE", "logo": "", "color": [30, 80, 180], "universe": "DC"},
            ],
        },
        {
            "id": "starwars",
            "name": "Star Wars Karakterleri",
            "display_title": "STAR WARS BATTLE",
            "icon": "🌌",
            "theme_primary": [255, 232, 31],
            "theme_secondary": [20, 20, 20],
            "background_color": [5, 5, 10],
            "contestants": [
                {"name": "Darth Vader", "short_name": "VADR", "logo": "", "color": [220, 20, 20], "universe": "Empire"},
                {"name": "Luke Skywalker", "short_name": "LUKE", "logo": "", "color": [50, 200, 50], "universe": "Jedi"},
                {"name": "Yoda", "short_name": "YODA", "logo": "", "color": [100, 220, 80], "universe": "Jedi"},
                {"name": "Obi-Wan Kenobi", "short_name": "MSTR", "logo": "", "color": [50, 100, 220], "universe": "Jedi"},
                {"name": "Kylo Ren", "short_name": "KYLO", "logo": "", "color": [255, 50, 50], "universe": "First Order"},
            ],
        },
        {
            "id": "got",
            "name": "Game of Thrones Haneleri",
            "display_title": "WESTEROS BATTLE",
            "icon": "⚔️",
            "theme_primary": [150, 0, 0],
            "theme_secondary": [200, 150, 50],
            "background_color": [20, 10, 10],
            "contestants": [
                {"name": "Jon Snow", "short_name": "SNOW", "logo": "", "color": [100, 110, 120], "universe": "Stark"},
                {"name": "Daenerys Targaryen", "short_name": "DANY", "logo": "", "color": [180, 30, 30], "universe": "Targaryen"},
                {"name": "Tyrion Lannister", "short_name": "TYRN", "logo": "", "color": [210, 180, 40], "universe": "Lannister"},
                {"name": "Arya Stark", "short_name": "ARYA", "logo": "", "color": [90, 90, 100], "universe": "Stark"},
                {"name": "Night King", "short_name": "NITE", "logo": "", "color": [40, 120, 255], "universe": "White Walkers"},
            ],
        },
        {
            "id": "techbrands",
            "name": "Teknoloji Devleri (Markalar)",
            "display_title": "TECH BRAND WARS",
            "icon": "💻",
            "theme_primary": [0, 150, 255],
            "theme_secondary": [200, 200, 200],
            "background_color": [15, 20, 30],
            "contestants": [
                {"name": "Apple", "short_name": "APPL", "logo": "", "color": [150, 150, 150], "universe": "Tech"},
                {"name": "Google", "short_name": "GOOG", "logo": "", "color": [66, 133, 244], "universe": "Tech"},
                {"name": "Microsoft", "short_name": "MSFT", "logo": "", "color": [242, 80, 34], "universe": "Tech"},
                {"name": "Amazon", "short_name": "AMZN", "logo": "", "color": [255, 153, 0], "universe": "Tech"},
                {"name": "Meta", "short_name": "META", "logo": "", "color": [6, 104, 225], "universe": "Tech"},
                {"name": "OpenAI", "short_name": "O-AI", "logo": "", "color": [16, 163, 127], "universe": "Tech"},
            ],
        },
        {
            "id": "fastfood",
            "name": "Fast Food Markalari",
            "display_title": "FAST FOOD WARS",
            "icon": "🍔",
            "theme_primary": [255, 100, 0],
            "theme_secondary": [255, 200, 0],
            "background_color": [30, 15, 5],
            "contestants": [
                {"name": "McDonalds", "short_name": "MCD", "logo": "", "color": [255, 199, 44], "universe": "Fast Food"},
                {"name": "Burger King", "short_name": "BK", "logo": "", "color": [215, 35, 0], "universe": "Fast Food"},
                {"name": "KFC", "short_name": "KFC", "logo": "", "color": [163, 20, 32], "universe": "Fast Food"},
                {"name": "Wendys", "short_name": "WNDY", "logo": "", "color": [225, 40, 40], "universe": "Fast Food"},
                {"name": "Taco Bell", "short_name": "TACO", "logo": "", "color": [112, 32, 130], "universe": "Fast Food"},
            ],
        },
        {
            "id": "football",
            "name": "Futbol Efsaneleri",
            "display_title": "FOOTBALL LEGENDS",
            "icon": "⚽",
            "theme_primary": [40, 200, 80],
            "theme_secondary": [255, 255, 255],
            "background_color": [10, 30, 15],
            "contestants": [
                {"name": "Lionel Messi", "short_name": "MESI", "logo": "", "color": [100, 180, 255], "universe": "Argentina / Barca"},
                {"name": "Cristiano Ronaldo", "short_name": "CR7", "logo": "", "color": [220, 20, 40], "universe": "Portugal / RM"},
                {"name": "Diego Maradona", "short_name": "D10S", "logo": "", "color": [80, 160, 240], "universe": "Argentina / Napoli"},
                {"name": "Pelé", "short_name": "PELE", "logo": "", "color": [255, 220, 0], "universe": "Brazil / Santos"},
                {"name": "Zinedine Zidane", "short_name": "ZIZU", "logo": "", "color": [0, 85, 164], "universe": "France / RM"},
                {"name": "Ronaldinho", "short_name": "R10", "logo": "", "color": [255, 200, 50], "universe": "Brazil / Barca"},
            ],
        },
        {
            "id": "games",
            "name": "Video Oyunlari (Esports vs)",
            "display_title": "GAMING WARS",
            "icon": "🎮",
            "theme_primary": [138, 43, 226],
            "theme_secondary": [0, 255, 255],
            "background_color": [20, 20, 40],
            "contestants": [
                {"name": "League of Legends", "short_name": "LOL", "logo": "", "color": [200, 170, 70], "universe": "Riot Games"},
                {"name": "Valorant", "short_name": "VALO", "logo": "", "color": [255, 70, 85], "universe": "Riot Games"},
                {"name": "CS:GO", "short_name": "CSGO", "logo": "", "color": [255, 200, 0], "universe": "Valve"},
                {"name": "Dota 2", "short_name": "DOTA", "logo": "", "color": [220, 60, 40], "universe": "Valve"},
                {"name": "Minecraft", "short_name": "MC", "logo": "", "color": [80, 200, 80], "universe": "Mojang"},
                {"name": "GTA V", "short_name": "GTA5", "logo": "", "color": [80, 180, 90], "universe": "Rockstar"},
            ],
        },
    ]
}


TECH_DOMAINS = {
    "Apple": "apple.com",
    "Google": "google.com",
    "Microsoft": "microsoft.com",
    "Amazon": "amazon.com",
    "Meta": "meta.com",
    "OpenAI": "openai.com",
}

FASTFOOD_DOMAINS = {
    "McDonalds": "mcdonalds.com",
    "Burger King": "burgerking.com",
    "KFC": "kfc.com",
    "Wendys": "wendys.com",
    "Taco Bell": "tacobell.com",
}

BRAND_COMMONS_URLS = {
    "Apple": "https://commons.wikimedia.org/wiki/Special:FilePath/Apple_logo_black.svg",
    "Google": "https://commons.wikimedia.org/wiki/Special:FilePath/Google_G_logo.svg",
    "Microsoft": "https://commons.wikimedia.org/wiki/Special:FilePath/Microsoft_logo_(2012).svg",
    "Amazon": "https://commons.wikimedia.org/wiki/Special:FilePath/Amazon_logo.svg",
    "Meta": "https://commons.wikimedia.org/wiki/Special:FilePath/Meta_Platforms_Inc._logo.svg",
    "OpenAI": "https://commons.wikimedia.org/wiki/Special:FilePath/OpenAI_logo_2025.svg",
    "McDonalds": "https://commons.wikimedia.org/wiki/Special:FilePath/McDonald's_Golden_Arches.svg",
    "Burger King": "https://commons.wikimedia.org/wiki/Special:FilePath/Burger_King_logo.svg",
    "KFC": "https://commons.wikimedia.org/wiki/Special:FilePath/KFC_logo.svg",
    "Wendys": "https://commons.wikimedia.org/wiki/Special:FilePath/Wendy's_Logo.svg",
    "Taco Bell": "https://commons.wikimedia.org/wiki/Special:FilePath/Taco_Bell_2016.svg",
}

STARWARS_GOT_TO_ACTOR = {
    "Darth Vader": "David Prowse",
    "Luke Skywalker": "Mark Hamill",
    "Yoda": "Frank Oz",
    "Obi-Wan Kenobi": "Ewan McGregor",
    "Kylo Ren": "Adam Driver",
    "Jon Snow": "Kit Harington",
    "Daenerys Targaryen": "Emilia Clarke",
    "Tyrion Lannister": "Peter Dinklage",
    "Arya Stark": "Maisie Williams",
    "Night King": "Vladimir Furdik",
}

STEAM_SEARCH_TERM = {
    "League of Legends": "League of Legends",
    "Valorant": "Valorant",
    "CS:GO": "Counter-Strike",
    "Dota 2": "Dota 2",
    "Minecraft": "Minecraft",
    "GTA V": "Grand Theft Auto V",
}

SUPERHERO_FALLBACK_URLS = {
    "Spider-Man": "https://upload.wikimedia.org/wikipedia/en/2/21/Web_of_Spider-Man_Vol_1_129-1.png",
    "Batman": "https://upload.wikimedia.org/wikipedia/en/c/c7/Batman_Infobox.jpg",
    "Iron Man": "https://upload.wikimedia.org/wikipedia/en/4/47/Iron_Man_%28circa_2018%29.png",
    "Superman": "https://upload.wikimedia.org/wikipedia/en/3/35/Supermanflying.png",
}


def _request(session: requests.Session, url: str, params: dict[str, Any] | None = None) -> requests.Response:
    response = session.get(url, params=params, timeout=TIMEOUT)
    return response


def _request_json(session: requests.Session, url: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
    last_error = ""
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            resp = _request(session, url, params=params)
            if resp.status_code == 429:
                time.sleep(2.0 * attempt)
                last_error = "HTTP 429"
                continue
            if resp.status_code != 200:
                last_error = f"HTTP {resp.status_code}"
                continue
            payload = resp.json()
            if isinstance(payload, dict):
                return payload
            last_error = "JSON object degil"
        except Exception as exc:  # noqa: BLE001
            last_error = str(exc)
            continue
    raise RuntimeError(last_error or "JSON request hatasi")


def _is_200(session: requests.Session, url: str) -> bool:
    cached = _STATUS_CACHE.get(url)
    if cached is not None:
        return cached

    try:
        for attempt in range(1, MAX_RETRIES + 1):
            resp = _request(session, url)
            if resp.status_code == 429:
                time.sleep(1.5 * attempt)
                continue
            ok = resp.status_code == 200
            _STATUS_CACHE[url] = ok
            return ok
        _STATUS_CACHE[url] = False
        return False
    except Exception:
        _STATUS_CACHE[url] = False
        return False


def _clearbit_or_fallback(session: requests.Session, domain: str, brand_query: str) -> str:
    primary = f"https://logo.clearbit.com/{domain}"
    if _is_200(session, primary):
        return primary

    fallback = f"https://img.logo.dev/{domain}?token={LOGODEV_TOKEN}"
    if _is_200(session, fallback):
        return fallback

    direct_brand = BRAND_COMMONS_URLS.get(brand_query, "")
    if direct_brand and _is_200(session, direct_brand):
        return direct_brand

    return _commons_search_file_url(
        session,
        query=f"{brand_query} logo",
        include_keywords=["logo", "wordmark", "symbol", "svg"],
        exclude_keywords=["building", "office", "headquarters", "campus", "photo"],
    )


def _commons_search_file_url(
    session: requests.Session,
    query: str,
    include_keywords: list[str] | None = None,
    exclude_keywords: list[str] | None = None,
) -> str:
    include_keywords = [k.lower() for k in (include_keywords or [])]
    exclude_keywords = [k.lower() for k in (exclude_keywords or [])]

    params = {
        "action": "query",
        "format": "json",
        "list": "search",
        "srnamespace": "6",
        "srlimit": "20",
        "srsearch": query,
    }
    payload = _request_json(session, "https://commons.wikimedia.org/w/api.php", params=params)
    rows = payload.get("query", {}).get("search", [])
    if not isinstance(rows, list):
        raise RuntimeError(f"Commons search bos: {query}")

    titles = [str(item.get("title") or "").strip() for item in rows if isinstance(item, dict)]
    titles = [t for t in titles if t.startswith("File:")]
    if not titles:
        raise RuntimeError(f"Commons file sonucu yok: {query}")

    def score(title: str) -> int:
        tl = title.lower()
        s = 0
        for k in include_keywords:
            if k in tl:
                s += 3
        for k in exclude_keywords:
            if k in tl:
                s -= 4
        return s

    titles.sort(key=score, reverse=True)
    for title in titles:
        p2 = {
            "action": "query",
            "format": "json",
            "titles": title,
            "prop": "imageinfo",
            "iiprop": "url",
        }
        detail = _request_json(session, "https://commons.wikimedia.org/w/api.php", params=p2)
        pages = detail.get("query", {}).get("pages", {})
        if not isinstance(pages, dict):
            continue
        for page in pages.values():
            if not isinstance(page, dict):
                continue
            ii = page.get("imageinfo")
            if not isinstance(ii, list) or not ii:
                continue
            image_url = str((ii[0] or {}).get("url") or "").strip()
            if image_url and _is_200(session, image_url):
                return image_url

    raise RuntimeError(f"Commons 200 veren file bulunamadi: {query}")


def _wiki_pageimage(session: requests.Session, title: str) -> str | None:
    params = {
        "action": "query",
        "titles": title,
        "prop": "pageimages",
        "format": "json",
        "pithumbsize": "500",
    }
    payload = _request_json(session, "https://en.wikipedia.org/w/api.php", params=params)
    pages = payload.get("query", {}).get("pages", {})
    if not isinstance(pages, dict):
        return None
    for page in pages.values():
        if not isinstance(page, dict):
            continue
        thumb = page.get("thumbnail")
        if isinstance(thumb, dict):
            url = str(thumb.get("source") or "").strip()
            if url and _is_200(session, url):
                return url
    return None


def _tmdb_person_portrait_from_web(session: requests.Session, person_name: str) -> str:
    url = f"https://www.themoviedb.org/search/person?query={urllib.parse.quote(person_name)}"
    html = _request(session, url).text
    # capture first 2-3 face thumbnails in page
    paths = re.findall(r"/t/p/w\d+_and_h\d+_face/([A-Za-z0-9._-]+)", html)
    seen: set[str] = set()
    filenames: list[str] = []
    for p in paths:
        if p not in seen:
            seen.add(p)
            filenames.append(p)
        if len(filenames) >= 4:
            break

    for filename in filenames[:3]:
        img_url = f"https://image.tmdb.org/t/p/w500/{filename}"
        if _is_200(session, img_url):
            return img_url

    raise RuntimeError(f"TMDB portrait bulunamadi: {person_name}")


def _steam_capsule_logo_or_fallback(session: requests.Session, game_name: str) -> str:
    term = STEAM_SEARCH_TERM.get(game_name, game_name)
    params = {"term": term, "l": "english", "cc": "US"}
    payload = _request_json(session, "https://store.steampowered.com/api/storesearch/", params=params)
    items = payload.get("items") if isinstance(payload, dict) else None
    if isinstance(items, list) and items:
        appid = str(items[0].get("id") or "").strip()
        if appid:
            candidate = f"https://cdn.akamai.steamstatic.com/steam/apps/{appid}/capsule_184x69.jpg"
            if _is_200(session, candidate):
                return candidate

    # steamde yoksa commons fallback
    return _commons_search_file_url(
        session,
        query=f"{game_name} logo",
        include_keywords=["logo", "wordmark", "icon"],
        exclude_keywords=["cover", "screenshot", "poster", "wallpaper"],
    )


def fill_logos() -> dict[str, Any]:
    data = json.loads(json.dumps(BASE_DATA, ensure_ascii=False))
    session = requests.Session()
    session.headers.update({"User-Agent": "PopCultureLogoResolver/1.0"})

    for category in data["categories"]:
        cid = category["id"]
        for team in category["contestants"]:
            name = team["name"]

            if cid in {"techbrands", "fastfood"}:
                domain_map = TECH_DOMAINS if cid == "techbrands" else FASTFOOD_DOMAINS
                team["logo"] = _clearbit_or_fallback(session, domain_map[name], name)
                continue

            if cid == "superheroes":
                hero_url = None
                hero_queries = [
                    f"{name} logo symbol",
                    f"{name} logo",
                    f"{name} symbol",
                    f"{name} emblem",
                ]
                for q in hero_queries:
                    try:
                        hero_url = _commons_search_file_url(
                            session,
                            query=q,
                            include_keywords=["logo", "symbol", "emblem", "mask", "shield", "icon"],
                            exclude_keywords=["poster", "movie", "actor", "cosplay", "wallpaper", "cover"],
                        )
                        break
                    except Exception:
                        continue
                if not hero_url:
                    fallback = SUPERHERO_FALLBACK_URLS.get(name, "")
                    if fallback and _is_200(session, fallback):
                        hero_url = fallback
                if not hero_url:
                    raise RuntimeError(f"Superhero logo bulunamadi: {name}")
                team["logo"] = hero_url
                continue

            if cid in {"starwars", "got"}:
                actor_name = STARWARS_GOT_TO_ACTOR[name]
                team["logo"] = _tmdb_person_portrait_from_web(session, actor_name)
                continue

            if cid == "football":
                # 1) commons search
                try:
                    team["logo"] = _commons_search_file_url(
                        session,
                        query=f"{name} footballer portrait",
                        include_keywords=["portrait", "football", "headshot", "fifa"],
                        exclude_keywords=["stadium", "match", "celebration", "crowd", "training"],
                    )
                except Exception:
                    # 2) wikipedia page image fallback
                    wiki = _wiki_pageimage(session, name)
                    if not wiki:
                        raise
                    team["logo"] = wiki
                continue

            if cid == "games":
                team["logo"] = _steam_capsule_logo_or_fallback(session, name)
                continue

            raise RuntimeError(f"Bilinmeyen kategori: {cid}")

    return data


def main() -> None:
    filled = fill_logos()
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(filled, ensure_ascii=False, indent=2), encoding="utf-8")
    print(str(OUTPUT_PATH))


if __name__ == "__main__":
    main()
