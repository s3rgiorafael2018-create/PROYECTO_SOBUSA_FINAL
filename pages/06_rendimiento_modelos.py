
"""Rendimiento del modelo H7 de demanda horaria por ruta."""

import json
from pathlib import Path

import dash
import pandas as pd
import plotly.graph_objects as go

from dash import dash_table, html

from utils.ui import (
    COLORES,
    encabezado,
    estilo_figura,
    figura_vacia,
    grafico,
    kpi,
    tarjeta,
    aviso,
)


dash.register_page(
    __name__,
    path="/modelos",
    name="Rendimiento de modelos",
    title="Modelos | SOBUSA",
    order=6,
    icon="gauge"
)


BASE_DIR = Path(__file__).resolve().parents[1]

META_PATH = (
    BASE_DIR / "data" / "modelos" / "ruta_H7_meta.json"
)

PRONOSTICO_PATH = (
    BASE_DIR / "data" / "pronostico_demanda_ruta.json"
)


# --------------------------------------------------
# CARGA DE METADATOS
# --------------------------------------------------

def cargar_json(ruta):

    if not ruta.exists():
        return None

    try:
        with ruta.open("r", encoding="utf-8") as archivo:
            return json.load(archivo)

    except (OSError, ValueError):
        return None


def formato_numero(valor, decimales=2, sufijo=""):

    if valor is None:
        return "—"

    return f"{float(valor):,.{decimales}f}{sufijo}"


def estilo_tabla():

    return {
        "style_header": {
            "backgroundColor": COLORES["navy"],
            "color": "white",
            "fontWeight": "600",
            "border": "none"
        },
        "style_cell": {
            "padding": "10px",
            "border": "none",
            "borderBottom": (
                f"1px solid {COLORES['borde']}"
            ),
            "fontFamily": "inherit",
            "fontSize": "13px",
            "textAlign": "left"
        },
        "style_table": {
            "overflowX": "auto"
        }
    }


# --------------------------------------------------
# GRÁFICO DE MÉTRICAS
# --------------------------------------------------

def grafica_metricas(metricas):

    nombres = [
        "wMAPE horario",
        "MAPE diario",
        "Sesgo"
    ]

    valores = [
        metricas.get("wMAPE_hora_%"),
        metricas.get("MAPE_dia_%"),
        metricas.get("sesgo_%")
    ]

    disponibles = [
        (nombre, float(valor))
        for nombre, valor in zip(nombres, valores)
        if valor is not None
    ]

    if not disponibles:
        return figura_vacia(
            "No hay métricas de error disponibles"
        )

    fig = go.Figure()

    fig.add_trace(
        go.Bar(
            x=[item[0] for item in disponibles],
            y=[item[1] for item in disponibles],
            marker_color=COLORES["teal"],
            text=[
                f"{item[1]:.2f}%"
                for item in disponibles
            ],
            textposition="outside"
        )
    )

    fig.update_layout(
        title="Indicadores porcentuales del test",
        xaxis_title="Métrica",
        yaxis_title="Porcentaje (%)",
        showlegend=False
    )

    return estilo_figura(fig)


# --------------------------------------------------
# GRÁFICO DE DEMANDA H7
# --------------------------------------------------

def grafica_pronostico(pronostico):

    if not isinstance(pronostico, dict):
        return figura_vacia(
            "No se encontró el pronóstico H7"
        )

    fechas = (
        pronostico.get("modelos", {})
        .get("H7", {})
        .get("fechas", {})
    )

    registros = []

    for fecha, horas in fechas.items():

        for hora, demanda in horas.items():

            registros.append({
                "dia": fecha,
                "hora": int(hora),
                "demanda": float(demanda)
            })

    if not registros:
        return figura_vacia(
            "No hay pronósticos H7 disponibles"
        )

    df = pd.DataFrame(registros)

    df["timestamp"] = (
        pd.to_datetime(df["dia"])
        + pd.to_timedelta(df["hora"], unit="h")
    )

    df = df.sort_values("timestamp")

    fig = go.Figure()

    fig.add_trace(
        go.Scatter(
            x=df["timestamp"],
            y=df["demanda"],
            mode="lines+markers",
            name="Demanda prevista H7",
            line=dict(
                color=COLORES["navy"],
                width=2
            )
        )
    )

    fig.update_layout(
        title="Pronóstico H7 almacenado",
        xaxis_title="Fecha y hora",
        yaxis_title="Pasajeros/hora",
        hovermode="x unified"
    )

    return estilo_figura(fig)


# --------------------------------------------------
# GRÁFICO DE CARACTERÍSTICAS
# --------------------------------------------------

def grafica_caracteristicas(metadata):

    features = metadata.get("features", [])

    if not features:
        return figura_vacia(
            "No hay características registradas"
        )

    # Este gráfico muestra las variables utilizadas.
    # No representa importancia SHAP ni ganancia.

    grupos = {
        "Calendario y tiempo": 0,
        "Festivos y estacionalidad": 0,
        "Rezagos y nivel": 0
    }

    for variable in features:

        if variable.startswith(
            ("lag_", "nivel")
        ):
            grupos["Rezagos y nivel"] += 1

        elif variable.startswith(
            ("es_", "estac_")
        ):
            grupos["Festivos y estacionalidad"] += 1

        else:
            grupos["Calendario y tiempo"] += 1

    fig = go.Figure(
        go.Bar(
            x=list(grupos.values()),
            y=list(grupos.keys()),
            orientation="h",
            marker_color=COLORES["teal"],
            text=list(grupos.values()),
            textposition="outside"
        )
    )

    fig.update_layout(
        title="Características por grupo",
        xaxis_title="Número de características",
        yaxis_title="",
        showlegend=False
    )

    return estilo_figura(fig)


# --------------------------------------------------
# LAYOUT
# --------------------------------------------------

def layout(**_):
    from utils.rutas_config import config, ruta_id
    cfg = config(ruta_id(_.get("ruta", 16)))
    metadata = cargar_json(cfg["meta_h7"])

    if metadata is None:

        return html.Div([

            encabezado(
                "Rendimiento de modelos",
                "Evaluación del modelo H7"
            ),

            aviso(
                "No fue posible cargar "
                "data/modelos/ruta_H7_meta.json.",
                "warn"
            )

        ])

    pronostico = cargar_json(cfg["pronostico"])

    metricas = metadata.get("metricas_test", {})

    fecha_corte = metadata.get(
        "entrenado_hasta",
        "—"
    )

    horizonte = metadata.get(
        "horizonte_dias",
        "—"
    )

    # ----------------------------------------------
    # TABLA DE EVALUACIÓN
    # ----------------------------------------------

    filas_metricas = [
        {
            "metrica": "wMAPE horario",
            "valor": formato_numero(
                metricas.get("wMAPE_hora_%"),
                sufijo=" %"
            ),
            "interpretacion": (
                "Error absoluto ponderado de "
                "la demanda horaria."
            )
        },
        {
            "metrica": "MAE horario",
            "valor": formato_numero(
                metricas.get("MAE_hora")
            ),
            "interpretacion": (
                "Error absoluto medio en pasajeros/hora."
            )
        },
        {
            "metrica": "MAPE diario",
            "valor": formato_numero(
                metricas.get("MAPE_dia_%"),
                sufijo=" %"
            ),
            "interpretacion": (
                "Error porcentual medio de los "
                "totales diarios."
            )
        },
        {
            "metrica": "Sesgo",
            "valor": formato_numero(
                metricas.get("sesgo_%"),
                sufijo=" %"
            ),
            "interpretacion": (
                "Desviación porcentual con signo; "
                "la dirección depende de la fórmula "
                "empleada en la evaluación."
            )
        }
    ]

    # ----------------------------------------------
    # CONFIGURACIÓN
    # ----------------------------------------------

    parametros = metadata.get("params", {})

    filas_configuracion = [
        {
            "campo": "Modelo",
            "valor": "H7 · LightGBM"
        },
        {
            "campo": "Objetivo",
            "valor": metadata.get("objetivo", "—")
        },
        {
            "campo": "Función objetivo LightGBM",
            "valor": parametros.get("objective", "—")
        },
        {
            "campo": "Horizonte máximo",
            "valor": f"{horizonte} días"
        },
        {
            "campo": "Entrenamiento desde",
            "valor": metadata.get(
                "entrenar_desde", "—"
            )
        },
        {
            "campo": "Entrenamiento hasta",
            "valor": fecha_corte
        },
        {
            "campo": "Filas de entrenamiento",
            "valor": str(
                metadata.get("filas_entrenamiento", "—")
            )
        },
        {
            "campo": "Filas de evaluación",
            "valor": str(
                metricas.get("n_filas", "—")
            )
        },
        {
            "campo": "Rondas de entrenamiento",
            "valor": str(
                metadata.get("n_rounds", "—")
            )
        },
        {
            "campo": "Variables utilizadas",
            "valor": str(
                len(metadata.get("features", []))
            )
        },
        {
            "campo": "Corrección de deriva (metadatos)",
            "valor": metadata.get(
                "configuracion_deriva", "—"
            )
        }
    ]

    tabla_estilo = estilo_tabla()

    # ----------------------------------------------
    # INTERFAZ
    # ----------------------------------------------

    contenido = [

        encabezado(
            "Rendimiento de modelos",
            "Evaluación del modelo H7 de demanda "
            f"horaria de la ruta {cfg['nombre']}"
        ),

        html.Div(
            className="grid grid-4",
            children=[
                kpi("Modelo seleccionado", "H7"),
                kpi(
                    "Horizonte",
                    f"{horizonte} días"
                ),
                kpi("Fecha de corte", fecha_corte),
                kpi(
                    "wMAPE horario",
                    formato_numero(
                        metricas.get("wMAPE_hora_%"),
                        sufijo=" %"
                    )
                )
            ]
        ),

        tarjeta(
            "Resultados de evaluación · H7",

            dash_table.DataTable(
                id="mod-tabla",
                columns=[
                    {
                        "name": "Métrica",
                        "id": "metrica"
                    },
                    {
                        "name": "Valor",
                        "id": "valor"
                    },
                    {
                        "name": "Interpretación",
                        "id": "interpretacion"
                    }
                ],
                data=filas_metricas,
                **tabla_estilo
            )
        ),

        html.Div(
            className="grid grid-2",
            children=[

                tarjeta(
                    "Errores porcentuales",
                    grafico(
                        "mod-error-hora",
                        grafica_metricas(metricas)
                    )
                ),

                tarjeta(
                    "Pronóstico de demanda H7",
                    grafico(
                        "mod-calibracion",
                        grafica_pronostico(pronostico)
                    )
                ),

                tarjeta(
                    "Variables del modelo",
                    grafico(
                        "mod-shap",
                        grafica_caracteristicas(metadata)
                    )
                ),

                tarjeta(
                    "Configuración del entrenamiento",

                    dash_table.DataTable(
                        id="mod-configuracion",
                        columns=[
                            {
                                "name": "Parámetro",
                                "id": "campo"
                            },
                            {
                                "name": "Valor",
                                "id": "valor"
                            }
                        ],
                        data=filas_configuracion,
                        **tabla_estilo
                    )
                )
            ]
        ),

        tarjeta(
            "Características del modelo",

            html.P(
                ", ".join(metadata.get("features", []))
            )
        ),

        tarjeta(
            "Alcance del pronóstico",

            html.P(
                metadata.get("advertencia", "")
            )
        )
    ]

    # Advertencia sobre versiones de pronóstico
    if isinstance(pronostico, dict):

        configuracion_json = (
            pronostico.get("configuracion", {})
            .get("deriva")
        )

        configuracion_meta = metadata.get(
            "configuracion_deriva"
        )

        if (
            configuracion_json
            and configuracion_meta
            and configuracion_json != configuracion_meta
        ):

            contenido.append(
                aviso(
                    "Atención: la configuración de deriva "
                    "del pronóstico almacenado no coincide "
                    "con la registrada en los metadatos H7. "
                    "Se recomienda verificar la versión "
                    "del modelo que generó el JSON.",
                    "warn"
                )
            )

    return html.Div(contenido)
