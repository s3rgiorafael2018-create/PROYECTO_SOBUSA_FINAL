"""Punto de entrada del dashboard SOBUSA · Frecuencias (Dash multipágina).

Orden de arranque (importa):
  1. Cargar .env                       -> variables de entorno disponibles
  2. Crear Flask + init_security()     -> TODAS las rutas quedan protegidas por login
  3. Crear Dash sobre ese Flask        -> páginas en /pages, estilos en /assets
Ejecución local:   python app.py
Producción:        gunicorn app:server   (más adelante, en Render)
"""
import logging
import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()   # debe ir ANTES de importar utils.*

import dash
from dash import Dash, Input, Output, callback, dcc, html
from flask import Flask
from flask_login import current_user

from utils.security import EN_PRODUCCION, init_security
from utils.svg_icons import icono
from utils.resultados_store import cargar_resultado
from utils.rutas_config import ruta_id, RUTAS

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"),
                    format="%(asctime)s %(levelname)s %(name)s: %(message)s")

BASE_DIR = Path(__file__).resolve().parent
# Tu carpeta se llama 'asssets' (3 s). Lo recomendable es renombrarla a 'assets'; mientras tanto funciona con ambas.
ASSETS = BASE_DIR / ("assets" if (BASE_DIR / "assets").is_dir() else "asssets")

# ---------------------------------------------------------------- 1) Flask + seguridad
server = Flask(__name__)
init_security(server)          # login obligatorio, sesión segura, cabeceras, límite de intentos

# ---------------------------------------------------------------- 2) Dash
app = Dash(
    __name__,
    server=server,
    use_pages=True,
    pages_folder=str(BASE_DIR / "pages"),
    assets_folder=str(ASSETS),
    suppress_callback_exceptions=True,
    title="SOBUSA | Frecuencias",
    update_title=None,
    meta_tags=[{"name": "viewport", "content": "width=device-width, initial-scale=1"}],
)


def _marca() -> html.Div:
    """Si existe assets/logo.png se usa; si no, el nombre en texto."""
    if (ASSETS / "logo.png").exists():
        return html.Div(html.Img(src=app.get_asset_url("logo.png"), className="brand-logo", alt="Extreme Technologies"),
                        className="brand")
    return html.Div(className="brand", children=[
        html.Span("EXTREME", className="brand-mark"),
        html.Span("SOBUSA · Frecuencias", className="brand-sub")])


def layout():
    """Se evalúa en cada carga de página (por eso puede leer el usuario de la sesión)."""
    usuario = current_user.get_id() if current_user.is_authenticated else ""
    return html.Div(className="app-shell", children=[
        dcc.Location(id="url"),
        
        # Última optimización guardada
        dcc.Store(
            id="opt-resultado-store",
            storage_type="session",
            data=None
        ),

        # Última predicción guardada
        dcc.Store(
            id="pred-resultado-store",
            storage_type="session",
            data=None
        ),
        
        html.Aside(className="sidebar", children=[
            _marca(),
            html.Nav(id="nav", className="nav", **{"aria-label": "Navegación principal"}),
            html.Div(className="sidebar-foot", children=[
                html.Span(f"Sesión: {usuario}", className="user-chip"),
                html.A([icono("logout", "#FFFFFF", 16), html.Span("Cerrar sesión")], href="/logout", className="logout"),
            ]),
        ]),
        html.Main(className="main", children=[
            html.Div(id="selector-rutas-global", className="route-tabs"),
            dash.page_container
        ]),
    ])


app.layout = layout



@callback(Output("nav", "children"), Input("url", "pathname"), Input("url", "search"))
def pintar_menu(pathname, search):

    paginas = sorted(
        [
            p for p in dash.page_registry.values()
            if p.get("module") != "dash"
        ],
        key=lambda p: (
            p.get("order") is None,
            p.get("order") if p.get("order") is not None else 99
        )
    )

    return [
        dcc.Link(
            [
                icono(
                    p.get("icon", "dashboard"),
                    "#C5CE00" if p["path"] == pathname else "#FFFFFF",
                    18
                ),
                html.Span(p["name"])
            ],
            href=p["relative_path"] + (search or "?ruta=16"),
            className="nav-link" + (
                " activo" if p["path"] == pathname else ""
            )
        )
        for p in paginas
    ]



"""if __name__ == "__main__":
    # Depurador de Werkzeug SOLO en desarrollo: en producción permitiría ejecutar código remoto.
    app.run(debug=not EN_PRODUCCION, host=os.getenv("HOST", "127.0.0.1"), port=int(os.getenv("PORT", "8050")))"""
    
# El selector conserva idruta en la URL: cada página se vuelve a renderizar
# cuando cambia ?ruta=16 / ?ruta=21 / ?ruta=2, sin stores globales compartidos.
from urllib.parse import parse_qs
from dash import State

@callback(Output("selector-rutas-global", "children"), Input("url", "pathname"), Input("url", "search"))
def mostrar_pestanas(pathname, search):
    rid = ruta_id(parse_qs((search or "").lstrip("?")).get("ruta", [16])[0])
    return html.Div([
        html.A(cfg["nombre"], href=f"{pathname or '/'}?ruta={r}",
               className="route-tab" + (" active" if r == rid else ""))
        for r, cfg in RUTAS.items()
    ])

@callback(Output("opt-resultado-store", "data", allow_duplicate=True),
          Output("pred-resultado-store", "data", allow_duplicate=True), Input("url", "search"),
          prevent_initial_call="initial_duplicate")
def cargar_resultados_ruta(search):
    rid = ruta_id(parse_qs((search or "").lstrip("?")).get("ruta", [16])[0])
    return cargar_resultado("optimizacion", rid), cargar_resultado("prediccion", rid)


# Registrar todos los callbacks ANTES de iniciar el servidor.
if __name__ == "__main__":
    app.run(
        debug=False,
        host="0.0.0.0",
        port=8050
    )

