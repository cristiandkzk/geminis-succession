"""`python herramientas/convergencia.py` — cuatro nodos que no se hablan, en una pantalla.

`demo.py` muestra **un** nodo conmutando. Eso alcanza para ver el mecanismo y no
alcanza para lo único que un fork es: dos nodos que dejan de estar en la misma
cadena. Esto es la otra mitad, y la que se puede filmar: cuatro nodos construidos
por separado, cada uno produciendo sus propios bloques, sin red, sin gossip y sin
compartir ni el objeto de la regla — y después la comparación, hecha desde afuera.

Lo que hay que poder leer en pantalla, en este orden:

1. los cuatro llegan al **mismo `H0_B`** y conmutan en la **misma altura**, y sus
   cadenas coinciden bloque por bloque. No se pusieron de acuerdo: no hubo canal
   por donde ponerse de acuerdo;
2. el quinto eligió **otro punto legítimo del espacio** —parte la emisión en cuatro
   en vez de en dos, mismo disparo, misma altura— y su `H0_B` es otro. Un hash dice
   que se fue;
3. y su linaje **verifica contra sí mismo**, porque es la misma función de hash. Lo
   que lo delata no es `Verify` fallando en el vacío: es que su `H0_B` no es el que
   Genesis determinó para esa generación. Injertado en el linaje de los demás, sí
   rompe, y dice dónde.

Las pruebas de esto están en `pruebas/test_convergencia_entre_nodos.py` (26
criterios). Esto no es una prueba: existe para poder *verlo*.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from nodo.pod import NodoPoD  # noqa: E402
from protocolo import genesis as g  # noqa: E402
from protocolo.generacion import Params  # noqa: E402
from protocolo.linaje import motivo_linaje_invalido, verificar_linaje  # noqa: E402
from sucesion.regla import ReglaEmisionAcumulada  # noqa: E402

#: Con `emision_por_bloque = 1_000` desde Genesis, dispara en la altura 100,
#: hace lock-in en 112 y activa en 176 — la misma altura que muestra `demo.py`.
PASO = 100_000
#: Justo arriba de la activación y por debajo del rearme (el umbral pasa a
#: 200.000 y a esta altura se emitieron 180.000): una sola generación, sin cola.
BLOQUES = 180
NOMBRES = ("A", "B", "C", "D")


class ReglaEmisionACuarto(ReglaEmisionAcumulada):
    """Parte la emisión en cuatro en vez de en dos. Es el adversario honesto.

    No rompe ningún hash ni elige un sucesor inválido: 250 está dentro del mismo
    `RangoEntero(0, 10_000)` que 500. Dispara por el mismo hecho del estado y en la
    misma altura. Lo único distinto son los `params`, que sí son insumo de `h0`.
    """

    def params_sucesor(self, estado, ruleset) -> Params:
        internos = dict(ruleset.params.internos)
        internos["emision_por_bloque"] = ruleset.interno("emision_por_bloque") // 4
        return Params(
            generacion=ruleset.generacion + 1,
            internos=internos,
            formatos=ruleset.formatos,
        )


def correr(regla) -> NodoPoD:
    """Un nodo que produce `BLOQUES` alturas por su cuenta. No recibe nada de nadie."""
    nodo = NodoPoD(reglas=[regla])
    for _ in range(BLOQUES):
        nodo.producir_bloque()
    return nodo


def linea(nombre: str, nodo: NodoPoD) -> str:
    punto = nodo.cronograma.checkpoints[0]
    return (
        f"  {nombre:<7}{punto.altura_activacion:<12}"
        f"{punto.h0.hex()[:16]}…  {nodo.estado.huella().hex()[:12]}…"
    )


def main() -> int:
    for flujo in (sys.stdout, sys.stderr):
        try:
            flujo.reconfigure(encoding="utf-8", errors="replace")
        except AttributeError:  # pragma: no cover
            pass

    print("FOUR NODES, NO COORDINATION")
    print()
    print(
        "Each node below was constructed on its own and produced its own blocks.\n"
        "No network, no gossip, not even a shared rule object. The comparison\n"
        f"happens afterwards, from outside, over {BLOQUES} blocks."
    )
    print()

    honestos = [correr(ReglaEmisionAcumulada(paso=PASO)) for _ in NOMBRES]

    print(f"  {'node':<7}{'switch at':<12}{'H0_B':<20}{'state'}")
    for nombre, nodo in zip(NOMBRES, honestos):
        print(linea(nombre, nodo))
    print()

    cadenas = [[b.hash() for b in n.cadena] for n in honestos]
    iguales = all(c == cadenas[0] for c in cadenas[1:])
    print(
        f"  -> {'identical' if iguales else 'DIVERGED'}: "
        f"{len(cadenas[0])} block hashes match across all four, bit for bit"
    )
    print(
        "     They didn't agree on this. There was nothing to agree about:\n"
        "     every one of them derived it from the chain."
    )
    print()

    print("THE FIFTH NODE PICKED A DIFFERENT SUCCESSOR")
    print()
    desviado = correr(ReglaEmisionACuarto(paso=PASO))
    honesto = honestos[0].cronograma.checkpoints[0]
    suyo = desviado.cronograma.checkpoints[0]

    print(linea("A", honestos[0]))
    print(linea("E", desviado))
    print()
    print(
        f"  same trigger block ({suyo.altura_disparo}), "
        f"same state_trigger ({'yes' if suyo.state_trigger == honesto.state_trigger else 'no'}), "
        f"different params ({'yes' if suyo.params != honesto.params else 'no'})"
    )
    print(
        f"  halved vs quartered: "
        f"{honesto.params.internos['emision_por_bloque']} vs "
        f"{suyo.params.internos['emision_por_bloque']} per block — both legal points"
    )
    print(f"  -> different H0_B: {'yes' if suyo.h0 != honesto.h0 else 'NO'}")
    print()

    print("AND ITS OWN LINEAGE VERIFIES — that's the part worth understanding")
    print()
    print(
        f"  Verify(its checkpoints, H0_GENESIS) = "
        f"{verificar_linaje(desviado.cronograma.checkpoints, g.H0_GENESIS)}"
    )
    print(
        "  It has to. It's the same hash function. A divergent chain is not caught\n"
        "  by Verify failing in a vacuum — it's caught because its H0_B is not the\n"
        "  H0_B Genesis determined for that generation."
    )
    print()
    # `motivo_linaje_invalido` devuelve su mensaje en español, y el resto de este
    # output está en inglés. No se traduce el módulo —es código de protocolo,
    # compartido— así que acá se reporta el veredicto y se muestran los hashes.
    roto = motivo_linaje_invalido([suyo], honesto.h0) is not None
    print("  Try to splice it in after the honest generation and it breaks:")
    print(f"    lineage accepts the graft: {not roto}")
    print(f"    it commits to ancestor  {suyo.h0_ancestro.hex()[:16]}…")
    print(f"    the honest ancestor is  {honesto.h0.hex()[:16]}…")
    print()
    print(
        "  One hash, no opinion. Nobody has to be trusted about which chain\n"
        "  is the real one: the lineage is checkable from Genesis forward."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
