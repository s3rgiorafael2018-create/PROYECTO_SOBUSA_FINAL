"""Registro único de rutas admitidas: rutas locales, sin construir paths con texto del usuario."""
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
RUTAS = {
    16: {
        "nombre": "CRA 54",
        "panel": BASE / "data/panel_horario",
        "grafo": BASE / "data/grafo_kra54.json",
        "pronostico": BASE / "data/pronostico_demanda_ruta.json",
        "ciclo": BASE / "data/ciclo_observado.csv",
        "meta_h7": BASE / "data/modelos/ruta_H7_meta.json",
        "lgbm": BASE / "data/modelos/lgbm_kra54.txt",
        "lgbm_meta": BASE / "data/modelos/lgbm_kra54_meta.json",
    },
    21: {
        "nombre": "Calle 72",
        "panel": BASE / "data/cl72/panel_horario",
        "grafo": BASE / "data/cl72/grafo_cl72.json",
        "pronostico": BASE / "data/cl72/pronostico_demanda_ruta.json",
        "ciclo": BASE / "data/cl72/ciclo_observado.csv",
        "meta_h7": BASE / "data/cl72/modelos/ruta_H7_meta.json",
        "lgbm": BASE / "data/cl72/modelos/lgbm_cl72.txt",
        "lgbm_meta": BASE / "data/cl72/modelos/lgbm_cl72_meta.json",
    },
    2: {
        "nombre": "Ruta 14-15",
        "panel": BASE / "data/r1415/panel_horario",
        "grafo": BASE / "data/r1415/grafo_r1415.json",
        "pronostico": BASE / "data/r1415/pronostico_demanda_ruta.json",
        "ciclo": BASE / "data/r1415/ciclo_observado.csv",
        "meta_h7": BASE / "data/r1415/modelos/ruta_H7_meta.json",
        "lgbm": BASE / "data/r1415/modelos/lgbm_r1415.txt",
        "lgbm_meta": BASE / "data/r1415/modelos/lgbm_r1415_meta.json",
    },
}


def config(idruta=16):
    """Devuelve solo rutas predefinidas. En la API rechaza IDs desconocidos."""
    try:
        return RUTAS[int(idruta)]
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("Ruta no admitida; usa 16 (CRA 54), 21 (Calle 72) o 2 (14-15).") from exc


def ruta_id(valor):
    """Normaliza el valor de navegación Dash; ruta 16 como alternativa segura."""
    try:
        numero = int(valor)
        return numero if numero in RUTAS else 16
    except (ValueError, TypeError):
        return 16


def modelos_pronostico(idruta):
    """Opciones H7/H1 efectivamente disponibles en el pronóstico exportado."""
    import json
    pronostico = config(idruta)["pronostico"]
    if not pronostico.is_file():
        return ("H7",)
    try:
        with pronostico.open(encoding="utf-8") as archivo:
            modelos = json.load(archivo).get("modelos", {})
        return tuple(m for m in ("H7", "H1") if m in modelos and modelos[m].get("fechas"))
    except (OSError, ValueError, AttributeError):
        return ("H7",)
