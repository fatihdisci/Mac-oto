# config.py
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, Tuple


# ============================================================
# VİDEO AYARLARI
# ============================================================
# total_duration_seconds:
# - Export edilen videonun gerçek süresi
# - 60.0 ise çıktı tam 60 saniye olur
# ============================================================

@dataclass(frozen=True)
class VideoConfig:
    width: int = 1080
    height: int = 1920
    fps: int = 60
    output_filename: str = "output_sim.mp4"
    background_color: Tuple[int, int, int] = (16, 22, 34)
    total_duration_seconds: float = 55.0


# ============================================================
# VİDEO PRESET (Shorts sure varyasyonları)
# ============================================================

@dataclass(frozen=True)
class VideoPreset:
    key: str
    label: str
    total_duration_seconds: float
    intro_seconds: float
    outro_seconds: float


VIDEO_PRESETS: dict[str, VideoPreset] = {
    "shorts_30": VideoPreset("shorts_30", "Shorts 30s", 30.0, 2.5, 2.5),
    "shorts_45": VideoPreset("shorts_45", "Shorts 45s", 45.0, 3.0, 3.0),
    "shorts_55": VideoPreset("shorts_55", "Shorts 55s (Varsayilan)", 55.0, 3.0, 2.0),
}

DEFAULT_VIDEO_PRESET_KEY = "shorts_55"


def get_video_preset(key: str | None) -> VideoPreset:
    if not key:
        return VIDEO_PRESETS[DEFAULT_VIDEO_PRESET_KEY]
    return VIDEO_PRESETS.get(key.strip(), VIDEO_PRESETS[DEFAULT_VIDEO_PRESET_KEY])


# ============================================================
# FİZİK AYARLARI
# ============================================================

@dataclass(frozen=True)
class PhysicsConfig:
    gravity_y: float = 1850.0
    substeps: int = 2
    space_iterations: int = 30
    damping: float = 0.999

    ball_radius: int = 34
    ball_mass: float = 1.0
    ball_elasticity: float = 0.72
    ball_friction: float = 0.95
    spawn_initial_angular_velocity_min: float = -8.0
    spawn_initial_angular_velocity_max: float = 8.0

    peg_radius: int = 14
    peg_elasticity: float = 0.95
    peg_friction: float = 0.8

    wall_elasticity: float = 0.7
    wall_friction: float = 0.9


# ============================================================
# SAHA / YERLEŞİM AYARLARI
# ============================================================

@dataclass(frozen=True)
class LayoutConfig:
    side_margin: int = 70
    top_spawn_y: int = 210

    peg_top_y: int = 290
    peg_rows: int = 15
    peg_spacing_x: int = 128
    peg_spacing_y: int = 95

    floor_y: int = 1760
    gap_post_height: int = 95

    side_gap_width: int = 170
    goal_gap_width: int = 220
    divider_width: int = 38

    exit_line_y: int = 1980


# ============================================================
# OYUN / ZAMAN AYARLARI
# ============================================================
# simulated_match_minutes:
# - Videoda gösterilen maç süresi
# - 90.0 ise ekrandaki maç saati 00:00 -> 90:00 akar
#
# max_rounds:
# - Ana bitiş kriteri değil
# - Sadece güvenlik sınırı
# ============================================================

@dataclass(frozen=True)
class GameplayConfig:
    simulated_match_minutes: float = 90.0
    round_pause_seconds: float = 0.75
    random_seed: Optional[int] = None

    left_gap_label: str = "CORNER"
    center_gap_label: str = "GOAL"
    right_gap_label: str = "OUT"

    # Ana bitiş mantığı video süresine göre olduğu için bu sadece güvenlik sınırı.
    max_rounds: int = 10_000

    # Team A ve Team B için spawn bölgeleri
    team_a_spawn_x_ratio: float = 0.42
    team_b_spawn_x_ratio: float = 0.58


# ============================================================
# TENSION (GERİLİM) AYARLARI
# ============================================================
# Son %X'te skor farkı ≤ max_score_diff ise gerilim modu aktif olur.
# - Yerçekimi yavaşlar (dramatik slow-motion hissi)
# - Ekrana kırmızı tint binmeye başlar
# - Peg'ler hafifçe titrer
# ============================================================

@dataclass(frozen=True)
class TensionConfig:
    threshold_progress: float = 0.85
    max_score_diff: int = 1
    gravity_multiplier: float = 0.55
    bg_tint_color: Tuple[int, int, int] = (180, 30, 30)
    bg_tint_alpha_max: int = 45
    peg_vibrate_amplitude: float = 2.5
    peg_vibrate_speed: float = 18.0


# ============================================================
# HUD AYARLARI
# ============================================================

@dataclass(frozen=True)
class HudConfig:
    title_text: str = "MARBLE FOOTBALL RACE"
    title_font_size: int = 58
    score_font_size: int = 52
    info_font_size: int = 34
    bottom_label_font_size: int = 36
    clock_font_size: int = 44


# ============================================================
# ANA KONFİGÜRASYON
# ============================================================
# Kritik değişiklik:
# - Artık takım bilgisi burada tutulmuyor.
# - config.py sadece sistem ayarlarını taşır.
# - Takım seçimi MatchSelection üzerinden dışarıdan gelir.
# ============================================================

@dataclass(frozen=True)
class SimulationConfig:
    video: VideoConfig = field(default_factory=VideoConfig)
    physics: PhysicsConfig = field(default_factory=PhysicsConfig)
    layout: LayoutConfig = field(default_factory=LayoutConfig)
    gameplay: GameplayConfig = field(default_factory=GameplayConfig)
    hud: HudConfig = field(default_factory=HudConfig)
    tension: TensionConfig = field(default_factory=TensionConfig)

    base_dir: Path = field(default_factory=lambda: Path(__file__).resolve().parent)
    assets_dir: Path = field(default_factory=lambda: Path(__file__).resolve().parent / "assets")
    data_dir: Path = field(default_factory=lambda: Path(__file__).resolve().parent / "data")

    @property
    def output_path(self) -> Path:
        return self.base_dir / self.video.output_filename

    @property
    def selected_match_path(self) -> Path:
        """
        GUI tarafından kaydedilen seçim dosyası.
        """
        return self.data_dir / "selected_match.json"

    @property
    def playfield_left(self) -> int:
        return self.layout.side_margin

    @property
    def playfield_right(self) -> int:
        return self.video.width - self.layout.side_margin

    @property
    def playfield_center_x(self) -> int:
        return self.video.width // 2

    @property
    def playfield_width(self) -> int:
        return self.playfield_right - self.playfield_left

    @property
    def total_video_frames(self) -> int:
        """
        Örnek:
        60 FPS * 60 saniye = 3600 frame
        """
        return int(round(self.video.fps * self.video.total_duration_seconds))

    @property
    def simulated_match_total_seconds(self) -> float:
        """
        Örnek:
        90 dakika = 5400 saniye
        """
        return self.gameplay.simulated_match_minutes * 60.0

    @property
    def simulated_match_seconds_per_video_second(self) -> float:
        """
        Örnek:
        5400 maç saniyesi / 60 video saniyesi = 90
        """
        return self.simulated_match_total_seconds / self.video.total_duration_seconds

    @property
    def simulated_match_seconds_per_frame(self) -> float:
        """
        Örnek:
        5400 maç saniyesi / 3600 frame = 1.5 maç saniyesi/frame
        """
        return self.simulated_match_total_seconds / self.total_video_frames

    def ensure_directories(self) -> None:
        """
        Gerekli klasörleri oluşturur.
        """
        self.assets_dir.mkdir(parents=True, exist_ok=True)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        (self.data_dir / "teams").mkdir(parents=True, exist_ok=True)
        (self.data_dir / "logos").mkdir(parents=True, exist_ok=True)


def build_default_config() -> SimulationConfig:
    cfg = SimulationConfig()
    cfg.ensure_directories()
    return cfg
