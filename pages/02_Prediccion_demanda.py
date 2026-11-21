
"""Predicción de demanda por ruta y horizonte de hasta 7 días."""

import dash
import pandas as pd
import plotly.express as px

from dash import (
    Input,
    Output,
    State,
    callback,
    dash_table,
    dcc,
    html
)

from dash.exceptions import PreventUpdate

from utils.api_client import SobusaAPIClient
from utils.ui import COLORES, encabezado, figura_vacia, grafico, tarjeta
from utils.resultados_store import guardar_resultado


dash.register_page(
    __name__,
    path="/prediccion",
    name="Predicción de demanda",
    title="Predicción | SOBUSA",
    order=2,
    icon="trend"
)


# --------------------------------------------------
# CONFIGURACIÓN
# --------------------------------------------------

from utils.rutas_config import RUTAS as CONFIG_RUTAS
RUTAS = {rid: cfg["nombre"] for rid, cfg in CONFIG_RUTAS.items()}

HORIZONTES = {
    1: "1 día",
    2: "2 días",
    3: "3 días",
    4: "4 días",
    5: "5 días",
    6: "6 días",
    7: "7 días"
}

FECHA_MINIMA = "2025-08-31"
FECHA_MAXIMA = "2025-09-06"

COLUMNAS = [
    {"name": "Fecha", "id": "dia"},
    {"name": "Hora", "id": "hora"},
    {
        "name": "Demanda prevista (pasajeros/hora)",
        "id": "demanda_predicha"
    }
]


# Cliente para comunicarse con FastAPI
api_client = SobusaAPIClient()


# --------------------------------------------------
# LAYOUT
# --------------------------------------------------

def layout(**_):
    from utils.rutas_config import ruta_id
    idruta = ruta_id(_.get("ruta", 16))

    return html.Div([

        encabezado(
            "Predicción de demanda",
            f"Pronóstico H7 de pasajeros por hora para {RUTAS[idruta]}"
        ),

        # Filtros
        tarjeta(
            "Parámetros de predicción",

            html.Div(className="filtros", children=[

                html.Div([
                    html.Label("Ruta", htmlFor="pred-ruta"),

                    dcc.Dropdown(
                        id="pred-ruta",
                        options=[
                            {"label": v, "value": k}
                            for k, v in RUTAS.items()
                        ],
                        value=idruta,
                        clearable=False
                    )
                ]),

                html.Div([
                    html.Label("Fecha de inicio", htmlFor="pred-fecha"),

                    dcc.DatePickerSingle(
                        id="pred-fecha",
                        date=FECHA_MINIMA,
                        min_date_allowed=FECHA_MINIMA,
                        max_date_allowed=FECHA_MAXIMA,
                        display_format="DD/MM/YYYY",
                        placeholder="Seleccionar fecha"
                    )
                ]),

                html.Div([
                    html.Label("Horizonte de predicción", htmlFor="pred-horizonte"),

                    dcc.Dropdown(
                        id="pred-horizonte",
                        options=[
                            {"label": v, "value": k}
                            for k, v in HORIZONTES.items()
                        ],
                        value=7,
                        clearable=False
                    )
                ]),

                html.Div([
                    html.Label(" "),
                    html.Button(
                        "Generar predicciones",
                        id="pred-generar",
                        n_clicks=0,
                        className="boton-principal"
                    )
                ])

            ])
        ),

        # Estado de la solicitud
        html.Div(
            id="pred-estado",
            style={"marginTop": "15px"}
        ),

        tarjeta(
            f"Demanda horaria prevista · {RUTAS[idruta]}",

            dcc.Loading(
                grafico(
                    "pred-grafico",
                    figura_vacia(
                        "Selecciona los parámetros y genera las predicciones"
                    )
                )
            )
        ),

        # Tabla
        tarjeta(
            "Detalle de predicciones",

            dash_table.DataTable(
                id="pred-tabla",
                columns=COLUMNAS,
                data=[],
                page_size=15,
                sort_action="native",
                filter_action="native",

                style_header={
                    "backgroundColor": COLORES["navy"],
                    "color": "white",
                    "fontWeight": "600",
                    "border": "none"
                },

                style_cell={
                    "padding": "10px",
                    "border": "none",
                    "borderBottom": f"1px solid {COLORES['borde']}",
                    "fontFamily": "inherit",
                    "fontSize": "13px",
                    "textAlign": "center"
                }
            )
        )

    ])


# --------------------------------------------------
# CALLBACK: GENERAR PREDICCIONES
# --------------------------------------------------


@callback(
    Output("pred-grafico", "figure"),
    Output("pred-tabla", "data"),
    Output("pred-estado", "children"),
    Output("pred-resultado-store", "data"),

    Input("pred-generar", "n_clicks"),

    State("pred-ruta", "value"),
    State("pred-fecha", "date"),
    State("pred-horizonte", "value"),

    prevent_initial_call=True
)
def actualizar(n_clicks, ruta, fecha, horizonte):

    if not n_clicks:
        raise PreventUpdate

    if ruta not in RUTAS:
        return (
            figura_vacia("Ruta no válida"),
            [],
            html.Div("La ruta seleccionada no es válida."),
            dash.no_update
        )

    if horizonte not in HORIZONTES:
        return (
            figura_vacia("Horizonte no válido"),
            [],
            html.Div("El horizonte debe estar entre 1 y 7 días."),
            dash.no_update
        )

    if not fecha:
        return (
            figura_vacia("Fecha no seleccionada"),
            [],
            html.Div("Debes seleccionar una fecha."),
            dash.no_update
        )

    from datetime import date, timedelta

    fecha_inicio = date.fromisoformat(fecha)
    fecha_final = fecha_inicio + timedelta(days=horizonte - 1)

    if (
        fecha_inicio < date.fromisoformat(FECHA_MINIMA)
        or fecha_final > date.fromisoformat(FECHA_MAXIMA)
    ):
        return (
            figura_vacia("Fechas fuera del pronóstico disponible"),
            [],
            html.Div(
                "El periodo solicitado debe estar comprendido "
                f"entre {FECHA_MINIMA} y {FECHA_MAXIMA}."
            ),
            dash.no_update
        )

    try:

        resultado = api_client.run_predictions(
            fecha_inicio=fecha,
            horizonte_dias=horizonte,
            idruta=ruta
        )

        resumen = resultado["resumen"]
        df = pd.DataFrame(resultado["predicciones"])

        if df.empty:
            return (
                figura_vacia("No hay predicciones disponibles"),
                [],
                html.Div("La API no devolvió resultados."),
                dash.no_update
            )

        df["timestamp"] = (
            pd.to_datetime(df["dia"])
            + pd.to_timedelta(df["hora"], unit="h")
        )

        df = df.sort_values("timestamp")

        fig = px.line(
            df,
            x="timestamp",
            y="demanda_predicha",
            markers=True,
            title="Demanda total prevista por hora · H7"
        )

        fig.update_layout(
            xaxis_title="Fecha y hora",
            yaxis_title="Pasajeros por hora",
            hovermode="x unified",
            template="plotly_white"
        )

        fig.update_xaxes(
            tickformat="%d/%m %H:%M"
        )

        tabla = df[
            ["dia", "hora", "demanda_predicha"]
        ].copy()

        tabla["demanda_predicha"] = (
            tabla["demanda_predicha"].round(2)
        )

        estado = html.Div([

            html.P(
                "Pronóstico H7 recuperado correctamente: "
                f"{resumen['total_predicciones']} registros."
            ),

            html.P(
                f"Fechas: {resumen['fechas']} | "
                f"Demanda total: {resumen['demanda_total']:,.2f} "
                "pasajeros"
            ),

            html.P(
                f"Promedio horario: "
                f"{resumen['promedio_horario']:,.2f} | "
                f"Máximo horario: "
                f"{resumen['maximo_horario']:,.2f}"
            )
        ])

        try:
            guardar_resultado("prediccion", resultado, ruta)
        except (OSError, ValueError) as error:
            print(
                "Advertencia: no se pudo guardar "
                f"la predicción: {error}"
            )

        return (
            fig,
            tabla.to_dict("records"),
            estado,
            resultado
        )

    except Exception as error:

        return (
            figura_vacia("Error al consultar predicciones"),
            [],
            html.Div(
                f"No fue posible completar la solicitud: {error}"
            ),
            dash.no_update
        )


# Sincroniza el selector previo de la página con las pestañas globales.
@callback(Output("url", "search"), Input("pred-ruta", "value"),
          State("url", "search"), prevent_initial_call=True)
def sincronizar_selector_prediccion(ruta, search):
    from urllib.parse import parse_qs
    from utils.rutas_config import ruta_id
    actual = ruta_id(parse_qs((search or "").lstrip("?")).get("ruta", [16])[0])
    if ruta == actual:
        raise PreventUpdate
    return f"?ruta={ruta_id(ruta)}"
