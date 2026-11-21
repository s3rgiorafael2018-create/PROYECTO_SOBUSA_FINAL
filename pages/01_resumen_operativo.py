
"""Resumen operativo de SOBUSA: predicción, optimización y alertas."""

from datetime import datetime
from zoneinfo import ZoneInfo

import dash
import pandas as pd
import plotly.graph_objects as go

from dash import Input, Output, callback, dcc, html

from utils import data_loader as dl
from utils.ui import (
    COLORES,
    aviso,
    encabezado,
    figura_vacia,
    grafico,
    kpi,
    tarjeta,
    estilo_figura
)


dash.register_page(
    __name__,
    path="/",
    name="Resumen operativo",
    title="Resumen operativo | SOBUSA",
    order=1,
    icon="dashboard"
)


ZONA_HORARIA = ZoneInfo("America/Bogota")
HORAS_OPERACION = list(range(4, 23))


# --------------------------------------------------
# FUNCIONES AUXILIARES
# --------------------------------------------------

def obtener_registros_optimizacion(resultado):

    if not isinstance(resultado, dict):
        return pd.DataFrame()

    registros = resultado.get("resultados", [])

    if not isinstance(registros, list) or not registros:
        return pd.DataFrame()

    df = pd.DataFrame(registros)

    columnas = [
        "hora",
        "demanda",
        "frecuencia",
        "headway_min",
        "no_atendidos",
        "tiempo_ciclo_min"
    ]

    if not all(col in df.columns for col in columnas):
        return pd.DataFrame()

    for columna in columnas:
        df[columna] = pd.to_numeric(
            df[columna],
            errors="coerce"
        )

    df = df.dropna(
        subset=["hora", "demanda", "frecuencia", "no_atendidos"]
    )

    df = df[df["hora"].isin(HORAS_OPERACION)]

    return df.sort_values("hora").drop_duplicates(
        subset=["hora"],
        keep="last"
    )


def obtener_siguiente_franja(df, hora_actual):

    if df.empty:
        return None

    # Primera franja disponible posterior a la hora actual.
    futuras = df[df["hora"] > hora_actual]

    if not futuras.empty:
        return futuras.iloc[0]

    # Fuera del horario: utilizar la primera franja
    # del siguiente ciclo diario de simulación.
    return df.iloc[0]


def construir_alertas_resumen(df):

    if df.empty:
        return []

    alertas = []

    horas_disponibles = set(df["hora"].astype(int))

    faltantes = [
        hora
        for hora in HORAS_OPERACION
        if hora not in horas_disponibles
    ]

    if faltantes:
        alertas.append({
            "codigo": "ALT-009",
            "alerta": "Datos incompletos",
            "nivel": "Crítica",
            "detalle": (
                "Faltan registros para: "
                + ", ".join(
                    f"{hora:02d}:00"
                    for hora in faltantes
                )
            )
        })

    for _, fila in df.iterrows():

        hora = int(fila["hora"])
        demanda = float(fila["demanda"])
        frecuencia = int(fila["frecuencia"])
        no_atendidos = float(fila["no_atendidos"])

        if no_atendidos > 0:
            alertas.append({
                "codigo": "ALT-003",
                "alerta": "Frecuencia insuficiente",
                "nivel": "Preventiva",
                "detalle": (
                    f"{hora:02d}:00 | "
                    f"{no_atendidos:,.1f} pasajeros no atendidos"
                )
            })

    # Misma condición adicional utilizada en Alertas:
    # frecuencia cero y demanda positiva en la hora actual.
    hora_actual = datetime.now(ZONA_HORARIA).hour

    actuales = df[df["hora"] == hora_actual]

    if not actuales.empty:

        actual = actuales.iloc[0]

        if (
            actual["frecuencia"] == 0
            and actual["demanda"] > 0
        ):
            alertas.append({
                "codigo": "ALT-003",
                "alerta": "Sin ciclos programados",
                "nivel": "Preventiva",
                "detalle": (
                    f"{hora_actual:02d}:00 | "
                    "Demanda positiva sin ciclos programados"
                )
            })

    return alertas



def grafica_demanda(df_opt, resultado_pred):

    fig = go.Figure()
    tiene_datos = False

    # Demanda horaria utilizada por el optimizador
    if not df_opt.empty:

        fig.add_trace(
            go.Scatter(
                x=df_opt["hora"],
                y=df_opt["demanda"],
                mode="lines+markers",
                name="Demanda usada en optimización",
                line=dict(color=COLORES["navy"], width=3)
            )
        )

        tiene_datos = True

    # Predicción H7: pasajeros por hora de la ruta completa
    if isinstance(resultado_pred, dict):

        registros = resultado_pred.get("predicciones", [])

        if isinstance(registros, list) and registros:

            df_pred = pd.DataFrame(registros)

            columnas = {"dia", "hora", "demanda_predicha"}

            if columnas.issubset(df_pred.columns):

                df_pred["demanda_predicha"] = pd.to_numeric(
                    df_pred["demanda_predicha"],
                    errors="coerce"
                )

                df_pred["hora"] = pd.to_numeric(
                    df_pred["hora"],
                    errors="coerce"
                )

                df_pred = df_pred.dropna(
                    subset=["hora", "demanda_predicha"]
                )

                if not df_pred.empty:

                    # Mantener cada fecha por separado.
                    # No sumar ni promediar días distintos.
                    for fecha, grupo in df_pred.groupby("dia"):

                        grupo = grupo.sort_values("hora")

                        fig.add_trace(
                            go.Scatter(
                                x=grupo["hora"],
                                y=grupo["demanda_predicha"],
                                mode="lines+markers",
                                name=f"Predicción H7 · {fecha}",
                                line=dict(
                                    color=COLORES["teal"],
                                    width=2,
                                    dash="dash"
                                )
                            )
                        )

                    tiene_datos = True

    if not tiene_datos:
        return figura_vacia(
            "Genera una predicción o una optimización para visualizar datos"
        )

    fig.update_layout(
        xaxis_title="Hora del día",
        yaxis_title="Demanda prevista (pasajeros/hora)",
        hovermode="x unified"
    )

    fig.update_xaxes(
        tickmode="array",
        tickvals=HORAS_OPERACION
    )

    return estilo_figura(fig)



def grafica_headway(df):

    if df.empty:
        return figura_vacia(
            "Ejecuta una optimización para visualizar el headway"
        )

    fig = go.Figure()

    fig.add_trace(
        go.Scatter(
            x=df["hora"],
            y=df["headway_min"],
            mode="lines+markers",
            name="Headway recomendado",
            line=dict(
                color=COLORES["teal"],
                width=3
            )
        )
    )

    fig.update_layout(
        xaxis_title="Hora del día",
        yaxis_title="Intervalo recomendado (min)",
        hovermode="x unified"
    )

    fig.update_xaxes(
        tickmode="array",
        tickvals=HORAS_OPERACION
    )

    return estilo_figura(fig)


# --------------------------------------------------
# LAYOUT
# --------------------------------------------------

def layout(**_):
    from utils.rutas_config import config, ruta_id
    rid = ruta_id(_.get("ruta", 16))
    nombre_ruta = config(rid)["nombre"]
    try:
        r = dl.resumen_datos(rid)

        estado = (
            aviso(
                f"Datos cargados: {r['filas']:,} registros · "
                f"{r['nodos']} nodos · "
                f"{r['desde']} → {r['hasta']}",
                "ok"
            )
            if r["filas"]
            else aviso(
                "No hay datos históricos disponibles.",
                "warn"
            )
        )

    except dl.ErrorDatos:
        estado = aviso(
            "No fue posible leer la fuente de datos.",
            "crit"
        )

    return html.Div([

        encabezado(
            "Resumen operativo",
            f"Estado de la ruta {nombre_ruta}: demanda, frecuencia, "
            "flota y alertas"
        ),

        estado,

        html.Div(
            id="res-estado-modelos",
            style={"marginBottom": "15px"}
        ),

        dcc.Interval(
            id="res-interval",
            interval=60000,
            n_intervals=0
        ),

        # ----------------------------------------------
        # INDICADORES
        # ----------------------------------------------

        html.Div(
            className="grid grid-4",
            children=[

                kpi(
                    "Pasajeros esperados (próx. franja)",
                    id_valor="res-pasajeros",
                    nota="Demanda horaria del optimizador"
                ),

                kpi(
                    "Headway recomendado (min)",
                    id_valor="res-headway-kpi",
                    nota="Intervalo teórico entre ciclos"
                ),

                kpi(
                    "Vehículos equivalentes requeridos",
                    id_valor="res-vehiculos",
                    nota="ceil(frecuencia × ciclo / 60)"
                ),

                kpi(
                    "Alertas activas",
                    id_valor="res-alertas-kpi",
                    nota="Alertas de la última optimización"
                )
            ]
        ),

        # ----------------------------------------------
        # GRÁFICAS
        # ----------------------------------------------

        html.Div(
            className="grid grid-2",
            children=[

                tarjeta(
                    "Demanda y predicción por hora",
                    grafico(
                        "res-demanda",
                        figura_vacia(
                            "Esperando resultados del modelo"
                        )
                    )
                ),

                tarjeta(
                    "Headway recomendado por franja",
                    grafico(
                        "res-headway",
                        figura_vacia(
                            "Esperando resultados del optimizador"
                        )
                    )
                )
            ]
        ),

        # ----------------------------------------------
        # ALERTAS
        # ----------------------------------------------

        tarjeta(
            "Alertas recientes de la simulación",

            html.Div(
                id="res-alertas-recientes",
                className="alertas-recientes"
            )
        )

    ])


# --------------------------------------------------
# CALLBACK DEL RESUMEN
# --------------------------------------------------

@callback(
    Output("res-pasajeros", "children"),
    Output("res-headway-kpi", "children"),
    Output("res-vehiculos", "children"),
    Output("res-alertas-kpi", "children"),
    Output("res-demanda", "figure"),
    Output("res-headway", "figure"),
    Output("res-alertas-recientes", "children"),
    Output("res-estado-modelos", "children"),

    Input("opt-resultado-store", "data"),
    Input("pred-resultado-store", "data"),
    Input("res-interval", "n_intervals")
)
def actualizar_resumen(resultado_opt, resultado_pred, _):

    ahora = datetime.now(ZONA_HORARIA)

    df = obtener_registros_optimizacion(resultado_opt)

    # Gráficas
    fig_demanda = grafica_demanda(df, resultado_pred)
    fig_headway = grafica_headway(df)

    # Valores iniciales
    pasajeros = "—"
    headway = "—"
    vehiculos = "—"
    total_alertas = "—"

    alertas_visuales = html.Div(
        "Ejecuta una optimización para consultar alertas.",
        className="vacio"
    )

    mensajes = []

    # ----------------------------------------------
    # OPTIMIZACIÓN
    # ----------------------------------------------

    if not df.empty:

        fila = obtener_siguiente_franja(
            df,
            ahora.hour
        )

        if fila is not None:

            pasajeros = f"{fila['demanda']:,.0f}"

            frecuencia = int(fila["frecuencia"])

            if frecuencia > 0:

                intervalo = 60.0 / frecuencia

                headway = f"{intervalo:.2f}"

                tiempo_ciclo = fila["tiempo_ciclo_min"]

                if pd.notna(tiempo_ciclo) and tiempo_ciclo > 0:

                    import math

                    vehiculos = str(
                        math.ceil(
                            frecuencia * tiempo_ciclo / 60.0
                        )
                    )

            else:
                headway = "Sin ciclos"
                vehiculos = "0"

        alertas = construir_alertas_resumen(df)

        total_alertas = str(len(alertas))

        if alertas:

            alertas_visuales = html.Div([

                html.Div(
                    className="aviso aviso-warn",
                    style={"marginBottom": "8px"},
                    children=[
                        html.Strong(
                            f"{a['codigo']} · {a['alerta']}"
                        ),
                        html.P(
                            a["detalle"],
                            style={"margin": "5px 0 0"}
                        )
                    ]
                )

                for a in alertas[:5]

            ])

        else:
            alertas_visuales = aviso(
                "No se identificaron alertas en la optimización.",
                "ok"
            )

        mensajes.append(
            f"Optimización: {resultado_opt.get('fecha')} "
            f"({resultado_opt.get('modelo')})"
        )

    else:
        mensajes.append("Optimización: sin resultados")


    # ----------------------------------------------
    # PREDICCIÓN H7
    # ----------------------------------------------

    if isinstance(resultado_pred, dict) and resultado_pred.get(
        "predicciones"
    ):

        resumen_pred = resultado_pred.get("resumen", {})

        fechas = resumen_pred.get("fechas", 0)
        demanda_total = resumen_pred.get("demanda_total", 0)

        mensajes.append(
            f"Predicción H7: disponible "
            f"({fechas} días, "
            f"{demanda_total:,.0f} pasajeros previstos)"
        )

    else:
        mensajes.append(
            "Predicción H7: sin resultados"
        )


    estado_modelos = aviso(
        " | ".join(mensajes)
        + " | Visualización de datos históricos/simulados.",
        "info"
    )

    return (
        pasajeros,
        headway,
        vehiculos,
        total_alertas,
        fig_demanda,
        fig_headway,
        alertas_visuales,
        estado_modelos
    )
