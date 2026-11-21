"""Optimización de frecuencias mediante FastAPI y MILP."""

import dash
import pandas as pd
import plotly.graph_objects as go

from plotly.subplots import make_subplots

from dash import (
    Input,
    Output,
    State,
    callback,
    dash_table,
    dcc,
    html,
    no_update
)

from dash.exceptions import PreventUpdate

from utils.api_client import SobusaAPIClient
from utils.resultados_store import guardar_resultado

from utils.ui import (
    COLORES,
    aviso,
    encabezado,
    figura_vacia,
    grafico,
    kpi,
    tarjeta
)


dash.register_page(
    __name__,
    path="/optimizacion",
    name="Optimización",
    title="Optimización | SOBUSA",
    order=3,
    icon="sliders"
)


# --------------------------------------------------
# CONFIGURACIÓN
# --------------------------------------------------

FECHA_MINIMA = "2025-08-31"
FECHA_MAXIMA = "2025-09-06"

api_client = SobusaAPIClient()


COLUMNAS = [

    {"name": "Hora", "id": "hora"},

    {"name": "Demanda (pasajeros)", "id": "demanda"},

    {"name": "Ciclos optimizados", "id": "frecuencia"},

    {"name": "Headway (min)", "id": "headway_min"},

    {"name": "No atendidos", "id": "no_atendidos"},

    {"name": "Espera (min)", "id": "espera_min"},

    {"name": "Ciclo (min)", "id": "tiempo_ciclo_min"}

]


# --------------------------------------------------
# COMPONENTES AUXILIARES
# --------------------------------------------------

def campo_numero(
    etiqueta,
    id_,
    valor,
    minimo,
    maximo,
    paso=1
):

    return html.Div([

        html.Label(
            etiqueta,
            htmlFor=id_
        ),

        dcc.Input(
            id=id_,
            type="number",
            value=valor,
            min=minimo,
            max=maximo,
            step=paso,
            debounce=True
        )

    ])


# --------------------------------------------------
# LAYOUT
# --------------------------------------------------

def layout(**_):
    from utils.rutas_config import ruta_id, modelos_pronostico
    idruta = ruta_id(_.get("ruta", 16))

    return html.Div([

        encabezado(
            "Optimización de frecuencias",
            "Asignación de ciclos completos mediante programación "
            "lineal entera mixta (MILP)"
        ),

        # ------------------------------------------
        # PARÁMETROS
        # ------------------------------------------

        tarjeta(
            "Parámetros de optimización",

            html.Div(className="filtros", children=[

                # Modelo
                html.Div([

                    html.Label(
                        "Modelo de demanda",
                        htmlFor="opt-modelo"
                    ),

                    dcc.Dropdown(
                        id="opt-modelo",

                        options=[
                            {"label": f"{m} - {'7 días' if m == 'H7' else '1 día'}", "value": m}
                            for m in modelos_pronostico(idruta)
                        ],

                        value="H7",
                        clearable=False

                    )

                ]),

                # Fecha
                html.Div([

                    html.Label(
                        "Fecha de optimización",
                        htmlFor="opt-fecha"
                    ),

                    dcc.DatePickerSingle(
                        id="opt-fecha",

                        date="2025-09-01",

                        min_date_allowed=FECHA_MINIMA,

                        max_date_allowed=FECHA_MAXIMA,

                        display_format="DD/MM/YYYY",

                        placeholder="Seleccionar fecha"

                    )

                ]),

                # Capacidad nominal
                campo_numero(
                    "Capacidad nominal del bus",
                    "opt-capacidad",
                    50,
                    1,
                    200
                ),

                # Presupuesto
                campo_numero(
                    "Presupuesto de ciclos",
                    "opt-presupuesto",
                    338,
                    1,
                    1000
                ),

                # Flota
                campo_numero(
                    "Flota disponible",
                    "opt-flota",
                    94,
                    1,
                    500
                ),

                # Delta
                campo_numero(
                    "Cambio máximo entre horas (DELTA)",
                    "opt-delta",
                    6,
                    0,
                    30
                ),

                # Peso de suavidad
                campo_numero(
                    "Peso de cambio de frecuencia",
                    "opt-peso-cambio",
                    1.0,
                    0,
                    100,
                    0.1
                ),

                # Ocupación
                html.Div([

                    html.Label(
                        "Ocupación objetivo (%)",
                        htmlFor="opt-ocupacion"
                    ),

                    dcc.Slider(
                        id="opt-ocupacion",

                        min=65,
                        max=100,
                        step=1,
                        value=75,

                        marks={
                            65: "65%",
                            75: "75%",
                            85: "85%",
                            100: "100%"
                        },

                        tooltip={
                            "placement": "bottom",
                            "always_visible": True
                        }

                    )

                ])

            ]),

            html.Div(

                "Factor de carga: 1.0 (supuesto, no medición "
                "de ocupación por segmento). Cada frecuencia "
                "representa un ciclo completo de ida y vuelta.",

                style={
                    "marginTop": "15px",
                    "fontSize": "13px",
                    "color": COLORES["texto_secundario"]
                    if "texto_secundario" in COLORES
                    else "#64748B"
                }

            ),

            html.Div([

                html.Button(
                    "Optimizar frecuencias",
                    id="opt-generar",
                    n_clicks=0,
                    className="boton-principal"
                )

            ], style={"marginTop": "20px"})

        ),

        # ------------------------------------------
        # ESTADO
        # ------------------------------------------

        html.Div(
            id="opt-estado",
            style={"marginTop": "15px"}
        ),

        # ------------------------------------------
        # INDICADORES
        # ------------------------------------------

        html.Div(

            className="grid grid-4",

            children=[

                kpi(
                    "Ciclos optimizados",
                    id_valor="opt-ciclos"
                ),

                kpi(
                    "Espera promedio",
                    id_valor="opt-espera"
                ),

                kpi(
                    "Pasajeros no atendidos",
                    id_valor="opt-no-atendidos"
                ),

                kpi(
                    "Buses equivalentes promedio",
                    id_valor="opt-buses"
                )

            ]

        ),

        # ------------------------------------------
        # GRÁFICO
        # ------------------------------------------

        tarjeta(

            "Demanda pronosticada y frecuencia optimizada",

            dcc.Loading(

                grafico(
                    "opt-grafico",
                    figura_vacia(
                        "Selecciona los parámetros y ejecuta "
                        "la optimización."
                    )
                )

            )

        ),

        # ------------------------------------------
        # TABLA
        # ------------------------------------------

        tarjeta(

            "Detalle de frecuencias por hora",

            dash_table.DataTable(

                id="opt-tabla",

                columns=COLUMNAS,

                data=[],

                page_size=19,

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

                    "fontSize": "13px",

                    "textAlign": "center"

                }

            )

        )

    ])


# --------------------------------------------------
# CALLBACK: OPTIMIZAR FRECUENCIAS
# --------------------------------------------------

@callback(

    Output("opt-estado", "children"),

    Output("opt-ciclos", "children"),

    Output("opt-espera", "children"),

    Output("opt-no-atendidos", "children"),

    Output("opt-buses", "children"),

    Output("opt-grafico", "figure"),

    Output("opt-tabla", "data"),
    
    Output("opt-resultado-store", "data"),

    Input("opt-generar", "n_clicks"),

    State("url", "search"),

    State("opt-modelo", "value"),

    State("opt-fecha", "date"),

    State("opt-capacidad", "value"),

    State("opt-ocupacion", "value"),

    State("opt-presupuesto", "value"),

    State("opt-flota", "value"),

    State("opt-delta", "value"),

    State("opt-peso-cambio", "value"),

    prevent_initial_call=True

)
def optimizar(

    n_clicks,

    ruta_search,

    modelo,

    fecha,

    capacidad,

    ocupacion,

    presupuesto,

    flota,

    delta,

    peso_cambio

):

    if not n_clicks:
        raise PreventUpdate

    from urllib.parse import parse_qs
    from utils.rutas_config import ruta_id
    idruta = ruta_id(parse_qs((ruta_search or "").lstrip("?")).get("ruta", [16])[0])

    # ------------------------------------------
    # 1. VALIDACIÓN DE PARÁMETROS
    # ------------------------------------------

    if None in (
        fecha,
        capacidad,
        ocupacion,
        presupuesto,
        flota,
        delta,
        peso_cambio
    ):

        return (

            aviso(
                "Completa todos los parámetros de optimización.",
                "warn"
            ),

            "—",
            "—",
            "—",
            "—",

            figura_vacia("Parámetros incompletos"),

            [],
            no_update

        )

    if modelo not in ("H7", "H1"):

        return (

            aviso("Modelo de demanda no válido.", "crit"),

            "—", "—", "—", "—",

            figura_vacia("Modelo no válido"),

            [],
            no_update

        )

    if capacidad <= 0 or flota <= 0 or presupuesto <= 0:

        return (

            aviso(
                "La capacidad, la flota y el presupuesto "
                "de ciclos deben ser mayores que cero.",
                "warn"
            ),

            "—", "—", "—", "—",

            figura_vacia("Parámetros no válidos"),

            [],
            
            no_update

        )

    # ------------------------------------------
    # 2. SOLICITUD A FASTAPI
    # ------------------------------------------

    try:

        resultado = api_client.run_optimization(

            fecha=fecha,

            modelo=modelo,

            capacidad_bus=float(capacidad),

            ocupacion_objetivo=float(ocupacion) / 100.0,

            presupuesto_ciclos=int(presupuesto),

            flota_disponible=int(flota),

            delta=int(delta),

            peso_cambio_frecuencia=float(peso_cambio),
            idruta=idruta

        )

        # --------------------------------------
        # 3. RECUPERAR RESULTADOS
        # --------------------------------------

        resumen = resultado["resumen"]

        df = pd.DataFrame(
            resultado["resultados"]
        )

        if df.empty:

            return (

                aviso(
                    "El optimizador no devolvió resultados.",
                    "warn"
                ),

                "—", "—", "—", "—",

                figura_vacia("Sin resultados"),

                [],
                no_update

            )

        # --------------------------------------
        # 4. CONSTRUIR GRÁFICO
        # --------------------------------------

        fig = make_subplots(
            specs=[[{"secondary_y": True}]]
        )

        fig.add_trace(

            go.Bar(

                x=df["hora"],

                y=df["demanda"],

                name="Demanda pronosticada",

                marker={
                    "color": "#4472C4"
                }

            ),

            secondary_y=False

        )

        fig.add_trace(

            go.Scatter(

                x=df["hora"],

                y=df["frecuencia"],

                name="Ciclos optimizados",

                mode="lines+markers",

                line={
                    "color": "#E67E22",
                    "width": 3
                }

            ),

            secondary_y=True

        )

        fig.update_layout(

            template="plotly_white",

            hovermode="x unified",

            legend_title="Variables",

            margin={
                "l": 40,
                "r": 40,
                "t": 30,
                "b": 40
            }

        )

        fig.update_xaxes(
            title_text="Hora del día",
            tickmode="linear",
            dtick=1
        )

        fig.update_yaxes(
            title_text="Pasajeros por hora",
            secondary_y=False
        )

        fig.update_yaxes(
            title_text="Ciclos completos por hora",
            secondary_y=True
        )

        # --------------------------------------
        # 5. PREPARAR TABLA
        # --------------------------------------

        df["demanda"] = df["demanda"].round(1)

        df["no_atendidos"] = (
            df["no_atendidos"].round(1)
        )

        df["espera_min"] = (
            df["espera_min"].round(2)
        )

        df["tiempo_ciclo_min"] = (
            df["tiempo_ciclo_min"].round(1)
        )

        tabla = df[
            [
                "hora",
                "demanda",
                "frecuencia",
                "headway_min",
                "no_atendidos",
                "espera_min",
                "tiempo_ciclo_min"
            ]
        ].to_dict("records")

        # --------------------------------------
        # 6. RESUMEN Y ADVERTENCIAS
        # --------------------------------------

        advertencias = resultado.get(
            "advertencias",
            []
        )

        estado = html.Div([

            aviso(
                "Optimización completada correctamente.",
                "ok"
            ),

            html.P(
                f"Modelo: {modelo} | Fecha: {fecha} | "
                f"Demanda total: "
                f"{resumen['demanda_total']:,.1f} pasajeros."
            ),

            html.Ul([
                html.Li(texto)
                for texto in advertencias
            ])

        ])
        # Guardar la última optimización exitosa
        try:
            guardar_resultado(
                "optimizacion",
                resultado,
                idruta
            )
        except (OSError, ValueError) as error:
            print(
                f"Advertencia: no se pudo guardar la optimización: {error}"
            )

        return (

            estado,

            str(resumen["ciclos_totales"]),

            f"{resumen['espera_promedio_min']:.2f} min",

            f"{resumen['no_atendidos_total']:,.1f}",

            f"{resumen['buses_equivalentes_promedio']:.1f}",

            fig,

            tabla,
            
            resultado

        )

    except Exception as error:

        return (

            aviso(
                f"No fue posible completar la optimización: {error}",
                "crit"
            ),

            "—", "—", "—", "—",

            figura_vacia("Error en la optimización"),

            [],
            no_update

        )