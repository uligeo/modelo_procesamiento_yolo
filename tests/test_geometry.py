from collections import deque

import numpy as np

from app.processor import (
    VIDEO_CRF,
    draw_track_trails,
    direction_for,
    resolve_class_mapping,
    resolve_device,
    segments_intersect,
    signed_side,
)
from app.reports import write_summary_csv
from app.schemas import CountLine


def test_segment_intersection_only_inside_drawn_line():
    assert segments_intersect((5, -2), (5, 2), (0, 0), (10, 0))
    assert not segments_intersect((15, -2), (15, 2), (0, 0), (10, 0))


def test_signed_side_and_direction():
    line = (0, 0, 10, 0)
    assert signed_side((5, -2), line) < 0
    assert signed_side((5, 2), line) > 0
    assert direction_for(-1, "entrada") == "entrada"
    assert direction_for(1, "entrada") == "salida"
    assert direction_for(-1, "salida") == "salida"


def test_explicit_device_is_preserved():
    assert resolve_device("cpu") == "cpu"


def test_line_coordinates_are_clamped_to_video_bounds():
    line = CountLine(id="line", name="Límite", x1=-0.001, y1=0.2, x2=1.001, y2=0.8)
    assert line.x1 == 0
    assert line.x2 == 1


def test_track_trail_is_drawn_for_active_id():
    frame = np.zeros((100, 100, 3), dtype=np.uint8)
    history = {7: deque([(10, 10), (30, 30), (50, 45)])}
    draw_track_trails(frame, {7}, history)
    assert frame.sum() > 0


def test_custom_aerial_model_classes_are_mapped_by_name():
    names = {0: "pedestrian", 1: "people", 2: "bicycle", 3: "car", 5: "truck", 8: "bus"}
    class_ids, mapping = resolve_class_mapping(names, ["persona", "auto", "truck", "bus"])
    assert class_ids == [0, 1, 3, 5, 8]
    assert mapping == {0: "persona", 1: "persona", 3: "auto", 5: "truck", 8: "bus"}


def test_video_quality_levels_reduce_bitrate_progressively():
    assert VIDEO_CRF["alta"] < VIDEO_CRF["equilibrada"] < VIDEO_CRF["liviana"]


def test_summary_csv_matches_final_result(tmp_path):
    path = tmp_path / "resumen.csv"
    summary = [{
        "numero": 1, "linea": "Avenida Norte", "total": 5,
        "entrada": {"auto": 3, "bus": 0}, "salida": {"auto": 1, "bus": 1},
    }]

    write_summary_csv(path, summary, ["auto", "bus"])

    assert path.read_text(encoding="utf-8-sig").splitlines() == [
        "linea_numero,linea,total,entrada_auto,entrada_bus,salida_auto,salida_bus",
        "1,Avenida Norte,5,3,0,1,1",
    ]
