# Mac-oto Geliştirme Planı v3.0 (Final)
## SimVersusArena YouTube Kanalı — Teknik Yol Haritası

Bu doküman Claude Code veya Gemini CLI'ye referans olarak verilecek.  
Mevcut 10 engine mode (SlowFast, Normal, VAR, Guided, Shifting, Blinking + Pop varyantları) KORUNUYOR.  
Tüm yeni özellikler bağımsız katman olarak ekleniyor, hiçbir mevcut davranışı bozmaz.

---

## KURAL: KATMAN MİMARİSİ

```
Engine Mode   → Fizik davranışı (kırmızı-yeşil çivi, shifting, blinking vs.)
Arena Theme   → Renk paleti / atmosfer (mevcut davranışa dokunmaz)
Video Preset  → Video süresi (sadece Shorts varyasyonları: 30/45/55sn)
Tension Mode  → Otomatik, koşula bağlı (son %15 + skor farkı ≤1)
Partiküller   → Otomatik, her çarpışmada (engine mode'dan bağımsız)
Hook          → Maç başlangıç overlay'i (title alanından dinamik metin)
```

Her biri bağımsız çalışır. Football Shifting + UCL Night tema + Shorts 30s + Tension aktif = kayan çiviler mavi tonlu, 30 saniyelik video, son %15'te gerilim modu.

---

## 1. NORMAL MAÇA TITLE (BAŞLIK) ALANI EKLENMESİ

### Sorun
Normal maçta title alanı yok. Title otomatik "Team A vs Team B" oluşuyor (models.py satır 136).  
Hook overlay'de "WHO WINS?" yerine maç bağlamına uygun başlık göstermek için bu alan şart.

### Dokunulacak dosyalar
- `launcher_gui.py` — Takım seçim tabına (footer bölgesi) text input ekle
- `_save_team_selection()` metodu — title değerini MatchSelection'a aktar

### Implementasyon

```python
# launcher_gui.py — footer bölgesine (guided_row'un üstüne, satır ~621 civarı) ekle:

title_row = ctk.CTkFrame(footer, fg_color="transparent")
title_row.grid(row=3, column=0, sticky="ew", padx=16, pady=(0, 8))  # row numaralarını kaydır
title_row.grid_columnconfigure(1, weight=1)

ctk.CTkLabel(
    title_row,
    text="Maç Başlığı:",
    font=ctk.CTkFont(size=12, weight="bold"),
    text_color="#D9E2F2",
).grid(row=0, column=0, sticky="w", padx=(0, 8))

self.match_title_var = StringVar(value="")
self.match_title_entry = ctk.CTkEntry(
    title_row,
    height=30,
    textvariable=self.match_title_var,
    placeholder_text="Ör: UCL QUARTER FINAL, DEV DERBİ, EL CLASICO...",
    fg_color="#0A111D",
    border_color="#243047",
)
self.match_title_entry.grid(row=0, column=1, sticky="ew")
```

```python
# _save_team_selection() içinde MatchSelection oluşturulurken:
title = self.match_title_var.get().strip()
if not title:
    title = f"{team_a.name} vs {team_b.name}"
# MatchSelection(... title=title ...)
```

### Hook'ta kullanımı
```python
# renderer.py — _draw_hook_overlay() satır 800-811 arasını değiştir:
# Eski: raw_title = "WHO WINS?" (sabit)
# Yeni:
raw_title = str(snapshot.get("match_title", "")).strip().upper()
if not raw_title or raw_title == f"{team_a['name']} VS {team_b['name']}".upper():
    hook_text = "WHO WINS?"  # Fallback — özel başlık girilmemişse
else:
    hook_text = raw_title  # "UCL QUARTER FINAL", "DEV DERBİ" vs.
```

**Kullanım senaryosu:** Launcher'da Galatasaray vs Fenerbahçe seçiyorsun, başlık alanına "DEV DERBİ" yazıyorsun. Hook'ta "DEV DERBİ" büyük fontla gösterilir, altında VS badge + takım logoları.

---

## 2. HOOK İYİLEŞTİRMESİ

### Mevcut sorunlar
- "WHO WINS?" her video için aynı — generic
- 2 saniye çok kısa — animasyon bitmeden fade-out başlıyor
- "Match is starting..." alttaki yazı gereksiz
- Title bilgisi kullanılmıyor

### Dokunulacak dosyalar
- `main.py` — intro_seconds'ı 2.0 → 3.0'a çıkar
- `renderer.py` — `_draw_hook_overlay()` title entegrasyonu + alt yazıyı kaldır

### Implementasyon

```python
# main.py — satır 385:
# Eski: intro_seconds = 2.0
# Yeni:
intro_seconds = 3.0
```

```python
# renderer.py — _draw_hook_overlay() değişiklikleri:

# 1) Satır 800-811 — "WHO WINS?" yerine dinamik başlık (Madde 1'deki gibi)

# 2) Satır 825-829 — "Match is starting..." yazısını kaldır veya
#    yerine maç bağlamı ekle:
#    Lig bilgisi veya turnuva adı (snapshot'tan)
league_a = str(team_a.get("league_name", "")).strip()
league_b = str(team_b.get("league_name", "")).strip()
if league_a and league_a == league_b:
    context_text = league_a.upper()
elif league_a:
    context_text = league_a.upper()
else:
    context_text = ""
if context_text:
    ctx = self.info_font.render(context_text, True, (180, 196, 220))
    ctx.set_alpha(int(200 * content_alpha))
    surface.blit(ctx, ctx.get_rect(center=(cx, h - 84)))
```

```python
# _hook_anim_values() — Timeline'ı 3 saniyeye uyarla:
# 0.0-0.25: Giriş animasyonu (scale + alpha)
# 0.25-0.75: Peak — logolar ve başlık tam görünür
# 0.75-1.0: Smooth fade-out → gameplay'e geçiş
```

---

## 3. SHORTS PRESET SİSTEMİ

### Amaç
Video süresi varyasyonları. Sadece Shorts formatı — long-form zaten turnuva/GP modu ile çözülüyor.

### Dokunulacak dosyalar
- `config.py` — Preset tanımları
- `launcher_gui.py` — Preset dropdown
- `models.py` — MatchSelection'a video_preset alanı
- `main.py` — Preset'ten süre alma

### Implementasyon

```python
# config.py:

@dataclass(frozen=True)
class VideoPreset:
    name: str
    total_duration_seconds: float
    intro_seconds: float
    outro_seconds: float

PRESETS = {
    "shorts_30": VideoPreset("Shorts 30s", 30.0, 2.5, 2.5),
    "shorts_45": VideoPreset("Shorts 45s", 45.0, 3.0, 3.0),
    "shorts_55": VideoPreset("Shorts 55s (Varsayılan)", 55.0, 3.0, 3.5),
}
```

```python
# models.py — MatchSelection'a:
video_preset: str = "shorts_55"
```

```python
# launcher_gui.py — footer'a preset dropdown:
VIDEO_PRESET_LABELS = {v.name: k for k, v in PRESETS.items()}
self.preset_var = StringVar(value="Shorts 55s (Varsayılan)")
self.preset_menu = ctk.CTkOptionMenu(
    footer, values=list(VIDEO_PRESET_LABELS.keys()),
    variable=self.preset_var, height=32,
    fg_color="#1A2336", button_color="#2457F5",
)
```

```python
# main.py — satır 383-387 arasını değiştir:
from config import PRESETS
preset_key = match_selection.video_preset or "shorts_55"
preset = PRESETS.get(preset_key, PRESETS["shorts_55"])
base_video_seconds = preset.total_duration_seconds
intro_seconds = preset.intro_seconds
outro_seconds = preset.outro_seconds
# cfg.video.total_duration_seconds artık kullanılmıyor, preset override ediyor
```

---

## 4. TENSION MODE (GERİLİM SİSTEMİ)

### Amaç
Son %15'te skor yakınsa (fark ≤1): yerçekimi yavaşlar, ekran kızarır, peg'ler titrer, heartbeat sesi.

### Dokunulacak dosyalar
- `config.py` — TensionConfig
- `main.py` — Tension hesaplama + gravity override + ses event
- `physics.py` — gravity_override parametresi
- `renderer.py` — Kızıl overlay + peg titreşimi

### Implementasyon

```python
# config.py:
@dataclass(frozen=True)
class TensionConfig:
    threshold_progress: float = 0.85
    max_score_diff: int = 1
    gravity_multiplier: float = 0.55
    bg_tint_color: tuple = (180, 30, 30)
    bg_tint_alpha_max: int = 45
    peg_vibrate_amplitude: float = 2.5
    peg_vibrate_speed: float = 18.0
```

```python
# physics.py — update() metodunun imzasını güncelle:
def update(self, dt: float, gravity_override: float | None = None) -> None:
    if self.simulation_finished:
        return
    if gravity_override is not None:
        self.space.gravity = (0.0, gravity_override)
    elif self.space.gravity[1] != self.cfg.physics.gravity_y:
        self.space.gravity = (0.0, self.cfg.physics.gravity_y)
    # ... geri kalan mevcut kod aynen
```

```python
# main.py — frame loop'ta snapshot oluşturmadan önce (satır ~975):
tension_cfg = TensionConfig()
tension_active = False
tension_progress = 0.0
if not is_intro and not is_outro and match_phase == "regular_time":
    score_diff = abs(score_a - score_b)
    if progress_ratio >= tension_cfg.threshold_progress and score_diff <= tension_cfg.max_score_diff:
        tension_active = True
        tension_progress = (progress_ratio - tension_cfg.threshold_progress) / (1.0 - tension_cfg.threshold_progress)

# physics.update çağrısını güncelle:
if tension_active:
    physics.update(fixed_dt, gravity_override=cfg.physics.gravity_y * tension_cfg.gravity_multiplier)
else:
    physics.update(fixed_dt)

# snapshot'a ekle:
snapshot["tension_active"] = tension_active
snapshot["tension_progress"] = tension_progress
```

```python
# renderer.py — draw() metodunda confetti'den önce:
self._draw_tension_overlay(target_surface, state_snapshot)

# Yeni metot:
def _draw_tension_overlay(self, surface, snapshot):
    if not snapshot.get("tension_active"):
        return
    tp = float(snapshot.get("tension_progress", 0.0))
    alpha = int(45 * tp)
    overlay = pygame.Surface(surface.get_size(), pygame.SRCALPHA)
    overlay.fill((180, 30, 30, alpha))
    surface.blit(overlay, (0, 0))
```

```python
# renderer.py — _draw_pegs() içinde peg çiziminde vibrasyon:
tension_active = snapshot.get("tension_active", False) if snapshot else False
physics_time = float(snapshot.get("physics_time_seconds", 0.0)) if snapshot else 0.0

for x, y in peg_centers:
    if tension_active:
        vib_x = math.sin(physics_time * 18.0 + x * 0.1) * 2.5
        vib_y = math.cos(physics_time * 22.0 + y * 0.1) * 1.5
        dx, dy = int(x + vib_x), int(y + vib_y)
    else:
        dx, dy = int(x), int(y)
    # Mevcut çizim kodunu (dx, dy) ile çağır
```

**Ses:** `data/sounds/tension_heartbeat.mp3` gerekli (Pixabay'den "heartbeat tension" — 8-12sn loop).

---

## 5. ÇARPIŞMA PARTİKÜL EFEKTİ

### Amaç
Top peg'e veya başka topa çarptığında küçük altın/turuncu kıvılcımlar.

### Dokunulacak dosyalar
- `physics.py` — Çarpışma callback ile spark verisi toplama
- `renderer.py` — Parçacık sistemi (spawn + update + draw)
- `main.py` — Spark verilerini snapshot'a aktarma

### Implementasyon

```python
# physics.py — __init__ sonuna:
self._collision_sparks: list[dict] = []
handler = self.space.add_default_collision_handler()
handler.post_solve = self._on_any_collision

def _on_any_collision(self, arbiter, space, data):
    if arbiter.total_impulse.length < 80.0:
        return
    for contact in arbiter.contact_point_set.points:
        self._collision_sparks.append({
            "x": float(contact.point_a.x),
            "y": float(contact.point_a.y),
            "impulse": min(1.0, arbiter.total_impulse.length / 800.0),
            "time": self._sim_time,
        })
    if len(self._collision_sparks) > 30:
        self._collision_sparks = self._collision_sparks[-20:]

def get_collision_sparks(self, since: float) -> list[dict]:
    return [s for s in self._collision_sparks if s["time"] >= since]
```

```python
# renderer.py — __init__'e:
self._impact_particles: list[dict] = []

# Yeni metotlar:
def _update_impact_particles(self, snapshot, dt):
    for spark in snapshot.get("collision_sparks", []):
        count = max(2, int(4 * spark.get("impulse", 0.5)))
        for _ in range(count):
            angle = random.uniform(0, 2 * math.pi)
            speed = random.uniform(60, 200) * spark.get("impulse", 0.5)
            self._impact_particles.append({
                "x": spark["x"], "y": spark["y"],
                "vx": math.cos(angle) * speed,
                "vy": math.sin(angle) * speed - 50,
                "life": random.uniform(0.15, 0.35),
                "age": 0.0,
                "size": random.uniform(1.5, 4.0),
                "color": random.choice([(255,220,120),(255,180,80),(255,255,200)]),
            })
    alive = []
    for p in self._impact_particles:
        p["age"] += dt
        if p["age"] < p["life"]:
            p["x"] += p["vx"] * dt
            p["y"] += p["vy"] * dt
            p["vy"] += 400 * dt
            alive.append(p)
    self._impact_particles = alive[-80:]

def _draw_impact_particles(self, surface):
    for p in self._impact_particles:
        ratio = 1.0 - (p["age"] / p["life"])
        sz = max(1, int(p["size"] * ratio))
        if ratio > 0.3:
            pygame.draw.circle(surface, p["color"], (int(p["x"]), int(p["y"])), sz)
```

```python
# main.py — snapshot'a:
spark_window = 2.0 / cfg.video.fps
snapshot["collision_sparks"] = physics.get_collision_sparks(since=physics._sim_time - spark_window)
```

---

## 6. ÇARPIŞMA SES EFEKTİ

### Dokunulacak dosyalar
- `audio_mixer.py` — Yeni ses tipi
- `main.py` — Güçlü çarpışmalarda ses event

```python
# audio_mixer.py:
SOUND_FILES["ball_hit_peg"] = "ball_hit.mp3"
VOLUME["ball_hit_peg"] = 0.08

# main.py — frame loop'ta:
collision_sparks = snapshot.get("collision_sparks", [])
strong_hits = [s for s in collision_sparks if s.get("impulse", 0) > 0.6]
if strong_hits and (video_seconds_elapsed - last_hit_sound_time) > 0.3:
    audio_events.append({"type": "ball_hit_peg", "time": round(video_seconds_elapsed, 2)})
    last_hit_sound_time = video_seconds_elapsed
```

**Ses:** `data/sounds/ball_hit.mp3` gerekli (Pixabay — "marble hit ping" — 0.2-0.5sn).

---

## 7. ARENA TEMALARI

### Dokunulacak dosyalar
- `config.py` — Tema sözlükleri
- `models.py` — MatchSelection'a arena_theme alanı
- `renderer.py` — Temadan renk okuma
- `launcher_gui.py` — Tema dropdown

```python
# config.py:
ARENA_THEMES = {
    "default":       {"name": "Classic Dark",   "bg": (16,22,34),  "field": (22,30,44),   "border": (46,58,82),   "wall": (105,118,145), "peg": (194,200,214), "peg_hi": (228,232,240), "peg_sh": (10,14,22)},
    "ucl_night":     {"name": "UCL Night",      "bg": (8,12,32),   "field": (14,20,52),   "border": (30,50,120),  "wall": (60,80,160),   "peg": (140,160,220), "peg_hi": (180,200,255), "peg_sh": (6,8,24)},
    "derby_fire":    {"name": "Derby Fire",     "bg": (34,12,8),   "field": (44,18,14),   "border": (120,40,20),  "wall": (180,70,40),   "peg": (220,160,120), "peg_hi": (255,200,150), "peg_sh": (24,8,4)},
    "green_pitch":   {"name": "Green Pitch",    "bg": (8,28,16),   "field": (14,38,22),   "border": (30,82,46),   "wall": (60,130,80),   "peg": (160,210,170), "peg_hi": (200,240,210), "peg_sh": (4,18,8)},
    "midnight_gold": {"name": "Midnight Gold",  "bg": (10,10,18),  "field": (16,16,28),   "border": (80,70,30),   "wall": (160,140,50),  "peg": (200,180,100), "peg_hi": (240,220,140), "peg_sh": (8,8,12)},
    "ice_arena":     {"name": "Ice Arena",      "bg": (18,28,38),  "field": (24,38,52),   "border": (60,100,140), "wall": (100,160,200), "peg": (180,210,230), "peg_hi": (220,240,255), "peg_sh": (12,18,26)},
}
```

```python
# models.py:
arena_theme: str = "default"
```

```python
# renderer.py — _build_static_background() ve _draw_pegs() temadan renk okur:
theme = ARENA_THEMES.get(snapshot.get("arena_theme", "default"), ARENA_THEMES["default"])
# bg_color = theme["bg"], peg_color = theme["peg"], vs.
```

```python
# launcher_gui.py — footer'a dropdown:
self.theme_var = StringVar(value="Classic Dark")
theme_names = [t["name"] for t in ARENA_THEMES.values()]
self.theme_menu = ctk.CTkOptionMenu(footer, values=theme_names, variable=self.theme_var, ...)
```

---

## 8. DİKEY GRAND PRIX MODU

### Sorun
Mevcut GP 1920x1080 yatay: sol board (1080x988) + sağ standings (650x988).  
Dikey GP (1080x1920) lazım — Shorts/Reels formatında GP turnuvaları için.

### Ekran düzeni tasarımı (1080x1920 dikey)

```
┌──────────────────────────┐
│      GRAND PRIX TITLE    │  ← 0-60px: Başlık barı
│      Round X / Y         │
├──────────────────────────┤
│                          │
│                          │
│      BOARD ALANI         │  ← 60-1200px: Kare board (~1080x1140)
│   (çiviler + delikler    │     Mevcut yatay board'un dikey adaptasyonu
│    + düşen toplar)       │     Delik sayısı 12 → 8-10'a düşürülebilir
│                          │     (dar alan, daha az delik)
│                          │
├──────────────────────────┤
│   STANDINGS TABLOSU      │  ← 1200-1920px: Alt panel (~1080x720)
│   1. 🏆 Team A    +12p  │     Tam genişlik standings
│   2.    Team B    +8p    │     4 takım: büyük logolu satırlar
│   3.    Team C    +5p    │     8 takım: kompakt satırlar
│   4.    Team D    -2p    │     16+ takım: iki sütunlu layout
│                          │
│   ROUND RESULT           │     Alt kısımda son round sonuçları
│   Team A: +5  Team B: -3 │
└──────────────────────────┘
```

### Dokunulacak dosyalar
- `run_grand_prix.py` — Dikey config seçeneği (orientation parametresi)
- `grand_prix_engine.py` — Board rect'i dikey layout'a göre hesaplama
- `grand_prix_renderer.py` — Dikey draw metotları
- `launcher_gui.py` — GP tab'a dikey/yatay seçeneği

### Implementasyon

```python
# run_grand_prix.py — build_grand_prix_config() güncelle:
def build_grand_prix_config(vertical: bool = False):
    cfg = build_default_config()
    if vertical:
        return replace(cfg, video=replace(cfg.video,
            width=1080, height=1920, fps=60,
            output_filename="grand_prix_vertical.mp4",
            background_color=(13, 18, 29),
        ))
    else:
        return replace(cfg, video=replace(cfg.video,
            width=1920, height=1080, fps=60,
            output_filename="grand_prix_output.mp4",
            background_color=(13, 18, 29),
        ))
```

```python
# grand_prix_engine.py — __init__'te orientation'a göre layout:
def __init__(self, cfg, *, title, teams, hole_values, round_count, random_seed,
             round_duration_seconds=22.0, vertical=False):
    # ... mevcut kod ...
    self.vertical = vertical
    if vertical:
        # Dikey: board üstte, standings altta
        board_margin = 20
        board_w = cfg.video.width - board_margin * 2   # 1040
        board_h = int(cfg.video.height * 0.58)          # ~1114
        self.board_rect = {
            "x": board_margin,
            "y": 65,
            "width": board_w,
            "height": board_h,
        }
        standings_top = self.board_rect["y"] + board_h + 12
        self.side_panel_rect = {
            "x": board_margin,
            "y": standings_top,
            "width": board_w,
            "height": cfg.video.height - standings_top - 16,
        }
    else:
        # Mevcut yatay layout aynen
        self.board_rect = {"x": 78, "y": 46, "width": 1080, "height": 988}
        self.side_panel_rect = {"x": 1190, "y": 46, "width": 650, "height": 988}
```

```python
# grand_prix_engine.py — Delik sayısını dikeyde azalt:
if vertical:
    self.hole_count = min(10, len(self.hole_values))
    # Dar board'da 12 delik sığmaz, 8-10 ideal
    self.hole_values = self.hole_values[:self.hole_count]
```

```python
# grand_prix_renderer.py — _draw_side_panel() dikey modda yatay standings:
# Dikeyde panel tam genişlik olduğu için tek sütun daha rahat sığar
# 4 takım: row_h=80, logo_size=44 — büyük ve okunaklı
# 8 takım: row_h=52, logo_size=34
# 16 takım: iki sütun layout (mevcut two_col mantığı)
```

```python
# grand_prix_renderer.py — _draw_background_accents() dikey uyarlama:
def _draw_background_accents(self, surface):
    w, h = surface.get_size()
    glow = pygame.Surface((w, h), pygame.SRCALPHA)
    if w < h:  # Dikey
        pygame.draw.circle(glow, (34, 88, 181, 55), (w // 4, 130), 180)
        pygame.draw.circle(glow, (213, 118, 42, 40), (w * 3 // 4, h - 300), 220)
    else:  # Yatay (mevcut)
        pygame.draw.circle(glow, (34, 88, 181, 55), (260, 130), 210)
        pygame.draw.circle(glow, (213, 118, 42, 40), (1650, 920), 260)
    surface.blit(glow, (0, 0))
```

```python
# launcher_gui.py — GP tab'a orientation seçeneği:
self.gp_orientation_var = StringVar(value="Yatay (1920x1080)")
ctk.CTkOptionMenu(
    gp_settings_frame,
    values=["Yatay (1920x1080)", "Dikey (1080x1920)"],
    variable=self.gp_orientation_var,
    ...
)
```

### Dikey GP süre hesabı
4 takım × 5 round × 22sn/round = 110sn (~1:50) + intro/final = ~2:15  
4 takım × 10 round × 22sn/round = 220sn (~3:40) + intro/final = ~4:00  
8 takım × 5 round × 22sn/round = 110sn + intro/final = ~2:15  

Kısa GP (4 takım, 5 round) Shorts'a bile sığar.  
Orta GP (4-8 takım, 10 round) 3-4 dakikalık ideal uzun format.

---

## 9. SES KATMANI GENİŞLETME

### Son 10 saniyede crowd volume artışı
```python
# audio_mixer.py — crowd_ambient FFmpeg filter'ında:
# volume='if(gt(t,{duration-10}),0.15+0.03*(t-{duration-10}),0.15)'
# Bu 0.15 → 0.45 arası linear ramp yapar
```

### Tension heartbeat (Madde 4 ile birlikte)
### Çarpışma sesi (Madde 6 ile birlikte)

---

## UYGULAMA ÖNCELİK SIRASI

| # | Özellik | Etki | Zorluk | Dosya Sayısı |
|---|---------|------|--------|-------------|
| 1 | Normal maça title alanı | Hook temeli | Düşük | 2 |
| 2 | Hook iyileştirmesi | CTR artışı | Düşük | 2 |
| 3 | Shorts preset | Üretim esnekliği | Düşük | 4 |
| 4 | Tension mode | Retention +30-50% | Orta | 4 |
| 5 | Çarpışma partikülleri | Görsel kalite | Orta | 3 |
| 6 | Çarpışma sesleri | Atmosfer | Düşük | 2 |
| 7 | Arena temaları | Çeşitlilik | Orta | 4 |
| 8 | Dikey Grand Prix | Yeni format | Yüksek | 4 |
| 9 | Ses katmanı genişletme | Atmosfer | Düşük | 1 |

### Önerilen uygulama sırası
**Faz 1 (Hemen):** 1 → 2 → 3 (title + hook + preset — temel altyapı)  
**Faz 2 (Sonra):** 4 → 5 → 6 (tension + partiküller + sesler — izleyici deneyimi)  
**Faz 3 (Son):** 7 → 8 → 9 (temalar + dikey GP + ses detayları — çeşitlilik)

### Gerekli ses dosyaları (Pixabay ücretsiz)
1. `data/sounds/tension_heartbeat.mp3` — 8-12sn heartbeat loop
2. `data/sounds/ball_hit.mp3` — 0.2-0.5sn kısa ping/tık sesi

### YAPILACAKLAR CHECKLIST
- [ ] `launcher_gui.py` → Title input + preset dropdown + tema dropdown + GP orientation
- [ ] `models.py` → video_preset + arena_theme alanları
- [ ] `config.py` → VideoPreset + TensionConfig + ARENA_THEMES
- [ ] `main.py` → Preset süre + tension hesaplama + collision spark + hook intro 3sn
- [ ] `physics.py` → gravity_override + collision spark toplama
- [ ] `renderer.py` → Hook title + tension overlay + peg vibrasyon + parçacık + tema renk
- [ ] `grand_prix_engine.py` → Dikey board layout
- [ ] `grand_prix_renderer.py` → Dikey standings layout
- [ ] `run_grand_prix.py` → vertical parametresi
- [ ] `audio_mixer.py` → Tension + hit sesleri + crowd ramp
- [ ] Ses dosyalarını Pixabay'den indirip `data/sounds/`'a koy
