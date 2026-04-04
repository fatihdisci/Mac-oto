# Calisma Gunlugu

Bu dosya, her mesaj sonrasinda yapilan guncellemeleri tarih-saat ile kaydeder.

## [2026-04-04 02:33:46]
- Turnuva kurallari cekirdekte guncellendi: tum turnuva maclari tek ayak (wins_needed=1) olarak zorunlu hale getirildi.
- Beraberlik cozumu record_match_result icine tasindi: 90dk beraberlik -> uzatma (15+15) -> hala beraberlikte penalti.
- GUI mod etiketi guncellendi: "Playoff (Tek Ayak + ET/PEN)".
- Eski kayitli turnuvalar yuklenirken de tek ayak kurali normalize ediliyor.
- Sentaks kontrolleri py_compile ile dogrulandi.

## [2026-04-04 02:40:20]
- Kullanici sorusu yanitlandi: Turnuva modunda skor belirleme mekanizmasi var mi?
- Aciklama hazirlandi: GUI manuel skor girisi + full run/otomatik sonuc akisi + beraberlikte ET/PEN otomatik cozumu.

## [2026-04-04 02:42:22]
- Kullanici ET/PEN calismiyor geri bildirimi verdi.
- Son turnuva JSON dosyalari kontrol edildi.
- Dogrulama: TOURNAMENT_RESULT_JSON satiri 90dk skorunu yaziyor; turnuvaya islenirken beraberlik ET/PEN ile cozumluyor.
- Ornek: t_20260404_023132.json r0_m4 -> regular 1-1, decided_by=penalties, penalty 3-4, final score 1-2.

## 2026-04-04 02:58:21
- Turnuva maclari icin video ici knockout faz akisi eklendi: 90 dakika beraberlikte ekstra sure (15+15) ve gerekirse penaltilar gorunur hale getirildi.
- Ortak kural dosyasi eklendi: knockout_rules.py. Hem main.py hem tournament_manager.py ayni ET/PEN sonucunu kullanacak sekilde baglandi.
- main.py icinde yeni fazlar: regular_time / extra_time / penalties / outro. Saat, progress log, payload ve ses eventleri bu fazlara gore guncellendi.
- renderer.py icinde scoreboard faz etiketi ET/PEN olacak sekilde guncellendi; penaltida shootout overlay eklendi; final overlay ET/PEN bilgisini gosterecek sekilde duzenlendi.
- run_tournament_full.py guncellendi: main.py payload’indaki decided_by, regular/ET/PEN alanlari turnuvaya override olarak kaydediliyor; boylece bracket sonucu videoyla birebir uyumlu.
- Ortam kisiti: Bu workspace’de calisan Python executable’e erisim yok (venv eski makine yoluna bagli), bu nedenle burada runtime compile/smoke test calistirilamadi.

## 2026-04-04 02:59:18
- ET fazinda tutarlilik icin fizik tabanli rastgele gol akisindan cikilip script kontrollu gol tetikleme modeline alindi; boylece video sonucu ile turnuva kaydi birebir eslesir.
- Penalty overlay ve final overlay detaylari (AET/PEN) render tarafinda netlestirildi.
- Turnuva kayit entegrasyonu video payload override ile tamamlandi.

## 2026-04-04 03:01:06
- Landscape broadcast drawtext hatasi giderildi: _ffmpeg_escape_text fonksiyonuna , ; [ ] | gibi filtreyi bozabilecek karakter kacislari eklendi.
- Merkez panel metinleri icin _broadcast_safe_text eklendi; apostrof (') ve pipe (|) karakterleri guvenli formata donusturuluyor (ornek: FC Twente '65 -> FC Twente 65).
- _make_landscape_segment icine emniyet fallback eklendi: metin overlay render'i hata verirse segment metinsiz panel ile yeniden render edilip turnuva akisi yarida kesilmeden devam eder.

## 2026-04-04 03:02:01
- Pop culture havuzunu cogaltma sorusuna yanit hazirlandi: pop_culture_catalog.py kategori/contestant ekleme akisi, sync_pop_culture_logos.py ile gercek logo kaynagi mapleme ve yukleme adimlari aciklandi.

## 2026-04-04 03:10:25
- 5 yeni Pop Culture kategori eklendi: Muzik Gruplari, Filmler, Giyim Markalari, Kahve Markalari, Araba Markalari (pop_culture_catalog.py).
- Her kategoriye 8'er contestant eklendi ve isim/short_name yapisi mevcut sistemle uyumlu tutuldu.
- sync_pop_culture_logos.py TEAM_SOURCE_MAP guncellendi; yeni 40 eleman icin Wikipedia ve/veya direct logo kaynaklari tanimlandi.

## 2026-04-04 03:10:47
- Kullanici sorusu yanitlandi: ET/PEN kurali sadece playoff degil, tournament run icindeki tum tek ayak eslesmeler (elimination dahil) icin gecerlidir. Tek ayak zorunlulugu aciklandi.
## 2026-04-04 03:12:46
- Turnuva format destegi genisletildi: 4 ve 8 takim eklendi (mevcut 16/32/48 korundu).
- tournament_manager.py guncellendi: SUPPORTED_SIZES -> {4, 8, 16, 32, 48}; format validasyon mesaji ve _build_matches routing 4/8 icin power-two knockout akisina alindi.
- launcher_gui.py guncellendi: TOURNAMENT_FORMAT_VALUES -> ["4", "8", "16", "32", "48"].
- ET/PEN ve tek ayak kurali degistirilmedi; yeni 4/8 formatlari da ayni kural setiyle calisir.
## 2026-04-04 03:18:54
- Yatay yayin merkezi paneli icin tercih analizi yapildi: 'canli gol/etkilesim' vs 'sonuclara gore guncellenen turnuva agaci'.
- En kolay ve stabil yolun turnuva agaci/sonuc panosu oldugu belirtildi; canli gol feed'in teknik olarak daha fazla parser + zaman esleme gerektirdigi not edildi.
## 2026-04-04 03:21:49
- Yatay yayin merkez paneli yeniden tasarlandi: Gecen / Simdiki (sol-sag) / Sonraki mac satirlari eklendi.
- Segment bazli canli bracket ilerleme satiri eklendi (round kisaltmalariyla: PI, R16, QF, SF, F vb.).
- run_tournament_full.py icinde schedule akisi eklendi; her segmentte completed indexe gore previous/next/bracket bilgisi hesaplanip merkeze yazdiriliyor.
- Sag-sol mac videolari ve mevcut export akisi korunarak sadece merkez bilgi katmani guncellendi.
## 2026-04-04 03:27:36
- Kullanici geri bildirimi: Turnuva tarafinda uzatma/penalti akisinin yatay videoda gorunmedigi veya tutarsiz calistigi raporlandi.
- Acik sorun notu: ET/PEN gorunurlugu ve tetikleme davranisi turnuva run senaryolarinda guvenilir degil.
- Istenen durum: Kod degisikligi yapmadan once bu sorunlarin acikca kayda alinmasi ve mevcut projenin GitHub'a guncellenmesi.
