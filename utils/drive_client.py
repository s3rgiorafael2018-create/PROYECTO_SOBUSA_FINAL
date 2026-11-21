import os
import io

from pathlib import Path
from dotenv import load_dotenv

from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload


BASE_DIR = Path(__file__).resolve().parent.parent

load_dotenv(BASE_DIR / ".env")

SCOPES = ["https://www.googleapis.com/auth/drive.readonly"]

CACHE_DIR = BASE_DIR / "data" / "drive_cache"
CACHE_DIR.mkdir(parents=True, exist_ok=True)


def conectar_drive():
    """Establece conexión autenticada con Google Drive."""

    if os.getenv("DRIVE_ENABLED", "0") != "1":
        raise RuntimeError("Google Drive está deshabilitado.")

    credenciales_path = BASE_DIR / os.getenv(
        "GOOGLE_APPLICATION_CREDENTIALS",
        "credentials/service-account.json"
    )

    credentials = service_account.Credentials.from_service_account_file(
        str(credenciales_path),
        scopes=SCOPES
    )

    return build(
        "drive",
        "v3",
        credentials=credentials,
        cache_discovery=False
    )


def listar_archivos():
    """Lista los archivos contenidos directamente en la carpeta."""

    service = conectar_drive()

    folder_id = os.getenv("DRIVE_FOLDER_ID")

    if not folder_id:
        raise ValueError("No se configuró DRIVE_FOLDER_ID.")

    resultado = service.files().list(
        q=f"'{folder_id}' in parents and trashed = false",
        fields="files(id, name, mimeType, size, modifiedTime)",
        orderBy="name"
    ).execute()

    return resultado.get("files", [])


def descargar_archivo(file_id: str, nombre: str):
    """Descarga un archivo de Drive a la caché local."""

    service = conectar_drive()

    destino = CACHE_DIR / Path(nombre).name

    request = service.files().get_media(
        fileId=file_id
    )

    with io.FileIO(destino, "wb") as archivo:

        downloader = MediaIoBaseDownload(
            archivo,
            request
        )

        terminado = False

        while not terminado:
            _, terminado = downloader.next_chunk()

    return destino


def descargar_csv():
    """Descarga todos los CSV de la carpeta."""

    archivos = listar_archivos()

    descargados = []

    for archivo in archivos:

        if archivo["name"].lower().endswith(".csv"):

            ruta = descargar_archivo(
                archivo["id"],
                archivo["name"]
            )

            descargados.append(ruta)

    return descargados