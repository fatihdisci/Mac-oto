from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pygame

from config import SimulationConfig


def _find_ffmpeg() -> str:
    """FFmpeg yolunu bul."""
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg:
        return ffmpeg
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


def _pick_encoder() -> list[str]:
    """GPU encoder varsa kullan, yoksa CPU H.264'e düş."""
    ffmpeg = _find_ffmpeg()
    # NVIDIA NVENC dene
    try:
        result = subprocess.run(
            [ffmpeg, "-hide_banner", "-encoders"],
            capture_output=True, text=True, timeout=10,
        )
        if "h264_nvenc" in result.stdout:
            return ["-c:v", "h264_nvenc", "-preset", "p4", "-cq", "20"]
    except Exception:
        pass
    # CPU libx264 fallback
    return ["-c:v", "libx264", "-preset", "fast", "-crf", "18"]


class Mp4VideoWriter:
    def __init__(self, cfg: SimulationConfig, output_path: Path | None = None) -> None:
        self.cfg = cfg
        self.output_path: Path = output_path or cfg.output_path
        self.process: subprocess.Popen | None = None
        self.width = int(cfg.video.width)
        self.height = int(cfg.video.height)
        self.frame_size = self.width * self.height * 3  # RGB bytes per frame

    def __enter__(self) -> "Mp4VideoWriter":
        self.output_path.parent.mkdir(parents=True, exist_ok=True)

        ffmpeg = _find_ffmpeg()
        encoder_args = _pick_encoder()

        cmd = [
            ffmpeg,
            "-y",
            "-hide_banner",
            "-loglevel", "error",
            # Input: raw RGB frames from pipe
            "-f", "rawvideo",
            "-pix_fmt", "rgb24",
            "-s", f"{self.width}x{self.height}",
            "-r", str(int(self.cfg.video.fps)),
            "-i", "pipe:0",
            # Encoding
            *encoder_args,
            "-pix_fmt", "yuv420p",
            "-movflags", "+faststart",
            str(self.output_path),
        ]

        self.process = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
        )

        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    def close(self) -> None:
        if self.process is not None:
            if self.process.stdin:
                self.process.stdin.close()
            self.process.wait(timeout=60)
            self.process = None

    def write_surface(self, surface: pygame.Surface) -> None:
        if self.process is None or self.process.stdin is None:
            raise RuntimeError("Video writer acik degil.")

        raw_bytes = pygame.image.tobytes(surface, "RGB")
        self.process.stdin.write(raw_bytes)
