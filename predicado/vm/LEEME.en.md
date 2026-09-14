# The machine — §6.2, Phase 4

*[Leer esto en español](LEEME.md)*

**The language changes here, on purpose.** The rest of `genesis/` is in Python because what it
models are rules, and rules are meant to be read. This isn't: it's the piece I1 freezes forever,
and the only one that runs third-party code under a budget.

It wasn't written from scratch. It reuses the RV32IM interpreter from the
`test2-interprete/telefono` harness, which already had the expensive part measured: the full
instruction set, pre-decoding, and a step count that reproduces byte for byte between x86 and
ARM. **What changes is who writes the program.** That harness ran its own guest; this one runs
the counterparty's program in a dispute — someone who wants the node to hang or crash.

```
src/
├── lib.rs        # Geminis's constants and the harness's assemblers
├── maquina.rs    # the interpreter: two ceilings, traps, canonical verdicts
├── admision.rs   # what gets decided before spending the first step
└── bin/          # the measurements — see ../RESULTADOS.md
tests/criterios.rs  # C2, C4, C5, C6, and the regression against Test 2
```

## The four differences from the harness, and all of them are about consensus

- **the ceiling cuts.** The harness counts steps and never stops. Here `pasos` (steps) is a
  budget: once the machine runs out, it stops at the exact step and returns a verdict. That's
  what prevents a dispute from being more expensive to verify than to create;
- **there's a second ceiling.** Distinct pages touched. **This is Phase 4's finding:** `lw` costs
  the same as `addi` with the data cached, and twenty-three times more without it — same opcode,
  so no per-instruction weight tells them apart;
- **out of range is a trap, not wraparound.** The harness does `addr & MASK`: deterministic, but
  **it depends on memory size**, so the same program would give a different result across two
  generations. That breaks I1 exactly where it can't;
- **every ending is a verdict, not an `Err`.** Both sides of a dispute have to read the same
  thing. The ending enters the block hash, so it's encoded in five bytes with no text.

## Two things that aren't here, and not by oversight

**No dependencies.** Every crate that got pulled in would be code that gets updated some day, and
a semantic change between two versions is a consensus fork nobody chose.

**No single wall-clock number.** A consensus machine that knew how long something takes would be
an oracle (I2). The only resources it can count are the ones that reproduce identically on any
hardware: steps and pages. Milliseconds live in the measurement binaries, and there's a test in
`pruebas/test_fase4_vm.py` that checks not a single `f32`, `f64`, or decimal literal sneaks into
the whole crate.

## Running it

```
cargo test --release              # the criteria that are properties
cargo run --release --bin mezclas    # C7 — throughput by instruction mix
cargo run --release --bin conjunto   # what it depends on: memory and text size
cargo run --release --bin bloque     # C1 — 26 verifications as a block
cargo run --release --bin vectores            # generates the C3 table
cargo run --release --bin vectores verificar  # compares it against vectores.csv
```

### On the phone (Termux, aarch64) — what's left to close C3

**This crate isn't self-contained:** `lib.rs` does `include_bytes!` on two guest ELFs — Test 2's
(`test2-interprete/telefono/guest-rv/guest.elf`, three levels above `src/`) and its own
(`guest-sha/guest.elf`, right next to it). In this repo both are already committed at the path
`lib.rs` expects, so it's enough to copy the whole repo (or `predicado/` + `test2-interprete/`
together, with the relative paths intact) to the phone:

```
pkg install -y rust tar
cd predicado/vm
cargo run --release --bin vectores verificar
```

Compiles in seconds: **the crate has no dependencies**, so there's no network, no registry, none
of the twenty minutes Test 2's harness took with `wasmtime`.

The seven vectors have to come out identical. **No tolerance**: if two nodes count differently,
the dispute has no result.

And while the phone's out, it's worth running `bloque` there too, because **the protocol's
reference hardware is the phone, not a desktop**: the C1 margin that's measured is x86-64's.
