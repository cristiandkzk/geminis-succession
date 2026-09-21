"""Corre el protocolo con otro hash (por defecto SHA3-256) en lugar de SHA-256, en un proceso propio.

No es una prueba (no empieza con `test`, `verificar.py` no lo descubre): lo lanza
`test_cambio_de_hash.py`. Vive aparte porque `H0_GENESIS` y otras constantes se
calculan al importar el módulo, así que cambiar de hash *después* de importar
dejaría la mitad del protocolo en SHA-256. Hay que parchear antes del primer
`import protocolo`, y eso sólo se logra en un proceso limpio.

    python pruebas/_correr_con_otro_hash.py h0 [algoritmo]      # sólo la raíz del linaje
    python pruebas/_correr_con_otro_hash.py suite [algoritmo]   # además, todas las pruebas

Imprime una línea JSON en stdout; lo demás (el ruido de unittest) va a stderr.
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
import unittest
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent

# Antes de importar nada del protocolo. `serializacion.huella` llama a
# `hashlib.sha256` por atributo, así que este es el único punto a tocar.
ALGORITMO = sys.argv[2] if len(sys.argv) > 2 else "sha3_256"
hashlib.sha256 = getattr(hashlib, ALGORITMO)

# Para que `test_cambio_de_hash` se salte a sí mismo dentro de este proceso y no
# se lance recursivamente.
os.environ["GEMINIS_HASH_EXPERIMENTO"] = "1"
sys.path.insert(0, str(RAIZ))

from protocolo import genesis as g  # noqa: E402


def main(modo: str) -> int:
    salida = {
        "algoritmo": ALGORITMO,
        "largo_h0": len(g.H0_GENESIS),
        "h0": g.H0_GENESIS.hex(),
    }
    if modo == "suite":
        suite = unittest.defaultTestLoader.discover(
            start_dir=str(RAIZ / "pruebas"), top_level_dir=str(RAIZ), pattern="test*.py"
        )
        resultado = unittest.TextTestRunner(stream=sys.stderr, verbosity=0).run(suite)
        salida.update(
            corridas=resultado.testsRun,
            fallos=len(resultado.failures),
            errores=len(resultado.errors),
        )
    print(json.dumps(salida))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1] if len(sys.argv) > 1 else "h0"))
