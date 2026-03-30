---
title: Football Race Studio
emoji: ⚽
colorFrom: green
colorTo: blue
sdk: gradio
sdk_version: "4.44.0"
python_version: "3.11"
app_file: app.py
pinned: false
---

# ⚽ Football Race Studio — Marble Race Video Generator

**YouTube Shorts & TikTok için otomatik futbol maçı simülasyon videoları üreten masaüstü uygulama.**

İki takım seçin, butona basın — 1080×1920 dikey formatta, ses efektli, profesyonel bir maç simülasyonu videosu saniyeler içinde hazır.

---

## 🎬 Ne Yapar?

- 🏟️ **Marble Race** fizik motoru ile gerçekçi top hareketleri
- 📊 **Canlı skor tablosu** ve maç saati (00:00 → 90:00)
- 🎵 **Otomatik ses miksajı** — düdük, gol tezahüratı, arka plan ambiyansı
- 🎨 **"WHO WINS?" intro ekranı** — glow efektleri, kıvılcım partikülleri, thumbnail-ready
- 📁 **800+ takım** — Süper Lig, Premier League, La Liga, Serie A, Bundesliga + milli takımlar
- 🖥️ **Tek pencere GUI** — takım seç, video üret, output klasörünü aç

---

## 📋 Gereksinimler

| Yazılım | Minimum Versiyon | Açıklama |
|---------|-----------------|----------|
| **Python** | 3.10+ | [python.org](https://www.python.org/downloads/) |
| **FFmpeg** | 5.0+ | Ses miksajı için gerekli |
| **Git** | 2.30+ | Repoyu klonlamak için |

---

## 🚀 Kurulum (Adım Adım)

### 1. Python Kur

Python 3.10 veya üstünü kurun. Kurulum sırasında **"Add Python to PATH"** kutucuğunu işaretleyin.

```bash
# Doğrulama:
python --version
# Python 3.10+ çıkmalı
```

### 2. FFmpeg Kur

#### Windows (winget ile — en kolay):
```bash
winget install ffmpeg
```

#### Windows (Manuel):
1. [ffmpeg.org/download.html](https://ffmpeg.org/download.html) adresinden Windows build indirin
2. Zip'i `C:\ffmpeg` klasörüne çıkarın
3. `C:\ffmpeg\bin` klasörünü **Sistem PATH**'e ekleyin:
   - Başlat → "Ortam Değişkenleri" ara → Path → Düzenle → Yeni → `C:\ffmpeg\bin`
4. Terminali kapatıp açın

```bash
# Doğrulama:
ffmpeg -version
```

### 3. Projeyi Klonla

```bash
git clone https://github.com/fatihdisci/Mac-oto.git
cd Mac-oto
```

### 4. Sanal Ortam Oluştur ve Bağımlılıkları Kur

```bash
# Sanal ortam oluştur
python -m venv .venv

# Aktive et (Windows CMD):
.venv\Scripts\activate

# Aktive et (Windows PowerShell):
.venv\Scripts\Activate.ps1

# Aktive et (macOS/Linux):
source .venv/bin/activate

# Bağımlılıkları kur:
pip install -r requirements.txt
```

### 5. Uygulamayı Başlat

#### Yöntem A — Batch dosyası (Windows, en kolay):
```
00_Launcher.bat
```
Çift tıklayın, otomatik açılır.

#### Yöntem B — Terminal:
```bash
python launcher_gui.py
```

---

## 📖 Kullanım Kılavuzu

### Adım 1: Takım Havuzunu Güncelle

İlk çalıştırmada takım veritabanı boştur. **"Takım Havuzunu Güncelle"** butonuna basın.

- İnternet bağlantısı gerekir (FBref'ten veri çeker)
- 800+ takım + logo otomatik indirilir
- `data/all_teams.json` dosyası oluşur
- **Bu işlem sadece 1 kez yapılır** (sonra tekrar güncelleme opsiyonel)

### Adım 2: Takım Seçimi

1. **"Takım Seç →"** butonuna basın (veya "Takım Seçimi" sekmesine gidin)
2. Sol panelden **Team A**, sağ panelden **Team B** seçin
3. Lig filtreleyebilir veya arama yapabilirsiniz
4. **"Seçimi Kaydet"** butonuna basın

### Adım 3: Videoyu Üret

1. **"Videoyu Üret"** butonuna basın
2. İşlem logu sekmesinde ilerlemeyi izleyin
3. Tamamlandığında `output/` klasöründe video hazır olur

**Çıktı dosyaları:**
- `output/takimA_vs_takimB_tarih.mp4` — sessiz ham video
- `output/takimA_vs_takimB_tarih_final.mp4` — **sesli final video** ✅

### Adım 4: Videoyu Al

**"Output Dosyasını Aç"** butonu ile doğrudan video klasörüne gidin.

---

## 📁 Proje Yapısı

```
Mac-oto/
├── 00_Launcher.bat       # Tek tıkla başlat (Windows)
├── launcher_gui.py       # Ana GUI uygulaması
├── main.py               # Video render motoru
├── renderer.py           # Görsel render (pygame)
├── physics.py            # Fizik motoru (pymunk)
├── audio_mixer.py        # Ses miksajı (FFmpeg)
├── config.py             # Tüm ayarlar
├── models.py             # Veri modelleri
├── match_selector.py     # CLI takım seçici (opsiyonel)
├── sync_teams.py         # Takım havuzu güncelleme
├── team_repository.py    # Takım veri deposu
├── video_writer.py       # MP4 yazıcı (OpenCV)
├── requirements.txt      # Python bağımlılıkları
├── .gitignore
├── data/
│   └── sounds/           # Ses efektleri (repo ile gelir)
│       ├── bg_music.mp3
│       ├── crowd_ambient.mp3
│       ├── goal_crowd.mp3
│       └── whistle.mp3
└── output/               # Üretilen videolar (gitignore'da)
```

---

## ⚙️ Özelleştirme

### Video Ayarları (`config.py`)

| Parametre | Varsayılan | Açıklama |
|-----------|-----------|----------|
| `width × height` | 1080 × 1920 | Dikey (Shorts/TikTok) format |
| `fps` | 60 | Kare hızı |
| `total_duration_seconds` | 55.0 | Video süresi (saniye) |
| `simulated_match_minutes` | 90.0 | Ekrandaki maç süresi |

### Ses Seviyeleri (`audio_mixer.py`)

```python
VOLUME = {
    "whistle_start": 0.75,
    "whistle_end": 0.80,
    "goal": 0.90,
    "background_music": 0.50,
    "crowd_ambient": 0.40,
}
```

### Fizik Motoru (`config.py`)

Gravity, ball elasticity, peg friction gibi parametreler `PhysicsConfig` dataclass'ında ayarlanabilir.

---

## ❓ Sık Sorulan Sorular

### "ModuleNotFoundError" alıyorum
Sanal ortamı aktive ettiğinizden emin olun:
```bash
.venv\Scripts\activate  # Windows
pip install -r requirements.txt
```

### FFmpeg bulunamıyor
PATH'e eklendiğinden emin olun. Terminal'de `ffmpeg -version` çalışmalı.

### Video oluştu ama ses yok
`data/sounds/` klasöründe 4 ses dosyası olmalı. Repo ile birlikte gelirler. Eksikse tekrar klonlayın.

### Takım logoları görünmüyor
**"Takım Havuzunu Güncelle"** ile logolar `data/logos/` klasörüne indirilir. İnternet bağlantısı gerekir.

### Farklı ses dosyası kullanmak istiyorum
`data/sounds/` klasörüne kendi dosyalarınızı koyabilirsiniz:
- `bg_music.mp3` — arka plan müziği
- `crowd_ambient.mp3` — tribün ambiyansı
- `goal_crowd.mp3` — gol tezahüratı
- `whistle.mp3` — hakam düdüğü

---

## 🖥️ Farklı PC'de Kurulum (Özet)

```bash
# 1. Python 3.10+ kur (PATH'e ekle)
# 2. FFmpeg kur (winget install ffmpeg)
# 3. Klonla ve kur:
git clone https://github.com/fatihdisci/Mac-oto.git
cd Mac-oto
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt

# 4. Çalıştır:
python launcher_gui.py
# veya 00_Launcher.bat dosyasını çift tıkla
```

---

## 📄 Lisans

Bu proje kişisel kullanım amaçlıdır.
