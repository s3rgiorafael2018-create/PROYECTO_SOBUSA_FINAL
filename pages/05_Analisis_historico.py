"""Análisis histórico: consultas en vivo a DuckDB con filtros SEGUROS (validados + parametrizados)."""
from datetime import timedelta

import dash
import plotly.graph_objects as go
from dash import Input, Output, State, callback, dcc, html

from utils import data_loader as dl
from utils.ui import aviso, encabezado, estilo_figura, figura_vacia, grafico, tarjeta

dash.register_page(__name__, path="/historico", name="Análisis histórico", title="Histórico | SOBUSA",
                   order=5, icon="history")

DIAS = {1: "Lun", 2: "Mar", 3: "Mié", 4: "Jue", 5: "Vie", 6: "Sáb", 7: "Dom"}
GRAN_ETIQUETAS = {"dia": "Día", "semana": "Semana", "mes": "Mes"}


def layout(**_):
    from utils.rutas_config import ruta_id
    rid = ruta_id(_.get("ruta", 16))
    try:
        d0, d1 = dl.rango_fechas(rid)
        nodos = dl.nodos_disponibles(rid)
    except dl.ErrorDatos:
        return html.Div([encabezado("Análisis histórico"), aviso("No fue posible leer la fuente de datos.", "crit")])
    if d0 is None:
        return html.Div([encabezado("Análisis histórico"),
                         aviso("Sin datos: coloca panel_*.csv y servicio_*.csv en data/panel_horario/.", "warn")])

    return html.Div([
        encabezado("Análisis histórico", "Patrones de demanda por hora, día de la semana y periodo (pasajeros por viaje)"),
        tarjeta(None, html.Div(className="filtros", children=[
            html.Div([html.Label("Rango de fechas"),
                      dcc.DatePickerRange(id="hist-fechas", min_date_allowed=d0, max_date_allowed=d1,
                                          start_date=max(d0, d1 - timedelta(days=60)), end_date=d1,
                                          display_format="YYYY-MM-DD")]),
            html.Div([html.Label("Nodos (vacío = todos)", htmlFor="hist-nodos"),
                      dcc.Dropdown(id="hist-nodos", multi=True, placeholder="Todos los nodos",
                                   options=[{"label": f"Nodo {n}", "value": n} for n in nodos])]),
            html.Div([html.Label("Granularidad"),
                      dcc.RadioItems(id="hist-gran", value="dia", className="radio-pills",
                                     options=[{"label": v, "value": k} for k, v in GRAN_ETIQUETAS.items()])]),
        ])),
        html.Div(id="hist-msg"),
        html.Div(className="grid grid-2", children=[
            tarjeta("Perfil horario", grafico("hist-perfil", figura_vacia("Cargando…"))),
            tarjeta("Mapa de calor: hora × día", grafico("hist-calor", figura_vacia("Cargando…"))),
        ]),
        tarjeta("Serie temporal",
                html.Div(html.Button("Descargar CSV", id="hist-descargar", n_clicks=0, className="btn"), className="card-actions"),
                grafico("hist-serie", figura_vacia("Cargando…")), dcc.Download(id="hist-download")),
    ])


def _filtros_validados(ini, fin, nodos, gran, idruta=16):
    """Punto único de validación para todos los callbacks de esta página."""
    i, f = dl.validar_rango(ini, fin)
    n = dl.validar_enteros(nodos, permitidos=set(dl.nodos_disponibles(idruta)), nombre="nodos")
    g = dl.validar_opcion(gran, dl.GRANULARIDADES)
    return i, f, n, g


@callback(
    Output("hist-perfil", "figure"), Output("hist-calor", "figure"), Output("hist-serie", "figure"),
    Output("hist-msg", "children"),
    Input("hist-fechas", "start_date"), Input("hist-fechas", "end_date"),
    Input("hist-nodos", "value"), Input("hist-gran", "value"), Input("url", "search"),
)
def actualizar(ini, fin, nodos, gran, search):
    from urllib.parse import parse_qs
    from utils.rutas_config import ruta_id
    rid = ruta_id(parse_qs((search or "").lstrip("?")).get("ruta", [16])[0])
    vacio = figura_vacia("Sin datos para el filtro seleccionado")
    try:
        i, f, n, g = _filtros_validados(ini, fin, nodos, gran, rid)
        perfil = dl.perfil_horario(i, f, n, rid)
        calor = dl.mapa_calor(i, f, n, rid)
        serie = dl.serie_temporal(i, f, n, g, rid)
    except dl.EntradaInvalida as exc:
        return vacio, vacio, vacio, aviso(str(exc), "warn")
    except dl.ErrorDatos:
        return vacio, vacio, vacio, aviso("No fue posible consultar los datos.", "crit")
    if perfil.empty:
        return vacio, vacio, vacio, aviso("No hay registros en el rango y nodos elegidos.", "info")

    fig_perfil = go.Figure(go.Bar(x=perfil["hora"], y=perfil["pas_por_viaje"], name="Pasajeros por viaje"))
    fig_perfil.update_xaxes(title="Hora", dtick=2)
    fig_perfil.update_yaxes(title="Pasajeros por viaje")

    pivote = calor.pivot(index="dow", columns="hora", values="pas_por_viaje").reindex(index=list(DIAS))
    fig_calor = go.Figure(go.Heatmap(z=pivote.values, x=pivote.columns, y=[DIAS[d] for d in pivote.index],
                                     colorscale=[[0, "#EAF6F8"], [0.5, "#009FAE"], [1, "#003B52"]],
                                     colorbar=dict(title="Pas/viaje")))
    fig_calor.update_xaxes(title="Hora", dtick=2)

    fig_serie = go.Figure()
    fig_serie.add_trace(go.Scatter(x=serie["periodo"], y=serie["subidas"], mode="lines+markers", name="Subidas"))
    fig_serie.add_trace(go.Scatter(x=serie["periodo"], y=serie["bajadas"], mode="lines", name="Bajadas"))
    fig_serie.update_yaxes(title="Pasajeros")
    return estilo_figura(fig_perfil, 320), estilo_figura(fig_calor, 320), estilo_figura(fig_serie, 340), None


@callback(
    Output("hist-download", "data"), Input("hist-descargar", "n_clicks"),
    State("hist-fechas", "start_date"), State("hist-fechas", "end_date"),
    State("hist-nodos", "value"), State("hist-gran", "value"), State("url", "search"), prevent_initial_call=True,
)
def descargar(_, ini, fin, nodos, gran, search):
    from urllib.parse import parse_qs
    from utils.rutas_config import ruta_id
    rid = ruta_id(parse_qs((search or "").lstrip("?")).get("ruta", [16])[0])
    """RF-017: exportación CSV. Reutiliza exactamente la misma validación que la vista."""
    try:
        i, f, n, g = _filtros_validados(ini, fin, nodos, gran, rid)
        df = dl.serie_temporal(i, f, n, g, rid)
    except (dl.EntradaInvalida, dl.ErrorDatos):
        raise dash.exceptions.PreventUpdate
    return dcc.send_data_frame(df.to_csv, "serie_historica.csv", index=False)
