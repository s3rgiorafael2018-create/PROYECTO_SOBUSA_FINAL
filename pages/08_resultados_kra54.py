
"""Resultados operativos por ruta con pronósticos H7."""

import json
from pathlib import Path

import dash
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

from dash import dash_table, dcc, html

from utils.ui import (
    COLORES,
    aviso,
    encabezado,
    estilo_figura,
    figura_vacia,
    grafico,
    kpi,
    tarjeta
)

from utils.resultados_store import cargar_resultado


dash.register_page(
    __name__,
    path="/resultados-kra54",
    name="Resultados por ruta",
    title="Resultados | SOBUSA",
    order=8,
    icon="bar-chart-3"
)


BASE_DIR = Path(__file__).resolve().parents[1]

PRONOSTICO_PATH = (
    BASE_DIR / "data" / "pronostico_demanda_ruta.json"
)


# --------------------------------------------------
# CARGA DE PRONÓSTICOS
# --------------------------------------------------

def cargar_pronosticos(idruta=16):
    from utils.rutas_config import config
    pronostico_path = config(idruta)["pronostico"]

    if not pronostico_path.exists():
        return pd.DataFrame()

    with pronostico_path.open(
        "r", encoding="utf-8"
    ) as archivo:
        datos = json.load(archivo)

    fechas = (
        datos.get("modelos", {})
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
        return pd.DataFrame()

    df = pd.DataFrame(registros)

    return df.sort_values(
        ["dia", "hora"]
    ).reset_index(drop=True)


# --------------------------------------------------
# GRÁFICAS
# --------------------------------------------------

def grafica_evolucion(df):

    if df.empty:
        return figura_vacia(
            "No hay pronósticos H7 disponibles"
        )

    datos = df.copy()

    datos["timestamp"] = (
        pd.to_datetime(datos["dia"])
        + pd.to_timedelta(datos["hora"], unit="h")
    )

    fig = px.line(
        datos,
        x="timestamp",
        y="demanda",
        markers=True,
        title="Evolución de la demanda prevista"
    )

    fig.update_traces(
        line_color=COLORES["navy"]
    )

    fig.update_layout(
        xaxis_title="Fecha y hora",
        yaxis_title="Pasajeros/hora",
        hovermode="x unified"
    )

    return estilo_figura(fig)


def grafica_demanda_diaria(df):

    if df.empty:
        return figura_vacia(
            "No hay demanda diaria disponible"
        )

    diario = (
        df.groupby("dia", as_index=False)["demanda"]
        .sum()
    )

    fig = px.bar(
        diario,
        x="dia",
        y="demanda",
        text_auto=".0f",
        title="Demanda total prevista por día"
    )

    fig.update_traces(
        marker_color=COLORES["teal"]
    )

    fig.update_layout(
        xaxis_title="Fecha",
        yaxis_title="Pasajeros previstos",
        showlegend=False
    )

    return estilo_figura(fig)


def grafica_perfil_horario(df):

    if df.empty:
        return figura_vacia(
            "No hay datos horarios disponibles"
        )

    perfil = (
        df.groupby("hora", as_index=False)["demanda"]
        .mean()
    )

    fig = px.bar(
        perfil,
        x="hora",
        y="demanda",
        title="Demanda horaria media del horizonte"
    )

    fig.update_traces(
        marker_color=COLORES["navy"]
    )

    fig.update_layout(
        xaxis_title="Hora del día",
        yaxis_title="Pasajeros/hora",
        showlegend=False
    )

    return estilo_figura(fig)


def grafica_optimizacion(resultado):

    if not isinstance(resultado, dict):
        return figura_vacia(
            "Ejecuta una optimización para ver resultados"
        )

    registros = resultado.get("resultados", [])

    if not registros:
        return figura_vacia(
            "No hay resultados de optimización"
        )

    df = pd.DataFrame(registros)

    fig = go.Figure()

    fig.add_trace(
        go.Bar(
            x=df["hora"],
            y=df["frecuencia"],
            name="Frecuencia",
            marker_color=COLORES["navy"]
        )
    )

    fig.update_layout(
        title=(
            "Frecuencias propuestas · "
            f"{resultado.get('fecha', '—')}"
        ),
        xaxis_title="Hora del día",
        yaxis_title="Ciclos por hora",
        showlegend=False
    )

    return estilo_figura(fig)


# --------------------------------------------------
# LAYOUT
# --------------------------------------------------

def layout(**_):
    from utils.rutas_config import config, ruta_id
    idruta = ruta_id(_.get("ruta", 16))
    nombre_ruta = config(idruta)["nombre"]
    try:
        df = cargar_pronosticos(idruta)

    except (OSError, ValueError, TypeError) as error:
        return html.Div([
            encabezado(f"Resultados {nombre_ruta}"),
            aviso(
                f"No fue posible cargar los pronósticos: {error}",
                "crit"
            )
        ])

    if df.empty:
        return html.Div([
            encabezado(f"Resultados {nombre_ruta}"),
            aviso(
                "No se encontraron pronósticos H7.",
                "warn"
            )
        ])

    try:
        resultado_opt = cargar_resultado("optimizacion", idruta)
    except (OSError, ValueError, TypeError):
        resultado_opt = None

    # ----------------------------------------------
    # INDICADORES DE PRONÓSTICO
    # ----------------------------------------------

    total = df["demanda"].sum()
    promedio = df["demanda"].mean()
    maximo = df.loc[df["demanda"].idxmax()]

    n_dias = df["dia"].nunique()

    diario = (
        df.groupby("dia", as_index=False)["demanda"]
        .sum()
    )

    diario["demanda"] = diario["demanda"].round(2)

    diario = diario.rename(
        columns={"demanda": "total_previsto"}
    )

    # ----------------------------------------------
    # INDICADORES DE OPTIMIZACIÓN
    # ----------------------------------------------

    resumen_opt = (
        resultado_opt.get("resumen", {})
        if isinstance(resultado_opt, dict)
        else {}
    )

    # ----------------------------------------------
    # CONTENIDO
    # ----------------------------------------------

    contenido = [

        encabezado(
            f"Resultados operativos · {nombre_ruta}",
            "Pronóstico de demanda H7 y resultados "
            "de la simulación de frecuencias"
        ),

        html.Div(
            className="grid grid-4",
            children=[
                kpi(
                    "Demanda total prevista",
                    f"{total:,.0f}",
                    "Pasajeros en el horizonte"
                ),
                kpi(
                    "Promedio horario",
                    f"{promedio:,.1f}",
                    "Pasajeros/hora"
                ),
                kpi(
                    "Pico de demanda",
                    f"{maximo['demanda']:,.0f}",
                    (
                        f"{maximo['dia']} · "
                        f"{int(maximo['hora']):02d}:00"
                    )
                ),
                kpi(
                    "Días pronosticados",
                    str(n_dias),
                    "Modelo H7"
                )
            ]
        ),

        html.Div(
            className="grid grid-2",
            children=[
                tarjeta(
                    "Evolución del pronóstico",
                    grafico(
                        "res-evolucion",
                        grafica_evolucion(df)
                    )
                ),
                tarjeta(
                    "Demanda por día",
                    grafico(
                        "res-diaria",
                        grafica_demanda_diaria(df)
                    )
                ),
                tarjeta(
                    "Perfil horario",
                    grafico(
                        "res-perfil",
                        grafica_perfil_horario(df)
                    )
                ),
                tarjeta(
                    "Frecuencias de optimización",
                    grafico(
                        "res-frecuencias",
                        grafica_optimizacion(resultado_opt)
                    )
                )
            ]
        ),

        tarjeta(
            "Demanda total prevista por fecha",

            dash_table.DataTable(
                id="res-tabla-diaria",

                columns=[
                    {
                        "name": "Fecha",
                        "id": "dia"
                    },
                    {
                        "name": "Pasajeros previstos",
                        "id": "total_previsto"
                    }
                ],

                data=diario.to_dict("records"),

                sort_action="native",

                style_header={
                    "backgroundColor": COLORES["navy"],
                    "color": "white",
                    "fontWeight": "600",
                    "border": "none"
                },

                style_cell={
                    "padding": "10px",
                    "border": "none",
                    "borderBottom": (
                        f"1px solid {COLORES['borde']}"
                    ),
                    "fontFamily": "inherit",
                    "fontSize": "13px"
                }
            )
        )
    ]

    # ----------------------------------------------
    # RESULTADOS DEL OPTIMIZADOR
    # ----------------------------------------------

    if resumen_opt:

        contenido.extend([

            encabezado(
                "Resultados de optimización",
                (
                    "Simulación correspondiente al "
                    f"{resultado_opt.get('fecha', '—')}"
                )
            ),

            html.Div(
                className="grid grid-4",
                children=[
                    kpi(
                        "Ciclos programados",
                        str(
                            resumen_opt.get(
                                "ciclos_totales", "—"
                            )
                        )
                    ),
                    kpi(
                        "Espera promedio",
                        (
                            f"{resumen_opt.get('espera_promedio_min', 0):.2f}"
                        ),
                        "Minutos"
                    ),
                    kpi(
                        "No atendidos",
                        (
                            f"{resumen_opt.get('no_atendidos_total', 0):,.0f}"
                        ),
                        "Pasajeros estimados"
                    ),
                    kpi(
                        "Buses equivalentes",
                        (
                            f"{resumen_opt.get('buses_equivalentes_promedio', 0):.2f}"
                        ),
                        "Promedio estimado"
                    )
                ]
            )
        ])

    else:

        contenido.append(
            aviso(
                "No existe una optimización guardada. "
                "Los resultados de demanda H7 siguen disponibles.",
                "info"
            )
        )

    contenido.append(
        tarjeta(
            "Alcance de los resultados",

            html.P(
                "Las predicciones corresponden a la demanda "
                "esperada bajo el servicio histórico de la ruta, "
                "agregada en ambos sentidos."
            ),

            html.P(
                "Los indicadores de optimización son resultados "
                "de una simulación MILP y no representan "
                "despachos ni ocupaciones observadas en tiempo real."
            )
        )
    )

    return html.Div(contenido)
