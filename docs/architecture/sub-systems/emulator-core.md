# emulator-core

Python NES console core: 6502 CPU, addressing helpers, flat memory helpers,
iNES ROM loading, and a PPU module that must at least compile and accept
register traffic.

## Purpose

Own the code that turns a cartridge image into CPU-executable memory and (as
tickets land) a clocked PPU/APU/bus. Punch-Out requires Mapper 9 (MMC2); the
current tree exposes the mapper interface with Mapper 0 for nestest.

## Anchor Files

- `src/cpu.py` — 6502 CPU and instruction decode/execute
- `src/addressing.py` — addressing-mode helpers
- `src/memory.py` — early flat-memory helper (to be replaced by a bus)
- `src/rom.py` — path-based iNES header and cartridge loader
- `src/mapper.py` — cartridge mapper interface and NROM implementation
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

- Unsupported cartridge hardware is rejected with its iNES mapper id.
- Syntax errors in `ppu.py` fail compileall and block the suite.
- Incorrect iNES flags select the wrong mirroring or mapper implementation.
