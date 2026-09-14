# Geminis · demo de conmutación generacional (Colosseum Crypto World's Fair)

*[Read this in English](README.en.md)*

Este repo es el submission del hackathon **Colosseum Crypto World's Fair**
(14/9–12/10/2026). Es un recorte de **Geminis** (antes *Genesis*,
[`github.com/cristiandkzk/Genesis`](https://github.com/cristiandkzk/Genesis)),
un protocolo que hace que una cadena cambie su propio *ruleset* —incluida la
primitiva criptográfica que la firma— sin fork humano, verificable por
cualquiera. El diseño completo está en el paper del repo Geminis; acá vive
sólo el mecanismo mínimo, corriendo.

```
python verificar.py       # las 81 pruebas de este recorte
python verificar.py -v    # con el nombre de cada criterio
```

Sin dependencias: sólo la biblioteca estándar de Python 3.11+.

## Qué es esto exactamente

El mecanismo central del paper (§2): un nodo llega a un *trigger*, computa
`H0_B = H(H0_A ‖ state_trigger ‖ params_nuevos)`, conmuta su propio ruleset
**in-place** —sin mover el estado— y cualquiera puede correr
`Verify(H0_B, H0_A, ...)` y confirmar que la sucesión es legítima.

Este recorte es **Fase 0 y Fase 1** de la implementación de referencia de
Geminis (`genesis/` en el repo completo), portadas tal cual:

| módulo | qué implementa |
|---|---|
| `protocolo/genesis.py` | el bloque 0: el espacio de descendientes, `Δ` por clase, `θ*`, `L_max`, el techo de pasos |
| `protocolo/generacion.py` | ruleset, etiqueta de generación, decodificación que falla cerrado (I5) |
| `protocolo/linaje.py` | `H0_B = H(H0_A ‖ state_trigger ‖ params)` y su `Verify` (I4) |
| `protocolo/invariantes.py` | I1–I5 ejecutables |
| `sucesion/regla.py` | `TRANSITION_RULE` — incluye `ReglaCanarioCriptografico`: el trigger es un canario ML-DSA-44 roto, que dispara la sucesora ML-DSA-87 (§6.6) |
| `sucesion/cronograma.py` | disparo → lock-in → activación, con más de una transición en vuelo |
| `sucesion/conmutador.py` | la conmutación en sí |
| `estado/sintetico.py` | el estado mínimo: balances + tag de generación |
| `nodo/pod.py` | aplica bloques, evalúa la regla, conmuta, reorganiza |
| `pruebas/` | los 81 criterios, con el texto del criterio en el docstring |

**El caso del canario ya viene incluido**: `ReglaCanarioCriptografico` usa
niveles reales de ML-DSA (44 como primitiva débil, 87 como sucesora) — no un
juguete inventado. El canario se deriva de una semilla pública
(`g.CANARIO_SEMILLA`) y el nodo lo verifica en cada bloque: una instancia que
no sale de esa semilla no pasa (`pruebas/test_i2_quien_elige_el_momento.py`).

## La máquina que ejecuta el switch (`predicado/vm/`, Rust)

Fase 4 de Geminis, portada completa. **No usa wasmi ni ninguna VM de WASM**
—eso era el plan original, revisado al mirar la implementación real—: es un
intérprete RV32IM propio, **sin dependencias** (ni siquiera de `std` fuera de
lo mínimo), que reutiliza el arnés de `test2-interprete/telefono` (el mismo
`guest.elf` de ML-DSA-44, referenciado por bytes exactos, no copiado). Corre
programas de terceros bajo presupuesto — el caso real de una impugnación, no
un benchmark de confianza:

```
cd predicado/vm
cargo test --release                          # 20 criterios (C1-C7)
cargo run --release --bin vectores verificar   # C3: 7 vectores bit-a-bit
cargo run --release --bin bloque               # C1: 67 verificaciones como bloque
```

Dos techos de consenso, no uno: pasos **y** páginas de memoria distintas
tocadas (`lw` cuesta 23× más sin la página en caché, mismo opcode que `addi`
— el hallazgo de la Fase 4). Fuera de rango es trampa determinista, no
`dirección & MASK` (eso depende del tamaño de memoria y rompe I1 entre
generaciones). Todo veredicto final se codifica en 5 bytes sin texto, para
que entre al hash del bloque.

**Verificado en este repo** (14/9): compila y los 20 tests + los 7 vectores
de C3 reproducen igual que en la implementación original — self-contained,
sin bajar dependencias.

## Ver el mecanismo corriendo (`herramientas/demo.py`)

Una sola corrida, un solo proceso, sin red: dos clases de transición
disparando **superpuestas** (la de circulación avisa 64 bloques antes, la
criptográfica 8 — por eso `Δ` es por clase y no global), el canario ML-DSA-44
gastándose mientras la otra transición sigue en vuelo, las dos conmutando en
el mismo bloque, y al final la cadena de linaje verificada explícitamente:

```
python herramientas/demo.py
```

La última sección imprime `Verify(checkpoints, H0_GENESIS) = True` sobre las
generaciones encadenadas de esa corrida — el `Verify(H0_B, H0_A, ...)` del
paper, no una aserción escondida en un test. Arriba de eso, la línea
`recibo-1 nació en la generación 0` sigue siendo legible después de dos
conmutaciones: el objeto viejo sigue válido (I5) y el estado nunca se movió
(I3) — es el mismo `id(nodo.estado)` de punta a punta.

## El demo completo, de punta a punta (guion para grabar)

Tres comandos, cada uno mostrando una pieza distinta del mismo mecanismo —
protocolo, máquina, y la verificación de linaje:

```
python verificar.py -v                        # 1. las 81 pruebas de Fase 0-1, nombradas
python herramientas/demo.py                    # 2. la conmutación corriendo y Verify() = True
cd predicado/vm && cargo run --release --bin bloque   # 3. la sucesora corriendo como bytecode, bajo presupuesto
```

**Qué decir en cada paso:**

1. *Las invariantes no son comentarios.* 81 criterios ejecutables, cinco
   invariantes (I1–I5), corridos contra el motor de sucesión real — no
   pseudocódigo.
2. *El mecanismo central del paper, corriendo.* Un canario criptográfico
   real (ML-DSA-44) se gasta, dispara la sucesora (ML-DSA-87), el nodo
   conmuta su propio ruleset sin mover el estado, y `Verify()` confirma la
   cadena de linaje desde el génesis. Señalar la línea `recibo-1 nació en la
   generación 0` — sigue siendo válido después de dos conmutaciones.
3. *La sucesora no es un anuncio, es código que corre.* La primitiva nueva
   se ejecuta como bytecode en un intérprete RV32IM sin dependencias, bajo
   presupuesto de pasos **y** de páginas de memoria — dos techos de
   consenso, no uno. Señalar `C1 APROBADO` y el margen contra los 1500 ms
   del bloque.

## Qué se declara en el submission

**Preexistente** (fuera de la ventana del hackathon, declarado como tal):
el paper completo de Geminis, la evidencia contra Ethereum (EIP-7892/8261/8368)
y el benchmark de presupuesto del intérprete de `test2-interprete`
(3,2–3,7× nativo con JIT, no los 26–54× de intérprete puro que el paper
asumía).

**Nuevo, dentro de la ventana 14/9–12/10:** este recorte — el simulador de
conmutación generacional corriendo (Fase 0-1), el canario criptográfico como
trigger real, la máquina RV32IM que ejecuta la sucesora bajo presupuesto
(Fase 4) y el hallazgo del segundo techo (páginas de memoria, 23× sin caché).
Cada pieza se puede fechar por commit en este repo.

## Qué falta a propósito (no está en este recorte)

- **Harness de replay contra Ethereum** (bomba de dificultad, blobs, gas
  limit) y **liquidación/orden** (Fases 2 y 3 de Geminis) — evidencia externa
  y mecanismo de settlement, no hace falta para este mecanismo.
- El video en sí — el guion de arriba está listo para grabar, no se grabó
  nada todavía.

Todo lo de acá es desechable por declaración, igual que en el repo completo:
los parámetros son de juguete, existen para que el mecanismo corra.
