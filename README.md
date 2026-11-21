# SOBUSA v1.0 — Dashboard de demanda y optimización de frecuencias

Dashboard multipágina desarrollado con **Dash** y **FastAPI** para consultar pronósticos horarios de demanda de pasajeros de la ruta **KRA 54 (idruta 16)**, simular frecuencias de servicio y revisar resultados, alertas y calidad de los datos.

> **Alcance de v1.0:** la predicción operativa utiliza el pronóstico **H7** previamente calculado y almacenado en `data/pronostico_demanda_ruta.json`. No realiza inferencia para fechas arbitrarias en tiempo de ejecución. El horizonte disponible en el archivo actual comprende **2025-08-31 a 2025-09-06**, sujeto a que dicho archivo esté presente.

Esta guía contempla dos formas de ejecución:

- **Desarrollo local:** entorno virtual de Python y dos procesos independientes (FastAPI y Dash).
- **Ejecución con Docker:** contenedores para FastAPI y Dash mediante Docker Compose. Docker construye su propio entorno y no requiere activar `.venv` en el equipo anfitrión.

## 1. Requisitos previos

- **Python 3.11 o superior** (entorno utilizado durante el desarrollo: Python 3.11.18).
- **Git**, para clonar el repositorio.
- **Windows con PowerShell** para los comandos de esta guía; en Linux/macOS cambian los comandos de activación del entorno.
- Para Docker: **Docker Desktop** en Windows o Docker Engine en Linux, con **Docker Compose v2**.
- Archivos de datos y pronósticos necesarios, que pueden no estar incluidos en el repositorio.
- Acceso a los recursos externos que requiera la configuración local (por ejemplo, Google Drive o PostgreSQL), si esas integraciones están habilitadas.

Comprobar las herramientas:

```powershell
python --version
git --version
docker --version
docker compose version
```

Docker Desktop debe estar iniciado antes de ejecutar los comandos de Docker.

## 2. Obtener el proyecto

En una terminal de PowerShell:

```powershell
git clone <URL_DEL_REPOSITORIO>
cd <CARPETA_DEL_REPOSITORIO>
```

Si ya tienes el proyecto descargado, abre su carpeta raíz en VS Code y continúa con el siguiente paso.

Ejecuta los comandos desde la raíz del repositorio, donde se encuentran `app.py`, `requirements.txt`, `Dockerfile` y `compose.yaml` (si se utiliza Docker).

## 3. Crear y activar el entorno virtual (desarrollo local)

Comprueba la versión de Python:

```powershell
python --version
```

Crea un entorno virtual desde la raíz del repositorio:

```powershell
py -3.11 -m venv .venv
```

Actívalo:

```powershell
.\.venv\Scripts\Activate.ps1
```

Si PowerShell bloquea la activación, puedes habilitarla **solo para esa sesión**:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\.venv\Scripts\Activate.ps1
```

Verifica que el intérprete activo pertenezca al entorno:

```powershell
python -c "import sys; print(sys.executable)"
```

> Este entorno se utiliza para ejecutar el proyecto directamente en el equipo. No es necesario crearlo para ejecutar los contenedores Docker: la imagen instala las dependencias definidas en `requirements.txt`.

## 4. Instalar dependencias (desarrollo local)

Con `.venv` activado:

```powershell
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python -m pip check
```

El proyecto utiliza Dash y Plotly para la interfaz, FastAPI y Uvicorn para los servicios, pandas/NumPy para los datos y SciPy para componentes numéricos. El archivo `requirements.txt` también contempla dependencias de autenticación y Google Drive.

> **Nota:** las dependencias se identificaron a partir del entorno de desarrollo. Antes de considerar la instalación completamente reproducible, es necesario validar las importaciones del repositorio y la disponibilidad del solver utilizado por el optimizador.

## 5. Verificar la estructura y los datos

La estructura relevante es aproximadamente:

```text
SOBUSA/
├── app.py
├── requirements.txt
├── Dockerfile
├── compose.yaml
├── .env.example
├── api/
│   ├── main.py
│   └── services/
├── pages/
│   ├── 01_resumen_operativo.py
│   ├── 02_Prediccion_demanda.py
│   ├── 03_optimizacion.py
│   ├── 06_rendimiento_modelos.py
│   ├── 07_calidad_datos.py
│   └── 08_resultados_kra54.py
├── utils/
│   ├── data_loader.py
│   └── resultados_store.py
├── data/
│   ├── panel_horario/
│   │   ├── panel_*.csv
│   │   └── servicio_*.csv
│   ├── modelos/
│   │   └── ruta_H7_meta.json
│   ├── pronostico_demanda_ruta.json
│   └── resultados/
└── fase2_optimizar_definitivo.py
```

Los nombres pueden variar según la versión del repositorio. Antes de iniciar, comprueba especialmente:

- `data/pronostico_demanda_ruta.json`: fuente del pronóstico H7 para predicción y optimización.
- `data/modelos/ruta_H7_meta.json`: metadatos y métricas que muestra la página de rendimiento.
- `data/panel_horario/panel_*.csv` y `servicio_*.csv`: fuentes de la página de calidad de datos.
- `fase2_optimizar_definitivo.py`: lógica de optimización utilizada por FastAPI.

Si los datos no se publican en Git por confidencialidad o tamaño, deben copiarse a las rutas correspondientes por un canal autorizado. **No publiques archivos privados ni credenciales en el repositorio.**

### Datos externos al repositorio

Si `data/` está excluida de Git, clonar el repositorio no descarga esos archivos. Cada integrante debe obtenerlos por el canal autorizado y ubicarlos en las rutas esperadas. Para Docker, los datos también deben quedar disponibles dentro del contenedor. Si el código espera la carpeta `/app/data`, puede montarse desde el equipo anfitrión mediante un volumen, por ejemplo:

```yaml
services:
  api:
    volumes:
      - ./data:/app/data:ro
  dash:
    volumes:
      - ./data:/app/data:ro
```

Agrega este bloque dentro de los servicios que realmente lean archivos de `data/`. El sufijo `:ro` monta los datos como solo lectura; si la aplicación necesita escribir resultados en `data/resultados/`, no uses solo lectura para ese directorio o configura un volumen separado con permisos de escritura. Verifica que la ruta de destino (`/app/data`) coincida con el `WORKDIR` y las rutas utilizadas por el código en el `Dockerfile`.

## 6. Configurar variables de entorno y autenticación

Si el proyecto utiliza un archivo `.env`, créalo en la raíz con las variables que realmente lea tu código. Si existe `.env.example`, úsalo como plantilla.

**Windows PowerShell:**

```powershell
Copy-Item .env.example .env
```

**Linux/macOS:**

```bash
cp .env.example .env
```

Si no existe `.env.example`, crea `.env` manualmente con la estructura documentada por el proyecto. No inventes credenciales ni valores de conexión. Revisa especialmente la configuración del cliente HTTP de Dash (dirección de FastAPI), las opciones de autenticación y cualquier integración opcional con Google Drive o PostgreSQL.

### Credenciales de acceso a Dash

Para una instalación de prueba se puede utilizar la cuenta predeterminada:

- **Usuario:** `isaac`
- **Contraseña:** `isaac`

La autenticación se configura mediante la variable `AUTH_USERS` en `.env`. La contraseña no debe guardarse en texto plano en esa variable: se almacena su hash bcrypt.

Si se desea conservar la cuenta predeterminada, `AUTH_USERS` debe contener el usuario `isaac` y el hash bcrypt correspondiente a la contraseña `isaac`, según la configuración de desarrollo distribuida para el proyecto.

Como alternativa, cada integrante puede crear su propia contraseña y generar un hash bcrypt desde un entorno donde esté instalada la librería `bcrypt`:

```powershell
python -c "import bcrypt,getpass; print(bcrypt.hashpw(getpass.getpass('Contraseña: ').encode()[:72], bcrypt.gensalt(12)).decode())"
```

Copia el hash generado en `AUTH_USERS`, siguiendo esta estructura:

```dotenv
AUTH_USERS='{"nombre_usuario": "HASH_BCRYPT_GENERADO"}'
```

Para usar el usuario `isaac` con una contraseña propia, reemplaza el valor del hash asociado a `isaac`. Después de modificar `.env`, reinicia los servicios para que tomen la nueva configuración.

> **Seguridad:** `isaac/isaac` es una cuenta predeterminada únicamente para pruebas o desarrollo. No debe utilizarse en una instalación pública o productiva. Cambia la contraseña por una robusta antes de exponer el dashboard. No publiques `.env`, hashes de contraseñas, claves de sesión ni contraseñas de bases de datos en GitHub. Cada integrante debe utilizar credenciales externas propias y autorizadas.

### URL de FastAPI según el modo de ejecución

La dirección que utiliza Dash para comunicarse con FastAPI depende de dónde se ejecutan los procesos:

- **Ejecución local:** `http://127.0.0.1:8000`.
- **Dash y FastAPI en Docker Compose:** `http://api:8000`, usando el nombre del servicio `api` como host dentro de la red de Compose.

Si el código utiliza `SOBUSA_API_URL`, configura esa variable con la dirección correspondiente. Si utiliza `API_URL`, configura esa variable en el entorno de Dash. Comprueba el nombre exacto leyendo la configuración del cliente HTTP en el código. No uses `127.0.0.1` para la comunicación entre contenedores: dentro del contenedor Dash, esa dirección apunta al propio contenedor Dash, no al contenedor de FastAPI.

Mantén `.env` y los archivos de credenciales fuera de Git. El `.gitignore` debe excluir `.env` y permitir que `.env.example` (si existe) se publique únicamente con valores de ejemplo y sin secretos.

## 7. Iniciar FastAPI (desarrollo local, terminal 1)

Abre una terminal en la raíz del proyecto, activa el entorno y ejecuta:

```powershell
.\.venv\Scripts\Activate.ps1
python -m uvicorn api.main:app --reload --host 127.0.0.1 --port 8000
```

Comprueba que el servidor esté activo:

- Documentación interactiva: [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)
- Endpoint de información del modelo, si está habilitado: [http://127.0.0.1:8000/model/info](http://127.0.0.1:8000/model/info)

Deja esta terminal abierta. Que la ruta raíz `/` responda `{"detail":"Not Found"}` no significa necesariamente que FastAPI esté fallando: puede que la aplicación no defina un endpoint raíz. Comprueba `/docs` y los endpoints declarados.

## 8. Iniciar Dash (desarrollo local, terminal 2)

Abre **otra** terminal en la misma carpeta, activa el entorno y ejecuta:

```powershell
.\.venv\Scripts\Activate.ps1
python app.py
```

Abre el dashboard en tu navegador:

**http://127.0.0.1:8050**

Si `app.py` configura otro puerto, utiliza el que aparezca en la terminal. FastAPI debe permanecer ejecutándose para que funcionen las solicitudes de predicción y optimización.

## 9. Ejecución con Docker Compose

Esta alternativa inicia FastAPI y Dash en contenedores separados. No necesitas activar `.venv` ni instalar `requirements.txt` en el equipo anfitrión; la imagen instala las dependencias durante la construcción.

### 9.1. Requisitos y archivos

- Docker Desktop iniciado (Windows) o Docker Engine y Compose v2 (Linux).
- `Dockerfile` en la raíz del proyecto.
- `compose.yaml` en la raíz del proyecto.
- Archivo `.env` local con las variables necesarias para Dash.
- Datos requeridos por la aplicación, disponibles en el contenedor mediante `COPY` o volúmenes, según la configuración del proyecto.

### 9.2. Construir e iniciar los servicios

Desde la raíz del repositorio:

```powershell
docker compose up -d --build
```

El comando construye la imagen a partir del `Dockerfile` y levanta los servicios definidos en `compose.yaml`. La primera ejecución puede tardar mientras descarga la imagen base e instala las dependencias.

Verifica el estado:

```powershell
docker compose ps
```

Consulta los registros:

```powershell
docker compose logs -f
```

Para revisar un servicio específico:

```powershell
docker compose logs -f dash
docker compose logs -f api
```

### 9.3. Direcciones de acceso

Con el mapeo de puertos configurado como en el proyecto:

- **Dashboard Dash:** [http://localhost:8050](http://localhost:8050)
- **FastAPI:** [http://localhost:8000](http://localhost:8000)
- **Documentación de FastAPI:** [http://localhost:8000/docs](http://localhost:8000/docs)

Desde el navegador del equipo anfitrión se utiliza `localhost`. Entre contenedores, Dash debe comunicarse con FastAPI usando el nombre del servicio de Compose, por ejemplo `http://api:8000`.

### 9.4. Comandos de administración

Detener y eliminar los contenedores de este proyecto:

```powershell
docker compose down
```

Volver a construir y levantar los servicios después de cambios en el código o dependencias:

```powershell
docker compose up -d --build
```

Reiniciar los servicios:

```powershell
docker compose restart
```

Entrar a una terminal del contenedor Dash:

```powershell
docker compose exec dash sh
```

Comprobar desde el contenedor Dash que la variable de autenticación esté cargada:

```powershell
docker compose exec dash python -c "import os; print(bool(os.getenv('AUTH_USERS')))"
```

El resultado `True` indica que la variable existe en el entorno del contenedor; no valida por sí solo que el usuario y el hash sean correctos.

### 9.5. Consideraciones para compartir el proyecto

Con la configuración basada en `build:`, cada persona que clone el repositorio construye localmente la imagen mediante `docker compose up -d --build`. No necesita descargar una imagen publicada en Docker Hub.

Para que otra persona pueda ejecutarlo:

1. Comparte el repositorio con el código, `Dockerfile`, `compose.yaml`, `requirements.txt` y, si aplica, `.env.example`.
2. No incluyas `.env` ni credenciales privadas en Git.
3. Proporciona los archivos de datos que no estén versionados mediante un canal autorizado y explica dónde deben ubicarse.
4. Cada integrante debe crear su propio `.env` y disponer de los permisos de acceso a los servicios externos que necesite.
5. Asegúrate de que el `Dockerfile` copie el código necesario y que los volúmenes de `compose.yaml` monten los datos requeridos.

Si se decide publicar imágenes preconstruidas en un registro como Docker Hub o GHCR, habría que configurar `image:` en Compose y definir el proceso de publicación y descarga. Esa no es la modalidad actual cuando el archivo usa `build:`.

> **Nota de producción:** si los contenedores se van a exponer públicamente, revisa el servidor de ejecución de Dash, autenticación, secretos, HTTPS, permisos de datos y configuración de FastAPI. No asumas que el servidor de desarrollo de Dash es apropiado para producción.

## 10. Recorrido de prueba

1. **Predicción de demanda:** selecciona la ruta KRA 54, la fecha **2025-09-01** y un horizonte de **1 día**. Comprueba que aparezcan las predicciones horarias H7.
2. **Optimización:** ejecuta la simulación con el modelo **H7** y la misma fecha. Comprueba las frecuencias, esperas y pasajeros no atendidos.
3. **Resumen operativo:** verifica que muestre los resultados de predicción y optimización con unidades coherentes de pasajeros por hora.
4. **Rendimiento de modelos:** verifica que lea las métricas H7 desde `ruta_H7_meta.json`.
5. **Calidad de datos:** revisa completitud, validez, duplicados y consistencia del panel horario.
6. **Resultados KRA 54:** revisa la demanda prevista del horizonte y, si existe una optimización guardada, las frecuencias propuestas.

El archivo de pronósticos actual contiene siete fechas, del 31 de agosto al 6 de septiembre de 2025, y horas de operación de **04:00 a 22:00**. Para horizontes de varios días, la fecha inicial y el número de días deben quedar dentro de ese intervalo.

## 11. Persistencia de resultados

El proyecto puede guardar la última predicción y optimización en:

```text
data/resultados/ultima_prediccion.json
data/resultados/ultima_optimizacion.json
```

Estos archivos son resultados de ejecución y pueden no existir en una instalación nueva. No se deben confundir con los archivos fuente del modelo. Si cambias la estructura de las respuestas de la API, elimina resultados antiguos incompatibles antes de volver a probar.

Si `data/resultados/` se monta como volumen de Docker, comprueba que el contenedor tenga permisos de escritura en esa carpeta.

## 12. Problemas frecuentes

| Problema | Comprobación sugerida |
|---|---|
| `ModuleNotFoundError` | En ejecución local, activa `.venv` e instala `requirements.txt`. En Docker, revisa el proceso de construcción y los registros. |
| Dash no conecta con FastAPI | Comprueba que FastAPI esté activo y revisa la URL configurada. En Compose utiliza `http://api:8000` para la comunicación entre contenedores. |
| FastAPI responde `{"detail":"Not Found"}` en `/` | Comprueba `/docs`; puede no existir un endpoint raíz. |
| No hay pronósticos para una fecha | El JSON H7 actual solo contiene 2025-08-31 a 2025-09-06. |
| La página de calidad aparece vacía | Verifica los archivos CSV en `data/panel_horario/` y que estén disponibles dentro del contenedor. |
| Falla la optimización | Revisa el error de la terminal de FastAPI, los datos H7 y la disponibilidad del solver. |
| No aparecen métricas del modelo | Comprueba la ruta `data/modelos/ruta_H7_meta.json`. |
| El puerto está ocupado | Cierra el proceso anterior o ajusta el puerto y la configuración correspondiente. |
| Dash no encuentra `AUTH_USERS` en Docker | Comprueba que el servicio `dash` cargue el archivo `.env` mediante `env_file:` y vuelve a crear los contenedores. |
| Los datos existen en el equipo, pero no en Docker | Comprueba que se hayan copiado a la imagen o montado mediante `volumes:` en la ruta que utiliza la aplicación. |

## 13. Limitaciones conocidas de v1.0

- **Pronósticos precomputados:** la predicción H7 se consulta desde JSON; no genera nuevos horizontes fuera de las fechas disponibles.
- **Trazabilidad del modelo pendiente:** `ruta_H7_meta.json` registra la corrección de deriva «pesos por recencia», mientras que `pronostico_demanda_ruta.json` registra «nivel reciente como offset». Hasta regenerar o verificar ambos artefactos, no se debe afirmar que las métricas del primero validan exactamente los pronósticos del segundo.
- **Resultados de optimización simulados:** las frecuencias y esperas propuestas no representan despachos observados en tiempo real.
- **Integridad relacional:** el control de llaves y catálogos de la página de calidad permanece pendiente si no se ha implementado la verificación contra la base de datos.

## 14. Detener los servicios

### Desarrollo local

En cada una de las dos terminales, presiona **Ctrl+C**. Para salir del entorno virtual:

```powershell
deactivate
```

### Docker Compose

Desde la raíz del proyecto:

```powershell
docker compose down
```

---

**Estado:** SOBUSA v1.0 — dashboard de desarrollo local y ejecución contenerizada. Antes de desplegarlo públicamente, revisar autenticación, protección de datos, configuración de producción y validación integral de dependencias.

## Tercera ruta: 14-15

La versión DASHv3 incorpora la ruta 14-15 (`idruta=2`) con sus modelos y panel enero-agosto 2025. Consulte `INTEGRACION_R1415.md` para rutas, pruebas e instrucciones de instalación (también explica cómo restaurar los paneles CRA54 y Calle72).
