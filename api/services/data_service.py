from pathlib import Path
import json

import holidays
import numpy as np
import pandas as pd
from utils.rutas_config import config


BASE_DIR = Path(__file__).resolve().parents[2]
DATA_DIR = BASE_DIR / "data" / "panel_horario"
GRAPH_PATH = BASE_DIR / "data" / "grafo_kra54.json"


# Orden exacto de las 16 características del entrenamiento
FEATURES = [
    "idpunto",
    "pos_rel",
    "hora",
    "dow",
    "hora_sin",
    "hora_cos",
    "dow_sin",
    "dow_cos",
    "es_festivo",
    "es_prefestivo",
    "lag_7d",
    "lag_14d",
    "lag_21d",
    "lag_28d",
    "lag_media",
    "nivel_nodo_7d",
]

LAGS = [7, 14, 21, 28]
HORIZONTE_DIAS = 7


class DataService:

    def __init__(self, idruta=16):
        cfg = config(idruta)
        self.data_dir = cfg["panel"]
        self.graph_path = cfg["grafo"]
        self.panel = None
        self.servicio = None
        self.data = None
        self.graph = None
        self.unmatched = None

    # ---------------------------------------------------------
    # 1. CARGA DE ARCHIVOS
    # ---------------------------------------------------------

    def load_data(self):

        panel_files = sorted(self.data_dir.glob("panel_*.csv"))
        servicio_files = sorted(self.data_dir.glob("servicio_*.csv"))

        if not panel_files:
            raise FileNotFoundError(
                "No se encontraron archivos panel_*.csv"
            )

        if not servicio_files:
            raise FileNotFoundError(
                "No se encontraron archivos servicio_*.csv"
            )

        self.panel = pd.concat(
            [pd.read_csv(f) for f in panel_files],
            ignore_index=True
        )

        self.servicio = pd.concat(
            [pd.read_csv(f) for f in servicio_files],
            ignore_index=True
        )

        with open(self.graph_path, "r", encoding="utf-8") as file:
            self.graph = json.load(file)

        return self

    # ---------------------------------------------------------
    # 2. VALIDACIÓN Y NORMALIZACIÓN
    # ---------------------------------------------------------

    def validate_data(self):

        panel_columns = {
            "dia", "hora", "idpunto",
            "subidas", "bajadas", "eventos"
        }

        servicio_columns = {
            "dia", "hora", "viajes", "vehiculos"
        }

        if not panel_columns.issubset(self.panel.columns):
            raise ValueError(
                "Faltan columnas requeridas en los archivos panel."
            )

        if not servicio_columns.issubset(self.servicio.columns):
            raise ValueError(
                "Faltan columnas requeridas en los archivos servicio."
            )

        # Normalizar fechas
        self.panel["dia"] = pd.to_datetime(
            self.panel["dia"], errors="raise"
        ).dt.normalize()

        self.servicio["dia"] = pd.to_datetime(
            self.servicio["dia"], errors="raise"
        ).dt.normalize()

        # Normalizar variables numéricas
        numeric_panel = [
            "hora", "idpunto", "subidas", "bajadas", "eventos"
        ]

        numeric_servicio = [
            "hora", "viajes", "vehiculos"
        ]

        for col in numeric_panel:
            self.panel[col] = pd.to_numeric(
                self.panel[col], errors="raise"
            )

        for col in numeric_servicio:
            self.servicio[col] = pd.to_numeric(
                self.servicio[col], errors="raise"
            )

        # La combinación nodo-hora-fecha debe ser única
        if self.panel.duplicated(
            ["idpunto", "hora", "dia"]
        ).any():
            raise ValueError(
                "Hay registros duplicados en panel para "
                "la combinación idpunto-hora-dia."
            )

        # Servicio debe tener una fila por fecha y hora
        if self.servicio.duplicated(
            ["dia", "hora"]
        ).any():
            raise ValueError(
                "Hay combinaciones dia-hora duplicadas en servicio."
            )

        return self

    # ---------------------------------------------------------
    # 3. POSICIÓN DE LOS NODOS EN EL GRAFO
    # ---------------------------------------------------------

    def add_graph_position(self, df):

        longitud = self.graph["longitud_ruta_m"]

        posiciones = {
            nodo["idpunto"]: (
                nodo["posicion_en_ruta_m"] / longitud
            )
            for nodo in self.graph["nodos"]
        }

        df = df.copy()

        df["pos_rel"] = df["idpunto"].map(posiciones)

        nodos_sin_posicion = df.loc[
            df["pos_rel"].isna(), "idpunto"
        ].unique()

        if len(nodos_sin_posicion) > 0:
            raise ValueError(
                "Hay idpunto que no aparecen en el grafo: "
                f"{nodos_sin_posicion.tolist()}"
            )

        return df

    # ---------------------------------------------------------
    # 4. UNIÓN PANEL + SERVICIO
    # ---------------------------------------------------------
    def clean_panel(self):

        limite = (
            self.panel
            .groupby(["idpunto", "hora"])["subidas"]
            .transform(
                lambda s: max(s.quantile(0.999) * 3, 20)
            )
        )

        # Se aplica el mismo límite a subidas y bajadas
        malo = (
            (self.panel["subidas"] > limite)
            | (self.panel["bajadas"] > limite)
        )

        self.cleaning_report = {
            "filas_antes": len(self.panel),
            "filas_eliminadas": int(malo.sum()),
            "filas_despues": int((~malo).sum()),
            "porcentaje_eliminado": (
                100 * malo.mean()
            )
        }

        self.panel = self.panel.loc[~malo].copy()

        return self

    def merge_data(self):

        # Conservar los registros sin correspondencia para auditoría
        self.clean_panel()
        
        auditoria = self.panel.merge(
            self.servicio[["dia", "hora", "viajes"]],
            on=["dia", "hora"],
            how="left",
            validate="many_to_one",
            indicator=True
        )

        self.unmatched = auditoria[
            auditoria["_merge"] == "left_only"
        ].copy()

        # Reproducir el INNER JOIN del notebook
        self.data = self.panel.merge(
            self.servicio,
            on=["dia", "hora"],
            how="inner",
            validate="many_to_one"
        )

        # El notebook excluye franjas sin viajes
        self.data = self.data[
            self.data["viajes"] > 0
        ].copy()

        # Objetivo expresado como pasajeros por viaje
        self.data["sub_por_viaje"] = (
            self.data["subidas"] / self.data["viajes"]
        )

        # Posición relativa en el recorrido
        self.data = self.add_graph_position(self.data)

        self.data.sort_values(
            ["dia", "hora", "idpunto"],
            inplace=True
        )

        self.data.reset_index(drop=True, inplace=True)

        return self.data

    # ---------------------------------------------------------
    # 5. CONSTRUCCIÓN DE CARACTERÍSTICAS
    # ---------------------------------------------------------

    def build_features(self, base=None, history=None):

        if history is None:
            history = self.data

        if base is None:
            base = history

        if history is None or base is None:
            raise ValueError(
                "Se necesitan datos históricos y filas objetivo."
            )

        base = base.copy()
        history = history.copy()

        if base.duplicated(
            ["idpunto", "hora", "dia"]
        ).any():
            raise ValueError(
                "Existen claves duplicadas en las filas objetivo."
            )

        if "pos_rel" not in base.columns:
            base = self.add_graph_position(base)

        out = base.copy()

        # -----------------------------------------------------
        # 5.1 Rezagos exactos por nodo, hora y fecha
        # -----------------------------------------------------

        source = history[
            ["idpunto", "hora", "dia", "sub_por_viaje"]
        ].copy()
        
        for k in LAGS:

            lag_data = (
                source.assign(
                    dia=source["dia"] + pd.Timedelta(days=k)
                )
                .rename(
                    columns={
                        "sub_por_viaje": f"lag_{k}d"
                    }
                )
            )

            out = out.merge(
                lag_data,
                on=["idpunto", "hora", "dia"],
                how="left",
                validate="one_to_one"
            )

        lag_columns = [f"lag_{k}d" for k in LAGS]

        # Media de rezagos: mínimo dos valores disponibles
        valid_lags = out[lag_columns].notna().sum(axis=1)

        out["lag_media"] = (
            out[lag_columns]
            .mean(axis=1)
            .where(valid_lags >= 2)
        )

        # -----------------------------------------------------
        # 5.2 Nivel reciente del nodo
        # -----------------------------------------------------

        # Primero se obtiene la tasa media diaria de cada nodo
        node_day = (
            history.groupby(
                ["idpunto", "dia"],
                as_index=False
            )["sub_por_viaje"]
            .mean()
        )

        node_columns = []

        # t-13, t-12, ..., t-7
        for k in range(HORIZONTE_DIAS, HORIZONTE_DIAS + 7):

            col = f"_nivel_{k}"

            node_lag = (
                node_day.assign(
                    dia=node_day["dia"] + pd.Timedelta(days=k)
                )
                .rename(
                    columns={"sub_por_viaje": col}
                )
            )

            out = out.merge(
                node_lag,
                on=["idpunto", "dia"],
                how="left",
                validate="many_to_one"
            )

            node_columns.append(col)

        # Promedio de los siete niveles diarios disponibles
        out["nivel_nodo_7d"] = (
            out[node_columns].mean(axis=1)
        )

        out.drop(columns=node_columns, inplace=True)

        # -----------------------------------------------------
        # 5.3 Variables temporales y cíclicas
        # -----------------------------------------------------

        out["dow"] = out["dia"].dt.dayofweek

        out["hora_sin"] = np.sin(
            2 * np.pi * out["hora"] / 24
        )

        out["hora_cos"] = np.cos(
            2 * np.pi * out["hora"] / 24
        )

        out["dow_sin"] = np.sin(
            2 * np.pi * out["dow"] / 7
        )

        out["dow_cos"] = np.cos(
            2 * np.pi * out["dow"] / 7
        )

        # -----------------------------------------------------
        # 5.4 Festivos y prefestivos de Colombia
        # -----------------------------------------------------

        years = sorted(
            out["dia"].dt.year.unique().tolist()
        )

        festivos = pd.to_datetime(
            list(
                holidays.country_holidays(
                    "CO",
                    years=years
                ).keys()
            )
        )

        out["es_festivo"] = (
            out["dia"].isin(festivos).astype(int)
        )

        out["es_prefestivo"] = (
            (out["dia"] + pd.Timedelta(days=1))
            .isin(festivos)
            .astype(int)
        )

        return out
    

    # ---------------------------------------------------------
    # 6. MATRIZ FINAL PARA LIGHTGBM
    # ---------------------------------------------------------

    def get_feature_matrix(self, df):

        missing = [
            col for col in FEATURES
            if col not in df.columns
        ]

        if missing:
            raise ValueError(
                f"Faltan características: {missing}"
            )

        X = df[FEATURES].copy()

        # Categorías de nodo consistentes con el entrenamiento
        categories = sorted(
            self.graph["nodos"],
            key=lambda nodo: nodo["idpunto"]
        )

        categories = [
            nodo["idpunto"] for nodo in categories
        ]

        X["idpunto"] = pd.Categorical(
            X["idpunto"],
            categories=categories
        )

        return X
    
    def create_prediction_grid(
        self,
        fecha_inicio,
        horizonte_dias=7
    ):

        if self.data is None:
            raise ValueError(
                "Primero debes preparar el histórico."
            )

        fecha_inicio = pd.Timestamp(fecha_inicio).normalize()

        ultima_fecha = self.data["dia"].max()

        if fecha_inicio <= ultima_fecha:
            raise ValueError(
                f"La fecha de inicio debe ser posterior "
                f"al último día histórico: {ultima_fecha.date()}."
            )

        fechas = pd.date_range(
            start=fecha_inicio,
            periods=horizonte_dias,
            freq="D"
        )

        grids = []

        for fecha in fechas:

            dow = fecha.dayofweek

            historico_dow = self.data[
                self.data["dia"].dt.dayofweek == dow
            ]

            combinaciones = (
                historico_dow[
                    ["idpunto", "hora"]
                ]
                .drop_duplicates()
                .copy()
            )

            if combinaciones.empty:
                raise ValueError(
                    f"No hay combinaciones históricas "
                    f"para el día de semana {dow}."
                )

            combinaciones["dia"] = fecha

            grids.append(combinaciones)

        grid = pd.concat(
            grids,
            ignore_index=True
        )

        grid = self.add_graph_position(grid)

        return grid.sort_values(
            ["dia", "hora", "idpunto"]
        ).reset_index(drop=True)