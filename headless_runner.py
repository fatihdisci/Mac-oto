"""
headless_runner.py

HF Spaces / sunucu ortamı için headless CLI çalıştırıcı.
Mevcut main.py'e DOKUNMAZ — sadece çağırır.

SDL dummy driver'ı pygame.init()'den önce set eder,
böylece görüntü gerektirmeyen ortamlarda sorunsuz çalışır.

CLI kullanımı:
    python headless_runner.py "Galatasaray" "Fenerbahçe"
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

# ── CRITICAL: SDL dummy driver — pygame.init()'den ÖNCE olmalı ──────────────
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
# ────────────────────────────────────────────────────────────────────────────

# Proje kökünü Python path'e ekle (farklı dizinlerden çağrılabilmek için)
_project_root = Path(__file__).resolve().parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from config import build_default_config          # noqa: E402
from models import MatchSelection                # noqa: E402
from team_repository import TeamRepository       # noqa: E402


def run_headless(team_a_name: str, team_b_name: str) -> Path:
    """
    İsme göre iki takım seçer, selected_match.json'u kaydeder
    ve headless modda simülasyonu çalıştırır.

    Args:
        team_a_name: Sol takımın tam adı (örn. "Galatasaray")
        team_b_name: Sağ takımın tam adı (örn. "Fenerbahçe")

    Returns:
        Oluşturulan final video dosyasının Path'i.
    """
    cfg = build_default_config()
    repo = TeamRepository(cfg.data_dir)

    team_a = repo.get_team_by_name(team_a_name)
    team_b = repo.get_team_by_name(team_b_name)

    if team_a is None:
        raise ValueError(
            f"Takım bulunamadı: '{team_a_name}'\n"
            "Önce takım senkronizasyonu yapın."
        )
    if team_b is None:
        raise ValueError(
            f"Takım bulunamadı: '{team_b_name}'\n"
            "Önce takım senkronizasyonu yapın."
        )

    match = MatchSelection(
        team_a=team_a,
        team_b=team_b,
        title=f"{team_a.name} vs {team_b.name}",
    )
    repo.save_selected_match(match)

    # main.py'i burada import ediyoruz — env var'lar zaten set edildi
    from main import run_simulation  # noqa: PLC0415
    return run_simulation()


def run_headless_by_key(team_a_key: str, team_b_key: str) -> Path:
    """
    team_key'e göre iki takım seçer ve headless modda simülasyonu çalıştırır.
    app.py (Gradio) tarafından kullanılır.
    """
    cfg = build_default_config()
    repo = TeamRepository(cfg.data_dir)

    team_a = repo.get_team_by_key(team_a_key)
    team_b = repo.get_team_by_key(team_b_key)

    if team_a is None:
        raise ValueError(f"Takım bulunamadı (key): '{team_a_key}'")
    if team_b is None:
        raise ValueError(f"Takım bulunamadı (key): '{team_b_key}'")

    match = MatchSelection(
        team_a=team_a,
        team_b=team_b,
        title=f"{team_a.name} vs {team_b.name}",
    )
    repo.save_selected_match(match)

    from main import run_simulation  # noqa: PLC0415
    return run_simulation()


# ── CLI giriş noktası ────────────────────────────────────────────────────────
if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Kullanım: python headless_runner.py 'Takım A' 'Takım B'")
        print("Örnek   : python headless_runner.py 'Galatasaray' 'Fenerbahçe'")
        sys.exit(1)

    try:
        output = run_headless(sys.argv[1], sys.argv[2])
        print(f"\nVideo hazır: {output}")
    except Exception as exc:
        print(f"\nHATA: {exc}")
        sys.exit(1)
