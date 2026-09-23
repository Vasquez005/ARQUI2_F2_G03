"""Crea los usuarios minimos exigidos (Fase_2_PORTUS.md sec. 2.1):
1 TERMINAL, 2 NAVIERA, 1 AGENTE, 1 AUTORIDAD, 2 TRANSPORTISTA.

Uso:
    cd backend
    .venv/bin/python3 seed.py

Es idempotente: si el username ya existe, no lo vuelve a crear. Las
contrasenas de ejemplo son solo para desarrollo/demostracion — cambiarlas
antes de la entrega si se van a usar como credenciales reales.
"""

import os

from models import Transportista, Usuario, make_db
from security import hash_password

DB_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), "portus_core.db"))

USUARIOS_MINIMOS = [
    ("terminal1", "TERMINAL", "Operador de Terminal"),
    ("naviera1", "NAVIERA", "Naviera Uno"),
    ("naviera2", "NAVIERA", "Naviera Dos"),
    ("agente1", "AGENTE", "Agente Aduanero"),
    ("autoridad1", "AUTORIDAD", "Autoridad Aduanera"),
]

TRANSPORTISTAS_MINIMOS = ["Transportista Uno", "Transportista Dos"]

PASSWORD_DEMO = "Portus2026!"


def main():
    SessionLocal = make_db(DB_PATH)
    with SessionLocal() as db:
        for username, rol, nombre in USUARIOS_MINIMOS:
            existente = db.query(Usuario).filter_by(username=username).first()
            if existente:
                print(f"[SKIP] {username} ya existe")
                continue
            db.add(Usuario(username=username, password_hash=hash_password(PASSWORD_DEMO),
                            rol=rol, nombre=nombre, activo=True))
            print(f"[OK] usuario {username} ({rol}) creado, password: {PASSWORD_DEMO}")

        for nombre in TRANSPORTISTAS_MINIMOS:
            existente = db.query(Transportista).filter_by(nombre=nombre).first()
            if existente:
                print(f"[SKIP] transportista {nombre} ya existe")
                continue
            db.add(Transportista(nombre=nombre))
            print(f"[OK] transportista {nombre} creado")

        db.commit()
    print("\nListo. Guardar estas credenciales en la documentacion de entrega (sec. 2.1 del PDF).")


if __name__ == "__main__":
    main()
