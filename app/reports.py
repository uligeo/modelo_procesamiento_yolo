from __future__ import annotations

import csv
from pathlib import Path
from typing import Any


def write_summary_csv(path: Path, summary: list[dict[str, Any]], classes: list[str]) -> None:
    fieldnames = ["linea_numero", "linea", "total"]
    fieldnames += [f"entrada_{name}" for name in classes]
    fieldnames += [f"salida_{name}" for name in classes]
    with path.open("w", newline="", encoding="utf-8-sig") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=fieldnames)
        writer.writeheader()
        for line in summary:
            row = {"linea_numero": line["numero"], "linea": line["linea"], "total": line["total"]}
            row.update({f"entrada_{name}": line["entrada"].get(name, 0) for name in classes})
            row.update({f"salida_{name}": line["salida"].get(name, 0) for name in classes})
            writer.writerow(row)
