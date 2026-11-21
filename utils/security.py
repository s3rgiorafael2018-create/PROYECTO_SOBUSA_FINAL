"""Seguridad de la aplicación.

- Autenticación obligatoria con Flask-Login + contraseñas hasheadas con bcrypt.
- Un ÚNICO guardián (before_request) protege TODAS las rutas: vistas de Dash,
  /_dash-layout y /_dash-update-component (callbacks). Solo quedan públicos
  /login y los estáticos de /assets/ (necesarios para pintar el login).
- Sesión endurecida (HttpOnly, SameSite, Secure en producción, caducidad).
- CSRF propio en el formulario de login, límite de intentos por IP y cabeceras HTTP seguras.

Las credenciales NUNCA están en el código: se leen de variables de entorno (.env).
"""
from __future__ import annotations

import hmac
import json
import logging
import os
import secrets
import time
from datetime import timedelta
from urllib.parse import quote, urlparse

import bcrypt
from dotenv import load_dotenv
from flask import Flask, jsonify, make_response, redirect, render_template_string, request, session
from flask_login import LoginManager, UserMixin, current_user, login_user, logout_user
from werkzeug.middleware.proxy_fix import ProxyFix

load_dotenv()
log = logging.getLogger("sobusa.security")

EN_PRODUCCION = os.getenv("APP_ENV", "development").lower() == "production"
MAX_INTENTOS = 5                 # intentos fallidos permitidos...
VENTANA_BLOQUEO_S = 15 * 60      # ...dentro de esta ventana (15 min) por IP
RUTAS_PUBLICAS = {"/login"}
PREFIJOS_PUBLICOS = ("/assets/", "/_favicon.ico")

_USUARIOS: dict[str, bytes] = {}
_INTENTOS: dict[str, list[float]] = {}
# Hash de relleno: si el usuario no existe igual se ejecuta bcrypt (evita revelar usuarios por tiempo).
_HASH_FALSO = bcrypt.hashpw(b"usuario-inexistente", bcrypt.gensalt(12))


class Usuario(UserMixin):
    def __init__(self, nombre: str):
        self.id = nombre


# --------------------------------------------------------------------------- configuración
def _clave_secreta() -> str:
    clave = os.getenv("SECRET_KEY", "")
    if len(clave) >= 32:
        return clave
    if EN_PRODUCCION:
        raise RuntimeError("SECRET_KEY (mínimo 32 caracteres) es obligatoria en producción.")
    log.warning("SECRET_KEY ausente: se usa una temporal (las sesiones se pierden al reiniciar).")
    return secrets.token_hex(32)


def _cargar_usuarios() -> dict[str, bytes]:
    """AUTH_USERS = JSON {"usuario": "hash_bcrypt"}. Si falta o es inválido, la app NO arranca."""
    crudo = os.getenv("AUTH_USERS", "").strip()
    if not crudo:
        raise RuntimeError("Defina AUTH_USERS en el .env (usuarios con hash bcrypt).")
    try:
        datos = json.loads(crudo)
    except json.JSONDecodeError as exc:
        raise RuntimeError("AUTH_USERS no es un JSON válido.") from exc
    if not isinstance(datos, dict) or not datos:
        raise RuntimeError("AUTH_USERS debe ser un objeto JSON no vacío.")
    usuarios: dict[str, bytes] = {}
    for nombre, hash_ in datos.items():
        if not isinstance(hash_, str) or not hash_.startswith(("$2a$", "$2b$", "$2y$")):
            raise RuntimeError(f"El valor de '{nombre}' en AUTH_USERS no es un hash bcrypt.")
        usuarios[str(nombre)] = hash_.encode()
    return usuarios


# --------------------------------------------------------------------------- utilidades
def _verificar(usuario: str, clave: str) -> bool:
    hash_ = _USUARIOS.get(usuario)
    # bcrypt solo considera los primeros 72 bytes; se recorta para evitar errores en versiones nuevas
    ok = bcrypt.checkpw(clave.encode("utf-8")[:72], hash_ or _HASH_FALSO)
    return bool(ok and hash_ is not None)


def _destino_seguro(destino: str | None) -> str:
    """Evita 'open redirect': solo se aceptan rutas locales."""
    if not destino:
        return "/"
    p = urlparse(destino)
    if p.scheme or p.netloc or not destino.startswith("/") or destino.startswith("//") or "\\" in destino:
        return "/"
    return destino


def _bloqueado(ip: str) -> bool:
    ahora = time.time()
    recientes = [t for t in _INTENTOS.get(ip, []) if ahora - t < VENTANA_BLOQUEO_S]
    if recientes:
        _INTENTOS[ip] = recientes
    else:
        _INTENTOS.pop(ip, None)
    return len(recientes) >= MAX_INTENTOS


def _registrar_fallo(ip: str) -> None:
    _INTENTOS.setdefault(ip, []).append(time.time())


PLANTILLA_LOGIN = """<!doctype html>
<html lang="es"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Ingresar | SOBUSA</title>
<link rel="stylesheet" href="/assets/style.css">
</head><body class="login-body">
<main class="login-card">
  <div class="login-brand"><span class="brand-mark">EXTREME</span><span class="brand-sub">SOBUSA · Frecuencias</span></div>
  <h1>Iniciar sesión</h1>
  {% if error %}<p class="login-error" role="alert">{{ error }}</p>{% endif %}
  <form method="post" action="/login?next={{ siguiente|urlencode }}" autocomplete="on">
    <input type="hidden" name="csrf" value="{{ csrf }}">
    <label for="usuario">Usuario</label>
    <input id="usuario" name="usuario" type="text" maxlength="64" autocomplete="username" required autofocus>
    <label for="clave">Contraseña</label>
    <input id="clave" name="clave" type="password" maxlength="128" autocomplete="current-password" required>
    <button type="submit">Entrar</button>
  </form>
  <p class="login-foot">Acceso restringido · Data Challenge 2026</p>
</main></body></html>"""


# --------------------------------------------------------------------------- inicialización
def init_security(server: Flask) -> None:
    """Registra autenticación, sesión, guardián global y cabeceras sobre el Flask de Dash."""
    global _USUARIOS
    _USUARIOS = _cargar_usuarios()

    server.config.update(
        SECRET_KEY=_clave_secreta(),
        SESSION_COOKIE_NAME="sobusa_session",
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_SECURE=EN_PRODUCCION,      # solo por HTTPS en producción
        PERMANENT_SESSION_LIFETIME=timedelta(hours=float(os.getenv("SESSION_HOURS", "8"))),
        MAX_CONTENT_LENGTH=1 * 1024 * 1024,       # 1 MB: los callbacks no necesitan más
    )
    # Detrás de Render/NGINX: IP y esquema reales (necesario para el límite de intentos y cookies Secure)
    if os.getenv("TRUST_PROXY", "0") == "1":
        server.wsgi_app = ProxyFix(server.wsgi_app, x_for=1, x_proto=1, x_host=1)

    login_manager = LoginManager()
    login_manager.init_app(server)

    @login_manager.user_loader
    def _cargar(uid: str):
        return Usuario(uid) if uid in _USUARIOS else None

    # ---- guardián global: nada se sirve sin sesión (vistas ni callbacks) ----
    @server.before_request
    def _exigir_login():
        ruta = request.path
        if ruta in RUTAS_PUBLICAS or ruta.startswith(PREFIJOS_PUBLICOS):
            return None
        if current_user.is_authenticated:
            return None
        if ruta.startswith("/_dash-") or ruta.startswith("/_reload-hash"):
            return make_response(jsonify(error="No autenticado"), 401)
        siguiente = request.path + (("?" + request.query_string.decode("utf-8", "ignore")) if request.query_string else "")
        return redirect("/login?next=" + quote(siguiente, safe=""))

    # ---- login / logout ----
    @server.route("/login", methods=["GET", "POST"])
    def login():
        siguiente = _destino_seguro(request.args.get("next"))
        if current_user.is_authenticated:
            return redirect(siguiente)
        error, codigo = None, 200
        if request.method == "POST":
            ip = request.remote_addr or "desconocida"
            esperado = session.get("csrf", "")
            recibido = request.form.get("csrf", "")

            log.warning("DEBUG CSRF:")
            log.warning("Método: %s", request.method)
            log.warning("Cookie de sesión recibida: %s", bool(request.cookies.get("sobusa_session")))
            log.warning("Token esperado existe: %s", bool(esperado))
            log.warning("Token recibido existe: %s", bool(recibido))
            log.warning("Tokens coinciden: %s", hmac.compare_digest(esperado, recibido) if esperado and recibido else False)
            
            log.warning("Token esperado: %s", esperado)
            log.warning("Token recibido: %s", recibido)
            log.warning("ID de sesión: %s", session.get("csrf"))
            
            if not esperado or not hmac.compare_digest(esperado, recibido):
                error, codigo = "La sesión del formulario expiró. Inténtalo de nuevo.", 400
            elif _bloqueado(ip):
                error, codigo = "Demasiados intentos fallidos. Espera unos minutos.", 429
                log.warning("Login bloqueado por exceso de intentos (ip=%s)", ip)
            else:
                usuario = request.form.get("usuario", "").strip()[:64]
                clave = request.form.get("clave", "")
                if _verificar(usuario, clave):
                    session.clear()                      # evita fijación de sesión
                    login_user(Usuario(usuario))
                    session.permanent = True
                    _INTENTOS.pop(ip, None)
                    log.info("Login correcto (usuario=%s)", usuario)
                    return redirect(siguiente)
                _registrar_fallo(ip)
                log.warning("Login fallido (usuario=%s, ip=%s)", usuario, ip)
                error = "Usuario o contraseña incorrectos."
        if not session.get("csrf"):
            session["csrf"] = secrets.token_urlsafe(32)

        html = render_template_string(
            PLANTILLA_LOGIN,
            error=error,
            csrf=session["csrf"],
            siguiente=siguiente
        )

        return make_response(html, codigo)

    @server.route("/logout")
    def logout():
        logout_user()
        session.clear()
        return redirect("/login")

    # ---- cabeceras de seguridad ----
    @server.after_request
    def _cabeceras(resp):
        resp.headers.setdefault("X-Content-Type-Options", "nosniff")
        resp.headers.setdefault("X-Frame-Options", "DENY")
        resp.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        resp.headers.setdefault("Permissions-Policy", "geolocation=(), microphone=(), camera=()")
        if EN_PRODUCCION:
            resp.headers.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
        if not request.path.startswith(("/assets/", "/_dash-component-suites/")):
            resp.headers["Cache-Control"] = "no-store"   # nada autenticado queda en caché
        return resp
