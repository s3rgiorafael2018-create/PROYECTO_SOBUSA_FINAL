"""Fórmulas de optimización de frecuencia (Especificación 10.3). Funciones puras, fáciles de probar con pytest.

    capacidad_efectiva = capacidad_nominal x ocupacion_objetivo
    buses_por_hora     = ceil(demanda_hora / capacidad_efectiva)
    headway (min)      = 60 / buses_por_hora
    vehiculos          = ceil(tiempo_ciclo / headway)

Esta es la LÍNEA BASE. Pendiente: incorporar incertidumbre de la demanda (usar el límite superior
del intervalo del modelo), restricciones reales y análisis de sensibilidad.
"""
from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass(frozen=True)
class Recomendacion:
    buses_hora: int
    headway_min: float | None
    vehiculos: int
    capacidad_efectiva: float
    ocupacion_esperada: float | None     # demanda / (buses_hora x capacidad_nominal)
    viable: bool
    motivos: tuple[str, ...] = ()        # por qué NO es viable
    avisos: tuple[str, ...] = ()         # observaciones que no impiden ejecutar


def calcular_frecuencia(demanda_hora: float, capacidad_nominal: float, ocupacion_objetivo: float,
                        tiempo_ciclo_min: float, flota_disponible: int | None = None,
                        headway_min_permitido: float | None = None,
                        espera_max_min: float = 5.0) -> Recomendacion:
    if demanda_hora < 0:
        raise ValueError("La demanda no puede ser negativa.")
    if capacidad_nominal <= 0:
        raise ValueError("La capacidad debe ser mayor que 0.")
    if not 0 < ocupacion_objetivo <= 1:
        raise ValueError("La ocupación objetivo debe estar en (0, 1].")
    if tiempo_ciclo_min <= 0:
        raise ValueError("El tiempo de ciclo debe ser mayor que 0.")

    cap_ef = capacidad_nominal * ocupacion_objetivo
    if demanda_hora == 0:
        return Recomendacion(0, None, 0, cap_ef, 0.0, True, avisos=("Sin demanda prevista en la franja.",))

    buses = math.ceil(demanda_hora / cap_ef)
    headway = 60.0 / buses
    vehiculos = math.ceil(tiempo_ciclo_min * buses / 60.0 - 1e-9)   # = ceil(ciclo / headway)

    motivos, avisos = [], []
    if headway_min_permitido and headway < headway_min_permitido:
        motivos.append(f"El headway requerido ({headway:.1f} min) es menor al mínimo permitido ({headway_min_permitido:g} min).")
    if flota_disponible is not None and vehiculos > flota_disponible:
        motivos.append(f"Se requieren {vehiculos} vehículos y solo hay {flota_disponible} disponibles.")
    if headway > espera_max_min:
        avisos.append(f"El headway ({headway:.1f} min) supera la espera máxima objetivo ({espera_max_min:g} min).")

    return Recomendacion(buses, headway, vehiculos, cap_ef, demanda_hora / (buses * capacidad_nominal),
                         not motivos, tuple(motivos), tuple(avisos))
