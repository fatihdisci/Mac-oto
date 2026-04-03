"""
app.py — Hugging Face Spaces Gradio arayüzü

Lokal masaüstü uygulamasının (launcher_gui.py) HF Spaces karşılığı.
Mevcut hiçbir dosyaya dokunmaz; headless_runner.py üzerinden çağırır.

Akış:
  1. Takım A ve Takım B seç
  2. Videoyu Üret → MP4 indir
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

# ── CRITICAL: SDL dummy driver — pygame import'undan ÖNCE olmalı ─────────────
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
# ─────────────────────────────────────────────────────────────────────────────

# Proje kökü Python path'inde olsun
_root = Path(__file__).resolve().parent
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))

import gradio as gr  # noqa: E402

from config import build_default_config      # noqa: E402
from team_repository import TeamRepository   # noqa: E402

# ── Global nesneler ──────────────────────────────────────────────────────────
_cfg = build_default_config()
_repo = TeamRepository(_cfg.data_dir)


# ── Yardımcı fonksiyonlar ────────────────────────────────────────────────────

def _team_choices() -> list[tuple[str, str]]:
    """Dropdown için (görünen ad, team_key) çiftlerini döndürür."""
    teams = _repo.load_teams(force_reload=True)
    return [(f"{t.name}  •  {t.league_name}", t.team_key) for t in teams]


# ── Gradio işleyicileri ──────────────────────────────────────────────────────

def do_generate(team_a_key: str, team_b_key: str):
    """
    Takımları seçip headless modda simülasyonu çalıştırır.
    Generator: her adımda (video_path | None, durum mesajı) yield eder.
    """
    # ── Doğrulama ────────────────────────────────────────────────────────────
    if not team_a_key:
        yield None, "❌ Lütfen Takım A seçin."
        return
    if not team_b_key:
        yield None, "❌ Lütfen Takım B seçin."
        return
    if team_a_key == team_b_key:
        yield None, "❌ Takım A ve Takım B aynı olamaz."
        return

    # ── Takımları yükle ──────────────────────────────────────────────────────
    yield None, "⏳ Takımlar hazırlanıyor..."

    team_a = _repo.get_team_by_key(team_a_key)
    team_b = _repo.get_team_by_key(team_b_key)

    if team_a is None or team_b is None:
        yield None, "❌ Takım verisi okunamadı."
        return

    # ── Maç seçimini kaydet ──────────────────────────────────────────────────
    from models import MatchSelection  # noqa: PLC0415
    match = MatchSelection(
        team_a=team_a,
        team_b=team_b,
        title=f"{team_a.name} vs {team_b.name}",
    )
    _repo.save_selected_match(match)

    yield None, (
        f"⏳ Simülasyon başlatıldı: {team_a.name} vs {team_b.name}\n"
        "Bu işlem 2-5 dakika sürebilir, lütfen bekleyin..."
    )

    # ── Simülasyonu çalıştır ─────────────────────────────────────────────────
    try:
        from headless_runner import run_headless_by_key  # noqa: PLC0415
        output_path = run_headless_by_key(team_a_key, team_b_key)
        yield str(output_path), f"✅ Video hazır!\n📁 {output_path.name}"
    except Exception as exc:
        yield None, f"❌ Video oluşturma hatası:\n{exc}"


# ── Gradio arayüzü ───────────────────────────────────────────────────────────

_initial_choices = _team_choices()

with gr.Blocks(
    title="Football Race Studio",
    theme=gr.themes.Soft(),
    css=".gr-button-primary { font-size: 1.1em; }",
) as demo:

    gr.Markdown(
        """
        # ⚽ Football Race Studio
        **YouTube Shorts / TikTok / Reels** için otomatik futbol simülasyonu videosu üretir.
        1080×1920 · 60 FPS · Ses efektleri dahil
        """
    )

    # ── Adım 1: Takım Seçimi ─────────────────────────────────────────────────
    gr.Markdown("### Adım 1 — Takım Seç")
    with gr.Row():
        team_a_dd = gr.Dropdown(
            choices=_initial_choices,
            label="Takım A  (Sol)",
            scale=1,
        )
        team_b_dd = gr.Dropdown(
            choices=_initial_choices,
            label="Takım B  (Sağ)",
            scale=1,
        )

    # ── Adım 2: Üretim ──────────────────────────────────────────────────────
    gr.Markdown("### Adım 2 — Videoyu Üret")
    generate_btn = gr.Button("🎬 Videoyu Üret", variant="primary", size="lg")
    gen_status = gr.Textbox(label="Durum", interactive=False, lines=3)
    video_out = gr.File(label="📥 Video İndir", interactive=False)

    # ── Bağlantılar ──────────────────────────────────────────────────────────
    generate_btn.click(
        fn=do_generate,
        inputs=[team_a_dd, team_b_dd],
        outputs=[video_out, gen_status],
    )


if __name__ == "__main__":
    demo.queue().launch()
