from __future__ import annotations

import csv
import re
from pathlib import Path
from typing import Any

SUMMARY_CLASSES = ["auto", "truck", "bus", "bicicleta", "persona"]


def processed_video_filename(source_filename: str) -> str:
    return f"{safe_result_stem(source_filename)}_procesado.mp4"


def safe_result_stem(source_filename: str) -> str:
    stem = Path(source_filename).stem
    safe_stem = re.sub(r'[\x00-\x1f\x7f"\\/]+', "_", stem).strip(" ._")
    return safe_stem or "video"


def result_filenames(result_stem: str) -> dict[str, str]:
    return {
        "video": f"{result_stem}_procesado.mp4",
        "csv": f"{result_stem}_resumen.csv",
        "json": f"{result_stem}_resultado.json",
    }


def available_result_stem(results_dir: Path, source_filename: str) -> str:
    base = safe_result_stem(source_filename)
    candidate = base
    suffix = 2
    while any((results_dir / name).exists() for name in result_filenames(candidate).values()):
        candidate = f"{base}_{suffix}"
        suffix += 1
    return candidate


def write_summary_csv(path: Path, summary: list[dict[str, Any]]) -> None:
    fieldnames = ["linea_numero", "Nombre carretera", "linea", "total"]
    fieldnames += [f"entrada_{name}" for name in SUMMARY_CLASSES]
    fieldnames += [f"salida_{name}" for name in SUMMARY_CLASSES]
    with path.open("w", newline="", encoding="utf-8-sig") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=fieldnames)
        writer.writeheader()
        for line in summary:
            row = {
                "linea_numero": line["numero"],
                "Nombre carretera": line["nombre_carretera"],
                "linea": line["linea"],
                "total": line["total"],
            }
            row.update({f"entrada_{name}": line["entrada"].get(name, 0) for name in SUMMARY_CLASSES})
            row.update({f"salida_{name}": line["salida"].get(name, 0) for name in SUMMARY_CLASSES})
            writer.writerow(row)
