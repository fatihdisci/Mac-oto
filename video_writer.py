from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np
import pygame

from config import SimulationConfig


class Mp4VideoWriter:
    def __init__(self, cfg: SimulationConfig, output_path: Path | None = None) -> None:
        self.cfg = cfg
        self.output_path: Path = output_path or cfg.output_path
        self.writer: cv2.VideoWriter | None = None

    def __enter__(self) -> "Mp4VideoWriter":
        self.output_path.parent.mkdir(parents=True, exist_ok=True)

        fourcc = cv2.VideoWriter_fourcc(*"mp4v")
        self.writer = cv2.VideoWriter(
            str(self.output_path),
            fourcc,
            float(self.cfg.video.fps),
            (int(self.cfg.video.width), int(self.cfg.video.height)),
        )

        if not self.writer.isOpened():
            raise RuntimeError(f"MP4 yazici acilamadi: {self.output_path}")

        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    def close(self) -> None:
        if self.writer is not None:
            self.writer.release()
            self.writer = None

    def write_surface(self, surface: pygame.Surface) -> None:
        if self.writer is None:
            raise RuntimeError("Video writer acik degil.")

        rgb_array = pygame.surfarray.array3d(surface)
        frame = np.transpose(rgb_array, (1, 0, 2))
        bgr_frame = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)
        self.writer.write(bgr_frame)
