from datetime import date
from typing import Literal

from pydantic import BaseModel, Field


class OptimizationRequest(BaseModel):

    idruta: int = Field(default=16)

    fecha: date

    modelo: Literal["H7", "H1"] = "H7"

    capacidad_bus: float = Field(gt=0)

    ocupacion_objetivo: float = Field(
        default=0.75,
        gt=0,
        le=1
    )

    presupuesto_ciclos: int | None = Field(
        default=338,
        ge=1
    )

    flota_disponible: int = Field(
        default=94,
        ge=1
    )

    delta: int = Field(
        default=6,
        ge=0
    )

    peso_cambio_frecuencia: float = Field(
        default=1.0,
        ge=0
    )

    time_limit: float = Field(
        default=60.0,
        gt=0,
        le=180
    )


class OptimizationRecord(BaseModel):

    hora: int

    demanda: float

    frecuencia: int

    headway_min: float | None

    no_atendidos: float

    espera_min: float

    tiempo_ciclo_min: float


class OptimizationResponse(BaseModel):

    fecha: str

    modelo: str

    resumen: dict

    resultados: list[OptimizationRecord]

    advertencias: list[str]