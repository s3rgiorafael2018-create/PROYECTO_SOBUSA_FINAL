from pathlib import Path

import numpy as np

from fase2_optimizar_definitivo import (
    HORAS,
    resolver,
    cargar_demanda_modelo,
    cargar_tiempos_ciclo
)

from api.schemas.optimization import OptimizationRequest
from utils.rutas_config import config


BASE_DIR = Path(__file__).resolve().parents[2]

DATA_DIR = BASE_DIR / "data"

JSON_PATH = DATA_DIR / "pronostico_demanda_ruta.json"

CYCLE_PATH = DATA_DIR / "ciclo_observado.csv"

CICLO_MEDIANO_MIN = 228.0

FACTOR_CARGA = 1.0


class OptimizationService:

    def __init__(self):
        pass

    # --------------------------------------------------
    # 1. CARGAR TIEMPOS DE CICLO
    # --------------------------------------------------

    def get_cycle_times(self, idruta=16):
        carpeta = config(idruta)["ciclo"].parent
        ciclo_path = config(idruta)["ciclo"]

        if ciclo_path.exists():

            ciclo_h, _ = cargar_tiempos_ciclo(
                data_dir=carpeta,
                archivo="ciclo_observado.csv"
            )

            return ciclo_h, (
                "Tiempos de ciclo obtenidos de ciclo_observado.csv."
            )

        # Si no existe el archivo, se utiliza la mediana
        # identificada previamente en el análisis.

        ciclo_h = np.full(
            len(HORAS),
            CICLO_MEDIANO_MIN,
            dtype=float
        )

        return ciclo_h, (
            "Se utilizó un tiempo de ciclo constante de "
            f"{CICLO_MEDIANO_MIN:.0f} minutos como referencia."
        )

    # --------------------------------------------------
    # 2. EJECUTAR OPTIMIZACIÓN
    # --------------------------------------------------

    def run_optimization(
        self,
        payload: OptimizationRequest
    ):

        # Verificar JSON de la ruta seleccionada
        ruta_json = config(payload.idruta)["pronostico"]
        if not ruta_json.exists():
            raise FileNotFoundError(
                f"No se encontró el archivo de pronóstico: {ruta_json}"
            )

        fecha = payload.fecha.isoformat()

        # Cargar demanda horaria H7/H1
        demanda_serie, fuente = cargar_demanda_modelo(
            ruta_json=ruta_json,
            modelo=payload.modelo,
            fecha=fecha
        )

        demanda = demanda_serie.to_numpy(dtype=float)

        # Obtener tiempos de ciclo
        ciclo_h, fuente_ciclo = self.get_cycle_times(payload.idruta)

        # Ejecutar MILP
        resultado = resolver(
            demanda_horaria=demanda,
            ciclo_min_por_hora=ciclo_h,

            capacidad_bus=payload.capacidad_bus,

            ocupacion_objetivo=payload.ocupacion_objetivo,

            factor_carga=FACTOR_CARGA,

            flota_disponible=payload.flota_disponible,

            delta=payload.delta,

            peso_cambio_frecuencia=(
                payload.peso_cambio_frecuencia
            ),

            presupuesto_ciclos=payload.presupuesto_ciclos,

            time_limit=payload.time_limit
        )

        if not resultado["ok"]:
            raise RuntimeError(
                "El optimizador no encontró una solución válida: "
                f"{resultado['status']}"
            )

        # --------------------------------------------------
        # 3. ORGANIZAR RESULTADOS POR HORA
        # --------------------------------------------------

        frecuencias = resultado["frecuencias"]

        no_atendidos = resultado["no_atendidos"]

        esperas = resultado["espera_por_hora_min"]

        registros = []

        for i, hora in enumerate(HORAS):

            frecuencia = int(frecuencias[i])

            headway = (
                round(60.0 / frecuencia, 2)
                if frecuencia > 0
                else None
            )

            registros.append({

                "hora": int(hora),

                "demanda": round(
                    float(demanda[i]), 2
                ),

                "frecuencia": frecuencia,

                "headway_min": headway,

                "no_atendidos": round(
                    float(no_atendidos[i]), 2
                ),

                "espera_min": round(
                    float(esperas[i]), 2
                ),

                "tiempo_ciclo_min": round(
                    float(ciclo_h[i]), 2
                )

            })

        # --------------------------------------------------
        # 4. RESUMEN GENERAL
        # --------------------------------------------------

        resumen = {

            "demanda_total": round(
                float(demanda.sum()), 2
            ),

            "ciclos_totales": int(
                resultado["ciclos"]
            ),

            "espera_promedio_min": round(
                resultado["espera_promedio_min"], 2
            ),

            "espera_total_min": round(
                resultado["espera_total_min"], 2
            ),

            "no_atendidos_total": round(
                resultado["total_no_atendidos"], 2
            ),

            "porcentaje_no_atendidos": round(
                resultado["pct_no_atendidos"] * 100, 2
            ),

            "buses_equivalentes_promedio": round(
                resultado["buses_equivalentes_promedio"], 2
            ),

            "capacidad_efectiva": round(
                resultado["capacidad_efectiva"], 2
            ),

            "suma_cambios_frecuencia": round(
                resultado["suma_cambios_frecuencia"], 2
            ),

            "objetivo_milp": round(
                resultado["objetivo"], 2
            )

        }

        # --------------------------------------------------
        # 5. ADVERTENCIAS Y SUPUESTOS
        # --------------------------------------------------

        advertencias = [

            "La demanda representa pasajeros por hora de la ruta completa, "
            "agregada en ambos sentidos.",

            "Cada frecuencia representa ciclos completos de ida y vuelta.",

            "El factor de carga utilizado es 1.0. Es un supuesto, "
            "no una medición de ocupación por segmento.",

            "La restricción de flota utiliza bus-minutos acumulados. "
            "No garantiza el máximo de buses simultáneamente ocupados.",

            "La espera estimada utiliza el supuesto de salidas uniformes: "
            "30 dividido entre la frecuencia."

        ]

        advertencias.append(fuente_ciclo)

        return {

            "fecha": fecha,

            "modelo": payload.modelo,

            "resumen": resumen,

            "resultados": registros,

            "advertencias": advertencias

        }