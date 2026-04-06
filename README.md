# Mac-oto: Marble Race & Pop Culture Battle Simulation

Bu proje, markaların, futbol takımlarının veya popüler kültür ikonlarının yarıştığı 2D fizik tabanlı bir misket yarışı simülatörüdür. TikTok, Reels ve Shorts gibi kısa formlu video platformları için yüksek kaliteli, dinamik ve heyecan verici içerikler üretmek üzere tasarlanmıştır.

## 🚀 Temel Özellikler

- **Çoklu Motor Modları:** 
  - **Football Mode:** VAR incelemeleri, devre arası sistemleri ve klasik futbol atmosferi.
  - **Pop Culture Mode:** Marka savaşları, "Glitch" efektleri ve modern görsel stil.
  - **Dinamik Engeller:** Shifting (kayan) ve Blinking (yanıp sönen) çivilerle zamanlama odaklı yarışlar.
- **🏆 Grand Prix Sistemi:** 
  - Puan tabloları, eleme turları ve dinamik turnuva isimleri ile profesyonel bir şampiyona deneyimi.
- **🎵 Gelişmiş Ses Miksajı:** 
  - Arka plan müzikleri (`fade-in/out`), ıslık sesleri, gol efektleri ve glitch seslerinin otomatik olarak videoya gömülmesi.
- **🎨 Görsel Kalite:** 
  - 1080x1920 (Dikey) çözünürlük, 60 FPS akıcılık.
  - Cam (Glassmorphism) arayüz panelleri ve dinamik ışıklandırma.
- **⚙️ Fizik Motoru:** 
  - `Pymunk` tabanlı gerçek zamanlı fizik simülasyonu. Topların sıkışmasını engelleyen optimize edilmiş sürtünme ve zıplama ayarları.

## 🛠️ Kurulum

Proje Windows ortamında kolayca kurulabilir:

1. **Python Kurulumu:** Bilgisayarınızda [Python 3.12+](https://www.python.org/downloads/) kurulu olduğundan emin olun.
2. **Bağımlılıklar:** `kurum.bat` dosyasını çalıştırın. Bu script otomatik olarak bir sanal ortam oluşturacak ve gerekli tüm kütüphaneleri (`pygame`, `pymunk`, `customtkinter`, `moviepy` vb.) kuracaktır.
3. **FFmpeg:** Ses miksajı için sisteminizde `ffmpeg` yüklü ve PATH'e ekli olmalıdır.

## 🎮 Kullanım

1. `00_Launcher.bat` dosyasını çalıştırarak ana kontrol panelini açın.
2. **Mod Seçimi:** Sol panelden "Normal Match" veya "Grand Prix" sekmelerinden birini seçin.
3. **Ayarlar:** 
   - Takımları seçin veya rastgele atayın.
   - Motor tipini (Normal, VAR, Shifting vb.) belirleyin.
   - Turnuva veya maç ismini girin.
4. **Başlat:** "START" veya "RUN" butonuna tıklayarak simülasyonu ve video üretimini başlatın.
5. **Sonuç:** İşlem bittiğinde `output_sim_final.mp4` dosyası proje ana dizininde hazır olacaktır.

## 🏗️ Proje Mimarisi ve Ayarlar

### 1. Fizik ve Görüntü (`config.py`)
Tüm sistem ayarları bu dosyada merkezi olarak tutulur:
- `gravity_y`: Yerçekimi gücü (Varsayılan: 1850.0).
- `ball_friction`: Top sürtünmesi (Varsayılan: 0.95).
- `total_duration_seconds`: Üretilecek videonun uzunluğu (Varsayılan: 55sn).

### 2. Ses Sistemi (`audio_mixer.py`)
Ses seviyeleri (Volume) `VOLUME` sözlüğü üzerinden yönetilir:
- `whistle_start`: 0.15 (Maç başlangıç ıslığı).
- `bg_music`: 0.60 (Arka plan müziği).
- `ambient`: 0.15 (Seyirci/Ortam sesi).

### 3. Render Motorları
- `renderer.py`: Standart maçların görselleştirilmesi.
- `grand_prix_renderer.py`: Turnuva turlarının ve puan tablolarının görselleştirilmesi.

## 📁 Dosya Yapısı
- `launcher_gui.py`: Ana GUI kontrolcü.
- `main.py`: Tekil maç yönetim scripti.
- `run_grand_prix.py`: Turnuva yönetim scripti.
- `physics_engine.py`: Fizik dünyasının kurallarını tanımlar.
- `audio_mixer.py`: Ses kanallarını birleştiren FFmpeg köprüsü.
- `data/`: Takım bilgileri, logolar ve ses dosyalarının bulunduğu dizin.

---
*Geliştirici Notu: Bu proje eğlence ve yüksek kaliteli sosyal medya içeriği üretimi için optimize edilmiştir.*
