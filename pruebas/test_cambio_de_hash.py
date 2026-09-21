"""¿Se puede cambiar SHA-256 por Keccak (SHA-3) sin tocar el protocolo?

Se elige SHA-3 y no SHA-512 a propósito: SHA-256 y SHA-512 son la misma familia
(SHA-2), y si se rompe una es probable que caiga la otra. Keccak es otra construcción
(esponja), así que es el reemplazo que cubre el escenario real de "rompieron SHA-256".
`hashlib.sha3_256` usa la permutación Keccak con el relleno del NIST; el Keccak-256 de
Ethereum sólo difiere en ese byte de relleno (y no está en la biblioteca estándar).

Esta prueba mide *portabilidad de la primitiva*, no sucesión de la primitiva. Son
dos preguntas distintas y sólo la primera está construida:

- **Reemplazo global** (lo que prueba este archivo): el hash sale de un único
  punto, `serializacion.huella`. Si se cambia ahí, ¿el protocolo entero sigue
  funcionando con Keccak? Es el prerrequisito de todo lo demás.
- **Sucesión dentro de la cadena** (NO probado, y hoy no se puede): que la
  generación A hashee con SHA-256 y la B con SHA-3, y que `Verify(H0_B, H0_A)`
  sepa cuál usar en cada eslabón. `huella` es una función global sin noción de
  generación, así que eso requeriría un formato de hash en `params`, igual que
  `firma/ml-dsa-44` lo es para la firma.

El aviso que justifica el archivo: ninguna otra prueba fija un hash literal, así
que un cambio de primitiva no rompe nada *por sí solo*. Lo que sí se puede
comprobar es que nada más hashee por su cuenta y que la raíz efectivamente cambió.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import unittest
from pathlib import Path

from protocolo import genesis as g

RAIZ = Path(__file__).resolve().parent.parent
RUNNER = RAIZ / "pruebas" / "_correr_con_otro_hash.py"

#: Dentro del proceso con SHA-3 la suite entera se vuelve a descubrir, y este
#: archivo con ella; sin esto se lanzaría a sí mismo en cadena.
_ES_EL_EXPERIMENTO = bool(os.environ.get("GEMINIS_HASH_EXPERIMENTO"))


def _correr(modo: str) -> dict:
    proceso = subprocess.run(
        [sys.executable, str(RUNNER), modo],
        cwd=RAIZ,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=300,
    )
    if proceso.returncode:
        raise AssertionError(f"el runner SHA-3 murió:\n{proceso.stderr}")
    return json.loads(proceso.stdout.strip().splitlines()[-1])


@unittest.skipIf(_ES_EL_EXPERIMENTO, "dentro del proceso SHA-3")
class ElHashSaleDeUnSoloLugar(unittest.TestCase):
    def test_solo_serializacion_importa_hashlib(self):
        """Si otro módulo hashea por su cuenta, el reemplazo dejaría hashes mezclados."""
        intrusos = []
        for carpeta in ("protocolo", "sucesion", "nodo", "estado", "herramientas"):
            for archivo in (RAIZ / carpeta).rglob("*.py"):
                if archivo.name == "serializacion.py":
                    continue
                texto = archivo.read_text(encoding="utf-8")
                # Imports y llamadas, no prosa: un docstring puede nombrar "sha3".
                if re.search(
                    r"^\s*(import|from)\s+(hashlib|hmac|_hashlib)\b|\b(hashlib|hmac)\.\w+\(",
                    texto,
                    re.MULTILINE,
                ):
                    intrusos.append(str(archivo.relative_to(RAIZ)))
        self.assertEqual(intrusos, [], "hashean fuera de serializacion.huella")


@unittest.skipIf(_ES_EL_EXPERIMENTO, "dentro del proceso SHA-3")
class ConKeccak(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.real = _correr("suite")

    def test_el_parche_mordio(self):
        """Control negativo: sin esto, "todo pasa" podría ser que nada cambió."""
        self.assertEqual(self.real["algoritmo"], "sha3_256")
        self.assertEqual(len(g.H0_GENESIS), 32, "este proceso sigue en SHA-256")
        self.assertNotEqual(self.real["h0"], g.H0_GENESIS.hex())

    def test_la_raiz_del_linaje_es_reproducible(self):
        otra = _correr("h0")
        self.assertEqual(otra["h0"], self.real["h0"])

    def test_todas_las_pruebas_pasan_con_sha3(self):
        self.assertGreater(self.real["corridas"], 100)
        self.assertEqual(self.real["fallos"], 0)
        self.assertEqual(self.real["errores"], 0)


if __name__ == "__main__":
    unittest.main()
