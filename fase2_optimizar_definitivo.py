"""
SOBUSA - Optimizacion de frecuencias (MILP).

Version reconstruida para integracion con FastAPI/Dash.

Unidad de decision:
    f[h] = ciclos completos (ida + vuelta) que comienzan en la franja h.

Demanda:
    Pasajeros por hora del reloj, ruta completa y ambos sentidos, sin dividir.
    La demanda es un insumo fijo; no cambia en funcion de las frecuencias propuestas.

Capacidad:
    capacidad_efectiva = capacidad_bus * ocupacion_objetivo.
    El usuario proporciona la capacidad nominal del bus y el porcentaje de
    ocupacion objetivo. No se fija una capacidad universal de 70 pasajeros.

Factor de carga:
    Los archivos panel + demanda disponibles no contienen el detalle por viaje
    y segmento necesario para reconstruir el pico simultaneo a bordo. Por tanto,
    no se reutiliza el factor derivado de 2023 ni se inventa uno de 2024.
    El valor por defecto es 1.0 (sin descuento por factor de carga): supuesto
    conservador que trata la demanda horaria por ciclo como carga potencial.
    La funcion acepta un factor escalar o vector si en el futuro se valida uno.

Restricciones conservadas:
    - una frecuencia entera por hora;
    - capacidad con variable de pasajeros no atendidos;
    - presupuesto fijo de ciclos, si se proporciona;
    - disponibilidad de flota mediante bus-minutos acumulados (limitacion conocida);
    - salto maximo de frecuencia entre horas (DELTA);
    - minimo de 1 ciclo cuando demanda > 1 y maximo JMAX=30.

Suavidad:
    Se conserva el limite DELTA y se agrega una penalizacion configurable
    por cambios absolutos entre frecuencias consecutivas.

Espera:
    Se mantiene espera media teorica = 30/f minutos (intervalos uniformes).
    Para f=0 se utiliza ESPERA_MAX.

No modifica ni reentrena ningun modelo predictivo.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from scipy.optimize import Bounds, LinearConstraint, milp
from scipy.sparse import coo_matrix


# ---------------------------------------------------------------------------
# Parametros operativos heredados o configurables
# ---------------------------------------------------------------------------

HORAS = list(range(4, 23))           # 04:00 a 22:00
HOLGURA_MIN = 31.0                  # minutos entre ciclos del mismo bus
VENTANA_MIN = 19 * 60.0             # ventana de operacion: 04:00-23:00
FLOTA_BASE = 94                     # mantener referencia historica hasta actualizarla
DELTA_FRECUENCIA = 6                # maximo salto entre horas consecutivas
ESPERA_MAX_MIN = 120.0              # politica heredada para una hora sin ciclos
PESO_NO_ATENDIDO = 40.0             # se conserva sin cambios
COSTO_CICLO = 2.0                   # se conserva para optimizaciones sin presupuesto
PESO_CAMBIO_FRECUENCIA = 1.0        # configurable; penaliza cambios absolutos
JMAX = 30
FACTOR_CARGA_BASE = 1.0             # sin factor medido disponible para 2024


# ---------------------------------------------------------------------------
# Rutas de datos
# ---------------------------------------------------------------------------

def _resolver_data_dir(data_dir: str | Path | None = None) -> Path:
    if data_dir is not None:
        return Path(data_dir).expanduser().resolve()

    aqui = Path(__file__).resolve().parent
    candidatos = [aqui / "data", aqui.parent / "data"]
    for candidato in candidatos:
        if candidato.exists():
            return candidato
    # Si todavia no existe, se usa la estructura esperada del proyecto:
    # scripts/fase2_optimizar_definitivo.py y data/ en la raiz.
    return aqui.parent / "data"


def _validar_demanda(serie: pd.Series, nombre: str = "demanda") -> pd.Series:
    serie = pd.Series(serie, dtype=float).sort_index()
    if serie.index.has_duplicates:
        raise ValueError(f"{nombre}: hay horas duplicadas.")
    faltantes = sorted(set(HORAS) - set(int(h) for h in serie.index))
    extras = sorted(set(int(h) for h in serie.index) - set(HORAS))
    if faltantes or extras:
        raise ValueError(
            f"{nombre}: se esperan las horas {HORAS}. "
            f"Faltantes={faltantes}; adicionales={extras}."
        )
    serie.index = serie.index.astype(int)
    serie = serie.reindex(HORAS)
    if not np.isfinite(serie.to_numpy()).all():
        raise ValueError(f"{nombre}: contiene valores NaN o infinitos.")
    if (serie < 0).any():
        raise ValueError(f"{nombre}: no puede contener valores negativos.")
    return serie


def cargar_demanda_historica(
    data_dir: str | Path | None = None,
    archivo: str = "demanda_ruta_2025.csv",
) -> tuple[pd.Series, str]:
    """Promedio de pasajeros por hora en dias laborables usando dias reales."""
    ruta = _resolver_data_dir(data_dir) / archivo
    if not ruta.exists():
        raise FileNotFoundError(f"No se encontro el archivo de demanda: {ruta}")

    dem = pd.read_csv(ruta)
    requeridas = {"hora", "dow", "subidas", "dias"}
    faltan = requeridas - set(dem.columns)
    if faltan:
        raise ValueError(f"{ruta.name}: faltan columnas {sorted(faltan)}.")

    dem = dem[(dem["dow"] >= 1) & (dem["dow"] <= 5)].copy()
    dem["sub_dia"] = dem["subidas"] / dem["dias"].replace(0, np.nan)
    serie = dem.groupby("hora")["sub_dia"].mean().sort_index()
    serie = _validar_demanda(serie, "demanda historica")
    return serie, f"historica ({ruta.name}, promedio laborable)"


def cargar_demanda_modelo(
    ruta_json: str | Path,
    modelo: str,
    fecha: str,
) -> tuple[pd.Series, str]:
    """Carga el pronostico H7/H1 del JSON existente, sin modificarlo."""
    if not fecha:
        raise ValueError("Se requiere una fecha YYYY-MM-DD para la fuente modelo.")

    ruta = Path(ruta_json).expanduser().resolve()
    if not ruta.exists():
        raise FileNotFoundError(f"No existe el pronostico: {ruta}")

    with ruta.open(encoding="utf-8") as archivo:
        pronostico = json.load(archivo)

    fechas = pronostico.get("modelos", {}).get(modelo, {}).get("fechas", {})
    if fecha not in fechas:
        disponibles = ", ".join(sorted(fechas)) or "ninguna"
        raise ValueError(
            f"El modelo {modelo} no contiene {fecha}. Fechas disponibles: {disponibles}"
        )

    serie = pd.Series(
        {int(h): float(v) for h, v in fechas[fecha].items()},
        dtype=float,
    )
    serie = _validar_demanda(serie, f"pronostico {modelo} {fecha}")
    descripcion = (
        f"modelo {modelo} para {fecha} "
        f"(historial hasta {pronostico.get('ultimo_dia_observado', '?')})"
    )
    return serie, descripcion



def cargar_tiempos_ciclo(
    data_dir: str | Path | None = None,
    archivo: str = "ciclo_observado.csv",
) -> tuple[np.ndarray, np.ndarray]:
    """
    Devuelve (duracion_mediana_por_hora, ciclos_observados_promedio).

    Solo utiliza medianas horarias cuando existe una cantidad suficiente
    de viajes observados. Para horas con muestras insuficientes, utiliza
    la mediana de la última hora anterior con datos suficientes.

    Los ciclos observados se conservan como referencia descriptiva. La
    restricción de flota sigue usando los minutos acumulados, no simultaneidad.
    """
    ruta = _resolver_data_dir(data_dir) / archivo
    if not ruta.exists():
        raise FileNotFoundError(f"No se encontro el archivo de ciclos: {ruta}")

    ciclo = pd.read_csv(ruta)
    requeridas = {"hora", "n_viajes", "dur_mediana"}
    faltan = requeridas - set(ciclo.columns)
    if faltan:
        raise ValueError(f"{ruta.name}: faltan columnas {sorted(faltan)}.")

    ciclo = ciclo.set_index("hora").reindex(HORAS)

    duracion = pd.to_numeric(ciclo["dur_mediana"], errors="coerce")
    viajes = pd.to_numeric(ciclo["n_viajes"], errors="coerce").fillna(0.0)

    # Umbral mínimo de observaciones para considerar confiable una mediana.
    MIN_VIAJES = 30

    # Conservar únicamente las medianas con suficientes observaciones.
    duracion_valida = duracion.where(
        (viajes >= MIN_VIAJES) & (duracion > 0)
    )

    # Propagar hacia adelante la última mediana horaria confiable.
    duracion = duracion_valida.ffill()

    # Si las primeras horas no tienen datos suficientes, usar la primera
    # mediana confiable disponible en el horizonte.
    duracion = duracion.bfill()

    # Respaldo final si no existe ninguna hora con datos suficientes.
    duracion = duracion.fillna(230.0).to_numpy(dtype=float)

    n_laborables = len(pd.bdate_range("2025-01-01", "2025-09-01"))
    ciclos_obs = (viajes / n_laborables).to_numpy(dtype=float)

    if not np.isfinite(duracion).all() or (duracion <= 0).any():
        raise ValueError("Los tiempos de ciclo deben ser positivos y finitos.")

    return duracion, ciclos_obs



def normalizar_factor_carga(
    factor_carga: float | list[float] | np.ndarray = FACTOR_CARGA_BASE,
    n_horas: int = len(HORAS),
) -> np.ndarray:
    """Acepta un factor de carga escalar o uno por hora."""
    factor = np.asarray(factor_carga, dtype=float)
    if factor.ndim == 0:
        factor = np.full(n_horas, float(factor))
    if factor.shape != (n_horas,):
        raise ValueError(f"factor_carga debe ser escalar o vector de {n_horas} horas.")
    if not np.isfinite(factor).all() or (factor <= 0).any():
        raise ValueError("factor_carga debe contener valores positivos y finitos.")
    return factor


# ---------------------------------------------------------------------------
# MILP
# ---------------------------------------------------------------------------

def _jmin(demanda_h: float) -> int:
    """Se conserva la regla actual: al menos un ciclo si demanda > 1."""
    return 1 if demanda_h > 1.0 else 0


def resolver(
    demanda_horaria: list[float] | np.ndarray | pd.Series,
    ciclo_min_por_hora: list[float] | np.ndarray,
    *,
    capacidad_bus: float,
    ocupacion_objetivo: float = 1.0,
    factor_carga: float | list[float] | np.ndarray = FACTOR_CARGA_BASE,
    flota_disponible: int = FLOTA_BASE,
    delta: int = DELTA_FRECUENCIA,
    peso_no_atendido: float = PESO_NO_ATENDIDO,
    costo_ciclo: float = COSTO_CICLO,
    peso_cambio_frecuencia: float = PESO_CAMBIO_FRECUENCIA,
    presupuesto_ciclos: int | None = None,
    espera_max_min: float = ESPERA_MAX_MIN,
    
    holgura_min: float = HOLGURA_MIN,
    ventana_min: float = VENTANA_MIN,
    jmax: int = JMAX,
    time_limit: float = 180.0,
) -> dict[str, Any]:
    """
    Resuelve la asignacion entera de ciclos completos por hora.

    capacidad_bus:
        Capacidad nominal elegida por el usuario (pasajeros por bus).

    ocupacion_objetivo:
        Fraccion de la capacidad nominal que se desea utilizar, entre 0 y 1.
        Ejemplo: 0.85 equivale a planificar hasta el 85% de la capacidad.

    factor_carga:
        Factor opcional por hora. Se usa 1.0 mientras no exista una medicion
        valida de ocupacion por viaje/segmento para 2024.

    presupuesto_ciclos:
        Si se especifica, fija el total de ciclos del dia. Si es None, el MILP
        puede decidir el total y aplica costo_ciclo por ciclo.
    """
    demanda = np.asarray(demanda_horaria, dtype=float)
    ciclo_h = np.asarray(ciclo_min_por_hora, dtype=float)
    n = len(HORAS)

    if demanda.shape != (n,) or ciclo_h.shape != (n,):
        raise ValueError(f"demanda_horaria y ciclo_min_por_hora deben tener {n} valores.")
    if not np.isfinite(demanda).all() or (demanda < 0).any():
        raise ValueError("La demanda debe ser finita y no negativa.")
    if not np.isfinite(ciclo_h).all() or (ciclo_h <= 0).any():
        raise ValueError("Los tiempos de ciclo deben ser positivos y finitos.")
    if capacidad_bus <= 0:
        raise ValueError("capacidad_bus debe ser mayor que cero.")
    if not 0 < ocupacion_objetivo <= 1:
        raise ValueError("ocupacion_objetivo debe estar en el intervalo (0, 1].")
    if flota_disponible <= 0 or jmax < 1 or delta < 0:
        raise ValueError("Flota, JMAX y DELTA deben ser valores validos.")
    if peso_no_atendido < 0 or costo_ciclo < 0 or peso_cambio_frecuencia < 0:
        raise ValueError("Los pesos y costos no pueden ser negativos.")
    if presupuesto_ciclos is not None and presupuesto_ciclos < 0:
        raise ValueError("presupuesto_ciclos no puede ser negativo.")

    factor = normalizar_factor_carga(factor_carga, n)
    capacidad_efectiva = float(capacidad_bus) * float(ocupacion_objetivo)
    carga_objetivo = demanda * factor
    jmin = [_jmin(d) for d in demanda]
    nj = jmax + 1

    n_y = n * nj
    n_slack = n
    n_dif = n - 1
    nv = n_y + n_slack + n_dif

    def iy(h: int, j: int) -> int:
        return h * nj + j

    def islack(h: int) -> int:
        return n_y + h

    def idif(h: int) -> int:
        return n_y + n_slack + h

    objetivo = np.zeros(nv)

    for h in range(n):
        for j in range(jmin[h], nj):
            if j == 0:
                objetivo[iy(h, j)] = demanda[h] * espera_max_min
            else:
                espera = 30.0 / j
                objetivo[iy(h, j)] = demanda[h] * espera
                if presupuesto_ciclos is None:
                    objetivo[iy(h, j)] += costo_ciclo * j
        objetivo[islack(h)] = peso_no_atendido

    for h in range(n_dif):
        objetivo[idif(h)] = peso_cambio_frecuencia

    filas, columnas, valores, limites_inf, limites_sup = [], [], [], [], []

    def agregar(entradas: list[tuple[int, float]], inferior: float, superior: float):
        fila = len(limites_inf)
        for columna, valor in entradas:
            if valor != 0:
                filas.append(fila)
                columnas.append(columna)
                valores.append(valor)
        limites_inf.append(inferior)
        limites_sup.append(superior)

    # 1) Elegir exactamente una frecuencia entera por hora.
    for h in range(n):
        agregar(
            [(iy(h, j), 1.0) for j in range(jmin[h], nj)],
            1.0, 1.0,
        )

    # 2) Capacidad efectiva y pasajeros no atendidos.
    for h in range(n):
        entradas = [(iy(h, j), capacidad_efectiva * j) for j in range(1, nj)]
        entradas.append((islack(h), 1.0))
        agregar(entradas, float(carga_objetivo[h]), np.inf)

    # 3) Presupuesto exacto de ciclos, cuando se solicita.
    if presupuesto_ciclos is not None:
        agregar(
            [(iy(h, j), float(j)) for h in range(n) for j in range(1, nj)],
            float(presupuesto_ciclos), float(presupuesto_ciclos),
        )

    # 4) Restriccion heredada de flota: bus-minutos acumulados.
    # No garantiza el maximo simultaneo; se conserva por falta de datos de despacho.
    flota = []
    for h in range(n):
        for j in range(1, nj):
            flota.append((iy(h, j), j * (ciclo_h[h] + holgura_min)))
    agregar(flota, -np.inf, float(flota_disponible * ventana_min))

    # 5) Limite de variacion entre horas consecutivas.
    # 6) Penalizacion lineal del cambio absoluto de frecuencia.
    for h in range(n - 1):
        f_h = [(iy(h, j), float(j)) for j in range(1, nj)]
        f_next = [(iy(h + 1, j), -float(j)) for j in range(1, nj)]

        agregar(f_h + f_next, -np.inf, float(delta))
        agregar(
            [(col, -val) for col, val in f_h + f_next],
            -np.inf, float(delta),
        )

        # d_h >= f_h - f_(h+1)
        agregar(f_h + f_next + [(idif(h), -1.0)], -np.inf, 0.0)
        # d_h >= f_(h+1) - f_h
        agregar(
            [(col, -val) for col, val in f_h + f_next] + [(idif(h), -1.0)],
            -np.inf, 0.0,
        )

    matriz = coo_matrix(
        (valores, (filas, columnas)),
        shape=(len(limites_inf), nv),
    ).tocsr()

    lb = np.zeros(nv)
    ub = np.full(nv, np.inf)
    # Las variables y[h,j] son binarias; slack y diferencias son continuas.
    integrality = np.zeros(nv, dtype=int)
    integrality[:n_y] = 1
    ub[:n_y] = 1.0

    # Desactivar las frecuencias inferiores al mínimo permitido.
    for h in range(n):
        for j in range(jmin[h]):
            ub[iy(h, j)] = 0.0
    restricciones = LinearConstraint(
        matriz,
        np.asarray(limites_inf, dtype=float),
        np.asarray(limites_sup, dtype=float),
    )

    resultado = milp(
        c=objetivo,
        constraints=restricciones,
        integrality=integrality,
        bounds=Bounds(lb, ub),
        options={"time_limit": float(time_limit), "mip_rel_gap": 1e-6},
    )

    if resultado.x is None or not resultado.success:
        return {
            "ok": False,
            "status": resultado.message,
            "solver_status": int(resultado.status),
            "objetivo": None,
        }

    frecuencias = np.zeros(n, dtype=int)
    for h in range(n):
        for j in range(jmin[h], nj):
            if resultado.x[iy(h, j)] > 0.5:
                frecuencias[h] = j
                break

    no_atendidos = np.maximum(
        0.0, carga_objetivo - frecuencias * capacidad_efectiva
    )
    esperas = np.where(
        frecuencias > 0,
        30.0 / np.maximum(frecuencias, 1e-9),
        espera_max_min,
    )
    cambios = np.abs(np.diff(frecuencias)).astype(float)

    return {
        "ok": True,
        "status": resultado.message,
        "solver_status": int(resultado.status),
        "frecuencias": frecuencias,
        "f": frecuencias,  # alias de compatibilidad con el script anterior
        "no_atendidos": no_atendidos,
        "espera_por_hora_min": esperas,
        "espera_promedio_min": float(
            np.average(esperas, weights=np.maximum(demanda, 1e-9))
        ),
        "espera_min": float(
            np.average(esperas, weights=np.maximum(demanda, 1e-9))
        ),
        "espera_total_min": float(np.sum(demanda * esperas)),
        "total_no_atendidos": float(no_atendidos.sum()),
        "pct_no_atendidos": float(
            no_atendidos.sum() / max(carga_objetivo.sum(), 1e-9)
        ),
        "ciclos": int(frecuencias.sum()),
        "capacidad_bus": float(capacidad_bus),
        "ocupacion_objetivo": float(ocupacion_objetivo),
        "capacidad_efectiva": capacidad_efectiva,
        "factor_carga": factor,
        "carga_objetivo": carga_objetivo,
        "cambios_frecuencia": cambios,
        "suma_cambios_frecuencia": float(cambios.sum()),
        "minutos_bus": float(np.sum(frecuencias * (ciclo_h + holgura_min))),
        "minutos_disponibles": float(flota_disponible * ventana_min),
        "buses_equivalentes_promedio": float(
            np.sum(frecuencias * (ciclo_h + holgura_min)) / ventana_min
        ),
        "objetivo": float(resultado.fun),
        "gap_mip": getattr(resultado, "mip_gap", None),
    }


def frecuencia_requerida(
    demanda_horaria: list[float] | np.ndarray,
    *,
    capacidad_bus: float,
    ocupacion_objetivo: float = 1.0,
    factor_carga: float | list[float] | np.ndarray = FACTOR_CARGA_BASE,
) -> np.ndarray:
    """Frecuencia mínima aritmética para cubrir la carga crítica por hora."""
    demanda = np.asarray(demanda_horaria, dtype=float)
    if demanda.shape != (len(HORAS),) or (demanda < 0).any():
        raise ValueError(f"demanda_horaria debe tener {len(HORAS)} valores no negativos.")
    if capacidad_bus <= 0 or not 0 < ocupacion_objetivo <= 1:
        raise ValueError("Capacidad y ocupacion objetivo no validas.")
    
    factor = normalizar_factor_carga(factor_carga, len(HORAS))
    cap_efectiva = capacidad_bus * ocupacion_objetivo
    carga = demanda * factor
    return np.array(
        [
            max(_jmin(demanda[h]), int(np.ceil(carga[h] / cap_efectiva)))
            for h in range(len(HORAS))
        ],
        dtype=int,
    )


def flota_de(
    frecuencias: list[float] | np.ndarray,
    ciclo_min_por_hora: list[float] | np.ndarray,
    *,
    holgura_min: float = HOLGURA_MIN,
    ventana_min: float = VENTANA_MIN,
) -> float:
    """Buses equivalentes promedio según bus-minutos acumulados (no simultaneidad)."""
    f = np.asarray(frecuencias, dtype=float)
    ciclo_h = np.asarray(ciclo_min_por_hora, dtype=float)
    if f.shape != (len(HORAS),) or ciclo_h.shape != (len(HORAS),):
        raise ValueError(f"frecuencias y tiempos deben tener {len(HORAS)} valores.")
    return float(np.sum(f * (ciclo_h + holgura_min)) / ventana_min)


def evaluar_plan(
    frecuencias: list[float] | np.ndarray,
    demanda_real: list[float] | np.ndarray,
    *,
    capacidad_bus: float,
    ocupacion_objetivo: float = 1.0,
    factor_carga: float | list[float] | np.ndarray = FACTOR_CARGA_BASE,
    peso_no_atendido: float = PESO_NO_ATENDIDO,
    espera_max_min: float = ESPERA_MAX_MIN,
) -> dict[str, float]:
    """Evalua un plan con demanda real usando las mismas unidades y supuestos."""
    f = np.asarray(frecuencias, dtype=float)
    demanda = np.asarray(demanda_real, dtype=float)
    if f.shape != (len(HORAS),) or demanda.shape != (len(HORAS),):
        raise ValueError(f"frecuencias y demanda_real deben tener {len(HORAS)} valores.")
    if (f < 0).any() or (demanda < 0).any():
        raise ValueError("Frecuencias y demanda no pueden ser negativas.")
    if capacidad_bus <= 0 or not 0 < ocupacion_objetivo <= 1:
        raise ValueError("Capacidad y ocupacion objetivo no validas.")

    factor = normalizar_factor_carga(factor_carga, len(HORAS))
    cap_efectiva = capacidad_bus * ocupacion_objetivo
    carga = demanda * factor
    no_atendidos = np.maximum(0.0, carga - f * cap_efectiva)
    espera = np.where(f > 0, 30.0 / np.maximum(f, 1e-9), espera_max_min)
    espera_total = float(np.sum(demanda * espera))
    penalizacion_no_atendidos = peso_no_atendido * float(no_atendidos.sum())

    return {
        "espera_total_min": espera_total,
        "espera_promedio_min": float(
            np.average(espera, weights=np.maximum(demanda, 1e-9))
        ),
        "no_atendidos": float(no_atendidos.sum()),
        "costo_espera": espera_total,
        "penalizacion_no_atendidos": penalizacion_no_atendidos,
        "costo": espera_total + penalizacion_no_atendidos,
        "ciclos": float(f.sum()),
    }


# ---------------------------------------------------------------------------
# Ejecucion de consola
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="SOBUSA - optimizacion de ciclos completos mediante MILP"
    )
    parser.add_argument("--fuente", choices=["historica", "modelo"], default="modelo")
    parser.add_argument("--modelo", choices=["H7", "H1"], default="H7")
    parser.add_argument("--fecha", default=None, help="YYYY-MM-DD para H7/H1")
    parser.add_argument("--pronostico", default=None)
    parser.add_argument("--data-dir", default=None)
    parser.add_argument("--capacidad-bus", type=float, required=True,
                        help="Capacidad nominal del bus en pasajeros")
    parser.add_argument("--ocupacion-objetivo", type=float, default=1.0,
                        help="Fraccion de capacidad permitida, entre 0 y 1")
    parser.add_argument("--factor-carga", type=float, default=FACTOR_CARGA_BASE,
                        help="Factor de carga; 1.0 mientras no exista medicion valida 2024")
    parser.add_argument("--flota", type=int, default=FLOTA_BASE)
    parser.add_argument("--delta", type=int, default=DELTA_FRECUENCIA)
    parser.add_argument("--peso-cambio-frecuencia", type=float,
                        default=PESO_CAMBIO_FRECUENCIA)
    parser.add_argument("--presupuesto-ciclos", type=int, default=None)
    parser.add_argument("--time-limit", type=float, default=180.0)
    args = parser.parse_args()

    data_dir = _resolver_data_dir(args.data_dir)
    if args.fuente == "historica":
        demanda_serie, fuente = cargar_demanda_historica(data_dir)
        fecha = None
    else:
        if not args.pronostico:
            ruta_json = data_dir / "pronostico_demanda_ruta.json"
        else:
            ruta_json = Path(args.pronostico)
        demanda_serie, fuente = cargar_demanda_modelo(
            ruta_json, args.modelo, args.fecha
        )
        fecha = args.fecha

    ciclo_h, ciclos_obs = cargar_tiempos_ciclo(data_dir)
    demanda = demanda_serie.to_numpy(dtype=float)

    resultado = resolver(
        demanda,
        ciclo_h,
        capacidad_bus=args.capacidad_bus,
        ocupacion_objetivo=args.ocupacion_objetivo,
        factor_carga=args.factor_carga,
        flota_disponible=args.flota,
        delta=args.delta,
        peso_cambio_frecuencia=args.peso_cambio_frecuencia,
        presupuesto_ciclos=args.presupuesto_ciclos,
        time_limit=args.time_limit,
    )

    print("=" * 76)
    print("SOBUSA | OPTIMIZACION DE FRECUENCIAS")
    print("=" * 76)
    print(f"Fuente de demanda       : {fuente}")
    print(f"Unidad                  : pasajeros/hora, ruta completa, ambos sentidos")
    print(f"Unidad de decision      : ciclos completos (ida + vuelta) por hora")
    print(f"Capacidad nominal       : {args.capacidad_bus:.1f} pasajeros/bus")
    print(f"Ocupacion objetivo      : {args.ocupacion_objetivo:.1%}")
    print(f"Capacidad efectiva      : {args.capacidad_bus * args.ocupacion_objetivo:.1f}")
    print(f"Factor de carga         : {args.factor_carga:.3f} (supuesto, no medido en 2024)")
    print(f"Flota disponible        : {args.flota}")
    print(f"Presupuesto de ciclos   : {args.presupuesto_ciclos}")
    print(f"Peso cambio frecuencia  : {args.peso_cambio_frecuencia}")
    print()

    if not resultado["ok"]:
        print(f"No se obtuvo solucion optima: {resultado['status']}")
        raise SystemExit(2)

    print(f"Demanda total           : {demanda.sum():,.0f} pasajeros/dia")
    print(f"Ciclos optimizados      : {resultado['ciclos']}")
    print(f"Buses equivalentes      : {resultado['buses_equivalentes_promedio']:.1f}")
    print(f"Espera promedio         : {resultado['espera_promedio_min']:.2f} min")
    print(f"Espera total            : {resultado['espera_total_min']:,.1f} pasajero-min")
    print(f"No atendidos            : {resultado['total_no_atendidos']:,.1f}")
    print(f"Cambios entre horas     : {resultado['suma_cambios_frecuencia']:.0f}")
    print()
    tabla = pd.DataFrame({
        "hora": HORAS,
        "demanda": demanda,
        "frecuencia_ciclos": resultado["frecuencias"],
        "headway_min": np.where(
            resultado["frecuencias"] > 0,
            60 / np.maximum(resultado["frecuencias"], 1),
            np.nan,
        ),
        "no_atendidos": resultado["no_atendidos"],
        "espera_min": resultado["espera_por_hora_min"],
    })
    print(tabla.to_string(index=False, formatters={
        "demanda": "{:,.1f}".format,
        "headway_min": "{:.1f}".format,
        "no_atendidos": "{:,.1f}".format,
        "espera_min": "{:.1f}".format,
    }))

    salida = {
        "ruta": "KRA 54 (CRA 54)",
        "fecha": fecha,
        "fuente_demanda": fuente,
        "unidad_demanda": "pasajeros por hora, ruta completa, ambos sentidos",
        "unidad_decision": "ciclos completos ida y vuelta por hora",
        "parametros": {
            "capacidad_bus": args.capacidad_bus,
            "ocupacion_objetivo": args.ocupacion_objetivo,
            "capacidad_efectiva": args.capacidad_bus * args.ocupacion_objetivo,
            "factor_carga": args.factor_carga,
            "factor_carga_es_medicion": False,
            "flota_disponible": args.flota,
            "delta": args.delta,
            "peso_cambio_frecuencia": args.peso_cambio_frecuencia,
            "presupuesto_ciclos": args.presupuesto_ciclos,
            "peso_no_atendido": PESO_NO_ATENDIDO,
            "espera_max_min": ESPERA_MAX_MIN,
            "holgura_min": HOLGURA_MIN,
        },
        "resultado": {
            "frecuencias_por_hora": {
                str(h): int(resultado["frecuencias"][i])
                for i, h in enumerate(HORAS)
            },
            "no_atendidos_por_hora": {
                str(h): float(resultado["no_atendidos"][i])
                for i, h in enumerate(HORAS)
            },
            "ciclos_totales": resultado["ciclos"],
            "espera_promedio_min": resultado["espera_promedio_min"],
            "espera_total_min": resultado["espera_total_min"],
            "no_atendidos_total": resultado["total_no_atendidos"],
            "buses_equivalentes_promedio": resultado["buses_equivalentes_promedio"],
        },
        "limitaciones": [
            "El factor de carga no se reconstruye con panel y demanda: no hay "
            "identificacion por viaje y carga por segmento. Se usa 1.0 como "
            "supuesto conservador, no como medicion de 2024.",
            "La restriccion de flota conserva bus-minutos acumulados y no garantiza "
            "el maximo de buses simultaneamente ocupados.",
            "La espera 30/f supone salidas uniformes dentro de cada hora.",
            "La demanda agregada no se divide por sentido; cada decision es un ciclo "
            "completo de ida y vuelta.",
        ],
    }

    nombre = (
        f"fase2_optimizacion_{args.modelo}_{fecha}.json"
        if args.fuente == "modelo"
        else "fase2_optimizacion_historica.json"
    )
    ruta_salida = data_dir / nombre
    ruta_salida.parent.mkdir(parents=True, exist_ok=True)
    ruta_salida.write_text(
        json.dumps(salida, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    print()
    print(f"Resultado guardado: {ruta_salida}")


if __name__ == "__main__":
    main()
    
