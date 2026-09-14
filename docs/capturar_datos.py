"""Corre exactamente el mismo escenario que `herramientas/demo.py` y vuelca los
eventos reales (alturas, hashes, generaciones) a `docs/timeline-data.json`, para
que `docs/timeline.html` los visualice. No inventa números: es la misma corrida.

    python docs/capturar_datos.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from nodo.pod import NodoPoD  # noqa: E402
from protocolo import genesis as g  # noqa: E402
from protocolo.linaje import verificar_linaje  # noqa: E402
from sucesion.regla import (  # noqa: E402
    ReglaCanarioCriptografico,
    ReglaEmisionAcumulada,
)

GASTAR_CANARIO = ("gastar_canario",)
ALTURA_DEL_CANARIO = 130
BLOQUES = 260


def main() -> int:
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

    checkpoints = nodo.cronograma.checkpoints
    ok = verificar_linaje(checkpoints, g.H0_GENESIS)

    salida = {
        "bloques": BLOQUES + 2,
        "ventana_finalidad": g.VENTANA_FINALIDAD,
        "altura_canario": ALTURA_DEL_CANARIO,
        "h0_genesis": g.H0_GENESIS.hex(),
        "checkpoints": [
            {
                "generacion": c.generacion,
                "clase": c.clase,
                "regla": c.regla,
                "altura_disparo": c.altura_disparo,
                "altura_lockin": c.altura_lockin,
                "altura_activacion": c.altura_activacion,
                "delta": g.delta(c.clase),
                "h0": c.h0.hex(),
                "h0_ancestro": c.h0_ancestro.hex(),
            }
            for c in checkpoints
        ],
        "conmutaciones": [
            {"altura": cm.altura, "generacion": cm.generacion}
            for cm in nodo.conmutaciones
        ],
        "verify_ok": ok,
        "resumen": {
            "altura_final": nodo.altura,
            "generacion_final": nodo.generacion,
            "arranques": nodo.arranques,
            "alice": nodo.estado.saldos["alice"],
            "recibo1_generacion": nodo.estado.objetos["recibo-1"].generacion,
        },
    }

    destino = Path(__file__).resolve().parent / "timeline-data.json"
    destino.write_text(json.dumps(salida, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"{destino.relative_to(destino.parents[2])}: {len(checkpoints)} checkpoints, verify={ok}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
