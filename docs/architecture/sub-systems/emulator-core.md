# emulator-core

Python NES console core: 6502 CPU, addressing helpers, flat memory helpers,
iNES ROM loading, and a PPU module that must at least compile and accept
register traffic.

## Purpose

Own the code that turns a cartridge image into CPU-executable memory and (as
tickets land) a clocked PPU/APU/bus. Punch-Out requires Mapper 9 (MMC2); the
current tree is still Mapper-agnostic and nestest-oriented.

## Anchor Files

- `src/cpu.py` — 6502 CPU and instruction decode/execute
- `src/addressing.py` — addressing-mode helpers
- `src/memory.py` — early flat-memory helper (to be replaced by a bus)
- `src/rom.py` — iNES loader (must stop hard-coding nestest)
- `src/ppu.py` — PPU skeleton (must compile; rendering is later tickets)

## Public Contract

- Callers construct a CPU with injected memory/ROM rather than relying on a
  module-level nestest path.
- ROM loading accepts a filesystem path and will grow a mapper interface.
- Commercial ROMs are never committed; nestest stays under `src/tests/testROMs/`.

## Key Invariants

- Python 3 only; `python3 -m compileall` over `src/` must succeed.
- CPU unit tests compare against `src/nestest.log.txt` when ROMTests run.
- No copyrighted Punch-Out (or other commercial) ROM in the tree.

## Security Posture

- Trust boundary: local process only; no network services.
- Sensitive data: none expected. Do not commit operator-supplied ROMs.
- Log hygiene: avoid dumping full ROM bytes to logs.

## Failure Modes

- Implicit nestest load inside `CPU()` breaks every test when cwd is wrong.
- Syntax errors in `ppu.py` fail compileall and block the suite.
- Hard-coded ROM paths ignore iNES mapper flags needed for Punch-Out.
