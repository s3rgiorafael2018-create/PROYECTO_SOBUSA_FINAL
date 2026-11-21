# SOBUSA · Integración CRA 54 / Calle 72

## Instalación

1. Extraer `DASH/` en una carpeta nueva. Se excluyó el entorno `.conda` del ZIP para reducir tamaño y evitar copiar binarios de Windows a otros equipos.
2. Restaurar tu archivo `.env` existente en `DASH/.env`. **No se incluye ninguna credencial en este ZIP.**
3. Restaurar los archivos históricos de CRA 54 `panel_*.csv` y `servicio_*.csv` en `DASH/data/panel_horario/` (se omitieron del ZIP original). Los 64 CSV de Calle 72 **sí se incluyen** en `DASH/data/cl72/panel_horario/`.
4. Crear entorno e instalar dependencias: `pip install -r requirements.txt`.
5. En terminal A, desde `DASH/`: `uvicorn api.main:app --host 127.0.0.1 --port 8000`.
6. En terminal B, desde `DASH/`: `python app.py`. Navegar a `http://127.0.0.1:8050` e iniciar sesión con la autenticación que ya usabas.
7. Usar las pestañas superiores CRA 54 / Calle 72. La ruta se propaga en la URL (`?ruta=16` o `?ruta=21`) y se conserva en la navegación.

## Qué cambió

- Selector común en `app.py` para las ocho páginas y navegación que conserva ruta.
- `utils/rutas_config.py`: mapa cerrado por ID de los archivos de cada ruta.
- `utils/data_loader.py`: vistas DuckDB separadas (`v_panel` y `v_panel_cl72`) con caché parametrizada por ruta.
- Predicción API `POST /predictions/run`, optimización API `POST /optimization/run` y metadatos `GET /model/info` aceptan `idruta`, con 16 como valor compatible por defecto.
- Persistencia separada: CRA 54 sigue en `data/resultados/ultima_*.json`, Calle 72 usa `data/resultados/cl72/ultima_*.json`.
- Páginas históricas, calidad, rendimiento, resultados y predicción/optimización consumen la ruta seleccionada.
- LightGBM por nodo carga sus características desde el metadato de la ruta: CRA 54 tiene 16 y Calle 72 tiene 20. El tablero de predicción/optimización, como antes, consulta pronósticos H7 ya calculados; **no realiza inferencia LightGBM en vivo**.
- Para Calle 72 el menú de optimización solo ofrece H7, porque el archivo de pronósticos suministrado no incluye H1.

## Limitaciones y comprobaciones pendientes en tu computadora

- Se comprobó la sintaxis de Python; se probaron ambos modelos LightGBM y los endpoints de información, pronóstico y optimización para ambas rutas utilizando los artefactos del ZIP.
- **No se pudo iniciar Dash ni probar sus callbacks visuales en este entorno**: faltaban las bibliotecas `dash` y `duckdb`, y el acceso a PyPI no estaba disponible. Verificar la navegación y los filtros de las ocho páginas al iniciar la aplicación local.
- El panel histórico CRA 54 no estaba en el ZIP original, por lo que hay que restaurarlo para que las páginas de histórico/calidad funcionen en esa ruta.
- El enriquecimiento OpenStreetMap de Calle 72 conserva las referencias que estaban disponibles; algunas no cuentan con dirección/lugar destacado.
- Los pronósticos H7 de ambos archivos se limitan al horizonte generado en 2025 (no son pronósticos actuales).
- Los parámetros predeterminados de flota/presupuesto son los del Dashboard existente: ajustarlos antes de interpretar las simulaciones de Calle 72 como propuestas operativas.
- La ingeniería de características de `DataService` sigue siendo el procedimiento original de CRA 54. Para inferencia online por nodo de Calle 72 habría que implementar las cuatro características adicionales; **eso no es necesario para la visualización H7 actual**.

## Verificación rápida de la API

Con ambos procesos arriba:

```bash
curl "http://127.0.0.1:8000/model/info?idruta=16"
curl "http://127.0.0.1:8000/model/info?idruta=21"
```

En `http://127.0.0.1:8050/?ruta=21`, comprueba sucesivamente Predicción, Optimización, Resumen, Alertas, Histórico, Modelos, Calidad y Resultados. Cambia a CRA 54 y comprueba que las fuentes cambien.
