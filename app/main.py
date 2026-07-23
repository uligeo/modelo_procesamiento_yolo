from __future__ import annotations

import re
import json
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncIterator

import cv2
import torch
from fastapi import BackgroundTasks, FastAPI, File, HTTPException, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from .processor import process_video
from .reports import available_result_stem, result_filenames, safe_result_stem
from .schemas import JobRequest
from .store import jobs


ROOT = Path(__file__).resolve().parent.parent
UPLOADS = ROOT / "data" / "uploads"
RESULTS = ROOT / "data" / "results"
STATIC = ROOT / "app" / "static"
for directory in (UPLOADS, RESULTS):
    directory.mkdir(parents=True, exist_ok=True)


def clear_orphan_uploads(directory: Path = UPLOADS) -> None:
    for path in directory.iterdir():
        if path.is_file() and path.name != ".gitkeep":
            path.unlink(missing_ok=True)


def organize_legacy_results(directory: Path = RESULTS) -> None:
    for report_path in directory.glob("*_resultado.json"):
        result_stem = report_path.name.removesuffix("_resultado.json")
        lock_path = directory / f".~lock.{result_stem}_resumen.csv#"
        if lock_path.exists():
            continue
        result_folder = directory / result_stem
        result_folder.mkdir(exist_ok=True)
        for filename in result_filenames(result_stem).values():
            source = directory / filename
            if source.exists():
                source.replace(result_folder / filename)


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    clear_orphan_uploads()
    organize_legacy_results()
    yield


app = FastAPI(title="Conteo vial YOLO26", version="0.1.0", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=STATIC), name="static")
app.mount("/media", StaticFiles(directory=UPLOADS), name="media")


@app.exception_handler(RequestValidationError)
async def validation_error_handler(_, exc: RequestValidationError) -> JSONResponse:
    errors = []
    for error in exc.errors():
        field = ".".join(str(part) for part in error["loc"] if part != "body")
        errors.append(f"{field}: {error['msg']}")
    return JSONResponse(
        status_code=422,
        content={"detail": "Datos inválidos — " + "; ".join(errors)},
    )


@app.get("/", include_in_schema=False)
def index() -> FileResponse:
    return FileResponse(STATIC / "index.html")


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/system")
def system_info() -> dict[str, object]:
    return {
        "mps_available": torch.backends.mps.is_available(),
        "cuda_available": torch.cuda.is_available(),
        "recommended_device": "cuda" if torch.cuda.is_available() else "mps" if torch.backends.mps.is_available() else "cpu",
    }


@app.post("/api/videos")
def upload_video(video: UploadFile = File(...)) -> dict[str, object]:
    extension = Path(video.filename or "video.mp4").suffix.lower()
    if extension not in {".mp4", ".mov", ".avi", ".mkv", ".webm", ".m4v"}:
        raise HTTPException(400, "Formato de video no admitido")
    video_id = uuid.uuid4().hex
    path = UPLOADS / f"{video_id}{extension}"
    with path.open("wb") as destination:
        while chunk := video.file.read(1024 * 1024):
            destination.write(chunk)

    capture = cv2.VideoCapture(str(path))
    if not capture.isOpened():
        path.unlink(missing_ok=True)
        raise HTTPException(400, "El archivo no es un video válido")
    width = int(capture.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT))
    frames = int(capture.get(cv2.CAP_PROP_FRAME_COUNT))
    fps = capture.get(cv2.CAP_PROP_FPS) or 0
    capture.release()
    return {
        "video_id": video_id, "url": f"/media/{path.name}", "filename": video.filename,
        "width": width, "height": height, "fps": round(fps, 2),
        "duration": round(frames / fps, 2) if fps else None,
    }


@app.delete("/api/videos/{video_id}", status_code=204)
def delete_temporary_video(video_id: str) -> None:
    if not re.fullmatch(r"[a-f0-9]{32}", video_id):
        raise HTTPException(404, "Video no encontrado")
    for path in UPLOADS.glob(f"{video_id}.*"):
        path.unlink(missing_ok=True)


@app.post("/api/jobs", status_code=202)
def create_job(request: JobRequest, background_tasks: BackgroundTasks) -> dict[str, str]:
    matches = list(UPLOADS.glob(f"{request.video_id}.*"))
    if len(matches) != 1:
        raise HTTPException(404, "Video no encontrado")
    job_id = uuid.uuid4().hex
    result_stem = available_result_stem(RESULTS, request.source_filename)
    filenames = result_filenames(result_stem)
    (RESULTS / result_stem).mkdir()
    jobs.create(job_id, {
        "job_id": job_id, "status": "en_cola", "progress": 0,
        "message": "Esperando procesamiento", "events_count": 0,
        "result_stem": result_stem, "result_folder": result_stem, "filenames": filenames,
    })
    background_tasks.add_task(process_video, job_id, request, matches[0], RESULTS, result_stem)
    return {"job_id": job_id}


def require_job(job_id: str) -> dict[str, object]:
    if not re.fullmatch(r"[a-f0-9]{32}", job_id):
        raise HTTPException(404, "Trabajo no encontrado")
    job = jobs.get(job_id)
    saved_result = RESULTS / f"{job_id}.json"
    report = None
    if not job and saved_result.exists():
        report = json.loads(saved_result.read_text(encoding="utf-8"))
    elif not job:
        for candidate in RESULTS.rglob("*_resultado.json"):
            candidate_report = json.loads(candidate.read_text(encoding="utf-8"))
            if candidate_report.get("job_id") == job_id:
                report = candidate_report
                saved_result = candidate
                break
    if not job and report:
        result_stem = report.get("result_stem") or safe_result_stem(report.get("source_filename", "video.mp4"))
        filenames = report.get("filenames") or result_filenames(result_stem)
        result_folder = report.get("result_folder")
        if result_folder is None and saved_result.parent != RESULTS:
            result_folder = saved_result.parent.name
        job = {
            "job_id": job_id, "status": "completado", "progress": 100,
            "message": "Conteo terminado", "summary": report["summary"],
            "events_count": len(report["events"]),
            "result_stem": result_stem, "result_folder": result_folder or "",
            "filenames": filenames,
            "output_video": (
                f"/api/jobs/{job_id}/video"
                if job_result_path(result_folder or "", filenames["video"]).exists()
                else None
            ),
            "csv": f"/api/jobs/{job_id}/csv", "json": f"/api/jobs/{job_id}/json",
        }
    if not job:
        raise HTTPException(404, "Trabajo no encontrado")
    return job


def job_result_path(result_folder: object, filename: object) -> Path:
    safe_folder = Path(str(result_folder)).name if result_folder else ""
    safe_filename = Path(str(filename)).name
    return RESULTS / safe_folder / safe_filename


@app.get("/api/jobs/{job_id}")
def get_job(job_id: str) -> dict[str, object]:
    return require_job(job_id)


@app.get("/api/jobs/{job_id}/csv")
def get_csv(job_id: str) -> FileResponse:
    job = require_job(job_id)
    filename = str(job.get("filenames", {}).get("csv", f"{job_id}.csv"))
    path = job_result_path(job.get("result_folder"), filename)
    if not path.exists():
        raise HTTPException(409, "El resultado todavía no está disponible")
    return FileResponse(path, media_type="text/csv", filename=filename)


@app.get("/api/jobs/{job_id}/video")
def get_result_video(job_id: str) -> FileResponse:
    job = require_job(job_id)
    filename = str(job.get("filenames", {}).get("video", f"{job_id}.mp4"))
    path = job_result_path(job.get("result_folder"), filename)
    if not path.exists():
        raise HTTPException(409, "El video todavía no está disponible")
    return FileResponse(
        path, media_type="video/mp4",
        filename=filename,
    )


@app.get("/api/jobs/{job_id}/json")
def get_json(job_id: str) -> FileResponse:
    job = require_job(job_id)
    filename = str(job.get("filenames", {}).get("json", f"{job_id}.json"))
    path = job_result_path(job.get("result_folder"), filename)
    if not path.exists():
        raise HTTPException(409, "El resultado todavía no está disponible")
    return FileResponse(path, media_type="application/json", filename=filename)
