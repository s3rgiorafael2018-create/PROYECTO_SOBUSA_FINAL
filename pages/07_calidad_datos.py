
"""Calidad de datos del panel horario SOBUSA."""

from datetime import date

import dash
from dash import html

from utils import data_loader as dl
from utils.ui import aviso, encabezado, kpi, tarjeta


dash.register_page(
    __name__,
    path="/calidad",
    name="Calidad de datos",
    title="Calidad | SOBUSA",
    order=7,
    icon="shield"
)


def _badge(estado):

    textos = {
        "ok": "Correcto",
        "warn": "Revisar",
        "info": "Informativo",
        "pend": "Pendiente"
    }

    return html.Span(
        textos[estado],
        className=f"badge badge-{estado}"
    )


def layout(**_):
    from utils.rutas_config import ruta_id
    rid = ruta_id(_.get("ruta", 16))
    try:
        c = dl.calidad_panel(rid)

    except (dl.ErrorDatos, OSError, ValueError) as error:
        return html.Div([
            encabezado("Calidad de datos"),
            aviso(
                f"No fue posible evaluar el panel: {error}",
                "crit"
            )
        ])

    if c["filas"] == 0:
        return html.Div([
            encabezado("Calidad de datos"),
            aviso(
                "No se encontraron registros en el panel horario.",
                "warn"
            )
        ])

    ratio = c["ratio_bajadas_subidas"]

    fecha_max = c["fecha_max"]
    dias = (date.today() - fecha_max).days

    controles = [
        (
            "Completitud",
            "Campos obligatorios no nulos",
            f"{c['nulos']:,} filas con nulos",
            "ok" if c["nulos"] == 0 else "warn"
        ),
        (
            "Validez",
            "Conteos ≥ 0, viajes > 0 y hora válida",
            f"{c['invalidos']:,} filas inválidas",
            "ok" if c["invalidos"] == 0 else "warn"
        ),
        (
            "Unicidad",
            "Combinación nodo-día-hora no duplicada",
            f"{c['duplicados']:,} duplicados",
            "ok" if c["duplicados"] == 0 else "warn"
        ),
        (
            "Consistencia",
            "Relación bajadas/subidas cercana a 1",
            (
                "No disponible"
                if ratio is None
                else f"Relación: {ratio:.3f}"
            ),
            (
                "info" if ratio is None
                else "ok" if 0.95 <= ratio <= 1.05
                else "warn"
            )
        ),
        (
            "Actualidad",
            "Fecha más reciente del panel",
            f"{fecha_max} · hace {dias} días",
            "info"
        ),
        (
            "Integridad relacional",
            "Referencias entre tablas y catálogos",
            "Validación no ejecutada",
            "pend"
        )
    ]

    filas = [
        html.Tr([
            html.Td(dimension, className="td-fuerte"),
            html.Td(validacion),
            html.Td(resultado),
            html.Td(_badge(estado))
        ])
        for dimension, validacion, resultado, estado
        in controles
    ]

    return html.Div([

        encabezado(
            "Calidad de datos",
            "Validaciones sobre el panel horario "
            "utilizado como fuente histórica"
        ),

        html.Div(
            className="grid grid-4",
            children=[
                kpi("Registros", f"{c['filas']:,}"),
                kpi(
                    "Periodo",
                    f"{c['fecha_min']} → {fecha_max}"
                ),
                kpi(
                    "Filas con nulos",
                    f"{c['nulos']:,}"
                ),
                kpi(
                    "Duplicados",
                    f"{c['duplicados']:,}"
                )
            ]
        ),

        tarjeta(
            "Controles de calidad del panel",

            html.Div(
                className="tabla-scroll",
                children=html.Table(
                    className="tabla",
                    children=[
                        html.Thead(
                            html.Tr([
                                html.Th("Dimensión"),
                                html.Th("Validación"),
                                html.Th("Resultado"),
                                html.Th("Estado")
                            ])
                        ),
                        html.Tbody(filas)
                    ]
                )
            )
        ),

        tarjeta(
            "Interpretación de los resultados",

            html.P(
                "Los controles evalúan la calidad del "
                "panel histórico disponible. No representan "
                "mediciones de operación en tiempo real."
            ),

            html.P(
                "La relación bajadas/subidas es un control "
                "agregado de consistencia; una diferencia "
                "no implica necesariamente registros incorrectos."
            ),

            html.P(
                "La integridad relacional queda pendiente "
                "hasta implementar la verificación de las "
                "llaves y catálogos correspondientes."
            )
        ),

        aviso(
            "El modelo H7 utiliza información histórica. "
            "La antigüedad de los registros debe interpretarse "
            "respecto al periodo de entrenamiento, no como "
            "una falla automática de calidad.",
            "info"
        )

    ])
