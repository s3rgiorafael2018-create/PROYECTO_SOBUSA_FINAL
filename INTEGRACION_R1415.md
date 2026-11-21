# Integración de la tercera ruta — 14-15 (idruta=2)

Se partió de `DASHv2.zip` y se incorporaron los datos de `r1415-20261120T215729Z-1-001.zip` sin modificar los archivos existentes de CRA 54 ni Calle 72.

## Datos incorporados

- `data/r1415/panel_horario`: 8 `panel_YYYYMM.csv` y 8 `servicio_YYYYMM.csv` (enero–agosto de 2025).
- `data/r1415/grafo_r1415.json`: 14 nodos y 13 aristas. Los 14 nodos figuran en el panel horario.
- `data/r1415/modelos/lgbm_r1415.txt` y `lgbm_r1415_meta.json` (20 características).
- `data/r1415/modelos/ruta_H7.txt`, `ruta_H7_meta.json`, `ruta_H1.txt`, `ruta_H1_meta.json`.
- `data/r1415/pronostico_demanda_ruta.json` y `data/r1415/ciclo_observado.csv`, además de sus demás CSV/JSON/HTML originales.

El ID oficial usado por los JSON de 14-15 es **2**, no 14 ni 15. En la interfaz se muestra «Ruta 14-15».

## Cambios en el código

1. `utils/rutas_config.py`: registro único de las tres rutas (16, 21 y 2), modelo y archivos asociados; detección de H7/H1 por disponibilidad.
2. `app.py`: tercera pestaña global y navegación con `?ruta=2`; registro de callbacks antes de arrancar el servidor.
3. `utils/data_loader.py`: vista `v_panel_r1415` independiente en DuckDB; los paneles de otras rutas no se mezclan.
4. `utils/resultados_store.py`: predicción y optimización para 14-15 en `data/resultados/r1415/`.
5. `pages/02_Prediccion_demanda.py`: 14-15 en selector y textos de ruta.
6. `pages/03_optimizacion.py`: muestra solo los horizontes H7/H1 disponibles por cada ruta.
7. `api/main.py`: metadatos H7 compatibles con archivos que no registran `entrenar_desde` (en ese caso devuelve `null`, sin inventar el dato).
8. Se mantienen las páginas existentes, incluido `pages/04_Alertas.py` con `def layout(**_)`.

## Para ejecutar en Windows / local

1. Descomprimir `DASHv3` en una nueva carpeta (no reemplazar archivos originales sin respaldo).
2. Copiar el `.env` propio de la instalación anterior a la raíz `DASHv3/.env` (no se distribuye en el ZIP).
3. Copiar de su instalación anterior los CSV existentes de **CRA 54** a `DASHv3/data/panel_horario/`, y los de **Calle 72** a `DASHv3/data/cl72/panel_horario/`. Los 16 CSV de **14-15** ya están dentro del ZIP.
4. Desde el entorno con dependencias instaladas, iniciar FastAPI desde la raíz: `uvicorn api.main:app --reload`.
5. En otra consola, desde la misma raíz, iniciar Dash: `python app.py`.
6. Probar el selector CRA 54 / Calle 72 / Ruta 14-15 en las ocho páginas, especialmente Alertas.
7. Probar H7 para las fechas entre 2025-08-31 y 2025-09-06. El modelo **H1** de 14-15 (y el de CRA54) solo tiene fecha 2025-08-31; el usuario debe seleccionar esa fecha en Optimización.

Si se omiten los CSV de CRA 54 y Calle 72, sus páginas históricas y de calidad informarán que no hay datos, aunque sus pronósticos y optimizaciones H7 siguen disponibles.

## Validaciones realizadas durante la integración

- Los 33 archivos Python pasaron validación sintáctica.
- Se confirmó la correspondencia de los 14 `idpunto` entre grafo y panel 14-15.
- En la carga histórica 14-15 se encontraron 54.240 celdas originales de panel, 47.591 celdas con servicio tras el proceso de limpieza y unión; sin `pos_rel` faltantes.
- Los modelos LightGBM se cargaron para CRA54 (16 características), CL72 (20) y 14-15 (20).
- FastAPI TestClient: `/model/info`, `/predictions/run` (133 registros H7) y `/optimization/run` (19 horas) respondieron con éxito en las tres rutas; también se probó H1 de 14-15.
- Las rutas ajenas a 16/21/2 reciben error 400 en la API.

**Limitación de verificación:** este entorno no tiene instalados Dash y DuckDB, ni contiene el `.env` ni los paneles de CRA54 y CL72. Por ello no se comprobó en un navegador el rendering de las ocho páginas ni las consultas DuckDB reales. Estas verificaciones deben hacerse en la máquina que ya ejecuta el dashboard.

**Los pronósticos del ZIP son históricos**, no predicciones actualizadas a noviembre de 2026; se muestran exactamente las fechas guardadas en los JSON.
