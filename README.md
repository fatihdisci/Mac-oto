# Mac-oto

Mac-oto, futbol marble race tabanli video uretimi icin masaustu aracidir.

Projede 3 ana akis vardir:
- Tek mac video uretimi
- Turnuva (4/8/16/32/48 takim, tek ayak + ET/PEN)
- Grand Prix modu (4/8 takim, 5-30 raunt)

GUI uzerinden calisir ve ciktilari `output/` klasorune yazar.

## Gereksinimler
- Windows 10/11
- Python 3.12+ (resmi python.org kurulumu onerilir)
- FFmpeg (ses miksaji icin)

Not:
- `tkinter` gerekli oldugu icin Windows Store Python yerine resmi Python kurulumu tavsiye edilir.
- FFmpeg yoksa video yine uretilir ancak ses miksaji kisitlanabilir.

## Yeni PC Kurulumu (Onerilen)
1. Repoyu cek:
```powershell
git clone https://github.com/fatihdisci/Mac-oto.git
cd Mac-oto
```

2. Cift tikla:
- `kurum.bat`  -> `.venv` olusturur ve `requirements.txt` kurar

3. Sonra cift tikla:
- `00_Launcher.bat` -> GUI acilir

## Manual Kurulum
```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe launcher_gui.py
```

## Ana Komutlar
- GUI:
```powershell
.\.venv\Scripts\python.exe launcher_gui.py
```

- Tek mac render:
```powershell
.\.venv\Scripts\python.exe main.py --headless --no-messagebox
```

- Full turnuva:
```powershell
.\.venv\Scripts\python.exe run_tournament_full.py --layout landscape_broadcast --replay-completed
```

- Grand Prix:
```powershell
.\.venv\Scripts\python.exe run_grand_prix.py --headless --progress-every 500
```

## Dosya Ozeti
- `00_Launcher.bat`: Tek tikla calistirma (venv kontrol + GUI)
- `kurum.bat`: Tek tikla kurulum (venv + paketler)
- `launcher_gui.py`: Ana uygulama penceresi
- `main.py`: Tek mac video akisi
- `run_tournament_full.py`: Turnuva toplu render ve layout
- `grand_prix_engine.py`: Grand Prix fizik/raunt motoru
- `grand_prix_renderer.py`: Grand Prix yatay yayin renderi
- `tournament_manager.py`: Turnuva bracket ve sonuc kaydi
- `audio_mixer.py`: FFmpeg ile ses miksaji

## Ciktilar
- Tek mac: `output/*_final.mp4`
- Turnuva: `output/tournament_runs/*.mp4`
- Grand Prix: `output/grand_prix_runs/*.mp4`

## Sorun Giderme
- `ModuleNotFoundError: tkinter`:
  - Resmi Python 3.12 kur ve tekrar `kurum.bat` calistir.

- `did not find executable ... Python314`:
  - Eski/bozuk `.venv` kalmis olabilir.
  - `kurum.bat` veya `00_Launcher.bat` ile ortami yeniden kur.

- Ses yok:
  - `data/sounds/` altinda ses dosyalari oldugunu kontrol et.
  - `ffmpeg -version` komutu calismali.

- Logo yok:
  - Takim havuzu/logolarin guncellenmesini GUI icinden tekrar calistir.

