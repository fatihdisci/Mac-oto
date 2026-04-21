# ⚽ Mac-oto: Profesyonel Misket Futbolu & Yarış Simülatörü

Mac-oto, TikTok, Reels ve YouTube Shorts gibi dikey video platformları için optimize edilmiş, Pymunk fizik motoru tabanlı gelişmiş bir 2D misket yarışı simülatörüdür. Gerçekçi fizik kuralları, dinamik skor sistemleri ve otomatik video prodüksiyon hattı ile yüksek kaliteli içerik üretimi sağlar.

---

## 🌟 Öne Çıkan Özellikler

*   **Gelişmiş Fizik Motoru:** Pymunk ile güçlendirilmiş, takılmaları önleyen (auto-recovery) akıllı top fiziği.
*   **Çoklu Oyun Modu:** Standart lig maçlarından, kaotik çarklı arenalara ve büyük turnuvalara kadar geniş yelpaze.
*   **Merkezi Prodüksiyon Hattı:** Ses miksajı, arka plan müziği ve Greenscreen (Like & Bell) efektlerini tek bir FFmpeg geçişinde birleştiren "Unified Post-Processing" sistemi.
*   **Dinamik HUD & UI:** Glassmorphism etkili modern arayüz, 90 dakikalık maç saati simülasyonu ve canlı istatistikler.
*   **VAR Sistemi:** Gol pozisyonlarını rastgele inceleyen ve iptal/onay kararı veren görsel VAR mekanizması.
*   **Tension (Gerilim) Modu:** Maç sonuna doğru skor yakınsa devreye giren slow-motion ve ekran titreme efektleri.

---

## 🎮 Oyun Modları

1.  **Standard & Guided:** Saf fizik deneyimi veya önceden belirlenen hedef skora (Guided) akıllıca yönlendiren profesyonel modlar.
2.  **Rotating Arena (YENİ):** Pürüzsüz poligon çizimli, dönen bir çember içinde geçen, 90 dakikalık maç simülasyonuna sahip en yeni ve dinamik mod.
3.  **Football VAR:** Gollerden sonra VAR incelemesi heyecanı katan mod.
4.  **Football Gears:** Sahada dönen çarkların ve bumperların olduğu yüksek tempolu mod.
5.  **Grand Prix:** Çoklu takımların (8+) yarıştığı, puan tabanlı turnuva serileri.
6.  **Power Pegs:** Toplara hız veren veya yavaşlatan özel bölgelerin olduğu mod.

---

## 🛠️ Kurulum

### Gereksinimler
*   **Python 3.10+**
*   **FFmpeg:** (Ses ve video birleştirme için zorunludur)
    *   Windows: `winget install ffmpeg`
    *   macOS: `brew install ffmpeg`

### Adımlar
1.  Depoyu klonlayın:
    ```bash
    git clone https://github.com/fatihdisci/Mac-oto.git
    cd Mac-oto
    ```
2.  Bağımlılıkları yükleyin:
    ```bash
    pip install -r requirements.txt
    ```

---

## 🚀 Kullanım

### Masaüstü Arayüzü (Önerilen)
Tüm ayarları görsel olarak yapmak ve önizleme ile çalışmak için:
```bash
python launcher_gui.py
```

### Headless (Sunucu) Modu
Sadece video üretmek için:
```bash
python main.py --headless
```

### Grand Prix (Turnuva) Çalıştırma
```bash
python run_grand_prix.py --vertical
```

---

## 🎬 Otomatik Prodüksiyon Detayları

Sistem, render işlemi bittikten sonra otomatik olarak şu işlemleri yapar:
*   **Ses Miksajı:** Başlangıç/bitiş düdüğü, seyirci ambiyansı ve top çarpma sesleri (`ball_hit.mp3`) gecikmesiz (zero-latency) olarak eklenir.
*   **Greenscreen Overlay:** Her videonun **20. saniyesinde** otomatik olarak `likebell.mp4` dosyası maskelenerek videoya eklenir ve bitince temiz bir şekilde kaldırılır.
*   **GPU Hızlandırma:** NVIDIA ekran kartınız varsa, FFmpeg otomatik olarak `h264_nvenc` encoder'ını kullanarak işlem süresini 5 kat hızlandırır.

---

## 📁 Proje Yapısı
*   `rotating_arena.py`: Dönen arena modu motoru ve render'ı.
*   `audio_mixer.py`: Merkezi ses ve video birleştirme birimi.
*   `physics.py`: Ana fizik motoru ve kural tanımları.
*   `renderer.py`: Ana Pygame render motoru (Glass UI).
*   `data/logos/`: Takım logolarının (PNG) bulunduğu dizin.
*   `data/sounds/`: Ses efektlerinin bulunduğu dizin.

---
*Geliştirici Notu: Bu proje, sosyal medya içerik üreticileri için profesyonel ve otomatize bir çözüm sunmak üzere optimize edilmiştir.*
