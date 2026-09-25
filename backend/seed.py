"""Crea los usuarios minimos exigidos (Fase_2_PORTUS.md sec. 2.1):
1 TERMINAL, 2 NAVIERA, 1 AGENTE, 1 AUTORIDAD, 2 TRANSPORTISTA.

Uso:
    cd backend
    .venv/bin/python3 seed.py          # usuarios, transportistas y tarjetas RFID
    .venv/bin/python3 seed.py --demo   # ademas, manifiestos con levante para probar la maqueta

Es idempotente: si el username ya existe, no lo vuelve a crear. Las
contrasenas de ejemplo son solo para desarrollo/demostracion — cambiarlas
antes de la entrega si se van a usar como credenciales reales.
"""

import os
import sys

from models import Declaracion, Manifiesto, Transportista, Usuario, Vehiculo, make_db
from security import hash_password

DB_PATH = os.getenv("PORTUS_DB_PATH", os.path.abspath(os.path.join(os.path.dirname(__file__), "portus_core.db")))

USUARIOS_MINIMOS = [
    ("terminal1", "TERMINAL", "Operador de Terminal"),
    ("naviera1", "NAVIERA", "Naviera Uno"),
    ("naviera2", "NAVIERA", "Naviera Dos"),
    ("agente1", "AGENTE", "Agente Aduanero"),
    ("autoridad1", "AUTORIDAD", "Autoridad Aduanera"),
]

TRANSPORTISTAS_MINIMOS = ["Transportista Uno", "Transportista Dos"]

PASSWORD_DEMO = "Portus2026!"

# Tarjetas de la maqueta -> transportista (fase 1: tarjeta -> contenedor).
# "90 C7 3D 5F" NO se registra a proposito: sirve para demostrar el rechazo
# "RFID no registrado" en la garita (E03).
# "E1 8E 3C 53" es la que el UNO de entrada simula fuera de tolerancia (RT01).
VEHICULOS = [
    ("E1 69 73 15", "Transportista Uno", "C-001"),
    ("E1 67 7F 15", "Transportista Dos", "C-002"),
    ("E1 8E 3C 53", "Transportista Uno", "C-003"),
]

# --demo: un manifiesto con levante otorgado (canal verde) por tarjeta.
MANIFIESTOS_DEMO = [
    ("MSCU0000001", "DEPOSITO", 1000, "E1 69 73 15", "naviera1"),
    ("MSCU0000002", "RETIRO", 1200, "E1 67 7F 15", "naviera2"),
    ("MSCU0000003", "DEPOSITO", 1500, "E1 8E 3C 53", "naviera1"),
]


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

        db.flush()
        for uid, nombre_transportista, placa in VEHICULOS:
            if db.get(Vehiculo, uid):
                print(f"[SKIP] vehiculo {uid} ya existe")
                continue
            t = db.query(Transportista).filter_by(nombre=nombre_transportista).first()
            db.add(Vehiculo(uid=uid, transportista_id=t.id if t else None, placa=placa))
            print(f"[OK] vehiculo {uid} -> {nombre_transportista}")

        if "--demo" in sys.argv:
            db.flush()
            for contenedor, operacion, peso, uid, naviera in MANIFIESTOS_DEMO:
                if db.query(Manifiesto).filter_by(contenedor_id=contenedor).first():
                    print(f"[SKIP] manifiesto {contenedor} ya existe")
                    continue
                vehiculo = db.get(Vehiculo, uid)
                usuario = db.query(Usuario).filter_by(username=naviera).first()
                m = Manifiesto(contenedor_id=contenedor, tipo_operacion=operacion, peso_declarado_g=peso,
                               naviera_usuario_id=usuario.id if usuario else None,
                               transportista_id=vehiculo.transportista_id if vehiculo else None,
                               vehiculo_uid=uid, estado_documental="levante_otorgado", canal="verde")
                db.add(m)
                db.flush()
                db.add(Declaracion(manifiesto_id=m.id, numero_declaracion=f"DEMO-{contenedor}",
                                   regimen="importacion_definitiva", descripcion="Carga de demostracion",
                                   valor_declarado=1000.0))
                print(f"[OK] manifiesto demo {contenedor} ({operacion}) -> tarjeta {uid}")

        db.commit()
    print("\nListo. Guardar estas credenciales en la documentacion de entrega (sec. 2.1 del PDF).")


if __name__ == "__main__":
    main()
