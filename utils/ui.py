"""Componentes de interfaz reutilizables (mantienen las páginas cortas y consistentes)."""
from __future__ import annotations

import plotly.graph_objects as go
from dash import dcc, html

# Colores corporativos de Extreme Technologies (muestreados del logo y del documento de especificación)
COLORES = {
    "navy": "#003B52", "navy_oscuro": "#002B3D",
    "lime": "#C5CE00", "teal": "#009FAE", "blue": "#2E75B6",
    "texto": "#0F2A36", "muted": "#5E7482", "borde": "#DCE4EA",
    "ok": "#2E9E5B", "warn": "#E0A100", "crit": "#D64545",
}
COLORWAY = [COLORES["teal"], COLORES["navy"], COLORES["lime"], COLORES["blue"], "#7A8F9B"]


def encabezado(titulo: str, subtitulo: str | None = None, *acciones) -> html.Div:
    return html.Div(className="page-header", children=[
        html.Div([html.H1(titulo), html.P(subtitulo, className="page-sub") if subtitulo else None]),
        html.Div(list(acciones), className="page-actions") if acciones else None,
    ])


def tarjeta(titulo: str | None, *hijos, clase: str = "") -> html.Section:
    return html.Section(className=f"card {clase}".strip(), children=[
        html.H3(titulo, className="card-title") if titulo else None, *hijos])


def kpi(titulo: str, valor: str = "—", nota: str | None = None, id_valor: str | None = None,
        pendiente: bool = False) -> html.Div:
    return html.Div(className="kpi" + (" kpi-pendiente" if pendiente else ""), children=[
        html.Span(titulo, className="kpi-titulo"),
        html.Span(valor, className="kpi-valor", id=id_valor) if id_valor else html.Span(valor, className="kpi-valor"),
        html.Span(nota, className="kpi-nota") if nota else None,
        html.Span("Pendiente de modelo", className="chip chip-pendiente") if pendiente else None,
    ])


def aviso(texto: str, tipo: str = "info") -> html.Div:
    """tipo: info | warn | crit | ok"""
    return html.Div(texto, className=f"aviso aviso-{tipo}", role="status")


def estilo_figura(fig: go.Figure, alto: int = 340) -> go.Figure:
    fig.update_layout(
        template="plotly_white", colorway=COLORWAY, height=alto, margin=dict(l=48, r=20, t=36, b=44),
        font=dict(family="Inter, Segoe UI, system-ui, sans-serif", color=COLORES["texto"], size=12),
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        legend=dict(orientation="h", y=1.12, x=0),
    )
    fig.update_xaxes(gridcolor="#EEF2F5", zeroline=False)
    fig.update_yaxes(gridcolor="#EEF2F5", zeroline=False)
    return fig


def figura_vacia(mensaje: str, alto: int = 340) -> go.Figure:
    fig = go.Figure()
    fig.add_annotation(text=mensaje, x=0.5, y=0.5, xref="paper", yref="paper", showarrow=False,
                       font=dict(size=14, color=COLORES["muted"]))
    fig.update_xaxes(visible=False)
    fig.update_yaxes(visible=False)
    return estilo_figura(fig, alto)


def grafico(id_: str, figura: go.Figure) -> dcc.Graph:
    return dcc.Graph(id=id_, figure=figura, config={"displaylogo": False, "displayModeBar": False},
                     className="grafico")
