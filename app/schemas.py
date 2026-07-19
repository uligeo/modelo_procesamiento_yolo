from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator


class CountLine(BaseModel):
    id: str = Field(min_length=1, max_length=80)
    name: str = Field(min_length=1, max_length=120)
    x1: float = Field(ge=0, le=1)
    y1: float = Field(ge=0, le=1)
    x2: float = Field(ge=0, le=1)
    y2: float = Field(ge=0, le=1)
    positive_direction: Literal["entrada", "salida"] = "entrada"

    @field_validator("x1", "y1", "x2", "y2", mode="before")
    @classmethod
    def clamp_normalized_coordinates(cls, value: object) -> float:
        coordinate = float(value)
        return min(1.0, max(0.0, coordinate))

    @model_validator(mode="after")
    def validate_length(self) -> "CountLine":
        if abs(self.x2 - self.x1) + abs(self.y2 - self.y1) < 0.01:
            raise ValueError("La línea debe tener una longitud visible")
        return self


class JobRequest(BaseModel):
    video_id: str = Field(pattern=r"^[a-f0-9]{32}$")
    lines: list[CountLine] = Field(min_length=1, max_length=30)
    classes: list[Literal["persona", "bicicleta", "auto", "bus", "truck"]] = Field(min_length=1)
    model: Literal["best.pt", "yolo26n.pt", "yolo26s.pt"] = "best.pt"
    device: Literal["auto", "mps", "cuda", "cpu"] = "auto"
    confidence: float = Field(default=0.10, ge=0.03, le=0.95)
    image_size: int = Field(default=1280, ge=320, le=1920)
    save_annotated_video: bool = False
