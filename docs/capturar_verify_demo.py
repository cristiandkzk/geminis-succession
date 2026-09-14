"""Corre los mismos escenarios que `pruebas/test_linaje.py` (I4) y vuelca el
resultado REAL de `verificar()`/`verificar_linaje()` contra cada variante
manipulada a `docs/verify-demo-data.json`, para que `docs/verify.html` los
muestre como un panel interactivo. Ningún resultado se simula en JS: todos
salen de correr el código real una vez y guardar qué dio.

    python docs/capturar_verify_demo.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from nodo.pod import NodoPoD  # noqa: E402
from protocolo import genesis as g  # noqa: E402
from protocolo.generacion import Params  # noqa: E402
from protocolo.linaje import verificar, verificar_linaje  # noqa: E402
from sucesion.regla import (  # noqa: E402
    ReglaCanarioCriptografico,
    ReglaEmisionAcumulada,
)

GASTAR_CANARIO = ("gastar_canario",)
ALTURA_DEL_CANARIO = 130
BLOQUES = 260
CERO_32 = b"\x00" * 32


def correr_escenario() -> list:
    nodo = NodoPoD(
        reglas=[
            ReglaEmisionAcumulada(paso=100_000),
            ReglaCanarioCriptografico(),
        ]
    )
    nodo.producir_bloque([("transferir", "reserva", "alice", 500)])
    nodo.producir_bloque([("crear_objeto", "recibo-1", "recibo/gen0")])
    for _ in range(BLOQUES):
        altura = nodo.altura + 1
        txs = [GASTAR_CANARIO] if altura == ALTURA_DEL_CANARIO else []
        nodo.producir_bloque(txs)
    return list(nodo.cronograma.checkpoints)


def corto(b: bytes) -> str:
    return b.hex()[:16] + "…"


def main() -> int:
    checkpoints = correr_escenario()
    p0 = checkpoints[0]

    escenarios = []

    def agregar(id_, titulo, explicacion, resultado, detalle):
        escenarios.append({
            "id": id_,
            "titulo": titulo,
            "explicacion": explicacion,
            "resultado": resultado,
            "detalle": detalle,
        })

    # --- nivel cadena: verificar_linaje(checkpoints, raiz) ---
    agregar(
        "cadena_real",
        "La cadena real, sin tocar",
        "Los 3 checkpoints exactos que produjo la corrida, verificados desde H0_GENESIS.",
        verificar_linaje(checkpoints, g.H0_GENESIS),
        f"H0_GENESIS = {corto(g.H0_GENESIS)}",
    )
    agregar(
        "raiz_equivocada",
        "Verificar contra otra raíz",
        "Misma cadena, pero se le pide que verifique contra una raíz que no es H0_GENESIS — "
        "una cadena que no conmutó no tiene checkpoint válido (§5).",
        verificar_linaje(checkpoints, CERO_32),
        f"raíz usada = {corto(CERO_32)} (no es H0_GENESIS)",
    )
    agregar(
        "eslabon_faltante",
        "Sacar el primer eslabón",
        "Se verifica la cadena sin el checkpoint de la generación 1 — el resto queda "
        "huérfano, sin ancestro válido.",
        verificar_linaje(checkpoints[1:], g.H0_GENESIS),
        f"quedan {len(checkpoints) - 1} de {len(checkpoints)} checkpoints",
    )
    agregar(
        "orden_invertido",
        "Invertir el orden",
        "Los mismos 3 checkpoints, en orden inverso — el linaje es una cadena, no un conjunto.",
        verificar_linaje(list(reversed(checkpoints)), g.H0_GENESIS),
        "gen 3 → gen 2 → gen 1 en vez de 1 → 2 → 3",
    )

    # --- nivel checkpoint: verificar(h0, h0_ancestro, state_trigger, params) ---
    agregar(
        "insumos_reales",
        "Un solo checkpoint, insumos reales",
        "El primer checkpoint, verificado con sus tres insumos reales tal como salieron "
        "de la corrida.",
        verificar(p0.h0, p0.h0_ancestro, p0.state_trigger, p0.params),
        f"H0_B = {corto(p0.h0)}",
    )
    agregar(
        "ancestro_alterado",
        "Alterar el ancestro",
        "Mismo H0_B, pero se le dice que su ancestro es otro H0 — el hash no reproduce.",
        verificar(p0.h0, CERO_32, p0.state_trigger, p0.params),
        f"H0_ancestro real = {corto(p0.h0_ancestro)}, se probó con {corto(CERO_32)}",
    )
    agregar(
        "estado_disparador_alterado",
        "Alterar el estado que disparó",
        "Mismo H0_B, mismo ancestro, pero el `state_trigger` (el estado que gatilló la "
        "transición) es otro.",
        verificar(p0.h0, p0.h0_ancestro, CERO_32, p0.params),
        f"state_trigger real = {corto(p0.state_trigger)}, se probó con {corto(CERO_32)}",
    )
    retocado = p0.params.con(tiempo_bloque_ms=5_000)
    agregar(
        "parametro_alterado",
        "Alterar un solo parámetro",
        "Se cambia `tiempo_bloque_ms` en los params nuevos — un solo campo, todo lo "
        "demás igual.",
        verificar(p0.h0, p0.h0_ancestro, p0.state_trigger, retocado),
        f"tiempo_bloque_ms real → 5000 (el resto de params_nuevos sin cambios)",
    )
    interfaz_retocada = Params(
        p0.params.generacion,
        dict(p0.params.internos),
        p0.params.formatos ^ {"firma/ml-dsa-44"},
    )
    agregar(
        "interfaz_alterada",
        "Alterar solo la interfaz (formatos)",
        "Se agrega o se saca un formato del conjunto — los formatos entran al hash "
        "igual que los parámetros internos.",
        verificar(p0.h0, p0.h0_ancestro, p0.state_trigger, interfaz_retocada),
        f"formatos reales = {sorted(p0.params.formatos)}",
    )

    salida = {"escenarios": escenarios}
    destino = Path(__file__).resolve().parent / "verify-demo-data.json"
    destino.write_text(json.dumps(salida, indent=2, ensure_ascii=False), encoding="utf-8")
    ok = sum(1 for e in escenarios if e["resultado"])
    print(f"{destino.name}: {len(escenarios)} escenarios, {ok} en True, {len(escenarios) - ok} en False")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
