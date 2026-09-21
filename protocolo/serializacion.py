"""Codificación canónica: la única forma de convertir datos en bytes para hashear.

Todo hash del protocolo —el linaje de I4, la huella de estado de I3, el hash de
bloque— pasa por acá. Que dos nodos calculen el mismo hash sobre los mismos datos
es una precondición de todo lo demás, así que la codificación tiene tres reglas
que no son de estilo:

- **No hay flotantes.** Ni siquiera se aceptan para codificarlos: `codificar`
  levanta `FlotanteProhibido`. La Fase 4 exige que el flotante esté prohibido o
  canonicalizado *antes* de que el guante corra por primera vez, y una condición
  sobre Genesis no se levanta después. Prohibirlo desde el primer archivo es más
  barato que descubrir en la Fase 4 que se coló uno en un acumulador.
- **Toda codificación es autodelimitada.** Cada valor lleva etiqueta de tipo y
  largo. Sin eso, `("ab", "c")` y `("a", "bc")` tendrían la misma imagen y dos
  estados distintos podrían compartir huella.
- **El orden no lo elige quien llama.** Los diccionarios se recorren por clave
  ordenada y los conjuntos por su codificación ordenada. Un `dict` de Python
  conserva el orden de inserción; si ese orden entrara al hash, el mismo estado
  daría huellas distintas según en qué orden se construyó.

Un objeto que quiera hashearse expone `canonico()` y devuelve datos ya
codificables (dicts, listas, enteros, strings, bytes).
"""

from __future__ import annotations

import hashlib
from collections.abc import Mapping

_PREFIJO = b"genesis/"

#: Los hashes que la máquina de Genesis sabe calcular, por nombre de formato.
#:
#: El hash **es un formato más** —igual que `firma/ml-dsa-44`— y por eso sucede por
#: la misma vía (I5: se agrega, no se quita). `HASH_GENESIS` es el del bloque 0 y **no
#: figura en `formatos`**: agregarlo movería `H0_GENESIS`, que ya está publicado.
HASH_SHA256 = "hash/sha256"
HASH_KECCAK = "hash/sha3-256"
HASH_GENESIS = HASH_SHA256

#: El orden de sucesión: el hash vigente de un ruleset es el **último** de esta
#: tupla que aparezca en sus `formatos`. Hace falta un orden porque `formatos` es un
#: conjunto, y como los formatos sólo se agregan, el hash sólo puede avanzar.
HASHES_EN_ORDEN = (HASH_SHA256, HASH_KECCAK)

_HASHES = {HASH_SHA256: hashlib.sha256, HASH_KECCAK: hashlib.sha3_256}


class HashDesconocido(ValueError):
    """Se pidió un hash que la máquina de Genesis no conoce."""


class FlotanteProhibido(TypeError):
    """Se intentó codificar un flotante. Ver el docstring del módulo."""


class NoCodificable(TypeError):
    """Tipo sin codificación canónica definida."""


def codificar(valor: object) -> bytes:
    """Bytes canónicos de `valor`. Determinístico entre procesos y arquitecturas."""
    if isinstance(valor, float):
        raise FlotanteProhibido(
            "los flotantes no entran a ningún hash del protocolo: usá enteros "
            "(partes por millón, satoshis, bloques) en vez de fracciones"
        )
    if isinstance(valor, bool):  # antes que int: bool es subclase de int
        return b"T" if valor else b"F"
    if valor is None:
        return b"n"
    if isinstance(valor, int):
        return b"i" + str(valor).encode("ascii") + b";"
    if isinstance(valor, str):
        crudo = valor.encode("utf-8")
        return b"s" + str(len(crudo)).encode("ascii") + b":" + crudo
    if isinstance(valor, (bytes, bytearray)):
        return b"b" + str(len(valor)).encode("ascii") + b":" + bytes(valor)

    metodo = getattr(valor, "canonico", None)
    if callable(metodo):
        return codificar(metodo())

    if isinstance(valor, Mapping):
        claves = list(valor)
        if any(not isinstance(clave, str) for clave in claves):
            raise NoCodificable("las claves de un mapa canónico son strings")
        cuerpo = b"".join(codificar(c) + codificar(valor[c]) for c in sorted(claves))
        return b"d" + str(len(claves)).encode("ascii") + b":" + cuerpo
    if isinstance(valor, (set, frozenset)):
        elementos = sorted(codificar(e) for e in valor)
        return b"S" + str(len(elementos)).encode("ascii") + b":" + b"".join(elementos)
    if isinstance(valor, (list, tuple)):
        elementos = [codificar(e) for e in valor]
        return b"l" + str(len(elementos)).encode("ascii") + b":" + b"".join(elementos)

    raise NoCodificable(f"sin codificación canónica para {type(valor).__name__}")


def hash_vigente(formatos: object) -> str:
    """El hash que gobierna un ruleset con estos `formatos`. Sin formato de hash: el de Genesis."""
    vigente = HASH_GENESIS
    for nombre in HASHES_EN_ORDEN:
        if nombre in formatos:
            vigente = nombre
    return vigente


def huella(valor: object, dominio: str, hash_id: str = HASH_GENESIS) -> bytes:
    """Hash de `valor` bajo un dominio de separación. Por defecto, SHA-256.

    El dominio evita que la imagen de un estado pueda hacerse pasar por la de un
    bloque o por la de un checkpoint generacional: son espacios distintos y no
    tienen por qué no colisionar por accidente.

    `hash_id` elige la primitiva. **Quien llama no lo decide a su gusto**: sale del
    ruleset vigente (`hash_vigente`), y para un checkpoint del linaje, del ruleset
    *ancestro* — ver `protocolo/linaje.py`.
    """
    try:
        funcion = _HASHES[hash_id]
    except KeyError:
        raise HashDesconocido(f"hash desconocido para la máquina: {hash_id!r}") from None
    return funcion(
        _PREFIJO + dominio.encode("utf-8") + b"\x00" + codificar(valor)
    ).digest()


def ceros_iniciales(digest: bytes) -> int:
    """Cuántos bits en cero tiene el digest al comienzo. Es la 'dificultad' del canario de hash."""
    total = len(digest) * 8
    como_entero = int.from_bytes(digest, "big")
    return total - como_entero.bit_length()


def corto(h: bytes) -> str:
    """Primeros 8 bytes en hexa. Sólo para mensajes y logs, nunca para comparar."""
    return h.hex()[:16]
