# audio_mixer.py
"""
Sessiz MP4 videoya ses efektleri ve arka plan müziği ekler.
FFmpeg kullanır.

Ses katmanları:
  1. Arka plan müziği (varsa) — düşük volume, loop
  2. Başlangıç düdüğü
  3. Gol tezahüratı (her gol anında)
  4. Bitiş düdüğü

Kullanım:
    from audio_mixer import mix_audio_into_video
    mix_audio_into_video(
        video_path="output_sim.mp4",
        event_timeline=[
            {"type": "whistle_start", "time": 2.0},
            {"type": "goal", "time": 12.5},
            {"type": "goal", "time": 28.3},
            {"type": "whistle_end", "time": 53.0},
        ],
        output_path="output_final.mp4",
    )
"""
from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any

import cv2

SOUNDS_DIR = Path(__file__).resolve().parent / "data" / "sounds"

SOUND_FILES = {
    "whistle_start": "whistle.mp3",
    "whistle_end": "whistle.mp3",
    "goal": "goal_crowd.mp3",
    "crowd_ambient": "crowd_ambient.mp3",
    "ball_hit_peg": "ball_hit.mp3",
    "hit": "ball_hit.mp3",  # Grand Prix alias
}

# Volume ayarları (0.0 - 1.0)
VOLUME = {
    "whistle_start": 0.15,
    "whistle_end": 0.18,
    "goal": 0.55,
    "background_music": 0.60,
    "crowd_ambient": 0.15,
    "ball_hit_peg": 0.55,  # 0.45'ten 0.55'e yükseltildi
    "hit": 0.55,           # Grand Prix için aynı seviye
}

# Fade ayarları (saniye)
FADE = {
    "bg_fade_in": 3.0,       # Müzik başlangıç fade-in
    "bg_fade_out": 3.0,      # Müzik bitiş fade-out (tatlı kapanış)
    "crowd_fade_in": 2.0,
    "crowd_fade_out": 3.0,
}


def _find_ffmpeg() -> str:
    """FFmpeg yolunu bul."""
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg:
        return ffmpeg
    # Windows yaygın konumlar
    for candidate in [
        r"C:\ffmpeg\bin\ffmpeg.exe",
        r"C:\Program Files\ffmpeg\bin\ffmpeg.exe",
    ]:
        if Path(candidate).exists():
            return candidate
    raise FileNotFoundError(
        "FFmpeg bulunamadi. Lutfen FFmpeg kurun:\n"
        "  winget install ffmpeg\n"
        "  veya https://ffmpeg.org/download.html"
    )


def _get_sound_path(sound_key: str) -> Path | None:
    """Ses dosyasının yolunu döndür. Yoksa None."""
    filename = SOUND_FILES.get(sound_key)
    if not filename:
        return None
    path = SOUNDS_DIR / filename
    return path if path.exists() else None


def _get_background_music() -> Path | None:
    """data/sounds/ içinde bg_music ile başlayan veya music içeren dosya ara."""
    if not SOUNDS_DIR.exists():
        return None
    for pattern in ["bg_music*", "background*", "music*"]:
        matches = list(SOUNDS_DIR.glob(pattern))
        if matches:
            return matches[0]
    return None


def _get_video_duration(video_path: str, ffmpeg_dir: str) -> float:
    """FFprobe ile video süresini al."""
    ffprobe = ffmpeg_dir.replace("ffmpeg", "ffprobe")
    if Path(ffprobe).exists() or shutil.which("ffprobe"):
        probe_cmd = shutil.which("ffprobe") or ffprobe
        try:
            result = subprocess.run(
                [
                    probe_cmd, "-v", "quiet",
                    "-show_entries", "format=duration",
                    "-of", "csv=p=0",
                    str(video_path),
                ],
                capture_output=True, text=True, timeout=10,
            )
            parsed = float(result.stdout.strip())
            if parsed > 0:
                return parsed
        except Exception:
            pass

    # ffprobe yoksa/bozulursa, OpenCV metadata'sindan hesapla.
    try:
        cap = cv2.VideoCapture(str(video_path))
        if cap.isOpened():
            fps = float(cap.get(cv2.CAP_PROP_FPS) or 0.0)
            frame_count = float(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0.0)
            cap.release()
            if fps > 0.0 and frame_count > 0.0:
                return frame_count / fps
    except Exception:
        pass

    return 55.0


def mix_audio_into_video(
    video_path: str | Path,
    event_timeline: list[dict[str, Any]],
    output_path: str | Path | None = None,
    background_music_path: str | Path | None = None,
) -> Path:
    """
    Sessiz MP4 videoya ses efektleri ve müzik ekler.

    Args:
        video_path: Sessiz MP4 dosyası
        event_timeline: [{"type": "goal"|"whistle_start"|"whistle_end"|"pop_start"|"pop_point"|"pop_end", "time": float}, ...]
        output_path: Çıktı dosyası (None ise video_path'in yanına _final ekler)
        background_music_path: Arka plan müziği (None ise otomatik arar)

    Returns:
        Final video yolu
    """
    video_path = Path(video_path)
    if not video_path.exists():
        raise FileNotFoundError(f"Video bulunamadi: {video_path}")

    if output_path is None:
        output_path = video_path.with_name(video_path.stem + "_final.mp4")
    output_path = Path(output_path)

    ffmpeg = _find_ffmpeg()
    video_duration = _get_video_duration(str(video_path), ffmpeg)

    # Arka plan müziği
    if background_music_path is None:
        background_music_path = _get_background_music()
    elif isinstance(background_music_path, str):
        background_music_path = Path(background_music_path)

    # Crowd ambient
    crowd_path = _get_sound_path("crowd_ambient")

    # Event'leri ses dosyalarıyla eşle
    audio_events: list[dict[str, Any]] = []
    for evt in event_timeline:
        evt_type = evt.get("type", "")
        evt_time = float(evt.get("time", 0))
        sound_path = _get_sound_path(evt_type)
        if sound_path:
            base_vol = VOLUME.get(evt_type, 0.5)
            
            # Dinamik volume: impulse parametresi varsa base_vol ile çarp.
            # Normalde impulse 0.5 - 1.0 arası gelir.
            final_vol = base_vol
            if "impulse" in evt and evt_type in {"ball_hit_peg", "hit"}:
                impulse = float(evt["impulse"])
                # impulse 0.0-1.0 aralığında, sesi çok kısmamak için alt limit koyalım
                final_vol = base_vol * max(0.4, impulse)

            audio_events.append({
                "type": evt_type,
                "time": evt_time,
                "path": str(sound_path),
                "volume": final_vol,
            })

    if not audio_events and not background_music_path and not crowd_path:
        print("[AudioMixer] Hic ses dosyasi bulunamadi. Sessiz video korunuyor.")
        shutil.copy2(video_path, output_path)
        return output_path

    # --- INPUTLARI HAZIRLA (Deduplication) ---
    inputs = ["-i", str(video_path)]
    input_idx = 1 # 0 = video

    # Background music
    bg_idx = None
    if background_music_path and background_music_path.exists():
        inputs.extend(["-stream_loop", "-1", "-i", str(background_music_path)])
        bg_idx = input_idx
        input_idx += 1

    # Crowd ambient
    crowd_idx = None
    if crowd_path:
        inputs.extend(["-stream_loop", "-1", "-i", str(crowd_path)])
        crowd_idx = input_idx
        input_idx += 1

    # Unique SFX paths
    unique_sfx_paths = []
    path_to_input_idx = {}
    sfx_usage: dict[str, list[dict[str, Any]]] = {}

    for evt in audio_events:
        p = evt["path"]
        if p not in path_to_input_idx:
            path_to_input_idx[p] = input_idx
            unique_sfx_paths.append(p)
            inputs.extend(["-i", p])
            input_idx += 1
            sfx_usage[p] = []
        sfx_usage[p].append(evt)

    # --- FILTER COMPLEX OLUSTUR ---
    filter_parts: list[str] = []
    overlay_labels: list[str] = []

    # Arka plan müziği
    if bg_idx is not None:
        vol = VOLUME["background_music"]
        fade_in = FADE["bg_fade_in"]
        fade_out = FADE["bg_fade_out"]
        fade_out_start = max(0, video_duration - fade_out)
        label = "bg"
        filter_parts.append(
            f"[{bg_idx}:a]atrim=0:{video_duration},asetpts=PTS-STARTPTS,"
            f"volume={vol},"
            f"afade=t=in:st=0:d={fade_in},"
            f"afade=t=out:st={fade_out_start}:d={fade_out}[{label}]"
        )
        overlay_labels.append(f"[{label}]")

    # Crowd ambient
    if crowd_idx is not None:
        vol = VOLUME["crowd_ambient"]
        peak_vol = min(1.0, vol * 3.5)
        ramp_start = max(0, video_duration - 10.0)
        vol_expr = f"'{vol} + ({peak_vol} - {vol}) * min(1, max(0, t - {ramp_start}) / 10)':eval=frame"
        
        fade_in = FADE["crowd_fade_in"]
        fade_out = FADE["crowd_fade_out"]
        fade_out_start = max(0, video_duration - fade_out)
        label = "crowd"
        filter_parts.append(
            f"[{crowd_idx}:a]atrim=0:{video_duration},asetpts=PTS-STARTPTS,"
            f"volume={vol_expr},"
            f"afade=t=in:st=0:d={fade_in},"
            f"afade=t=out:st={fade_out_start}:d={fade_out}[{label}]"
        )
        overlay_labels.append(f"[{label}]")

    # Hit sesleri için MP3 encoder delay'ini kesmek için atrim ekle (yaklaşık 25ms sessizlik)
    HIT_TYPES = {"ball_hit_peg", "hit"}
    HIT_TRIM = "atrim=start=0.025,asetpts=PTS-STARTPTS,"

    # Event ses efektleri (her unique inputu ihtiyac kadar split et)
    sfx_total_count = 0
    for p in unique_sfx_paths:
        idx = path_to_input_idx[p]
        events = sfx_usage[p]
        n = len(events)
        
        if n > 1:
            split_labels = "".join(f"[u{idx}e{j}]" for j in range(n))
            filter_parts.append(f"[{idx}:a]asplit={n}{split_labels}")
            for j, evt in enumerate(events):
                in_label = f"u{idx}e{j}"
                out_label = f"sfx{sfx_total_count}"
                sfx_total_count += 1
                
                delay_ms = int(evt["time"] * 1000)
                vol = evt["volume"]
                trim_prefix = HIT_TRIM if evt["type"] in HIT_TYPES else ""
                
                if evt["type"] in {"goal", "pop_point", "pop_end"}:
                    filter_parts.append(
                        f"[{in_label}]volume={vol},afade=t=out:st=2.0:d=1.2,"
                        f"adelay={delay_ms}|{delay_ms},apad=whole_dur={video_duration}[{out_label}]"
                    )
                else:
                    filter_parts.append(
                        f"[{in_label}]{trim_prefix}volume={vol},"
                        f"adelay={delay_ms}|{delay_ms},apad=whole_dur={video_duration}[{out_label}]"
                    )
                overlay_labels.append(f"[{out_label}]")
        else:
            # Tek bir kullanim varsa split'e gerek yok
            evt = events[0]
            out_label = f"sfx{sfx_total_count}"
            sfx_total_count += 1
            
            delay_ms = int(evt["time"] * 1000)
            vol = evt["volume"]
            trim_prefix = HIT_TRIM if evt["type"] in HIT_TYPES else ""
            
            filter_parts.append(
                f"[{idx}:a]{trim_prefix}volume={vol},"
                f"adelay={delay_ms}|{delay_ms},apad=whole_dur={video_duration}[{out_label}]"
            )
            overlay_labels.append(f"[{out_label}]")

    if not overlay_labels:
        shutil.copy2(video_path, output_path)
        return output_path

    # Tüm ses katmanlarını birleştir
    mix_input = "".join(overlay_labels)
    n_streams = len(overlay_labels)
    filter_parts.append(
        f"{mix_input}amix=inputs={n_streams}:duration=longest:dropout_transition=2:normalize=0[aout]"
    )

    filter_complex_str = ";\n".join(filter_parts)

    # Filter script ve cikti icin temp dosyalar
    fscript_path = None
    tmp_path = None
    try:
        # Filter script dosyasi
        with tempfile.NamedTemporaryFile(suffix=".txt", delete=False, mode="w", encoding="utf-8", dir=str(video_path.parent)) as fs:
            fs.write(filter_complex_str)
            fscript_path = fs.name

        # Temp video dosyasi
        with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False, dir=str(video_path.parent)) as tmp:
            tmp_path = tmp.name

        cmd = [
            ffmpeg,
            *inputs,
            "-filter_complex_script", fscript_path,
            "-map", "0:v",
            "-map", "[aout]",
            "-c:v", "copy",
            "-c:a", "aac",
            "-b:a", "256k",
            "-t", f"{video_duration:.3f}",
            "-y",
            tmp_path,
        ]

        print(f"[AudioMixer] {len(audio_events)} ses efekti ({len(unique_sfx_paths)} benzersiz dosya) + "
              f"{'muzik' if background_music_path else 'muzik yok'} + "
              f"{'ambient' if crowd_path else 'ambient yok'}")
        print(f"[AudioMixer] FFmpeg calistiriliyor...")

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=180,
            encoding="utf-8",
            errors="replace",
        )

        if result.returncode != 0:
            print(f"[AudioMixer] FFmpeg HATA (kod {result.returncode}):")
            stderr_lines = result.stderr.strip().split("\n")
            for line in stderr_lines[-10:]:
                print(f"  {line}")
            shutil.copy2(video_path, output_path)
            return output_path

        # Başarılı — temp'i final'e taşı
        shutil.move(tmp_path, str(output_path))
        print(f"[AudioMixer] Basarili: {output_path}")
        return output_path

    except subprocess.TimeoutExpired:
        print("[AudioMixer] FFmpeg zaman asimi (180s). Sessiz video korunuyor.")
        shutil.copy2(video_path, output_path)
        return output_path
    except Exception as exc:
        print(f"[AudioMixer] Beklenmeyen hata: {exc}")
        shutil.copy2(video_path, output_path)
        return output_path
    finally:
        if fscript_path and Path(fscript_path).exists():
            Path(fscript_path).unlink(missing_ok=True)
        if tmp_path and Path(tmp_path).exists():
            Path(tmp_path).unlink(missing_ok=True)



def save_event_timeline(events: list[dict[str, Any]], path: str | Path) -> None:
    """Event timeline'ı JSON olarak kaydet."""
    Path(path).write_text(
        json.dumps(events, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def load_event_timeline(path: str | Path) -> list[dict[str, Any]]:
    """Event timeline'ı JSON'dan yükle."""
    return json.loads(Path(path).read_text(encoding="utf-8"))
