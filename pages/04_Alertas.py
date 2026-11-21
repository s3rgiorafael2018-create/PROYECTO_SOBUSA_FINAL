
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import dash
from dash import Input, Output, callback, dcc, html, dash_table


dash.register_page(
    __name__,
    path="/alertas",
    name="Alertas",
    title="Alertas operativas",
    order=4,
    icon="bell"
)

# --------------------------------------------------
# CONFIGURACIÓN
# --------------------------------------------------

ZONA_HORARIA = ZoneInfo("America/Bogota")

HORAS_OPERACION = list(range(4, 23))


# --------------------------------------------------
# CATÁLOGO DE ALERTAS
# --------------------------------------------------

CATALOGO_ALERTAS = [
    {
        "codigo": "ALT-001",
        "alerta": "Alta demanda prevista",
        "nivel": "Preventiva",
        "condicion": "Demanda prevista superior al umbral establecido.",
        "accion": "Revisar la capacidad y la frecuencia programada."
    },
    {
        "codigo": "ALT-002",
        "alerta": "Sobreocupación",
        "nivel": "Crítica",
        "condicion": "Ocupación real superior a la capacidad permitida.",
        "accion": "Revisar la asignación de vehículos."
    },
    {
        "codigo": "ALT-003",
        "alerta": "Frecuencia insuficiente",
        "nivel": "Preventiva",
        "condicion": "La optimización registra pasajeros no atendidos.",
        "accion": "Evaluar un aumento de frecuencia."
    },
    {
        "codigo": "ALT-004",
        "alerta": "Frecuencia excesiva",
        "nivel": "Informativa",
        "condicion": "Frecuencia superior a la demanda requerida.",
        "accion": "Revisar la eficiencia de la programación."
    },
    {
        "codigo": "ALT-005",
        "alerta": "Caída anormal de demanda",
        "nivel": "Preventiva",
        "condicion": "Demanda inferior al comportamiento esperado.",
        "accion": "Revisar la demanda y el pronóstico."
    },
    {
        "codigo": "ALT-006",
        "alerta": "Despacho ausente o tardío",
        "nivel": "Crítica",
        "condicion": "No existe registro de un despacho esperado.",
        "accion": "Verificar el despacho del vehículo."
    },
    {
        "codigo": "ALT-007",
        "alerta": "Desviación del pronóstico",
        "nivel": "Preventiva",
        "condicion": "Demanda observada diferente a la pronosticada.",
        "accion": "Evaluar el comportamiento del modelo."
    },
    {
        "codigo": "ALT-008",
        "alerta": "Consolidado anómalo",
        "nivel": "Preventiva",
        "condicion": "Inconsistencias en los datos consolidados.",
        "accion": "Revisar los registros de origen."
    },
    {
        "codigo": "ALT-009",
        "alerta": "Datos incompletos",
        "nivel": "Crítica",
        "condicion": "Faltan horas o valores necesarios para operar.",
        "accion": "Verificar la información de entrada."
    },
    {
        "codigo": "ALT-010",
        "alerta": "Modelo degradado",
        "nivel": "Crítica",
        "condicion": "El rendimiento del modelo cae por debajo del umbral.",
        "accion": "Evaluar y actualizar el modelo."
    }
]


# --------------------------------------------------
# FUNCIONES AUXILIARES
# --------------------------------------------------

def obtener_resultados_validos(resultado):

    if not isinstance(resultado, dict):
        return None

    registros = resultado.get("resultados")

    if not isinstance(registros, list) or not registros:
        return None

    registros_por_hora = {}

    for registro in registros:

        if not isinstance(registro, dict):
            continue

        try:
            hora = int(registro["hora"])
            frecuencia = int(registro["frecuencia"])
            demanda = float(registro["demanda"])
            no_atendidos = float(registro["no_atendidos"])
            headway = registro.get("headway_min")

            if hora not in HORAS_OPERACION:
                continue

            if frecuencia < 0 or demanda < 0 or no_atendidos < 0:
                continue

            if frecuencia > 0:
                headway = float(headway)

                if headway <= 0:
                    continue
            else:
                headway = None

            registros_por_hora[hora] = {
                "hora": hora,
                "frecuencia": frecuencia,
                "demanda": demanda,
                "no_atendidos": no_atendidos,
                "headway_min": headway
            }

        except (KeyError, TypeError, ValueError):
            continue

    return registros_por_hora


def obtener_proxima_salida(registros, ahora):

    """
    Calcula la siguiente salida teórica.

    Para cada hora:
        frecuencia = 3 -> salidas cada 20 minutos.
        frecuencia = 4 -> salidas cada 15 minutos.

    Se distribuyen uniformemente dentro de cada hora.
    """

    candidatos = []

    for desplazamiento_dias in range(3):

        fecha = ahora.date() + timedelta(
            days=desplazamiento_dias
        )

        for hora in HORAS_OPERACION:

            registro = registros.get(hora)

            if registro is None:
                continue

            frecuencia = registro["frecuencia"]

            if frecuencia <= 0:
                continue

            inicio_hora = datetime(
                fecha.year,
                fecha.month,
                fecha.day,
                hora,
                0,
                0,
                tzinfo=ZONA_HORARIA
            )

            intervalo_minutos = 60.0 / frecuencia

            for indice in range(frecuencia):

                salida = inicio_hora + timedelta(
                    minutes=indice * intervalo_minutos
                )

                if salida > ahora:

                    candidatos.append(salida)

    if not candidatos:
        return None

    return min(candidatos)


def formato_cuenta_regresiva(segundos):

    segundos = max(0, int(segundos))

    horas, resto = divmod(segundos, 3600)
    minutos, segundos = divmod(resto, 60)

    return f"{horas:02d}:{minutos:02d}:{segundos:02d}"


def construir_alertas(registros):

    alertas = []

    # Datos incompletos
    horas_faltantes = [
        hora
        for hora in HORAS_OPERACION
        if hora not in registros
    ]

    if horas_faltantes:

        alertas.append({
            "codigo": "ALT-009",
            "alerta": "Datos incompletos",
            "nivel": "Crítica",
            "detalle": (
                "No se encontraron registros para las horas: "
                + ", ".join(f"{h:02d}:00" for h in horas_faltantes)
            ),
            "accion": "Verificar el resultado de la optimización."
        })

    # Frecuencia insuficiente
    for hora, registro in registros.items():

        if registro["no_atendidos"] > 0:

            alertas.append({
                "codigo": "ALT-003",
                "alerta": "Frecuencia insuficiente",
                "nivel": "Preventiva",
                "detalle": (
                    f"Hora {hora:02d}:00. "
                    f"Pasajeros no atendidos: "
                    f"{registro['no_atendidos']:,.1f}"
                ),
                "accion": (
                    "Evaluar un aumento de frecuencia "
                    "para esta franja."
                )
            })

    return alertas


# --------------------------------------------------
# COMPONENTES VISUALES
# --------------------------------------------------

def tarjeta(titulo, componente, subtitulo=None):

    return html.Div(
        className="card",
        children=[
            html.P(titulo, className="card-title"),
            componente,
            html.P(
                subtitulo,
                className="card-subtitle"
            ) if subtitulo else None
        ]
    )


def layout(**_):

    return html.Div(
        className="page-container",
        children=[

            dcc.Interval(
                id="alertas-interval",
                interval=1000,
                n_intervals=0
            ),

            html.Div(
                className="page-header",
                children=[
                    html.H2("Alertas operativas"),
                    html.P(
                        "Seguimiento de frecuencias y "
                        "próximos despachos de la ruta."
                    )
                ]
            ),

            # Estado de la optimización
            html.Div(
                id="alertas-estado-opt",
                className="alert alert-info",
                children="Esperando una optimización..."
            ),

            # --------------------------------------------------
            # PRÓXIMA SALIDA
            # --------------------------------------------------

            html.Div(
                className="alertas-grid",
                children=[

                    tarjeta(
                        "Próxima salida teórica",
                        html.H3(
                            "—",
                            id="alertas-hora-salida"
                        ),
                        "Hora local de Colombia"
                    ),

                    tarjeta(
                        "Tiempo restante",
                        html.H2(
                            "--:--:--",
                            id="alertas-cuenta-regresiva"
                        ),
                        "Cuenta regresiva hasta la próxima salida"
                    ),

                    tarjeta(
                        "Frecuencia actual",
                        html.H3(
                            "—",
                            id="alertas-frecuencia"
                        ),
                        "Ciclos completos por hora"
                    ),

                    tarjeta(
                        "Intervalo entre salidas",
                        html.H3(
                            "—",
                            id="alertas-headway"
                        ),
                        "Minutos entre salidas teóricas"
                    )

                ]
            ),

            # --------------------------------------------------
            # ESTADO DE LA HORA ACTUAL
            # --------------------------------------------------

            html.Div(
                className="card",
                children=[
                    html.H3("Estado de la franja actual"),

                    html.Div(
                        id="alertas-estado-franja"
                    )
                ]
            ),

            # --------------------------------------------------
            # ALERTAS ACTIVAS
            # --------------------------------------------------

            html.Div(
                className="card",
                children=[
                    html.H3("Alertas activas"),

                    html.Div(
                        id="alertas-total"
                    ),

                    dash_table.DataTable(
                        id="alertas-tabla-activas",

                        columns=[
                            {
                                "name": "Código",
                                "id": "codigo"
                            },
                            {
                                "name": "Alerta",
                                "id": "alerta"
                            },
                            {
                                "name": "Nivel",
                                "id": "nivel"
                            },
                            {
                                "name": "Detalle",
                                "id": "detalle"
                            },
                            {
                                "name": "Acción recomendada",
                                "id": "accion"
                            }
                        ],

                        data=[],

                        page_size=8,

                        style_table={
                            "overflowX": "auto"
                        },

                        style_cell={
                            "textAlign": "left",
                            "padding": "10px",
                            "whiteSpace": "normal",
                            "height": "auto",
                            "minWidth": "100px",
                            "maxWidth": "280px"
                        },

                        style_header={
                            "fontWeight": "bold"
                        },

                        style_data_conditional=[
                            {
                                "if": {
                                    "filter_query": '{nivel} = "Crítica"',
                                    "column_id": "nivel"
                                },
                                "color": "#dc2626",
                                "fontWeight": "bold"
                            },
                            {
                                "if": {
                                    "filter_query": '{nivel} = "Preventiva"',
                                    "column_id": "nivel"
                                },
                                "color": "#d97706",
                                "fontWeight": "bold"
                            }
                        ]
                    )
                ]
            ),

            # --------------------------------------------------
            # CATÁLOGO DE ALERTAS
            # --------------------------------------------------

            html.Div(
                className="card",
                children=[
                    html.H3("Catálogo de alertas"),

                    dash_table.DataTable(
                        id="alertas-catalogo",

                        columns=[
                            {
                                "name": "Código",
                                "id": "codigo"
                            },
                            {
                                "name": "Alerta",
                                "id": "alerta"
                            },
                            {
                                "name": "Nivel",
                                "id": "nivel"
                            },
                            {
                                "name": "Condición",
                                "id": "condicion"
                            },
                            {
                                "name": "Acción",
                                "id": "accion"
                            }
                        ],

                        data=CATALOGO_ALERTAS,

                        page_size=10,

                        style_table={
                            "overflowX": "auto"
                        },

                        style_cell={
                            "textAlign": "left",
                            "padding": "10px",
                            "whiteSpace": "normal",
                            "height": "auto",
                            "minWidth": "100px",
                            "maxWidth": "280px"
                        },

                        style_header={
                            "fontWeight": "bold"
                        }
                    )
                ]
            ),

            html.P(
                "Nota: los horarios y contadores son estimaciones "
                "teóricas basadas en la última optimización exitosa. "
                "No representan confirmaciones de despacho real.",
                className="text-muted"
            )

        ]
    )


# --------------------------------------------------
# CALLBACK PRINCIPAL
# --------------------------------------------------

@callback(

    Output("alertas-estado-opt", "children"),

    Output("alertas-hora-salida", "children"),

    Output("alertas-cuenta-regresiva", "children"),

    Output("alertas-frecuencia", "children"),

    Output("alertas-headway", "children"),

    Output("alertas-estado-franja", "children"),

    Output("alertas-total", "children"),

    Output("alertas-tabla-activas", "data"),

    Input("opt-resultado-store", "data"),

    Input("alertas-interval", "n_intervals")

)
def actualizar_alertas(resultado, n_intervals):

    # --------------------------------------------------
    # 1. VALIDAR OPTIMIZACIÓN
    # --------------------------------------------------

    registros = obtener_resultados_validos(resultado)

    if not registros:

        return (
            "No hay una optimización válida disponible. "
            "Ejecuta primero una optimización.",

            "—",
            "--:--:--",
            "—",
            "—",

            html.P(
                "No existe información suficiente "
                "para calcular los próximos despachos."
            ),

            "0 alertas activas",
            []
        )

    # --------------------------------------------------
    # 2. HORA ACTUAL DE COLOMBIA
    # --------------------------------------------------

    ahora = datetime.now(ZONA_HORARIA)

    hora_actual = ahora.hour

    registro_actual = registros.get(hora_actual)

    # --------------------------------------------------
    # 3. CALCULAR PRÓXIMA SALIDA
    # --------------------------------------------------

    proxima_salida = obtener_proxima_salida(
        registros,
        ahora
    )

    if proxima_salida is None:

        hora_salida = "Sin salidas programadas"
        cuenta = "—"

    else:

        hora_salida = proxima_salida.strftime(
            "%d/%m/%Y %H:%M:%S"
        )

        segundos_restantes = (
            proxima_salida - ahora
        ).total_seconds()

        cuenta = formato_cuenta_regresiva(
            segundos_restantes
        )

    # --------------------------------------------------
    # 4. INFORMACIÓN DE LA HORA ACTUAL
    # --------------------------------------------------

    if registro_actual is None:

        frecuencia_texto = "Sin datos"
        headway_texto = "Sin datos"

        estado_franja = html.P(
            f"No hay información optimizada para "
            f"la franja de las {hora_actual:02d}:00."
        )

    else:

        frecuencia = registro_actual["frecuencia"]

        frecuencia_texto = str(frecuencia)

        headway = registro_actual["headway_min"]

        headway_texto = (
            f"{headway:.2f} min"
            if headway is not None
            else "No aplica"
        )

        if frecuencia == 0:

            estado_franja = html.P(
                "No hay ciclos programados para la hora actual.",
                className="alert alert-warning"
            )

        else:

            estado_franja = html.Div(
                children=[
                    html.P(
                        f"Hora actual: {hora_actual:02d}:00 - "
                        f"{hora_actual:02d}:59"
                    ),
                    html.P(
                        f"Frecuencia programada: {frecuencia} "
                        f"ciclos completos."
                    ),
                    html.P(
                        f"Intervalo teórico: {headway:.2f} minutos."
                    ),
                    html.P(
                        f"Demanda prevista: "
                        f"{registro_actual['demanda']:,.1f} pasajeros."
                    ),
                    html.P(
                        f"Pasajeros no atendidos: "
                        f"{registro_actual['no_atendidos']:,.1f}."
                    )
                ]
            )

    # --------------------------------------------------
    # 5. GENERAR ALERTAS
    # --------------------------------------------------

    alertas = construir_alertas(registros)

    # Alerta operativa adicional para frecuencia cero
    if (
        registro_actual is not None
        and registro_actual["frecuencia"] == 0
        and registro_actual["demanda"] > 0
    ):

        alertas.append({
            "codigo": "ALT-003",
            "alerta": "Sin ciclos programados",
            "nivel": "Preventiva",
            "detalle": (
                f"Existe demanda prevista de "
                f"{registro_actual['demanda']:,.1f} pasajeros "
                f"a las {hora_actual:02d}:00, pero la frecuencia "
                "optimizada es cero."
            ),
            "accion": (
                "Revisar la asignación de ciclos para esta franja."
            )
        })

    total_alertas = len(alertas)

    return (

        (
            f"Última optimización: "
            f"{resultado.get('fecha', 'Sin fecha')} | "
            f"Modelo: {resultado.get('modelo', 'N/D')}"
        ),

        hora_salida,

        cuenta,

        frecuencia_texto,

        headway_texto,

        estado_franja,

        f"{total_alertas} alertas activas",

        alertas

    )
