
from datetime import date

from pydantic import BaseModel, Field


class PredictionRequest(BaseModel):
    idruta: int = Field(default=16)
    fecha_inicio: date
    horizonte_dias: int = Field(default=7, ge=1, le=7)


class PredictionRecord(BaseModel):
    dia: str
    hora: int
    demanda_predicha: float


class PredictionSummary(BaseModel):
    modelo: str
    total_predicciones: int
    fechas: int
    demanda_total: float
    promedio_horario: float
    maximo_horario: float
    minimo_horario: float


class PredictionResponse(BaseModel):
    resumen: PredictionSummary
    predicciones: list[PredictionRecord]
