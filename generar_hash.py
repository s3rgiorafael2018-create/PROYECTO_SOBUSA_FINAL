"""Genera SECRET_KEY y el hash bcrypt para el .env.  Uso:  python generar_hash.py"""
import bcrypt, getpass, json, secrets

usuario = input("Usuario: ").strip()
clave = getpass.getpass("Contraseña (no se muestra, máx. 72 caracteres): ")
if getpass.getpass("Repite la contraseña: ") != clave:
    raise SystemExit("Las contraseñas no coinciden.")
hash_ = bcrypt.hashpw(clave.encode("utf-8")[:72], bcrypt.gensalt(12)).decode()

print("\nCopia estas líneas en tu .env:\n")
print(f"SECRET_KEY={secrets.token_hex(32)}")
print("AUTH_USERS='" + json.dumps({usuario: hash_}) + "'")