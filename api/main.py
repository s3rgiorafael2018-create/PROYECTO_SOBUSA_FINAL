from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request

from pathlib import Path
from utils.rutas_config import config
import json

from api.services.prediction_service import PredictionService
from api.services.optimization_service import OptimizationService

from api.schemas.prediction import (
    PredictionRequest,
    PredictionResponse
)

from api.schemas.optimization import (
    OptimizationRequest,
    OptimizationResponse
)



@asynccontextmanager
async def lifespan(app: FastAPI):

    prediction_service = PredictionService()
    optimization_service = OptimizationService()

    app.state.prediction_service = prediction_service
    app.state.optimization_service = optimization_service

    print("API inicializada correctamente.")
    print("Pronósticos H7 disponibles mediante archivo JSON.")
    print("Servicio de optimización inicializado.")

    yield

    app.state.prediction_service = None
    app.state.optimization_service = None

    print("API detenida.")



app = FastAPI(
    title="SOBUSA - API de Predicciones y Optimización",
    description=(
        "API para generar predicciones de demanda "
        "y optimizar frecuencias para CRA 54, Calle 72 y Ruta 14-15."
    ),
    version="1.1.0",
    lifespan=lifespan
)


# ---------------------------------------
# 1. Verificar estado de la API
# ---------------------------------------

@app.get("/health")
def health():

    return {
        "status": "ok",
        "message": "API funcionando correctamente."
    }


# ---------------------------------------
# 2. Consultar información del modelo
# ---------------------------------------

@app.get("/model/info")
def model_info(idruta: int = 16):

    try:
        ruta = config(idruta)["meta_h7"]
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if not ruta.exists():
        raise HTTPException(
            status_code=503,
            detail="No se encontraron los metadatos H7."
        )

    with ruta.open("r", encoding="utf-8") as archivo:
        metadata = json.load(archivo)

    return {
        "modelo": "H7",
        "objetivo": metadata["objetivo"],
        "horizonte_dias": metadata["horizonte_dias"],
        "features": metadata["features"],
        "entrenado_desde": metadata.get("entrenar_desde"),
        "entrenado_hasta": metadata["entrenado_hasta"],
        "metricas_test": metadata["metricas_test"]
    }



# ---------------------------------------
# 3. Generar predicciones
# ---------------------------------------

@app.post(
    "/predictions/run",
    response_model=PredictionResponse
)
def run_predictions(
    payload: PredictionRequest,
    request: Request
):

    prediction_service = request.app.state.prediction_service

    try:

        predictions = prediction_service.run_predictions(
            fecha_inicio=payload.fecha_inicio.isoformat(),
            horizonte_dias=payload.horizonte_dias,
            idruta=payload.idruta
        )

        summary = prediction_service.get_summary(predictions)

        return {
            "resumen": summary,
            "predicciones": predictions.to_dict(orient="records")
        }

    except (ValueError, TypeError) as error:

        raise HTTPException(
            status_code=400,
            detail=str(error)
        )

    except RuntimeError as error:

        raise HTTPException(
            status_code=503,
            detail=str(error)
        )
        
    except FileNotFoundError as error:
        raise HTTPException(
            status_code=503,
            detail=str(error)
        )


# ---------------------------------------
# 4. Optimizar frecuencias
# ---------------------------------------

@app.post(
    "/optimization/run",
    response_model=OptimizationResponse
)
def run_optimization(
    payload: OptimizationRequest,
    request: Request
):

    optimization_service = (
        request.app.state.optimization_service
    )

    try:

        resultado = optimization_service.run_optimization(
            payload
        )

        return resultado

    except (ValueError, TypeError) as error:

        raise HTTPException(
            status_code=400,
            detail=str(error)
        )

    except FileNotFoundError as error:

        raise HTTPException(
            status_code=503,
            detail=str(error)
        )

    except RuntimeError as error:

        raise HTTPException(
            status_code=503,
            detail=str(error)
        )