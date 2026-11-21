"""Capa de datos: DuckDB de solo lectura + consultas parametrizadas.

REGLA DE ORO (anti SQL-injection)
---------------------------------
* El texto SQL es SIEMPRE una constante escrita en este archivo.
* Todo valor que venga del usuario (fechas, nodos, horas...) viaja como PARÁMETRO (?),
  jamás dentro del string SQL.
* Lo único que no se puede parametrizar son identificadores/funciones (p. ej. la
  granularidad día/semana/mes): esos se eligen de una LISTA CERRADA (GRANULARIDADES).
* Además, cada entrada se valida por tipo y rango antes de llegar a la consulta.

FUENTES DE DATOS
----------------
DATA_SOURCE=local (por defecto)
    DuckDB en memoria + vistas sobre los archivos de data/panel_horario/
    (panel_*.csv|parquet y servicio_*.csv|parquet, los mismos de la Fase 1 del notebook).
PG_ENABLED=1 (opcional)
    Adjunta PostgreSQL con credenciales del .env como catálogo `pg`, en modo READ_ONLY,
    para consultar tablas operativas (p. ej. pg.public.timbradas_consolidado).
"""
from __future__ import annotations

import logging
import os
import re
import threading
import time
from datetime import date, datetime
from functools import wraps
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

import duckdb
import pandas as pd
from dotenv import load_dotenv

load_dotenv()
log = logging.getLogger("sobusa.data")

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = (BASE_DIR / os.getenv("DATA_DIR", "data")).resolve()
PANEL_DIR = DATA_DIR / "panel_horario"
from utils.rutas_config import config

MAX_DIAS_RANGO = 800     # tope de ventana de fechas por consulta
MAX_NODOS = 200          # tope de nodos por consulta
# Lista cerrada de granularidades: clave de UI -> parte de date_trunc (constante, no viene del usuario)
GRANULARIDADES = {"dia": "day", "semana": "week", "mes": "month"}


_RE_FECHA = re.compile(r"\d{4}-\d{2}-\d{2}(?:[T ]\d{2}:\d{2}(?::\d{2}(?:\.\d+)?)?)?")


class EntradaInvalida(ValueError):
    """El usuario envió un valor fuera de lo permitido (se muestra como aviso, no como error)."""


class ErrorDatos(RuntimeError):
    """Falla de acceso a datos (mensaje genérico para la UI; el detalle va al log)."""


# =============================================================================
# 1. VALIDADORES DE ENTRADA
# =============================================================================
def validar_fecha(valor: Any, nombre: str = "fecha") -> date:
    if isinstance(valor, datetime):
        return valor.date()
    if isinstance(valor, date):
        return valor
    # Formato estricto: YYYY-MM-DD (opcionalmente con hora). Cualquier texto extra se rechaza.
    if isinstance(valor, str) and _RE_FECHA.fullmatch(valor):
        try:
            return date.fromisoformat(valor[:10])
        except ValueError:
            pass
    raise EntradaInvalida(f"La {nombre} no es válida.")


def validar_rango(inicio: Any, fin: Any) -> tuple[date, date]:
    i, f = validar_fecha(inicio, "fecha inicial"), validar_fecha(fin, "fecha final")
    if i > f:
        raise EntradaInvalida("La fecha inicial es posterior a la final.")
    if (f - i).days > MAX_DIAS_RANGO:
        raise EntradaInvalida(f"El rango máximo es de {MAX_DIAS_RANGO} días.")
    return i, f


def validar_enteros(valores: Any, permitidos: Iterable[int] | None = None,
                    nombre: str = "valores", maximo: int = MAX_NODOS) -> list[int]:
    """Convierte a lista de enteros y (opcional) exige pertenencia a un conjunto permitido."""
    if valores is None:
        return []
    if isinstance(valores, (str, bytes)) or not isinstance(valores, Iterable):
        valores = [valores]
    salida: list[int] = []
    for v in valores:
        if isinstance(v, bool) or not isinstance(v, (int, str)):
            raise EntradaInvalida(f"{nombre}: valor no válido.")
        try:
            salida.append(int(v))
        except ValueError:
            raise EntradaInvalida(f"{nombre}: valor no válido.") from None
    if len(salida) > maximo:
        raise EntradaInvalida(f"{nombre}: máximo {maximo} elementos.")
    if permitidos is not None:
        permitidos = set(permitidos)
        if not set(salida) <= permitidos:
            raise EntradaInvalida(f"{nombre}: contiene valores no permitidos.")
    return salida


def validar_opcion(valor: Any, permitidos: Mapping | Iterable) -> Any:
    """El valor debe estar en una lista/diccionario cerrado de opciones."""
    if valor not in permitidos:
        raise EntradaInvalida("Opción no permitida.")
    return valor


# =============================================================================
# 2. CONEXIÓN DUCKDB (una por proceso; un cursor por consulta = lectura concurrente)
# =============================================================================
_con: duckdb.DuckDBPyConnection | None = None
_lock = threading.Lock()


def _lit(texto: str) -> str:
    """Escapa un literal SQL. SOLO para valores de CONFIGURACIÓN (rutas, .env), nunca del usuario."""
    return "'" + texto.replace("'", "''") + "'"


def _lector(prefijo: str, panel_dir=None) -> str | None:
    """Devuelve read_parquet/read_csv_auto sobre data/panel_horario/<prefijo>_*, o None si no hay archivos."""
    panel_dir = panel_dir or PANEL_DIR
    for ext, fn in (("parquet", "read_parquet({})"), ("csv", "read_csv_auto({}, union_by_name=true)")):
        if sorted(panel_dir.glob(f"{prefijo}_*.{ext}")):
            return fn.format(_lit((panel_dir / f"{prefijo}_*.{ext}").as_posix()))
    return None


VISTA_PANEL_VACIA = """
CREATE OR REPLACE VIEW v_panel AS
SELECT CAST(NULL AS DATE) AS dia, CAST(NULL AS INTEGER) AS hora, CAST(NULL AS INTEGER) AS idpunto,
       CAST(NULL AS DOUBLE) AS subidas, CAST(NULL AS DOUBLE) AS bajadas, CAST(NULL AS DOUBLE) AS viajes
WHERE FALSE
"""



def _crear_vistas(con: duckdb.DuckDBPyConnection) -> None:
    """v_panel = panel horario + viajes (misma lógica de 2.4.2: solo horas con servicio, viajes > 0)."""
    panel, serv = _lector("panel"), _lector("servicio")
    if panel is None or serv is None:
        log.warning("No hay panel_*/servicio_* en %s: v_panel queda vacía.", PANEL_DIR)
        con.execute(VISTA_PANEL_VACIA)
    else:
        con.execute(f"""
        CREATE OR REPLACE VIEW v_panel AS
        SELECT CAST(p.dia AS DATE)      AS dia,
               CAST(p.hora AS INTEGER)  AS hora,
               CAST(p.idpunto AS INTEGER) AS idpunto,
               CAST(p.subidas AS DOUBLE) AS subidas,
               CAST(p.bajadas AS DOUBLE) AS bajadas,
               CAST(s.viajes AS DOUBLE)  AS viajes
        FROM {panel} p
        JOIN {serv} s ON CAST(p.dia AS DATE) = CAST(s.dia AS DATE) AND p.hora = s.hora
        WHERE s.viajes > 0
    """)

    # Vistas independientes para cada ruta adicional: ninguna mezcla paneles.
    for idruta, nombre_vista in ((21, "v_panel_cl72"), (2, "v_panel_r1415")):
        carpeta = config(idruta)["panel"]
        panel_ruta = _lector("panel", carpeta)
        servicio_ruta = _lector("servicio", carpeta)
        if panel_ruta is None or servicio_ruta is None:
            log.warning("Panel o servicio ausente en %s; %s queda vacía.", carpeta, nombre_vista)
            con.execute(VISTA_PANEL_VACIA.replace("v_panel", nombre_vista))
            continue
        con.execute(f"""
        CREATE OR REPLACE VIEW {nombre_vista} AS
        SELECT CAST(p.dia AS DATE) AS dia,
               CAST(p.hora AS INTEGER) AS hora,
               CAST(p.idpunto AS INTEGER) AS idpunto,
               CAST(p.subidas AS DOUBLE) AS subidas,
               CAST(p.bajadas AS DOUBLE) AS bajadas,
               CAST(s.viajes AS DOUBLE) AS viajes
        FROM {panel_ruta} p
        JOIN {servicio_ruta} s
          ON CAST(p.dia AS DATE) = CAST(s.dia AS DATE)
         AND CAST(p.hora AS INTEGER) = CAST(s.hora AS INTEGER)
        WHERE s.viajes > 0
        """)


def _dsn_valor(v: str) -> str:
    return "'" + v.replace("\\", "\\\\").replace("'", "\\'") + "'"


def _adjuntar_postgres(con: duckdb.DuckDBPyConnection) -> None:
    """Adjunta PostgreSQL como catálogo `pg` en SOLO LECTURA. Credenciales: variables PG_* del .env."""
    if os.getenv("PG_ENABLED", "0") != "1":
        return
    faltan = [k for k in ("PG_HOST", "PG_DB", "PG_USER", "PG_PASSWORD") if not os.getenv(k)]
    if faltan:
        log.warning("PG_ENABLED=1 pero faltan variables: %s", ", ".join(faltan))
        return
    dsn = " ".join(f"{clave}={_dsn_valor(os.environ[var])}" for clave, var in (
        ("host", "PG_HOST"), ("dbname", "PG_DB"), ("user", "PG_USER"), ("password", "PG_PASSWORD")))
    dsn += f" port={int(os.getenv('PG_PORT', '5432'))} sslmode={os.getenv('PG_SSLMODE', 'require')}"
    try:
        con.execute("INSTALL postgres")
        con.execute("LOAD postgres")
        con.execute(f"ATTACH {_lit(dsn)} AS pg (TYPE postgres, READ_ONLY)")
        log.info("PostgreSQL adjuntado en modo solo lectura (catálogo 'pg').")
    except Exception:  # noqa: BLE001 - no se registra el DSN (contiene la contraseña)
        log.exception("No se pudo adjuntar PostgreSQL; se continúa solo con datos locales.")


def _conexion() -> duckdb.DuckDBPyConnection:
    global _con
    if _con is None:
        with _lock:
            if _con is None:
                hilos = max(1, int(os.getenv("DUCKDB_THREADS", "2")))
                memoria = os.getenv("DUCKDB_MEMORY_LIMIT", "1GB")
                if not re.fullmatch(r"\d+(\.\d+)?\s?(MB|GB|MiB|GiB)", memoria):
                    raise ErrorDatos("DUCKDB_MEMORY_LIMIT inválido (ej.: 1GB).")
                con = duckdb.connect(":memory:", config={"threads": hilos, "memory_limit": memoria})
                _adjuntar_postgres(con)
                _crear_vistas(con)
                _con = con
    return _con


def consultar(sql: str, params: Sequence[Any] | None = None, idruta=16) -> pd.DataFrame:
    """Ejecuta una consulta PARAMETRIZADA. `sql` debe ser una constante; los valores van en `params`."""
    config(idruta)  # Validación de lista cerrada antes de insertar identificadores SQL
    nombre_vista = {16: "v_panel", 21: "v_panel_cl72", 2: "v_panel_r1415"}[int(idruta)]
    if nombre_vista != "v_panel":
        sql = re.sub(r"\bv_panel\b", nombre_vista, sql)
    cur = _conexion().cursor()      # cursor propio por llamada: seguro entre hilos/callbacks
    try:
        return cur.execute(sql, list(params or [])).df()
    except Exception as exc:        # noqa: BLE001
        log.exception("Falló una consulta DuckDB")
        raise ErrorDatos("No fue posible consultar los datos.") from exc
    finally:
        cur.close()


def cache_ttl(segundos: int, maximo: int = 256):
    """Caché en memoria con caducidad. Los argumentos deben ser hashables."""
    def deco(fn):
        almacen: dict[tuple, tuple[float, Any]] = {}

        @wraps(fn)
        def interno(*args):
            ahora = time.monotonic()
            hit = almacen.get(args)
            if hit and ahora - hit[0] < segundos:
                valor = hit[1]
            else:
                valor = fn(*args)
                if len(almacen) >= maximo:
                    almacen.clear()
                almacen[args] = (ahora, valor)
            return valor.copy() if isinstance(valor, pd.DataFrame) else valor
        return interno
    return deco


# =============================================================================
# 3. CONSULTAS DEL DASHBOARD (SQL constante + parámetros)
# =============================================================================
@cache_ttl(300)
def rango_fechas(idruta=16) -> tuple[date | None, date | None]:
    df = consultar("SELECT MIN(dia) AS d0, MAX(dia) AS d1 FROM v_panel", idruta=idruta)
    d0, d1 = df.loc[0, "d0"], df.loc[0, "d1"]
    if pd.isna(d0):
        return None, None
    return pd.Timestamp(d0).date(), pd.Timestamp(d1).date()


@cache_ttl(300)
def nodos_disponibles(idruta=16) -> tuple[int, ...]:
    df = consultar("SELECT DISTINCT idpunto FROM v_panel WHERE idpunto IS NOT NULL ORDER BY idpunto", idruta=idruta)
    return tuple(int(x) for x in df["idpunto"])


@cache_ttl(300)
def resumen_datos(idruta=16) -> dict[str, Any]:
    df = consultar("""
        SELECT COUNT(*) AS filas, COUNT(DISTINCT idpunto) AS nodos,
               MIN(dia) AS d0, MAX(dia) AS d1, SUM(subidas) AS subidas
        FROM v_panel
    """, idruta=idruta)
    r = df.iloc[0]
    vacio = int(r["filas"]) == 0
    return {"filas": int(r["filas"]), "nodos": int(r["nodos"]), "subidas": 0 if vacio else float(r["subidas"]),
            "desde": None if vacio else pd.Timestamp(r["d0"]).date(),
            "hasta": None if vacio else pd.Timestamp(r["d1"]).date()}


def _filtros(inicio: Any, fin: Any, nodos: Any, idruta=16) -> tuple[date, date, tuple[int, ...]]:
    """Valida los tres filtros comunes. Nodos vacíos = todos. Los nodos deben existir en la base."""
    i, f = validar_rango(inicio, fin)
    validos = nodos_disponibles(idruta)
    lista = validar_enteros(nodos, permitidos=validos, nombre="nodos")
    return i, f, tuple(lista) if lista else validos


SQL_PERFIL = """
SELECT hora,
       SUM(subidas)            AS subidas,
       AVG(subidas / viajes)   AS pas_por_viaje
FROM v_panel
WHERE dia BETWEEN ? AND ? AND list_contains(?, idpunto)
GROUP BY hora ORDER BY hora
"""

SQL_CALOR = """
SELECT isodow(dia) AS dow, hora, AVG(subidas / viajes) AS pas_por_viaje
FROM v_panel
WHERE dia BETWEEN ? AND ? AND list_contains(?, idpunto)
GROUP BY 1, 2 ORDER BY 1, 2
"""


@cache_ttl(120)
def _consulta_filtrada(sql: str, i: date, f: date, nodos: tuple[int, ...], idruta=16) -> pd.DataFrame:
    if not nodos:
        return pd.DataFrame()
    return consultar(sql, [i, f, list(nodos)], idruta=idruta)


def perfil_horario(inicio: Any, fin: Any, nodos: Any, idruta=16) -> pd.DataFrame:
    i, f, n = _filtros(inicio, fin, nodos, idruta)
    return _consulta_filtrada(SQL_PERFIL, i, f, n, idruta)


def mapa_calor(inicio: Any, fin: Any, nodos: Any, idruta=16) -> pd.DataFrame:
    i, f, n = _filtros(inicio, fin, nodos, idruta)
    return _consulta_filtrada(SQL_CALOR, i, f, n, idruta)


def serie_temporal(inicio: Any, fin: Any, nodos: Any, granularidad: str = "dia", idruta=16) -> pd.DataFrame:
    i, f, n = _filtros(inicio, fin, nodos, idruta)
    parte = GRANULARIDADES[validar_opcion(granularidad, GRANULARIDADES)]   # constante de lista cerrada
    # `parte` NO viene del usuario: es el valor de un diccionario fijo. Es el único f-string de SQL permitido.
    sql = f"""
        SELECT CAST(date_trunc('{parte}', dia) AS DATE) AS periodo,
               SUM(subidas) AS subidas, SUM(bajadas) AS bajadas,
               AVG(subidas / viajes) AS pas_por_viaje
        FROM v_panel
        WHERE dia BETWEEN ? AND ? AND list_contains(?, idpunto)
        GROUP BY 1 ORDER BY 1
    """
    return _consulta_filtrada(sql, i, f, n, idruta)


@cache_ttl(300)
def calidad_panel(idruta=16) -> dict[str, Any]:
    """Controles de calidad de 6.3 sobre v_panel (completitud, validez, unicidad, consistencia, oportunidad)."""
    base = consultar("""
        SELECT COUNT(*) AS filas,
               COUNT(*) FILTER (WHERE dia IS NULL OR hora IS NULL OR idpunto IS NULL
                                   OR subidas IS NULL OR bajadas IS NULL OR viajes IS NULL) AS nulos,
               COUNT(*) FILTER (WHERE subidas < 0 OR bajadas < 0 OR viajes <= 0
                                   OR hora < 0 OR hora > 23) AS invalidos,
               SUM(subidas) AS subidas, SUM(bajadas) AS bajadas,
               MIN(dia) AS d0, MAX(dia) AS d1
        FROM v_panel
    """, idruta=idruta).iloc[0]
    dup = consultar("""
        SELECT COUNT(*) AS n FROM (
            SELECT 1 FROM v_panel GROUP BY idpunto, dia, hora HAVING COUNT(*) > 1)
    """, idruta=idruta).iloc[0]["n"]
    filas = int(base["filas"])
    return {
        "filas": filas, "nulos": int(base["nulos"]), "invalidos": int(base["invalidos"]),
        "duplicados": int(dup),
        "ratio_bajadas_subidas": (float(base["bajadas"]) / float(base["subidas"])) if filas and base["subidas"] else None,
        "fecha_min": None if filas == 0 else pd.Timestamp(base["d0"]).date(),
        "fecha_max": None if filas == 0 else pd.Timestamp(base["d1"]).date(),
    }


# =============================================================================
# 4. EJEMPLO: CONSULTA A POSTGRES (solo si PG_ENABLED=1) CON CREDENCIALES DEL .env
# =============================================================================
def demanda_consolidada_pg(id_ruta: int) -> pd.DataFrame:
    """Ejemplo de consulta parametrizada a una tabla operativa (solo lectura).

    Requiere PG_ENABLED=1 y PG_HOST/PG_DB/PG_USER/PG_PASSWORD en el .env.
    El nombre del catálogo/tabla es constante; el id de ruta viaja como parámetro.
    """
    ruta = validar_enteros([id_ruta], nombre="id_ruta", maximo=1)
    if not ruta:
        raise EntradaInvalida("id_ruta requerido.")
    return consultar("""
        SELECT id_dia_semana, id_estacionalidad, hora_inicio, subidas, bajadas, nro_viajes
        FROM pg.public.timbradas_consolidado
        WHERE id_ruta = ?
    """, [ruta[0]])
