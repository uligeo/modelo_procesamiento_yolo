from __future__ import annotations

from pathlib import Path
from typing import Any

import imageio_ffmpeg


VIDEO_CRF = {"alta": 20, "equilibrada": 26, "liviana": 31}


class H264VideoWriter:
    def __init__(self, path: Path, fps: float, size: tuple[int, int], quality: str) -> None:
        self._writer = imageio_ffmpeg.write_frames(
            str(path), size,
            fps=fps,
            codec="libx264",
            pix_fmt_in="bgr24",
            pix_fmt_out="yuv420p",
            quality=None,
            macro_block_size=2,
            output_params=[
                "-crf", str(VIDEO_CRF[quality]),
                "-preset", "veryfast",
                "-movflags", "+faststart",
            ],
            ffmpeg_log_level="warning",
        )
        self._writer.send(None)
        self._closed = False

    def write(self, frame: Any) -> None:
        self._writer.send(frame)

    def release(self) -> None:
        if not self._closed:
            self._writer.close()
            self._closed = True
