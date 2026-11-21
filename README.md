# DASHv3 — Instalación y ejecución con Docker

Esta guía describe cómo preparar el proyecto desde cero, configurar las variables de entorno, disponer de los datos y levantar los servicios Dash y FastAPI mediante Docker Compose.

## 1. Requisitos

Instalar en el equipo:

- Git.
- Miniconda o Anaconda (para crear el entorno de desarrollo y ejecutar tareas locales, si se requieren).
- Docker Desktop en Windows, o Docker Engine y Docker Compose v2 en Linux.
- Acceso autorizado a PostgreSQL, si se va a utilizar esa fuente de datos.

Comprobar las instalaciones:

```bash
git --version
conda --version
docker --version
docker compose version
```

Docker Desktop debe estar iniciado antes de ejecutar los comandos de Docker.

## 2. Descargar el repositorio

```bash
git clone <URL_DEL_REPOSITORIO>
cd DASHv3
```

Ejecutar los siguientes comandos desde la carpeta raíz del proyecto, donde se encuentran `Dockerfile` y `compose.yaml`.

## 3. Crear el entorno Conda (desarrollo local)

Este entorno sirve para ejecutar y probar el proyecto directamente en el equipo, fuera de Docker. No es un requisito para ejecutar los contenedores: Docker construye su propio entorno a partir del `Dockerfile` y `requirements.txt`.

Si el proyecto tiene un `environment.yml`, crear el entorno con:

```bash
conda env create -f environment.yml
conda activate DASH_Sobusa
```

Si se administra mediante `requirements.txt`, crear un entorno con la versión de Python compatible con el proyecto e instalar las dependencias:

```bash
conda create -n DASH_Sobusa python=3.11 pip -y
conda activate DASH_Sobusa
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

Si el proyecto utiliza otra versión de Python, ajustar `3.11` a la versión definida en el `Dockerfile` y compatible con sus dependencias.

## 4. Crear y configurar el archivo `.env`

El archivo `.env` contiene secretos y credenciales. Está excluido del repositorio mediante `.gitignore`, por lo que **cada persona debe crear su propio `.env` en la raíz del proyecto**. No se debe solicitar, copiar ni publicar el `.env` personal de otro integrante.

Crear el archivo a partir de la plantilla:

**Windows PowerShell:**

```powershell
Copy-Item .env.example .env
```

**Linux/macOS:**

```bash
cp .env.example .env
```

Si el repositorio todavía no contiene `.env.example`, crear un archivo llamado `.env` y utilizar la estructura de referencia que aparece a continuación. Completar los valores con la configuración y las credenciales autorizadas para el entorno de cada persona.

### Estructura de referencia del `.env`

```dotenv
# Aplicación
APP_ENV=development
SECRET_KEY=REEMPLAZAR_POR_UN_SECRETO_ALEATORIO_DE_AL_MENOS_32_CARACTERES
SESSION_HOURS=8
TRUST_PROXY=0

# Usuarios del dashboard: JSON con hashes bcrypt, no contraseñas en texto plano.
# Generar un hash bcrypt con el procedimiento documentado en el proyecto.
AUTH_USERS='{"usuario": "HASH_BCRYPT_GENERADO"}'
# puede usar AUTH_USERS='{"isaac": "$2b$12$FkFyPMBSghhOkzFJeW0f3.bRBAdYjNatICi6X2MUYrxG8YyP6Kn9m"}' este es el usuario y contraseña predeterminado del DASH
# Datos locales
DATA_SOURCE=local
DATA_DIR=data
DUCKDB_THREADS=2
DUCKDB_MEMORY_LIMIT=1GB

# PostgreSQL (opcional; activar solo si se dispone de acceso)
PG_ENABLED=0
#dirección de servidor
PG_HOST=
PG_PORT=5432
#nombre del dataset, por defecto "dataset"
PG_DB=dataset
#usuario
PG_USER=
#contraseña
PG_PASSWORD=
PG_SSLMODE=require

# URL de la API
# En Docker Compose, el nombre del servicio API es "api".
SOBUSA_API_URL=http://api:8000
```

### Variables que deben personalizarse

- `SECRET_KEY`: generar una clave aleatoria propia. No dejarla vacía ni reutilizar la de otra persona.
- `AUTH_USERS`: definir los usuarios autorizados del dashboard en el formato JSON que espera `utils/security.py`. El valor debe contener hashes bcrypt, nunca contraseñas en texto plano. Generar los hashes mediante el procedimiento seguro documentado por el proyecto.
- `DATA_SOURCE` y `DATA_DIR`: configurar la fuente y la ruta de los datos que utilizará la aplicación.
- `PG_ENABLED`: usar `1` únicamente cuando se vaya a conectar a PostgreSQL; usar `0` si no se utiliza esa fuente.
- `PG_HOST`, `PG_PORT`, `PG_DB`, `PG_USER`, `PG_PASSWORD` y `PG_SSLMODE`: completar con las credenciales entregadas o autorizadas para cada persona/entorno.
- `SOBUSA_API_URL`: dentro de Docker Compose, utilizar `http://api:8000` para que Dash pueda comunicarse con el servicio FastAPI. No utilizar `127.0.0.1` o `localhost` para llegar desde un contenedor a otro.

**Importante sobre el archivo de referencia:** los nombres y valores de las variables deben coincidir con los que realmente lee el código del proyecto. Si alguna variable no es utilizada por la aplicación, no es necesario agregarla; si el código requiere otras variables, deben documentarse y añadirse a la plantilla.

### Generación de secretos

Para generar una clave de sesión aleatoria desde Python:

```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

Para generar un hash bcrypt, utilizar el procedimiento definido por el proyecto. Si se usa el siguiente comando, debe estar instalado `bcrypt` en el entorno activo:

```bash
python -c "import bcrypt,getpass; print(bcrypt.hashpw(getpass.getpass('Contraseña: ').encode()[:72], bcrypt.gensalt(12)).decode())"
```

Guardar los valores generados en el `.env` local.

## 5. Disponer los datos locales

La configuración de ejemplo utiliza:

```dotenv
DATA_SOURCE=local
DATA_DIR=data
```

Por tanto, antes de iniciar los contenedores, colocar los archivos requeridos por la aplicación en la carpeta `data/`, respetando la estructura y los nombres de archivo que espera el proyecto (por ejemplo, `data/panel_horario/` y sus archivos correspondientes).

La carpeta `data/` y las bases de datos locales pueden estar excluidas de Git. En ese caso, cada persona debe obtener los archivos por el mecanismo de distribución autorizado y ubicarlos localmente.

Si los contenedores necesitan acceder a esa carpeta, debe montarse como volumen en el servicio correspondiente de `compose.yaml`. Por ejemplo:

```yaml
volumes:
  - ./data:/app/data:ro
```

La ruta `/app/data` debe coincidir con la ruta que utiliza el código dentro del contenedor. Añadir este montaje al servicio `api`, `dash` o a ambos, según cuál de ellos lea los archivos. El sufijo `:ro` monta los datos en modo solo lectura; quitarlo únicamente si la aplicación necesita escribir en esa carpeta.

## 6. Construir las imágenes y levantar los contenedores

El `compose.yaml` del proyecto utiliza `build` y un `Dockerfile`. Por ello, la persona que descarga el repositorio **construye las imágenes localmente y levanta los contenedores**. No necesita descargar imágenes publicadas ni ejecutar `docker build` manualmente.

Desde la raíz del proyecto:

```bash
docker compose up -d --build
```

Docker Compose:

1. Construye las imágenes a partir del `Dockerfile`.
2. Instala las dependencias definidas en `requirements.txt`.
3. Crea la red interna de Compose.
4. Inicia el contenedor de FastAPI (`api`).
5. Inicia el contenedor de Dash (`dash`).

La primera construcción puede tardar varios minutos. En ejecuciones posteriores, Docker reutiliza las capas que no hayan cambiado.

## 7. Verificar y acceder a la aplicación

Comprobar el estado:

```bash
docker compose ps
```

Consultar los registros:

```bash
docker compose logs --tail=100 api
docker compose logs --tail=100 dash
```

Direcciones locales:

| Servicio | Dirección |
|---|---|
| Dashboard Dash | http://localhost:8050 |
| API FastAPI | http://localhost:8000 |
| Documentación interactiva de FastAPI | http://localhost:8000/docs |

Abrir `http://localhost:8050` para acceder al dashboard e iniciar sesión.

## 8. Comandos de administración

Ver los registros en tiempo real:

```bash
docker compose logs -f
```

Detener y eliminar los contenedores y la red de Compose:

```bash
docker compose down
```

Iniciar los servicios existentes:

```bash
docker compose up -d
```

Reconstruir después de modificar el `Dockerfile`, `requirements.txt` o archivos incorporados a la imagen:

```bash
docker compose up -d --build
```

Aplicar cambios realizados en `.env` recreando los contenedores:

```bash
docker compose up -d --force-recreate
```

## 9. Consideraciones de configuración

- El `.env` debe estar en la misma carpeta que `compose.yaml`. El servicio Dash debe declararlo mediante `env_file: - .env`.
- No subir `.env`, contraseñas, tokens, hashes bcrypt ni claves privadas al repositorio.
- Mantener un `.env.example` versionado con todos los nombres de variables necesarios y valores vacíos o marcadores ficticios.
- No incluir credenciales reales en `.env.example`, el README, archivos de configuración versionados ni registros de ejecución.
- Las credenciales de PostgreSQL deben ser proporcionadas por el responsable del servicio y tener únicamente los permisos necesarios. Si no se utiliza PostgreSQL, mantener `PG_ENABLED=0`.
- Si se modifica la URL de la API, recordar que `localhost` dentro de un contenedor apunta a ese mismo contenedor. Para la comunicación entre los servicios de este Compose, utilizar el nombre DNS del servicio (`api`).
- `depends_on` controla el orden de inicio, pero no garantiza que la API esté lista para atender solicitudes cuando Dash arranca. Si la aplicación necesita esa garantía, configurar un `healthcheck` y una condición de espera.

## Acceso a Dash

Para una instalación de prueba, se puede utilizar la cuenta predeterminada:

- **Usuario:** `isaac`
- **Contraseña:** `isaac`

Si se prefiere utilizar otra cuenta, se puede crear una contraseña propia y generar su hash bcrypt. Desde el entorno de Python donde esté instalado `bcrypt`, ejecutar:

```bash
python -c "import bcrypt,getpass; print(bcrypt.hashpw(getpass.getpass('Contraseña: ').encode()[:72], bcrypt.gensalt(12)).decode())"
```

Copiar el hash generado en la variable `AUTH_USERS` del archivo `.env`, con esta estructura:

```dotenv
AUTH_USERS='{"nombre_usuario": "HASH_BCRYPT_GENERADO"}'
```

Por ejemplo, para conservar el usuario `isaac` pero establecer una contraseña diferente, se debe generar el hash de esa nueva contraseña y asignarlo a `isaac` en `AUTH_USERS`. Después de modificar `.env`, reiniciar los servicios:

```bash
docker compose down
docker compose up -d
```

**Importante:** las credenciales `isaac/isaac` son únicamente para pruebas o desarrollo. No se deben publicar en un repositorio público ni utilizar en producción. Antes de desplegar la aplicación públicamente, cambia la contraseña por una robusta y configura una clave `SECRET_KEY` propia. Nunca compartas ni subas el archivo `.env` a GitHub.



## Tercera ruta: 14-15

La versión DASHv3 incorpora la ruta 14-15 (`idruta=2`) con sus modelos y panel enero-agosto 2025. Consulte `INTEGRACION_R1415.md` para rutas, pruebas e instrucciones de instalación (también explica cómo restaurar los paneles CRA54 y Calle72).
