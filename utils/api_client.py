
import os
from pathlib import Path

import requests
from dotenv import load_dotenv


# Cargar variables de entorno
BASE_DIR = Path(__file__).resolve().parents[1]
load_dotenv(BASE_DIR / ".env")

API_BASE_URL = os.getenv(
    "API_URL",
    "http://127.0.0.1:8000"
).rstrip("/")


class SobusaAPIClient:

    def __init__(self, base_url=API_BASE_URL):
        self.base_url = base_url.rstrip("/")
        self.timeout = (5, 120)

    def check_health(self):
        """
        Comprueba la disponibilidad de FastAPI.
        """
        try:
            response = requests.get(
                f"{self.base_url}/health",
                timeout=self.timeout
            )

            response.raise_for_status()
            return response.json()

        except requests.exceptions.RequestException as error:
            raise RuntimeError(
                f"No fue posible conectar con la API: {error}"
            ) from error

    def get_model_info(self, idruta=16):
        """
        Obtiene los metadatos del modelo.
        """
        try:
            response = requests.get(
                f"{self.base_url}/model/info",
                params={"idruta": int(idruta)},
                timeout=self.timeout
            )

            response.raise_for_status()
            return response.json()

        except requests.exceptions.RequestException as error:
            raise RuntimeError(
                f"No fue posible consultar el modelo: {error}"
            ) from error

    def run_predictions(
        self,
        fecha_inicio,
        horizonte_dias=7,
        idruta=16
    ):
        """
        Solicita predicciones a FastAPI.
        """

        payload = {
            "fecha_inicio": str(fecha_inicio),
            "horizonte_dias": horizonte_dias,
            "idruta": int(idruta)
        }

        try:
            response = requests.post(
                f"{self.base_url}/predictions/run",
                json=payload,
                timeout=self.timeout
            )

            response.raise_for_status()
            return response.json()

        except requests.exceptions.RequestException as error:
            raise RuntimeError(
                f"No fue posible generar las predicciones: {error}"
            ) from error
            
    def run_optimization(
    self,
    fecha,
    modelo,
    capacidad_bus,
    ocupacion_objetivo,
    presupuesto_ciclos=338,
    flota_disponible=94,
    delta=6,
    peso_cambio_frecuencia=1.0,
    idruta=16
    ):
        """
        Solicita a FastAPI la optimización de frecuencias.
        """

        payload = {

            "fecha": str(fecha),
            "idruta": int(idruta),

            "modelo": modelo,

            "capacidad_bus": float(capacidad_bus),

            "ocupacion_objetivo": float(ocupacion_objetivo),

            "presupuesto_ciclos": (
                int(presupuesto_ciclos)
                if presupuesto_ciclos is not None
                else None
            ),

            "flota_disponible": int(flota_disponible),

            "delta": int(delta),

            "peso_cambio_frecuencia": float(
                peso_cambio_frecuencia
            )

        }

        try:

            response = requests.post(
                f"{self.base_url}/optimization/run",
                json=payload,
                timeout=self.timeout
            )

            response.raise_for_status()

            return response.json()

        except requests.exceptions.RequestException as error:

            detalle = ""

            if error.response is not None:
                detalle = f" Respuesta de la API: {error.response.text}"

            raise RuntimeError(
                f"No fue posible optimizar las frecuencias: "
                f"{error}.{detalle}"
            ) from error
