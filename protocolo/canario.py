"""El canario de firma (§6.6): una instancia debilitada que hay que romper para gastarlo.

Antes de este módulo, gastar el canario era `canarios_gastados += 1`: cualquiera que
pudiera meter la transacción en un bloque disparaba la transición cuando quisiera, que
es la "compuerta con disfraz criptográfico" contra la que I2 existe. Acá el gasto es
**una firma válida**, y producirla sin la clave exige resolver un logaritmo discreto.

**La instancia.** Un esquema de Schnorr sobre un subgrupo de orden primo `q` de `Z_p*`,
con `q` de 32 bits: chico a propósito, para que romperlo cueste ~`√q ≈ 2^16` pasos y se
pueda gastar de verdad en una prueba. Todo sale de la semilla pública y del índice del
canario, y **nada lo fija a mano**: `q`, `p`, `g` y la clave pública `y` se derivan
por hash. `y` se obtiene elevando un elemento derivado por hash a la potencia del
cofactor, así que su logaritmo en base `g` no lo conoce nadie —ni quien escribió la
semilla—: *nadie retiene la trampa*. Si `y` fuera `g^H(semilla)`, la clave privada sería
el propio hash y el canario se gastaría solo.

**El k-ésimo canario.** Cada transición de la regla consume **una instancia distinta**
(`indice = canarios_gastados`). Así una firma no se puede reutilizar para disparar la
siguiente transición: quien vio el gasto del canario 0 no gana nada para el canario 1.

**Lo que mide y lo que no.** Mide que alguien resolvió un logaritmo discreto en un grupo
de 32 bits. No dice nada de ed25519: es la misma clase de canario que el de hash, una
*capacidad de cómputo* demostrada sobre una instancia debilitada, y `q` de 32 bits es un
valor de demostración, no calibrado (ver `CANARIO_HASH_BITS` en `genesis.py`).

El lado del atacante (`romper`, `firmar`, `gasto`) vive acá y no en las pruebas porque el
protocolo tiene que poder mostrar que el canario **es** gastable: uno que nadie puede
gastar no alarma de nada.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import cache
from math import isqrt

from protocolo.serializacion import HASH_GENESIS, huella

_BASES_MILLER_RABIN = (2, 3, 5, 7, 11, 13, 17, 19, 23, 29, 31, 37)  # exacto hasta 3,3e24


def _es_primo(n: int) -> bool:
    if n < 2:
        return False
    for chico in _BASES_MILLER_RABIN:
        if n % chico == 0:
            return n == chico
    d, s = n - 1, 0
    while d % 2 == 0:
        d //= 2
        s += 1
    for base in _BASES_MILLER_RABIN:
        x = pow(base, d, n)
        if x in (1, n - 1):
            continue
        for _ in range(s - 1):
            x = x * x % n
            if x == n - 1:
                break
        else:
            return False
    return True


def _entero(semilla: str, indice: int, etiqueta: str, cuenta: int = 0) -> int:
    """Un entero de 256 bits derivado por hash. Siempre con el hash de Genesis."""
    digest = huella(
        {"semilla": semilla, "indice": indice, "etiqueta": etiqueta, "cuenta": cuenta},
        dominio="canario/firma",
        hash_id=HASH_GENESIS,
    )
    return int.from_bytes(digest, "big")


@dataclass(frozen=True)
class Instancia:
    p: int  # módulo, primo
    q: int  # orden del subgrupo, primo de 32 bits
    g: int  # generador del subgrupo de orden q
    y: int  # clave pública: su logaritmo en base g no lo conoce nadie

    def canonico(self) -> dict:
        return {"p": self.p, "q": self.q, "g": self.g, "y": self.y}


@cache
def instancia(semilla: str, indice: int = 0) -> Instancia:
    """La instancia debilitada `indice` que sale de `semilla`. Determinística."""
    q = (_entero(semilla, indice, "q") % 2**31) + 2**31 | 1
    while not _es_primo(q):
        q += 2

    cofactor = ((_entero(semilla, indice, "cofactor") % 2**31) + 2**31) & ~1
    while not _es_primo(cofactor * q + 1):
        cofactor += 2
    p = cofactor * q + 1

    def al_subgrupo(etiqueta: str) -> int:
        cuenta = 0
        while True:
            elemento = _entero(semilla, indice, etiqueta, cuenta) % (p - 2) + 2
            en_subgrupo = pow(elemento, cofactor, p)
            if en_subgrupo != 1:
                return en_subgrupo
            cuenta += 1

    return Instancia(p=p, q=q, g=al_subgrupo("g"), y=al_subgrupo("y"))


def compromiso(semilla: str) -> bytes:
    """Huella de la primera instancia: lo que Genesis publica como `CANARIO_INSTANCIA`."""
    return huella(instancia(semilla, 0).canonico(), dominio="canario", hash_id=HASH_GENESIS)


# --------------------------------------------------------------------------- #
# Firmar y verificar (Schnorr)
# --------------------------------------------------------------------------- #


def _mensaje(indice: int) -> bytes:
    return b"gasto del canario/%d" % indice


def _desafio(inst: Instancia, r: int, indice: int) -> int:
    digest = huella(
        {"r": r, "y": inst.y, "mensaje": _mensaje(indice)},
        dominio="canario/firma/desafio",
        hash_id=HASH_GENESIS,
    )
    return int.from_bytes(digest, "big") % inst.q


def verifica(semilla: str, indice: int, e: int, s: int) -> bool:
    """¿`(e, s)` es una firma válida del canario `indice`? Sólo función de Genesis."""
    if not (isinstance(e, int) and isinstance(s, int)):
        return False
    inst = instancia(semilla, indice)
    if not (0 <= e < inst.q and 0 <= s < inst.q):
        return False
    r = pow(inst.g, s, inst.p) * pow(inst.y, inst.q - e, inst.p) % inst.p
    return _desafio(inst, r, indice) == e


# --------------------------------------------------------------------------- #
# El lado del atacante
# --------------------------------------------------------------------------- #


def romper(inst: Instancia) -> int:
    """`x` con `g^x = y`, por baby-step giant-step: ~`√q` pasos. Eso es "romper" el canario."""
    m = isqrt(inst.q) + 1
    pequenos = {}
    actual = 1
    for j in range(m):
        pequenos.setdefault(actual, j)
        actual = actual * inst.g % inst.p
    salto = pow(inst.g, -m, inst.p)
    gamma = inst.y
    for i in range(m):
        if gamma in pequenos:
            return (i * m + pequenos[gamma]) % inst.q
        gamma = gamma * salto % inst.p
    raise ArithmeticError("no hay logaritmo: la instancia no es del subgrupo")


def firmar(semilla: str, indice: int, x: int) -> tuple[int, int]:
    inst = instancia(semilla, indice)
    # Nonce determinístico: sin fuente de azar, la firma es reproducible.
    t = _entero(f"nonce/{x}", indice, "t") % inst.q or 1
    e = _desafio(inst, pow(inst.g, t, inst.p), indice)
    return e, (t + x * e) % inst.q


@cache
def gasto(semilla: str, indice: int = 0) -> tuple:
    """La transacción que gasta el canario `indice`: rompe la instancia y firma con eso."""
    e, s = firmar(semilla, indice, romper(instancia(semilla, indice)))
    return ("gastar_canario", e, s)
