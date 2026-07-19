from __future__ import annotations

import csv
import json
import math
import time
import traceback
from collections import defaultdict, deque
from pathlib import Path
from typing import Any

import cv2
import imageio_ffmpeg
import numpy as np
import torch
from ultralytics import YOLO

from .schemas import JobRequest
from .store import jobs


TRACKER_CONFIG = Path(__file__).resolve().parent / "tracker_aerial.yaml"
PROJECT_ROOT = Path(__file__).resolve().parent.parent
CLASS_ALIASES = {
    "persona": {"person", "pedestrian", "people"},
    "bicicleta": {"bicycle", "bike"},
    "auto": {"car"},
    "truck": {"truck"},
    "bus": {"bus"},
}
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


def resolve_class_mapping(
    model_names: dict[int, str] | list[str], requested_classes: list[str]
) -> tuple[list[int], dict[int, str]]:
    names = model_names.items() if isinstance(model_names, dict) else enumerate(model_names)
    requested = set(requested_classes)
    mapping: dict[int, str] = {}
    for class_id, model_name in names:
        normalized = model_name.strip().lower()
        for app_name, aliases in CLASS_ALIASES.items():
            if app_name in requested and normalized in aliases:
                mapping[int(class_id)] = app_name
                break
    missing = requested - set(mapping.values())
    if missing:
        raise RuntimeError(f"El modelo no contiene las clases solicitadas: {', '.join(sorted(missing))}")
    return sorted(mapping), mapping


def signed_side(point: tuple[float, float], line: tuple[int, int, int, int]) -> float:
    x, y = point
    x1, y1, x2, y2 = line
    return (x2 - x1) * (y - y1) - (y2 - y1) * (x - x1)


def segments_intersect(
    a: tuple[float, float], b: tuple[float, float],
    c: tuple[float, float], d: tuple[float, float],
) -> bool:
    def orientation(p: tuple[float, float], q: tuple[float, float], r: tuple[float, float]) -> float:
        return (q[0] - p[0]) * (r[1] - p[1]) - (q[1] - p[1]) * (r[0] - p[0])

    o1, o2 = orientation(a, b, c), orientation(a, b, d)
    o3, o4 = orientation(c, d, a), orientation(c, d, b)
    return o1 * o2 <= 0 and o3 * o4 <= 0


def direction_for(previous_side: float, positive_direction: str) -> str:
    moved_to_positive = previous_side < 0
    if moved_to_positive:
        return positive_direction
    return "salida" if positive_direction == "entrada" else "entrada"


def resolve_device(requested: str) -> str:
    if requested != "auto":
        return requested
    if torch.cuda.is_available():
        return "cuda"
    if torch.backends.mps.is_available():
        return "mps"
    return "cpu"


def draw_line_overlay(frame: Any, line: dict[str, Any], counts: dict[str, Any]) -> None:
    p1 = (line["px1"], line["py1"])
    p2 = (line["px2"], line["py2"])
    color = (44, 220, 170)
    cv2.line(frame, p1, p2, color, 3, cv2.LINE_AA)
    dx, dy = p2[0] - p1[0], p2[1] - p1[1]
    length = max(math.hypot(dx, dy), 1)
    mid = ((p1[0] + p2[0]) // 2, (p1[1] + p2[1]) // 2)
    normal = (-dy / length, dx / length)
    positive_is_entry = line["positive_direction"] == "entrada"
    for sign, label_direction in ((1, "E" if positive_is_entry else "S"), (-1, "S" if positive_is_entry else "E")):
        arrow_end = (int(mid[0] + normal[0] * 35 * sign), int(mid[1] + normal[1] * 35 * sign))
        arrow_color = (44, 220, 170) if label_direction == "E" else (45, 145, 255)
        cv2.arrowedLine(frame, mid, arrow_end, arrow_color, 3, tipLength=0.35)
        cv2.putText(frame, label_direction, (arrow_end[0] + 4, arrow_end[1]), cv2.FONT_HERSHEY_SIMPLEX, .5, arrow_color, 2)
    entry_total = sum(counts["entrada"].values())
    exit_total = sum(counts["salida"].values())
    label = f'{line["name"]}: E {entry_total} | S {exit_total}'
    cv2.putText(frame, label, (p1[0], max(24, p1[1] - 10)), cv2.FONT_HERSHEY_SIMPLEX, .65, color, 2, cv2.LINE_AA)


def draw_track_trails(
    frame: Any,
    active_track_ids: set[int],
    track_history: dict[int, deque[tuple[int, int]]],
) -> None:
    for track_id in active_track_ids:
        points = track_history[track_id]
        if len(points) < 2:
            continue
        trail = np.array(points, dtype=np.int32).reshape((-1, 1, 2))
        cv2.polylines(frame, [trail], False, (220, 80, 220), 3, cv2.LINE_AA)
        cv2.circle(frame, points[-1], 5, (80, 220, 160), -1, cv2.LINE_AA)


def process_video(job_id: str, request: JobRequest, video_path: Path, results_dir: Path) -> None:
    cap = None
    writer = None
    try:
        device = resolve_device(request.device)
        jobs.update(
            job_id, status="procesando",
            message=f"Cargando {request.model} en {device.upper()}",
            device=device, model=request.model,
        )
        local_model = PROJECT_ROOT / request.model
        model = YOLO(str(local_model) if local_model.exists() else request.model)
        class_ids, class_names = resolve_class_mapping(model.names, request.classes)
        cap = cv2.VideoCapture(str(video_path))
        if not cap.isOpened():
            raise RuntimeError("No fue posible abrir el video")

        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        pixel_lines = []
        for line in request.lines:
            values = line.model_dump()
            values.update({
                "px1": round(line.x1 * width), "py1": round(line.y1 * height),
                "px2": round(line.x2 * width), "py2": round(line.y2 * height),
            })
            pixel_lines.append(values)

        if request.save_annotated_video:
            output_path = results_dir / f"{job_id}.mp4"
            writer = H264VideoWriter(output_path, fps, (width, height), request.video_quality)

        counts: dict[str, dict[str, dict[str, int]]] = {
            line["id"]: {
                "entrada": {name: 0 for name in request.classes},
                "salida": {name: 0 for name in request.classes},
            }
            for line in pixel_lines
        }
        events: list[dict[str, Any]] = []
        previous_centers: dict[int, tuple[float, float]] = {}
        track_history: dict[int, deque[tuple[int, int]]] = defaultdict(lambda: deque(maxlen=60))
        observed_track_ids: set[int] = set()
        last_crossing: dict[tuple[str, int], int] = {}
        frame_number = 0
        processing_started = time.perf_counter()
        cooldown_frames = max(round(fps * 1.25), 1)

        while True:
            ok, frame = cap.read()
            if not ok:
                break
            frame_number += 1
            tracked = model.track(
                frame, persist=True, classes=class_ids, conf=request.confidence,
                imgsz=request.image_size, tracker=str(TRACKER_CONFIG), device=device, verbose=False,
            )[0]
            active_track_ids: set[int] = set()

            if tracked.boxes is not None and tracked.boxes.id is not None:
                boxes = tracked.boxes.xyxy.cpu().tolist()
                track_ids = tracked.boxes.id.int().cpu().tolist()
                class_indexes = tracked.boxes.cls.int().cpu().tolist()
                for box, track_id, class_index in zip(boxes, track_ids, class_indexes):
                    center = ((box[0] + box[2]) / 2, (box[1] + box[3]) / 2)
                    active_track_ids.add(track_id)
                    observed_track_ids.add(track_id)
                    track_history[track_id].append((round(center[0]), round(center[1])))
                    previous = previous_centers.get(track_id)
                    class_name = class_names.get(class_index)
                    if previous and class_name:
                        for line in pixel_lines:
                            segment = (line["px1"], line["py1"], line["px2"], line["py2"])
                            p1, p2 = (segment[0], segment[1]), (segment[2], segment[3])
                            previous_side = signed_side(previous, segment)
                            current_side = signed_side(center, segment)
                            key = (line["id"], track_id)
                            cooled_down = frame_number - last_crossing.get(key, -cooldown_frames) >= cooldown_frames
                            if (
                                previous_side * current_side < 0
                                and segments_intersect(previous, center, p1, p2)
                                and cooled_down
                            ):
                                direction = direction_for(previous_side, line["positive_direction"])
                                counts[line["id"]][direction][class_name] += 1
                                last_crossing[key] = frame_number
                                events.append({
                                    "line_id": line["id"], "linea": line["name"],
                                    "direccion": direction, "clase": class_name,
                                    "track_id": track_id, "frame": frame_number,
                                    "segundo": round(frame_number / fps, 2),
                                })
                    previous_centers[track_id] = center

            if writer is not None:
                annotated = tracked.plot(labels=True, conf=True) if tracked.boxes is not None else frame.copy()
                draw_track_trails(annotated, active_track_ids, track_history)
                for line in pixel_lines:
                    draw_line_overlay(annotated, line, counts[line["id"]])
                writer.write(annotated)
            if frame_number % 10 == 0:
                progress = round((frame_number / total_frames) * 100, 1) if total_frames else 0
                elapsed = max(time.perf_counter() - processing_started, .001)
                jobs.update(
                    job_id, progress=min(progress, 99.9), frame=frame_number,
                    events_count=len(events), processing_fps=round(frame_number / elapsed, 1),
                    active_tracks=len(active_track_ids), unique_tracks=len(observed_track_ids),
                )

        summary = []
        for line in pixel_lines:
            line_counts = counts[line["id"]]
            summary.append({
                "line_id": line["id"], "linea": line["name"],
                "entrada": line_counts["entrada"], "salida": line_counts["salida"],
                "total": sum(sum(values.values()) for values in line_counts.values()),
            })

        csv_path = results_dir / f"{job_id}.csv"
        with csv_path.open("w", newline="", encoding="utf-8-sig") as csv_file:
            fieldnames = ["line_id", "linea", "direccion", "clase", "track_id", "frame", "segundo"]
            writer_csv = csv.DictWriter(csv_file, fieldnames=fieldnames)
            writer_csv.writeheader()
            writer_csv.writerows(events)

        json_path = results_dir / f"{job_id}.json"
        json_path.write_text(
            json.dumps({"job_id": job_id, "summary": summary, "events": events}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        output_video = f"/api/jobs/{job_id}/video" if request.save_annotated_video else None
        jobs.update(
            job_id, status="completado", progress=100, message="Conteo terminado",
            summary=summary, events_count=len(events), active_tracks=0,
            unique_tracks=len(observed_track_ids), output_video=output_video,
            csv=f"/api/jobs/{job_id}/csv", json=f"/api/jobs/{job_id}/json",
        )
    except Exception as exc:
        jobs.update(job_id, status="error", message=str(exc), error=traceback.format_exc())
    finally:
        if cap is not None:
            cap.release()
        if writer is not None:
            writer.release()
