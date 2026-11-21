
"""Predicciones H7 de demanda horaria para la ruta completa."""

from datetime import date, timedelta

import pandas as pd

from utils.rutas_config import config
from fase2_optimizar_definitivo import cargar_demanda_modelo


class PredictionService:

    def run_predictions(
        self,
        fecha_inicio: str,
        horizonte_dias: int = 7,
        idruta: int = 16
    ) -> pd.DataFrame:

        if not isinstance(horizonte_dias, int):
            raise TypeError("El horizonte debe ser un entero.")

        if not 1 <= horizonte_dias <= 7:
            raise ValueError(
                "El horizonte debe estar entre 1 y 7 días."
            )

        fecha_inicial = date.fromisoformat(fecha_inicio)

        registros = []

        for i in range(horizonte_dias):

            fecha = (
                fecha_inicial + timedelta(days=i)
            ).isoformat()

            # Misma función y fuente del optimizador
            demanda_serie, _ = cargar_demanda_modelo(
                ruta_json=config(idruta)["pronostico"],
                modelo="H7",
                fecha=fecha
            )

            for hora, demanda in demanda_serie.items():

                registros.append({
                    "dia": fecha,
                    "hora": int(hora),
                    "demanda_predicha": float(demanda)
                })

        return pd.DataFrame(
            registros,
            columns=["dia", "hora", "demanda_predicha"]
        ).sort_values(
            ["dia", "hora"]
        ).reset_index(drop=True)

    def get_summary(
        self,
        predictions: pd.DataFrame
    ) -> dict:

        if predictions.empty:
            raise ValueError(
                "No hay predicciones para resumir."
            )

        valores = predictions["demanda_predicha"]

        return {
            "modelo": "H7",
            "total_predicciones": int(len(predictions)),
            "fechas": int(predictions["dia"].nunique()),
            "demanda_total": float(valores.sum()),
            "promedio_horario": float(valores.mean()),
            "maximo_horario": float(valores.max()),
            "minimo_horario": float(valores.min())
        }
