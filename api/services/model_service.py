
import json
from pathlib import Path

import numpy as np
import pandas as pd
import lightgbm as lgb

from utils.rutas_config import config


BASE_DIR = Path(__file__).resolve().parents[2]

MODEL_PATH = BASE_DIR / "data" / "modelos" / "lgbm_kra54.txt"
META_PATH = BASE_DIR / "data" / "modelos" / "lgbm_kra54_meta.json"


class ModelService:

    def __init__(self, idruta=16):
        cfg = config(idruta)
        self.model_path = cfg["lgbm"]
        self.meta_path = cfg["lgbm_meta"]
        self.features = []
        self.model = None
        self.metadata = None
        self.load_model()

    # -----------------------------------------------------
    # 1. CARGAR MODELO Y METADATOS
    # -----------------------------------------------------

    def load_model(self):

        if not self.model_path.exists():
            raise FileNotFoundError(
                f"No se encontró el modelo: {self.model_path}"
            )

        if not self.meta_path.exists():
            raise FileNotFoundError(
                f"No se encontraron los metadatos: {self.meta_path}"
            )

        self.model = lgb.Booster(
            model_file=str(self.model_path)
        )

        with open(self.meta_path, "r", encoding="utf-8") as file:
            self.metadata = json.load(file)

        # Verificar características
        model_features = self.model.feature_name()
        metadata_features = self.metadata["features"]

        if model_features != metadata_features:
            raise ValueError(
                "Las características del LightGBM y sus metadatos no coinciden."
            )
        self.features = metadata_features

        # Verificar número de árboles
        expected_trees = self.metadata["n_arboles"]

        if self.model.num_trees() != expected_trees:
            raise ValueError(
                "El número de árboles del modelo no coincide "
                "con los metadatos."
            )

        return self

    # -----------------------------------------------------
    # 2. EJECUTAR INFERENCIA
    # -----------------------------------------------------

    def predict(self, X: pd.DataFrame):

        if self.model is None:
            raise RuntimeError(
                "El modelo no ha sido cargado."
            )

        if not isinstance(X, pd.DataFrame):
            raise TypeError(
                "La entrada debe ser un pandas DataFrame."
            )

        # Comprobar características requeridas
        missing = [
            col for col in self.features
            if col not in X.columns
        ]

        if missing:
            raise ValueError(
                f"Faltan características para inferencia: {missing}"
            )

        # Asegurar el orden exacto del entrenamiento
        X_model = X[self.features].copy()

        # Ejecutar predicción
        predictions = self.model.predict(X_model)

        predictions = np.asarray(predictions)

        if len(predictions) != len(X_model):
            raise ValueError(
                "El número de predicciones no coincide "
                "con el número de registros de entrada."
            )

        if not np.isfinite(predictions).all():
            raise ValueError(
                "El modelo produjo valores no finitos."
            )

        return predictions

    # -----------------------------------------------------
    # 3. CONSULTAR INFORMACIÓN DEL MODELO
    # -----------------------------------------------------

    def get_info(self):

        if self.model is None:
            raise RuntimeError(
                "El modelo no ha sido cargado."
            )

        return {
            "ruta": self.metadata["ruta"],
            "objetivo": self.metadata["objetivo_modelo"],
            "n_arboles": self.model.num_trees(),
            "n_caracteristicas": len(self.features),
            "features": self.features,
            "horizonte_dias": self.metadata["horizonte_dias"],
            "entrenado_con": self.metadata["entrenado_con"]
        }
