
"""Persistencia local de resultados de SOBUSA."""

import json
import logging
import os
import tempfile

from pathlib import Path


logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parents[1]

RESULTADOS_DIR = BASE_DIR / "data" / "resultados"

ARCHIVOS = {
    "prediccion": "ultima_prediccion.json",
    "optimizacion": "ultima_optimizacion.json"
}


def obtener_ruta(tipo, idruta=16):

    if tipo not in ARCHIVOS:
        raise ValueError(
            f"Tipo de resultado no válido: {tipo}"
        )

    from utils.rutas_config import config
    config(idruta)
    if int(idruta) == 16:
        return RESULTADOS_DIR / ARCHIVOS[tipo]
    subcarpeta = {21: "cl72", 2: "r1415"}[int(idruta)]
    return RESULTADOS_DIR / subcarpeta / ARCHIVOS[tipo]


def guardar_resultado(tipo, resultado, idruta=16):
    """
    Guarda una respuesta exitosa de FastAPI.
    """

    if not isinstance(resultado, dict):
        raise ValueError(
            "El resultado debe ser un diccionario."
        )

    ruta = obtener_ruta(tipo, idruta)

    ruta.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    temporal = None

    try:

        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=ruta.parent,
            suffix=".tmp",
            delete=False
        ) as archivo:

            temporal = Path(archivo.name)

            json.dump(
                resultado,
                archivo,
                ensure_ascii=False,
                allow_nan=False
            )

        os.replace(temporal, ruta)

        logger.info(
            "Resultado de %s guardado correctamente.",
            tipo
        )

    finally:

        if temporal is not None and temporal.exists():
            temporal.unlink()


def cargar_resultado(tipo, idruta=16):
    """
    Recupera el último resultado guardado.
    Devuelve None cuando no existe o no puede leerse.
    """

    ruta = obtener_ruta(tipo, idruta)

    if not ruta.exists():
        return None

    try:

        with ruta.open(
            "r",
            encoding="utf-8"
        ) as archivo:

            resultado = json.load(archivo)

        if not isinstance(resultado, dict):
            raise ValueError(
                "El archivo no contiene un objeto JSON."
            )

        return resultado

    except (OSError, ValueError) as error:

        logger.warning(
            "No se pudo cargar %s: %s",
            tipo,
            error
        )

        return None
